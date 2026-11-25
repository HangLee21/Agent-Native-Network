"""Independently re-evaluate 0.5/1/2 s outcomes and right censoring."""
import csv,hashlib,json,sys
from collections import Counter,defaultdict
from pathlib import Path
root=Path(sys.argv[1]);b=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if b['status']!='completed':raise RuntimeError('batch is incomplete')
rows=[]
for i,spec in enumerate(b['specs']):
 d=root/f'case-{i:04d}';offers={};received={};rejected=set();outcomes={}
 summary=json.loads((d/'summary.json').read_text(encoding='utf-8'))
 if not summary.get('event_recording_complete',True):raise RuntimeError(f'case {i} firmware event queue overflow; endpoint metrics incomplete')
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  for line in f:
   e=json.loads(line);key=(e['origin_id'],e['origin_boot_id'],e['seq'])
   if e['event']=='offered':assert key not in offers;offers[key]=(e['time_us'],e['dst_id'],e['payload_hex'])
   elif e['event']=='submission_rejected':rejected.add(key)
   elif e['event']=='destination_received':
    assert key in offers and key not in received and e['dst_id']==offers[key][1] and e['bytes_match'];received[key]=e['time_us']
   elif e['event']=='deadline_outcome':assert key in offers and key not in outcomes;outcomes[key]=e
 assert len(offers)==len(outcomes)
 end=spec['seconds']*1000000
 for limit,label in ((500000,'status_500ms'),(1000000,'status_1s'),(2000000,'status_2s')):
  counts=Counter();nodes=defaultdict(lambda:[0,0])
  for key,(sent,_,_) in offers.items():
   status=('submission_rejected' if key in rejected else 'received_on_time' if key in received and received[key]-sent<=limit else 'right_censored' if sent+limit>end else 'no_endpoint_receipt_by_deadline')
   assert outcomes[key][label]==status
   counts[status]+=1
   if sent+limit<=end:
    nodes[key[0]][0]+=1;nodes[key[0]][1]+=status=='received_on_time'
  eligible=sum(v[0] for v in nodes.values());ontime=sum(v[1] for v in nodes.values())
  rows.append(dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],deadline_ms=limit//1000,
   offered=len(offers),eligible=eligible,eligible_on_time=ontime,eligible_on_time_rate=ontime/eligible if eligible else None,
   immature_offers=len(offers)-eligible,unresolved_right_censored=counts['right_censored'],submission_rejected=counts['submission_rejected'],
   no_endpoint_receipt_by_deadline=counts['no_endpoint_receipt_by_deadline'],
   worst_eligible_node_rate=min((x[1]/x[0] for x in nodes.values() if x[0]),default=None)))
with (root/'deadline_audit.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
r={'status':'passed','cases':len(b['specs']),'deadlines_ms':[500,1000,2000],'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'batch_sha256':hashlib.sha256((root/'batch.json').read_bytes()).hexdigest(),'limitation':'No endpoint receipt is not a unique causal loss reason.'}
(root/'deadline_audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
