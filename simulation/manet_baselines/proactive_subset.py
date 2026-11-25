"""Finite message-driven proactive MANET subset; not RFC wire implementation."""
import argparse,heapq,hashlib,importlib.util,json,math,random,sys,time,os
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/'simulation/outputs/E1-030/20261114-62-engineering-frozen/src/motion.py'
spec=importlib.util.spec_from_file_location('frozen_motion',FROZEN);motion=importlib.util.module_from_spec(spec);spec.loader.exec_module(motion)
N=30
class Node:
 def __init__(self,i,metric):self.i=i;self.metric=metric;self.links={};self.tc={};self.mpr=set();self.selectors=set();self.seen={};self.ownpos=None;self.hello_seq=0;self.peer_lru=[]
 def hello(self,pos):
  self.ownpos=pos;self.hello_seq+=1
  return dict(origin=self.i,seq=self.hello_seq,pos=pos,heard=sorted(self.links),mpr=sorted(self.mpr),qualities={j:v['q'] for j,v in self.links.items()} if self.metric!='hop' else {})
 def receive_hello(self,msg,t):
  i=msg['origin'];prev=self.links.get(i);q=(prev['q']+.2) if prev else .2
  radial=0
  if prev and t>prev['time']:
   radial=(math.dist(self.ownpos,msg['pos'])-prev['distance'])/(t-prev['time'])
  self.links[i]=dict(time=t,q=q,reverse=msg['qualities'].get(self.i,0),heard=msg['heard'],distance=math.dist(self.ownpos,msg['pos']),radial=radial,symmetric=self.i in msg['heard'],selected=self.i in msg['mpr'])
 def expire(self,t):
  self.links={i:v for i,v in self.links.items() if t-v['time']<=6};self.tc={i:v for i,v in self.tc.items() if t-v['time']<=15}
  sym={i:v for i,v in self.links.items() if v['symmetric']};self.selectors={i for i,v in sym.items() if v['selected']}
  two={x for v in sym.values() for x in v['heard'] if x!=self.i and x not in sym};chosen=set()
  while two:
   scores=[(len(two.intersection(v['heard'])),-i,i) for i,v in sym.items() if i not in chosen]
   if not scores or max(scores)[0]==0:break
   i=max(scores)[2];chosen.add(i);two.difference_update(sym[i]['heard'])
  self.mpr=chosen
 def weight(self,v):
  if self.metric=='hop':return 1.
  base=1/max(.05,v['q']*v['reverse'])
  return base*(math.exp(max(-2,min(2,.05*v['radial']))) if self.metric=='predictive_subset' else 1.)
 def tc_message(self,t):
  edges=[(self.i,i,self.weight(self.links[i])) for i in sorted(self.selectors) if i in self.links]
  return dict(origin=self.i,seq=t,edges=edges)
 def receive_tc(self,msg,t):
  origin=msg['origin'];old=self.seen.get(origin,-1)
  if msg['seq']<=old:return False
  self.seen[origin]=msg['seq'];self.tc[origin]=dict(time=t,edges=msg['edges']);return True
 def next_hop(self,dst):
  adj={i:[] for i in range(N)}
  for i,v in self.links.items():
   if v['symmetric'] and (self.metric=='hop' or v['reverse']>0):adj[self.i].append((i,self.weight(v)))
  for v in self.tc.values():
   for a,b,w in v['edges']:adj[a].append((b,w));adj[b].append((a,w))
  q=[(0.,self.i,-1)];best={}
  while q:
   dist,node,first=heapq.heappop(q)
   if node in best:continue
   best[node]=dist
   if node==dst:return first
   for nxt,w in adj[node]:
    if nxt not in best:heapq.heappush(q,(dist+w,nxt,nxt if node==self.i else first))
  return None

