"""Editable-link causal discrete event runner. SOFTWARE ONLY; no ports/server."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import argparse,collections,copy,datetime,hashlib,heapq,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from simulation.mid_link_study.scenarios.custom import normalize_settings,compile_scenario,state_at
from simulation.mid_link_study.engine.run import Engine,optimize,save,sha,uniform,MAC,BACK,pack,quantize

class CustomEngine(Engine):
 def __init__(self,s,seed,arm,out,cancel=None,progress=None):
  super().__init__(s,seed,arm,out);self.duration=s['duration_s'];self.cancel=cancel;self.progress=progress;self.cancelled=False;self.transit=0
 def environment(self,t=None):return state_at(self.s,min(self.duration,max(0,self.t if t is None else t)))
 def interrupted(self):return bool(self.cancel() if callable(self.cancel) else self.cancel and self.cancel.is_set())
 def select(self):
  epoch=int(round(self.t*2))
  for node,(version,table) in self.tables.items():
   if node not in self.environment()['active_nodes']:continue
   for f,flow in enumerate(table['flows']):
    row=next((r for r in table['routes'] if r['node']==MAC[node] and r['src']==flow['src'] and r['dst']==flow['dst']),None)
    draw,key=uniform(self.seed,'editable-five-v1','route',node,epoch,f);chosen=None
    if row:
     position=int(draw*65535);total=0
     for g,w in zip(row['gateways'],quantize([g['weight'] for g in row['gateways']])):
      total+=w
      if position<total:chosen=BACK[g['node']];break
    self.choice[node,f]=chosen;self.log('route_selected',node=node,flow=f,next_hop=chosen,version=version,epoch=epoch,draw=draw,random_key=key)
 def start(self,edge):
  if not self.queues[edge]:return
  q=self.queues[edge].popleft();e=self.edge(*edge);self.busy.add(edge)
  fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'],control_bytes=q['bytes'])
  draw,key=uniform(self.seed,'editable-five-v1','channel',int(self.t*1000),*edge,fields.get('packet_id','control:'+str(q.get('version'))))
  serialization=q['bytes']*8/e['capacity_payload_bps'] if e['capacity_payload_bps']>0 else .01
  propagation=e.get('propagation_delay_s',.01);self.transit+=1
  q.update(p_start=e['pdr'],draw=draw,random_key=key,service_start_s=self.t,serialization_s=serialization,propagation_delay_s=propagation,scheduled_arrival_s=self.t+serialization+propagation,transit_id=f'{self.arm}-{self.transit}')
  self.log('tx_attempt' if q['kind']=='data' else 'control_tx',node=edge[0],next_hop=edge[1],route_version=q.get('route_version'),draw=draw,random_key=key,p_success_at_start=e['pdr'],capacity_payload_bps=e['capacity_payload_bps'],serialization_s=serialization,propagation_delay_s=propagation,scheduled_arrival_s=q['scheduled_arrival_s'],transit_id=q['transit_id'],**fields)
  self.schedule(self.t+serialization,'complete',q)
 def complete(self,q):
  edge=q['node'],q['next_hop'];self.busy.discard(edge);e=self.edge(*edge)
  prob=min(q['p_start'],e['pdr']) if e['capacity_payload_bps']>0 else 0;ok=q['draw']<prob
  fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])
  self.log('link_result',node=edge[0],next_hop=edge[1],kind=q['kind'],success=ok,p_success=prob,random_key=q['random_key'],transit_id=q['transit_id'],**fields)
  if ok:self.schedule(q['scheduled_arrival_s'],'receive',q)
  else:self.log('drop' if q['kind']=='data' else 'control_drop',node=edge[0],next_hop=edge[1],reason='link_failure_or_zero_service',transit_id=q['transit_id'],**fields)
  self.start(edge)
 def flight_probability(self,q):
  # Include ALL intervention boundaries. A disconnect that heals before arrival
  # still destroys this in-flight frame. No future state is passed to a policy.
  a=q['service_start_s'];b=self.t;points={a,b}
  for edge in self.s['edges']:
   if (edge['src'],edge['dst'])==(q['node'],q['next_hop']):
    for segment in edge.get('segments',[]):
     points.update(t for t in (segment['start_s'],segment['end_s']) if a<=t<=b)
  for interval in self.s.get('node_intervals',[]):
   if interval['node'] in (q['node'],q['next_hop']):points.update(t for t in (interval['start_s'],interval['end_s']) if a<=t<=b)
  probability=1.
  for t in points:
   e=self.edge(q['node'],q['next_hop'],t)
   probability=min(probability,e['pdr'] if e['capacity_payload_bps']>0 else 0)
  return probability
 def receive(self,q):
  probability=self.flight_probability(q);fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])
  common=dict(node=q['next_hop'],previous_hop=q['node'],transit_id=q['transit_id'],service_start_s=q['service_start_s'],serialization_s=q['serialization_s'],propagation_delay_s=q['propagation_delay_s'],scheduled_arrival_s=q['scheduled_arrival_s'],flight_min_probability=probability)
  if q['draw']>=probability:
   self.log('drop' if q['kind']=='data' else 'control_drop',reason='in_flight_failure',**common,**fields);return
  self.log('arrival',kind=q['kind'],**common,**fields)
  # Parent receive uses this subclass environment; its checks and data/control
  # delivery/duplicate/install rules remain original, including 500ms invalidation.
  super().receive(q)
 def routing_signature(self,obs):
  d=copy.deepcopy(obs);d.pop('time_s',None)
  for e in d['edges']:e.pop('delay_ms',None);e.pop('propagation_delay_s',None)
  return json.dumps(d,sort_keys=True)
 def run(self):
  initial_observation=self.environment(0);answer,info,problem=optimize(initial_observation)
  self.problems[info['input_key']]=dict(problem=problem,result=answer);self.initial_status=answer['status']
  self.initial=answer['update'] if answer['status']=='optimal' else dict(schema='mid.network_update.v1',nodes=[MAC[n] for n in initial_observation['active_nodes']],flows=[dict(src=MAC[a],dst=MAC[b]) for a,b in [('A','B'),('B','A')]],routes=[])
  if answer['status']!='optimal':self.log('initial_no_table',status=answer['status'],**info)
  for n in 'ABCDE':self.install(n,self.initial,0,True)
  self.last_observed=self.routing_signature(initial_observation)
  for tick in range(int((self.duration+20)*2)+1):self.schedule(tick*.5,'tick')
  for slot in range(int(self.duration*2)):
   for src,dst in [('A','B'),('B','A')]:self.schedule(slot*.5,'generate',src,dst,slot)
  for observation in range(1,int(self.duration)):self.schedule(observation,'observe')
  last_progress=-1
  while self.heap:
   if self.interrupted():self.cancelled=True;self.log('run_cancelled');break
   self.t,_,kind,args=heapq.heappop(self.heap)
   if self.t>self.duration+20:break
   if self.progress and self.t<self.duration and int(self.t)//5!=last_progress:
    last_progress=int(self.t)//5;self.progress(dict(arm=self.arm,t_s=self.t,duration_s=self.duration))
   if kind=='tick':self.select()
   elif kind=='generate':
    src,dst,slot=args;packet=dict(packet_id=f'{src}>{dst}:{slot:03}',src=src,dst=dst,origin=src,sim_boot=self.seed,seq=slot+1,payload_bytes=32,payload_tag=hashlib.sha256(f'editable-five-v1:{self.seed}:{src}:{dst}:{slot}'.encode()).hexdigest(),ttl=8)
    self.generated+=1;self.log('generate',node=src,**self.packet_fields(packet));self.arrive_data(src,packet)
   elif kind=='observe':
    observed_at=max(0,self.t-.5);obs=self.environment(observed_at);signature=self.routing_signature(obs)
    self.log('observed_state',observed_at_s=observed_at,observation=obs,observation_delay_s=.5)
    if signature!=self.last_observed:
     self.log('detection',observed_at_s=observed_at);self.last_observed=signature
     if self.arm=='adaptive':
      self.log('solve_start',observed_at_s=observed_at);answer,info,problem=optimize(obs);self.problems[info['input_key']]=dict(problem=problem,result=answer);self.schedule(self.t+.2,'solve_ready',answer,info,observed_at)
   elif kind=='solve_ready':
    answer,info,observed_at=args;self.log('solve_end',status=answer['status'],observed_at_s=observed_at,simulated_compute_delay_s=.2,**info)
    if answer['status']=='optimal':
     self.update_id+=1;v=self.update_id;update=answer['update'];self.log('config_publish',node='A',update_id=v,table=update);self.install('A',update,v);self.flood('A',update,v,8)
    else:self.log('keep_previous_table',reason=answer['status'])
   elif kind=='complete':self.complete(*args)
   elif kind=='receive':self.receive(*args)
  self.out.mkdir(parents=True,exist_ok=False)
  with (self.out/'events.jsonl').open('w',encoding='utf-8') as f:
   for event in self.events:f.write(json.dumps(event,separators=(',',':'))+'\n')
  context=dict(evidence_kind='software_simulation',run_id=self.id,pair_id=f'{self.s["id"]}:{self.seed}',scenario_id=self.s['id'],seed=self.seed,arm=self.arm,duration_s=self.duration,drain_until_s=self.duration+20,coverage_end_s=self.t,status='cancelled' if self.cancelled else 'complete',settings_sha256=self.s['settings_sha256'],initial_solver_status=self.initial_status,initial_table_sha256=hashlib.sha256(json.dumps(self.initial,sort_keys=True).encode()).hexdigest(),source_planned=self.duration*4,traffic=self.s['traffic'],impact_start_s=self.s['custom_settings']['fault_start_s'],recovery_anchor_s=self.s['custom_settings']['fault_end_s'],
   model=dict(observation_period_s=1,observation_delay_s=.5,sensing='ideal delayed centralized snapshot, no reachability oracle',simulated_compute_s=.2,wall_and_cache='separate in solve_end',route_period_s=.5,TTL=8,data_dedup_entries=64,queue='independent directed-edge FIFO32, no RF contention or half-duplex',data_service_bytes=32,header_service_bytes=0,retry=False,control='finite per-edge fanout source/seq flood, not periodic or reliable; same serialized server',propagation='data and control use edge delay at service start; serialization additional; midflight delay edits not retroactive; any encountered zero-service/offline interval destroys frame even if healed before arrival',random_namespace='editable-five-v1 common across arms AND edited settings with same seed',planner_objective='capacity/PDR robust margin, NOT propagation latency; delay-only change does not publish a fake new route',initial='same preinstalled table; infeasible -> empty routes and explicit no-table drops',inactive='saved state suspended, no install/receive',drain='20 simulated seconds bounded; later pending not fabricated as delivery'))
  save(self.out/'context.json',context);save(self.out/'planner_inputs.json',self.problems)
  rx=[e for e in self.events if e['event']=='destination_rx'];before={e['packet_id'] for e in rx if e['t_s']<self.duration};seen={e['packet_id'] for e in rx}
  summary=dict(status=context['status'],run_id=self.id,arm=self.arm,generated=self.generated,source_planned=self.duration*4,destination_unique=len(seen),destination_unique_before_end=len(before),destination_unique_before60=len(before) if self.duration==60 else None,late_unique=len(seen-before),events=len(self.events),initial_solver_status=self.initial_status,evidence_kind='software_simulation');save(self.out/'summary.json',summary);return summary

def run_pair(settings,output_dir,cancel=None,progress=None):
 normalized=normalize_settings(settings);s=compile_scenario(normalized);out=Path(output_dir);out.mkdir(parents=True,exist_ok=False);save(out/'settings.json',normalized);save(out/'scenario.json',s);started=time.monotonic();runs=[]
 index=dict(status='running',evidence_kind='software_simulation',run_id=out.name,settings_sha256=s['settings_sha256'],runs=runs,output_directory=str(out.resolve()))
 save(out/'INDEX.json',index)
 try:
  for arm in ('fixed','adaptive'):
   summary=CustomEngine(s,normalized['seed'],arm,out/arm,cancel,progress).run();runs.append(dict(summary,path=arm,events=arm+'/events.jsonl',context=arm+'/context.json'))
   if summary['status']=='cancelled':index['status']='cancelled';break
   save(out/'INDEX.json',index)
  else:index['status']='complete'
 except Exception as e:index.update(status='failed',error=repr(e))
 index['wall_s']=time.monotonic()-started;save(out/'INDEX.json',index)
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-020',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=['run_pair',normalized],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out.resolve()),seeds=[normalized['seed']],status=index['status'],exit_code=0 if index['status']=='complete' else 1,limitations=['Software simulation, edge queues and ideal sensing simplified; no hardware'],dirty_files_sha256={'runner':sha(Path(__file__))});save(out/'RUN_MANIFEST.json',m)
 return index

def main():
 p=argparse.ArgumentParser();p.add_argument('--settings',required=True);p.add_argument('--output',required=True);p.add_argument('--cancel-file');a=p.parse_args();settings=json.loads(Path(a.settings).read_text(encoding='utf-8'))
 result=run_pair(settings,a.output,(lambda:Path(a.cancel_file).exists()) if a.cancel_file else None);print(json.dumps(result));return 0 if result['status']=='complete' else 2

if __name__=='__main__':raise SystemExit(main())
