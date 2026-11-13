"""M-023 latency-aware SIMPLE SOURCE PATH comparison, explicitly NOT MID SOCP."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import argparse,copy,datetime,hashlib,heapq,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from simulation.mid_link_console.settings.routing import normalize_settings,compile_scenario,state_at,candidate_paths
from simulation.mid_link_console.runner.pair import CustomEngine
from simulation.mid_link_study.engine.run import save,sha

class RoutingEngine(CustomEngine):
 def __init__(self,s,seed,arm,out,cancel=None,progress=None):
  super().__init__(s,seed,arm,out,cancel,progress);self.installed={};self.current={};self.path_counter=0
 def environment(self,t=None):return state_at(self.s,min(self.duration,max(0,self.t if t is None else t)))
 def select_bundle(self,snapshot,current):
  routes=[]
  for flow in self.s['traffic']['flows']:
   key=flow['src']+'>'+flow['dst'];choices=candidate_paths(snapshot,flow['src'],flow['dst'],self.s['routing']['hops'],32)
   best=choices[0] if choices else None
   previous=current.get(key)
   if best and previous:
    old=next((p for p in choices if p['path']==previous['path']),None)
    if old and abs(old['estimated_delay_s']-best['estimated_delay_s'])<=1e-12:best=old
   routes.append(dict(flow,key=key,path=best['path'] if best else None,estimated_delay_s=best['estimated_delay_s'] if best else None,candidates=choices,status='available' if best else ('no_exact_k_path' if self.s['routing']['hops'] is not None else 'no_feasible_simple_path')))
  return dict(routes=routes,requested_hops=self.s['routing']['hops'],policy='latency_aware_simple_path')
 def install(self,node,bundle,version,initial=False):
  if node not in self.environment()['active_nodes']:return
  self.installed[node]=(version,copy.deepcopy(bundle));self.control_seen[node]=version
  self.log('config_install',node=node,update_id=version,version=version,initial=initial,routes=bundle['routes'],control_effective=True)
 def flood(self,node,bundle,version,ttl):
  if ttl<=1:return
  n=len(json.dumps(dict(version=version,bundle=bundle['routes']),separators=(',',':')).encode())
  # Send only selected path/cost, not all candidates in the control payload.
  n=len(json.dumps(dict(version=version,routes=[{k:r[k] for k in ('src','dst','key','path','estimated_delay_s','status')} for r in bundle['routes']]),separators=(',',':')).encode())
  for e in self.environment()['edges']:
   if e['src']==node and e['capacity_payload_bps']>0 and e['pdr']>0:self.enqueue(dict(kind='control',update=bundle,version=version,ttl=ttl-1,node=node,next_hop=e['dst'],bytes=n))
 def packet_fields(self,p):
  v=super().packet_fields(p)
  for k in ('locked_path','actual_path','path_version','planned_hops','path_index'):
   if k in p:v[k]=copy.deepcopy(p[k])
  return v
 def arrive_data(self,node,p):
  v=self.packet_fields(p)
  if node not in self.environment()['active_nodes']:self.log('drop',node=node,reason='inactive_node',**v);return
  chain=p.get('locked_path');idx=p.get('path_index',0)
  if not chain:self.log('drop',node=node,reason='no_exact_k_path' if self.s['routing']['hops'] is not None else 'no_feasible_simple_path',**v);return
  if len(set(chain))!=len(chain) or idx>=len(chain) or node!=chain[idx] or (self.s['routing']['hops'] is not None and len(chain)-1!=self.s['routing']['hops']):self.log('drop',node=node,reason='invalid_locked_path',**v);return
  if p['packet_id'] in self.seen[node]:self.log('drop',node=node,reason='duplicate_64_cache',**v);return
  p=dict(p,actual_path=p.get('actual_path',[])+[node]);self.seen[node].append(p['packet_id']);v=self.packet_fields(p)
  self.log('hop_rx',node=node,**v)
  if node==p['dst']:
   if idx!=len(chain)-1:self.log('drop',node=node,reason='premature_destination',**v);return
   self.delivered.add(p['packet_id']);self.log('destination_rx',node=node,actual_hops=len(p['actual_path'])-1,**v);return
  if p['ttl']<=1:self.log('drop',node=node,reason='TTL',**v);return
  next_hop=chain[idx+1];self.log('source_admitted' if idx==0 else 'relay',node=node,next_hop=next_hop,route_version=p['path_version'],**v)
  self.enqueue(dict(kind='data',packet=dict(p,path_index=idx+1,ttl=p['ttl']-(0 if idx==0 else 1)),node=node,next_hop=next_hop,route_version=p['path_version'],bytes=32))
 def receive(self,q):
  probability=self.flight_probability(q);fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])
  common=dict(node=q['next_hop'],previous_hop=q['node'],transit_id=q['transit_id'],service_start_s=q['service_start_s'],serialization_s=q['serialization_s'],propagation_delay_s=q['propagation_delay_s'],scheduled_arrival_s=q['scheduled_arrival_s'],flight_min_probability=probability)
  if q['draw']>=probability:self.log('drop' if q['kind']=='data' else 'control_drop',reason='in_flight_failure',**common,**fields);return
  self.log('arrival',kind=q['kind'],**common,**fields);node=q['next_hop']
  if q['kind']=='data':self.log('rx',node=node,previous_hop=q['node'],**fields);self.arrive_data(node,q['packet']);return
  self.log('control_rx',node=node,previous_hop=q['node'],update_id=q['version'])
  if q['version']<=self.control_seen[node]:self.log('control_duplicate',node=node,update_id=q['version']);return
  self.install(node,q['update'],q['version']);self.flood(node,q['update'],q['version'],q['ttl'])
 def run(self):
  observed=self.environment(0);self.initial=self.select_bundle(observed,{})
  self.current={r['key']:r for r in self.initial['routes']};self.controller=self.s['routing']['src']
  for n in 'ABCDE':self.install(n,self.initial,0,True)
  self.log('candidate_paths',observed_at_s=0,routes=self.initial['routes'],preinstalled=True)
  # Delay is a routing input in this NEW strategy; legacy MID remains unchanged.
  def signature(view):
   d=copy.deepcopy(view);d.pop('time_s',None);return json.dumps(d,sort_keys=True)
  last=signature(observed)
  for slot in range(int(self.duration*2)):
   for flow in self.s['traffic']['flows']:self.schedule(slot*.5,'generate',flow['src'],flow['dst'],slot)
  for t in range(1,int(self.duration)):self.schedule(t,'observe')
  last_progress=-1
  while self.heap:
   if self.interrupted():self.cancelled=True;self.log('run_cancelled');break
   self.t,_,kind,args=heapq.heappop(self.heap)
   if self.t>self.duration+20:break
   if self.progress and self.t<self.duration and int(self.t)//5!=last_progress:last_progress=int(self.t)//5;self.progress(dict(arm=self.arm,t_s=self.t,duration_s=self.duration))
   if kind=='generate':
    src,dst,slot=args;version,bundle=self.installed.get(src,(-1,dict(routes=[])));route=next((r for r in bundle['routes'] if r['src']==src and r['dst']==dst),None);chain=copy.deepcopy(route['path']) if route else None
    p=dict(packet_id=f'{src}>{dst}:{slot:03}',src=src,dst=dst,origin=src,sim_boot=self.seed,seq=slot+1,payload_bytes=32,payload_tag=hashlib.sha256(f'editable-five-v1:{self.seed}:{src}:{dst}:{slot}'.encode()).hexdigest(),ttl=8,locked_path=chain,path_version=version,planned_hops=len(chain)-1 if chain else None,path_index=0,actual_path=[])
    self.generated+=1;self.log('generate',node=src,**self.packet_fields(p));self.arrive_data(src,p)
   elif kind=='observe':
    at=max(0,self.t-.5);view=self.environment(at);sig=signature(view);self.log('observed_state',observed_at_s=at,observation=view,observation_delay_s=.5)
    if sig!=last:
     last=sig;self.log('detection',observed_at_s=at)
     if self.arm=='latency_aware':
      effective={}
      for flow in self.s['traffic']['flows']:
       source_bundle=self.installed.get(flow['src'],(-1,dict(routes=[])))[1]
       for row in source_bundle['routes']:
        if row['src']==flow['src'] and row['dst']==flow['dst']:effective[row['key']]=row
      wall=time.perf_counter();bundle=self.select_bundle(view,effective);elapsed=time.perf_counter()-wall
      self.log('plan_start',observed_at_s=at,routes=bundle['routes'],compute_wall_s=elapsed);self.schedule(self.t+.2,'plan_ready',bundle,at,elapsed)
   elif kind=='plan_ready':
    bundle,at,wall=args;self.log('plan_end',observed_at_s=at,simulated_compute_delay_s=.2,compute_wall_s=wall,routes=bundle['routes'])
    if [(r['key'],r['path']) for r in bundle['routes']]==[(r['key'],r['path']) for r in self.current.values()]:self.log('keep_current_chain',reason='same_chain_or_equal_cost_tie');continue
    self.current={r['key']:r for r in bundle['routes']};self.update_id+=1;v=self.update_id
    self.log('config_publish',node=self.controller,update_id=v,routes=bundle['routes']);self.install(self.controller,bundle,v);self.flood(self.controller,bundle,v,8)
   elif kind=='complete':self.complete(*args)
   elif kind=='receive':self.receive(*args)
  self.out.mkdir(parents=True,exist_ok=False)
  with (self.out/'events.jsonl').open('w',encoding='utf-8') as f:
   for e in self.events:f.write(json.dumps(e,separators=(',',':'))+'\n')
  rx=[e for e in self.events if e['event']=='destination_rx'];before={e['packet_id'] for e in rx if e['t_s']<self.duration};delivered={e['packet_id'] for e in rx}
  context=dict(evidence_kind='software_simulation',run_id=self.id,pair_id=f'{self.s["id"]}:{self.seed}',scenario_id=self.s['id'],seed=self.seed,arm=self.arm,duration_s=self.duration,drain_until_s=self.duration+20,status='cancelled' if self.cancelled else 'complete',coverage_end_s=self.t,settings_sha256=self.s['settings_sha256'],source_planned=self.s['traffic']['planned_per_arm'],traffic=self.s['traffic'],routing=self.s['routing'],initial_table_sha256=hashlib.sha256(json.dumps(self.initial,sort_keys=True).encode()).hexdigest(),impact_start_s=self.s['custom_settings']['fault_start_s'],recovery_anchor_s=self.s['custom_settings']['fault_end_s'],
   model=dict(policy='fixed initial source chain vs latency-aware simple source path, NOT original MID/SOCP',hop_semantics='each packet carries immutable simple chain/version selected at generation; every forwarded edge follows it, never splices new table',observation_period_s=1,observation_delay_s=.5,observation='ideal delayed centralized sensor, no future state',simulated_compute_s=.2,control='source-controller install at publish after computation, remote source installs only on finite causal flood arrival; initial preinstalled before0',tie_rule='retain current feasible path for equal cost within1e-12s',no_path='explicit None, no fallback to another hop count',queue='independent directed-edge FIFO32, no RF contention/half-duplex',propagation='per-edge delay plus payload serialization, all in-flight outage boundaries checked',retry=False,TTL=8,random_namespace='editable-five-v1 same seed exogenous hash, no arm input'))
  save(self.out/'context.json',context);save(self.out/'planner_inputs.json',dict(policy='simple_path_enumeration_not_SOCP',initial_candidates=self.initial))
  summary=dict(status=context['status'],run_id=self.id,arm=self.arm,generated=self.generated,source_planned=self.s['traffic']['planned_per_arm'],destination_unique=len(delivered),destination_unique_before_end=len(before),destination_unique_before60=len(before) if self.duration==60 else None,late_unique=len(delivered-before),events=len(self.events),evidence_kind='software_simulation');save(self.out/'summary.json',summary);return summary

def run_pair(settings,output_dir,cancel=None,progress=None):
 normalized=normalize_settings(settings);s=compile_scenario(normalized);out=Path(output_dir);out.mkdir(parents=True,exist_ok=False);save(out/'settings.json',normalized);save(out/'scenario.json',s);started=time.monotonic();runs=[]
 result=dict(status='running',schema='mid.routing.result.v1',evidence_kind='software_simulation',run_id=out.name,settings_sha256=s['settings_sha256'],runs=runs,output_directory=str(out.resolve()),policy='latency_aware_simple_path_not_MID_SOCP');save(out/'INDEX.json',result)
 try:
  for arm in ('fixed','latency_aware'):
   row=RoutingEngine(s,normalized['seed'],arm,out/arm,cancel,progress).run();runs.append(dict(row,path=arm,events=arm+'/events.jsonl',context=arm+'/context.json'))
   if row['status']=='cancelled':result['status']='cancelled';break
   save(out/'INDEX.json',result)
  else:result['status']='complete'
 except Exception as e:result.update(status='failed',error=repr(e))
 result['wall_s']=time.monotonic()-started;save(out/'INDEX.json',result)
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-021',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=['routing_run_pair',normalized],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out.resolve()),seeds=[normalized['seed']],status=result['status'],exit_code=0 if result['status']=='complete' else 1,dirty_files_sha256={'runner':sha(Path(__file__))},limitations=['Software-only new latency-aware path policy, not original MID']);save(out/'RUN_MANIFEST.json',m);return result

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--settings',required=True);p.add_argument('--output',required=True);p.add_argument('--cancel-file');a=p.parse_args();r=run_pair(json.loads(Path(a.settings).read_text(encoding='utf-8')),a.output,(lambda:Path(a.cancel_file).exists()) if a.cancel_file else None);print(json.dumps(r));raise SystemExit(0 if r['status']=='complete' else 2)