def sample(mode,seed,seconds,metric):
 def draw(*parts):return int.from_bytes(hashlib.sha256(('|'.join(map(str,(seed,*parts)))).encode()).digest()[:8],'big')/2**64
 nodes=[Node(i,metric) for i in range(N)];counts={'offered':0,'delivered':0,'no_route':0,'stale_next_hop':0,'loop_or_hoplimit':0,'control_bytes':0,'control_frames':0,'control_airtime_us':0,'data_bytes':0,'data_airtime_us':0,'control_mtu_rejected':0,'peer_evicted':0};events=[]
 def frame(t,kind,sender,nbytes):
  if nbytes>250:
   counts['control_mtu_rejected']+=1;events.append(dict(t=t,event='control_rejected',sender=sender,bytes=nbytes,reason='estimated_mtu_250'));return False
  counts['control_bytes']+=nbytes;counts['control_frames']+=1;counts['control_airtime_us']+=192+8*nbytes;events.append(dict(t=t,event=kind,sender=sender,bytes=nbytes,airtime_us=192+8*nbytes));return True
 for t in range(seconds):
  pos=motion.positions('crossing',25,seed,t);edges=motion.graph(pos,150);adj={i:set() for i in range(N)}
  for a,b in edges:adj[a].add(b);adj[b].add(a)
  for node in nodes:node.ownpos=pos[node.i];node.expire(t)
  if t%2==0:
   messages=[n.hello(pos[n.i]) for n in nodes]
   for node in nodes:
    for v in node.links.values():v['q']*=.8
   for n,msg in zip(nodes,messages):
    if not frame(t,'hello',n.i,24+2*len(msg['heard'])+2*len(msg['mpr'])+5*len(msg['qualities'])+(16 if metric=='predictive_subset' else 0)):continue
    for peer in sorted(adj[n.i]):
     if draw('hello',t,n.i,peer)<.95:nodes[peer].receive_hello(msg,t)
  if t%5==0:
   for origin in nodes:
    msg=origin.tc_message(t);queue=[origin.i];sent={origin.i}
    while queue:
     sender=queue.pop(0)
     if not frame(t,'tc',sender,20+12*len(msg['edges'])):continue
     for peer in sorted(adj[sender]):
      if draw('tc',t,origin.i,sender,peer)>=.95 or peer==origin.i:continue
      fresh=nodes[peer].receive_tc(msg,t)
      if fresh and peer not in sent and peer in nodes[sender].mpr:sent.add(peer);queue.append(peer)
  for i,n in enumerate(nodes):
   dst=(i+1+(t*7+seed)%(N-1))%N;counts['offered']+=1;visited={i};current=i;success=False;why='loop_or_hoplimit'
   for hop in range(16):
    nxt=nodes[current].next_hop(dst)
    if nxt is None:why='no_route';break
    peers=nodes[current].peer_lru
    if nxt in peers:peers.remove(nxt)
    elif len(peers)>=19:peers.pop(0);counts['peer_evicted']+=1
    peers.append(nxt)
    counts['data_bytes']+=48;counts['data_airtime_us']+=192+8*48
    if nxt not in adj[current] or draw('data',t,i,dst,current,nxt,hop)>=.95:why='stale_next_hop';break
    if nxt==dst:success=True;break
    if nxt in visited:break
    visited.add(nxt);current=nxt
   counts['delivered' if success else why]+=1
   events.append(dict(t=t,event='destination_received' if success else 'packet_failed',origin=i,dst=dst,seq=t+1,reason=None if success else why))
 return counts,events

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=60);p.add_argument('--seeds',type=int,default=3);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=datetime.now(timezone.utc).isoformat();rows=[]
 for metric in ['hop','etx_subset','predictive_subset']:
  for seed in range(a.seeds):
   counts,events=sample('crossing',seed,a.seconds,metric);counts.update(metric=metric,seed=seed,seconds=a.seconds);rows.append(counts)
   with (out/f'{metric}-{seed}.jsonl').open('w') as f:
    for e in events:f.write(json.dumps(e,separators=(',',':'))+'\n')
   print(metric,seed,counts['delivered'],'/',counts['offered'],flush=True)
 (out/'summary.json').write_text(json.dumps(rows,indent=2));h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();manifest=dict(task_id='E2-034',run_id=out.name,started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(ROOT),git_commit=None,dirty_files_sha256={str(Path(__file__)):h(Path(__file__))},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={str(FROZEN):h(FROZEN)},config_file=None,seeds=list(range(a.seeds)),budget=dict(workers=1,seconds=a.seconds),output_directory=str(out),process_id=os.getpid(),status='passed',exit_code=0,review_reference=None,limitations=['Message-driven standalone pedagogical subset, not RFC 3626 or original P-OLSR implementation; no channel contention, propagation, bandwidth scheduling, target C or full RFC state.','Delay is zero within one simulation tick; no deadline or fair comparison with E1.','ETX and radial-speed estimates are approximations and not original published implementation.','Airtime assumes 1 Mbit/s plus 192 us per frame; accounting only, no contention or time scheduling. Oversized estimated control frames are rejected rather than fragmented; unicast peer LRU has 19 slots plus broadcast, with zero modeled registration time. Conditional success coins are keyed by seed/time/frame/link.'])
 (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(rows))
if __name__=='__main__':main()
