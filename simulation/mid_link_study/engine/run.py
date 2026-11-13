"""M-021 causal discrete-event SOFTWARE SIMULATION. No devices/network."""
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import sys,json,time,hashlib,heapq,copy,collections,argparse,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/mid_baseline/planner'))
from simulation.mid_link_study.scenarios.scenarios import IDS,load,state_at
from planner import solve
sys.path.insert(0,str(ROOT/'tools/mid_baseline/bridge'))
from bridge import pack,quantize
MAC={n:f'02:00:00:00:00:{i+1:02x}' for i,n in enumerate('ABCDE')};BACK={v:k for k,v in MAC.items()}
CACHE={}
def save(p,v):p.write_text(json.dumps(v,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def uniform(*parts):
 key=json.dumps(parts,separators=(',',':'));return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')/2**64,key

def optimize(observation):
 nodes=observation['active_nodes'];edge={(e['src'],e['dst']):e for e in observation['edges']};maximum=max(e['capacity_payload_bps'] for e in edge.values());mean=[];var=[]
 for a in nodes:
  mr=[];vr=[]
  for b in nodes:
   e=edge.get((a,b));cap=e['capacity_payload_bps'] if e else 0;p=e['pdr'] if e else 0
   mr.append(cap*p)
   vr.append(0 if a==b else (cap*cap*p*(1-p) if cap*p>0 else max(1,maximum*10)**2))
  mean.append(mr);var.append(vr)
 problem=dict(nodes=[MAC[n] for n in nodes],flows=[dict(src=MAC[a],dst=MAC[b],rate=512,qos=.9) for a,b in [('A','B'),('B','A')]],mean=mean,variance=var,channel_provenance='SYNTHETIC edge service mean=capacity_payload_bps*pdr; Bernoulli service variance cap^2*p*(1-p). Absent/zero-service edges use declared logical variance penalty (10*maxcap)^2, not measured uncertainty. Independent link approximation.')
 key=hashlib.sha256(json.dumps(problem,sort_keys=True).encode()).hexdigest();start=time.perf_counter();hit=key in CACHE
 if not hit:
  answer=solve(problem)
  if answer['status']=='optimal':
   for r in answer['update']['routes']:
    for g in r['gateways']:
     e=edge.get((BACK[r['node']],BACK[g['node']]))
     if not e or e['expected_payload_bps']<=0:answer=dict(status='rejected_forbidden_edge',update=None)
  CACHE[key]=(answer,time.perf_counter()-start,problem)
 answer,original_wall,problem=CACHE[key]
 return copy.deepcopy(answer),dict(input_key=key,cache_hit=hit,lookup_or_compute_wall_s=time.perf_counter()-start,original_compute_wall_s=original_wall),problem

class Engine:
 def __init__(self,s,seed,arm,out):
  self.s=s;self.seed=seed;self.arm=arm;self.out=out;self.id=f"{s['id']}-{seed}-{arm}";self.t=0.;self.serial=0;self.heap=[];self.events=[];self.tables={};self.choice={};self.seen={n:collections.deque(maxlen=64) for n in 'ABCDE'};self.control_seen={n:-1 for n in 'ABCDE'};self.queues=collections.defaultdict(collections.deque);self.busy=set();self.update_id=0;self.generated=0;self.delivered=set();self.problems={}
 def log(self,event,**v):self.events.append(dict(evidence_kind='software_simulation',t_s=round(self.t,9),event=event,run_id=self.id,pair_id=f"{self.s['id']}:{self.seed}",scenario_id=self.s['id'],seed=self.seed,arm=self.arm,**v))
 def schedule(self,t,kind,*args):
  self.serial+=1;heapq.heappush(self.heap,(round(t,9),self.serial,kind,args))
 def environment(self,t=None):return state_at(self.s,min(60,max(0,self.t if t is None else t)))
 def edge(self,a,b,t=None):return next((e for e in self.environment(t)['edges'] if e['src']==a and e['dst']==b),dict(pdr=0,capacity_payload_bps=0,expected_payload_bps=0))
 def install(self,node,update,version,initial=False):
  if node not in self.environment()['active_nodes']:return
  if MAC[node] not in update['nodes']:return
  self.tables[node]=(version,update);self.control_seen[node]=version
  for f in range(2):self.choice.pop((node,f),None)
  self.log('config_install',node=node,update_id=version,version=version,initial=initial,table=update)
 def select(self):
  epoch=int(round(self.t*2))
  for node,(version,table) in self.tables.items():
   if node not in self.environment()['active_nodes']:continue
   for f,flow in enumerate(table['flows']):
    row=next((r for r in table['routes'] if r['node']==MAC[node] and r['src']==flow['src'] and r['dst']==flow['dst']),None)
    chosen=None;draw,_=uniform(self.seed,self.s['id'],'route',node,epoch,f)
    if row:
     weights=quantize([g['weight'] for g in row['gateways']]);position=int(draw*65535);total=0
     for g,w in zip(row['gateways'],weights):
      total+=w
      if position<total:chosen=BACK[g['node']];break
    self.choice[node,f]=chosen
    self.log('route_selected',node=node,flow=f,next_hop=chosen,version=version,epoch=epoch,draw=draw)
 def packet_fields(self,p):return {k:p[k] for k in ('packet_id','src','dst','origin','sim_boot','seq','payload_bytes','payload_tag')}
 def arrive_data(self,node,p):
  v=self.packet_fields(p)
  if node not in self.environment()['active_nodes']:self.log('drop',node=node,reason='inactive_node',**v);return
  key=p['packet_id']
  if key in self.seen[node]:self.log('drop',node=node,reason='duplicate_64_cache',**v);return
  if node==p['dst']:
   self.seen[node].append(key);self.delivered.add(key);self.log('destination_rx',node=node,**v);return
  if p['ttl']<=1:self.log('drop',node=node,reason='TTL',**v);return
  f=0 if p['src']=='A' else 1;next_hop=self.choice.get((node,f));version=self.tables.get(node,(-1,None))[0]
  if not next_hop:self.log('drop',node=node,reason='no_installed_next_hop',route_version=version,**v);return
  self.seen[node].append(key);self.log('relay' if node!=p['src'] else 'source_admitted',node=node,next_hop=next_hop,route_version=version,**v)
  q=dict(kind='data',packet=dict(p,ttl=p['ttl']-(0 if node==p['src'] else 1)),node=node,next_hop=next_hop,route_version=version,bytes=32);self.enqueue(q)
 def flood(self,node,update,version,ttl):
  if ttl<=1:return
  for e in self.environment()['edges']:
   if e['src']==node and e['capacity_payload_bps']>0 and e['pdr']>0:
    n=len(pack(update,MAC['A'],1,version+1));self.enqueue(dict(kind='control',update=update,version=version,ttl=ttl-1,node=node,next_hop=e['dst'],bytes=n))
 def enqueue(self,q):
  edge=q['node'],q['next_hop'];queue=self.queues[edge]
  if len(queue)>=32:
   fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])
   self.log('queue_drop',node=edge[0],next_hop=edge[1],reason='per_directed_edge_FIFO32',**fields);return
  queue.append(q)
  if edge not in self.busy:self.start(edge)
 def start(self,edge):
  queue=self.queues[edge]
  if not queue:return
  q=queue.popleft();e=self.edge(*edge);self.busy.add(edge)
  fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'],control_bytes=q['bytes'])
  draw,key=uniform(self.seed,self.s['id'],'channel',int(self.t*1000),*edge,fields.get('packet_id','control:'+str(q.get('version'))))
  q.update(p_start=e['pdr'],draw=draw,random_key=key,service_start_s=self.t)
  self.log('tx_attempt' if q['kind']=='data' else 'control_tx',node=edge[0],next_hop=edge[1],route_version=q.get('route_version'),draw=draw,random_key=key,p_success_at_start=e['pdr'],capacity_payload_bps=e['capacity_payload_bps'],**fields)
  duration=q['bytes']*8/e['capacity_payload_bps'] if e['capacity_payload_bps']>0 else .01
  self.schedule(self.t+duration,'complete',q)
 def complete(self,q):
  edge=q['node'],q['next_hop'];self.busy.discard(edge);e=self.edge(*edge)
  prob=min(q['p_start'],e['pdr']) if e['capacity_payload_bps']>0 else 0
  ok=q['draw']<prob
  fields=self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])
  self.log('link_result',node=edge[0],next_hop=edge[1],kind=q['kind'],success=ok,p_success=prob,random_key=q['random_key'],**fields)
  if ok:self.schedule(self.t+(.01 if q['kind']=='data' else .05),'receive',q)
  else:self.log('drop' if q['kind']=='data' else 'control_drop',node=edge[0],next_hop=edge[1],reason='link_failure_or_zero_service',**fields)
  self.start(edge)
 def receive(self,q):
  node=q['next_hop']
  edge=self.edge(q['node'],node)
  if edge['capacity_payload_bps']<=0 or edge['pdr']<=0:
   self.log('drop' if q['kind']=='data' else 'control_drop',node=node,reason='edge_unavailable_at_arrival',**(self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])));return
  if node not in self.environment()['active_nodes']:
   self.log('drop' if q['kind']=='data' else 'control_drop',node=node,reason='inactive_at_arrival',**(self.packet_fields(q['packet']) if q['kind']=='data' else dict(update_id=q['version'])));return
  if q['kind']=='data':self.log('rx',node=node,previous_hop=q['node'],**self.packet_fields(q['packet']));self.arrive_data(node,q['packet'])
  else:
   self.log('control_rx',node=node,previous_hop=q['node'],update_id=q['version'])
   if q['version']<=self.control_seen[node]:self.log('control_duplicate',node=node,update_id=q['version']);return
   if MAC[node] not in q['update']['nodes']:self.log('control_not_member',node=node,update_id=q['version']);return
   self.install(node,q['update'],q['version']);self.flood(node,q['update'],q['version'],q['ttl'])
 def run(self):
  answer,info,problem=optimize(state_at(self.s,0));assert answer['status']=='optimal'
  self.initial=answer['update'];self.problems[info['input_key']]=dict(problem=problem,result=answer)
  for n in 'ABCDE':self.install(n,self.initial,0,True)
  self.last_observed=json.dumps(state_at(self.s,0),sort_keys=True)
  # Initial state comparison excludes the observation timestamp.
  initial=state_at(self.s,0);initial.pop('time_s');self.last_observed=json.dumps(initial,sort_keys=True)
  for tick in range(125):self.schedule(tick*.5,'tick')
  for slot in range(120):
   for src,dst in [('A','B'),('B','A')]:self.schedule(slot*.5,'generate',src,dst,slot)
  for observation in range(1,60):self.schedule(observation,'observe')
  while self.heap:
   self.t,_,kind,args=heapq.heappop(self.heap)
   if self.t>62:break
   if kind=='tick':self.select()
   elif kind=='generate':
    src,dst,slot=args;packet=dict(packet_id=f'{src}>{dst}:{slot:03}',src=src,dst=dst,origin=src,sim_boot=self.seed,seq=slot+1,payload_bytes=32,payload_tag=hashlib.sha256(f'{self.s["id"]}:{self.seed}:{src}:{dst}:{slot}'.encode()).hexdigest(),ttl=8)
    self.generated+=1;self.log('generate',node=src,**self.packet_fields(packet));self.arrive_data(src,packet)
   elif kind=='observe':
    observed_at=max(0,self.t-.5);obs=state_at(self.s,observed_at);comparable=copy.deepcopy(obs);comparable.pop('time_s');signature=json.dumps(comparable,sort_keys=True)
    self.log('observed_state',observed_at_s=observed_at,observation=obs,observation_delay_s=.5)
    if signature!=self.last_observed:
     self.log('detection',observed_at_s=observed_at);self.last_observed=signature
     if self.arm=='adaptive':
      self.log('solve_start',observed_at_s=observed_at);answer,info,problem=optimize(obs);self.problems[info['input_key']]=dict(problem=problem,result=answer)
      self.schedule(self.t+.2,'solve_ready',answer,info,observed_at)
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
  initial_hash=hashlib.sha256(json.dumps(self.initial,sort_keys=True).encode()).hexdigest()
  context=dict(evidence_kind='software_simulation',run_id=self.id,pair_id=f'{self.s["id"]}:{self.seed}',scenario_id=self.s['id'],seed=self.seed,arm=self.arm,duration_s=60,drain_until_s=62,source_planned=240,initial_table_sha256=initial_hash,traffic=self.s['traffic'],scenario_file=f'simulation/mid_link_study/scenarios/{self.s["id"]}.json',scenario_sha256=sha(ROOT/f'simulation/mid_link_study/scenarios/{self.s["id"]}.json'),impact_start_s=20,recovery_anchor_s=40 if self.s['id']=='partition_restore' else 20,
   model=dict(observation_period_s=1,observation_delay_s=.5,detection='at next poll on delayed snapshot change',sensing='ideal centralized delayed whole-state sensor, no reachability oracle or future input; sensor transport/loss not simulated',compute_delay_s=.2,solver_wall_separate=True,route_period_s=.5,TTL=8,data_dedup_entries=64,queue='FIFO32 per directed edge, independent edge servers, no shared RF contention/half-duplex coupling',data_service_bytes=32,header_service_bytes=0,retry=False,data_propagation_s=.01,control_propagation_s=.05,control='single causal source/sequence dedup flood per successful changed-state solve; per-edge fanout copies serialized on same edge server, application bytes not PHY airtime; no periodic refresh/ACK/retry',initial='all nodes preinstalled same solved table before t0, no bootstrap cost',inactive='cannot receive/install/process, saved table retained on return (suspension, not reboot)',installation='invalidate selected next hops until next500ms tick, matching mid_config/mid_tick',channel='hash(seed,scenario,millisecond,edge,packet_id) without arm, start/end p_success minimum',route_random='hash(seed,scenario,node,epoch,flow) common across arms',late_results='[60,62] drain separately; leftovers unresolved, no synthetic delivery'))
  save(self.out/'context.json',context);save(self.out/'planner_inputs.json',self.problems)
  before={e['packet_id'] for e in self.events if e['event']=='destination_rx' and e['t_s']<60}
  summary=dict(run_id=self.id,generated=self.generated,destination_unique=len(self.delivered),destination_unique_before60=len(before),events=len(self.events),evidence_kind='software_simulation');save(self.out/'summary.json',summary);return summary

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--first-pair',action='store_true');p.add_argument('--skip-first-pair',action='store_true');a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=False);started=time.monotonic();summaries=[]
 for sid in IDS:
  s=load(sid)
  for seed in s['seeds']:
   if a.skip_first_pair and sid==IDS[0] and seed==s['seeds'][0]:continue
   if a.first_pair and (sid!=IDS[0] or seed!=s['seeds'][0]):continue
   for arm in ['fixed','adaptive']:
    summary=Engine(s,seed,arm,out/f'{sid}-{seed}-{arm}').run();summaries.append(summary);save(out/'INDEX.json',dict(status='running',runs=summaries));print(json.dumps(summary),flush=True)
   if time.monotonic()-started>1800:raise RuntimeError('30-minute simulation budget exceeded; no auto restart')
 save(out/'INDEX.json',dict(status='complete',evidence_kind='software_simulation',runs=summaries,source_planned=len(summaries)*240,wall_s=time.monotonic()-started,engine_sha256=sha(Path(__file__)),planner_sha256=sha(ROOT/'tools/mid_baseline/planner/planner.py')))
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-019',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out.resolve()),seeds=[11,23,37,53,71],status='passed',exit_code=0,budget=dict(wall_s=1800,cpu_jobs=2),limitations=['Software simulation only; see per-run context for ideal sensing/queues/control assumptions']);save(out/'RUN_MANIFEST.json',m)

if __name__=='__main__':main()
