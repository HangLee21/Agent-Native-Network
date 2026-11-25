"""Reconstruct sender and receiver delivery fairness from mature 1 s offers."""
import csv,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);batch=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if batch['status']!='completed':raise RuntimeError('batch incomplete')
rows=[];cases=[]
for i,spec in enumerate(batch['specs']):
 d=root/f'case-{i:04d}';summary=json.loads((d/'summary.json').read_text(encoding='utf-8'))
 if not summary.get('event_recording_complete',False):raise RuntimeError(f'case {i} incomplete event record')
 offers={};recv={}
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  for line in f:
   e=json.loads(line);k=(e['origin_id'],e['origin_boot_id'],e['seq'])
   if e['event']=='offered':assert k not in offers;offers[k]=(e['time_us'],e['dst_id'])
   elif e['event']=='destination_received':assert k in offers and k not in recv and e['dst_id']==offers[k][1] and e['bytes_match'];recv[k]=e['time_us']
 assert len(offers)==summary['offered'] and len(recv)==summary['delivered']
 counts=[dict(sent=0,sent_on_time=0,target=0,target_on_time=0) for _ in range(30)]
 for k,(t,dst) in offers.items():
  if t+1000000>spec['seconds']*1000000:continue
  ok=k in recv and recv[k]-t<=1000000
  counts[k[0]]['sent']+=1;counts[k[0]]['sent_on_time']+=ok
  counts[dst]['target']+=1;counts[dst]['target_on_time']+=ok
 rates=[]
 for node,c in enumerate(counts):
  sr=c['sent_on_time']/c['sent'] if c['sent'] else None;dr=c['target_on_time']/c['target'] if c['target'] else None
  rows.append(dict(case=i,node=node,**c,sender_on_time_rate=sr,receiver_on_time_rate=dr))
  if dr is not None:rates.append(dr)
 cases.append(dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],
  receiver_nodes_with_offers=len(rates),worst_receiver_on_time_rate=min(rates) if rates else None,
  receiver_median_on_time_rate=statistics.median(rates) if rates else None,
  receiver_jain=(sum(rates)**2/(len(rates)*sum(x*x for x in rates))) if rates and any(rates) else None))
with (root/'node_delivery_1s.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
with (root/'receiver_fairness_cases.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=cases[0]);w.writeheader();w.writerows(cases)
r={'status':'passed','cases':len(cases),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'batch_sha256':hashlib.sha256((root/'batch.json').read_bytes()).hexdigest(),
 'limitations':['1 s mature offers only','ratio of per-node rates, not proof of application fairness','unvalidated radio model']}
(root/'node_delivery_audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
