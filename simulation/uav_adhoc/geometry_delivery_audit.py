"""Compute 1s outcomes by submit-time <=4-hop geometric condition."""
import csv,hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);batch=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if batch['status']!='completed':raise RuntimeError('batch incomplete')
rows=[]
for i,spec in enumerate(batch['specs']):
 d=root/f'case-{i:04d}';summary=json.loads((d/'summary.json').read_text(encoding='utf-8'))
 if not summary.get('event_recording_complete',False):raise RuntimeError(f'case {i} incomplete core event log')
 offers={};received={}
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  for line in f:
   e=json.loads(line);key=(e['origin_id'],e['origin_boot_id'],e['seq'])
   if e['event']=='offered':assert key not in offers;offers[key]=(e['time_us'],e['dst_id'],e['geometric_4hop_at_submit'])
   elif e['event']=='destination_received':
    assert key in offers and key not in received and e['dst_id']==offers[key][1] and e['bytes_match'];received[key]=e['time_us']
 assert len(offers)==summary['offered'] and len(received)==summary['delivered']
 end=spec['seconds']*1000000;eligible=[k for k,v in offers.items() if v[0]+1000000<=end]
 geom=[k for k in eligible if offers[k][2]];other=[k for k in eligible if not offers[k][2]]
 def success(keys):return sum(k in received and received[k]-offers[k][0]<=1000000 for k in keys)
 good=success(geom);other_good=success(other)
 rows.append(dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],
  all_eligible=len(eligible),geom_eligible=len(geom),geom_on_time=good,geom_rate=good/len(geom) if geom else None,
  nongeom_eligible=len(other),nongeom_on_time=other_good,nongeom_rate=other_good/len(other) if other else None,
  geom_share=len(geom)/len(eligible) if eligible else None))
with (root/'geom_at_submit_1s.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
r={'status':'passed','cases':len(rows),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'batch_sha256':hashlib.sha256((root/'batch.json').read_bytes()).hexdigest(),
 'limitations':['Geometry only at offer time, <=4 hops, ideal radius; not an RF success criterion',
 'Topology can change after submission; nongeometric samples may still arrive',
 '1 s maturity rule excludes unresolved near-end samples; overall offered must also be reported']}
(root/'geom_at_submit_audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
