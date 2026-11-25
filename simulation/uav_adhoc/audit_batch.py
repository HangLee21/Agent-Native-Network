"""Independent raw-event accounting for a completed engineering batch."""
import csv, hashlib, json, math, statistics, sys
from collections import defaultdict
from pathlib import Path
root=Path(sys.argv[1]);batch=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if batch['status']!='completed':raise RuntimeError('batch incomplete')
rows=[]; pairs={}
for i,spec in enumerate(batch['specs']):
 d=root/f'case-{i:04d}';summary=json.loads((d/'summary.json').read_text());offers={};received={}
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  for line in f:
   e=json.loads(line);key=(e['origin_id'],e['origin_boot_id'],e['seq'])
   if e['event']=='offered':
    assert key not in offers;offers[key]=(e['time_us'],e['dst_id'],e['payload_hex'])
   elif e['event']=='destination_received':
    assert key in offers and key not in received and offers[key][1]==e['dst_id'] and e['bytes_match']
    received[key]=e['time_us']
 assert len(offers)==summary['offered'] and len(received)==summary['delivered']
 end=spec['seconds']*1000000;eligible={k for k,v in offers.items() if v[0]+1000000<=end}
 timely={k for k in received if k in eligible and received[k]-offers[k][0]<=1000000}
 per=defaultdict(lambda:[0,0])
 for k in eligible:per[k[0]][0]+=1;per[k[0]][1]+=k in timely
 worst=min((v[1]/v[0] for v in per.values() if v[0]),default=None)
 row=dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],
  offered=len(offers),received=len(received),pdr=len(received)/len(offers),eligible_1s=len(eligible),on_time_1s=len(timely),
  on_time_eligible=len(timely)/len(eligible) if eligible else None,right_censored_1s=len(offers)-len(eligible),
  worst_node_1s=worst,p95_ms=summary['delivery_p95_ms'],p99_ms=summary['delivery_p99_ms'],
  peer_rejected=summary['peer_rejected'],peer_evicted=summary['peer_evicted'],
  attempts=summary['attempts'],control_airtime_us=summary['control_airtime_us'])
 rows.append(row)
 if batch['suite']=='pilot':
  pair=(spec['mode'],spec['speed'],spec['density'],spec['seed']);pairs.setdefault(pair,{})[spec['policy']]=(row,offers)
for key,values in pairs.items():
 assert set(values)=={0,3},key
 assert values[0][1]==values[3][1],f'paired traffic mismatch {key}'
with (root/'audited_cases.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
if pairs:
 with (root/'paired_differences.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['mode','speed','density','seed','delta_pdr','delta_on_time_1s','delta_p95_ms','delta_control_airtime_us']);w.writeheader()
  for (m,s,d,seed),v in sorted(pairs.items()):
   x,y=v[0][0],v[3][0];w.writerow(dict(mode=m,speed=s,density=d,seed=seed,delta_pdr=y['pdr']-x['pdr'],delta_on_time_1s=y['on_time_eligible']-x['on_time_eligible'],delta_p95_ms=(y['p95_ms']-x['p95_ms'] if y['p95_ms'] is not None and x['p95_ms'] is not None else None),delta_control_airtime_us=y['control_airtime_us']-x['control_airtime_us']))
audit=dict(status='passed',cases=len(rows),paired_scenarios=len(pairs),raw_endpoint_keys_checked=True,paired_exact_offers_checked=bool(pairs),
 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),batch_sha256=hashlib.sha256((root/'batch.json').read_bytes()).hexdigest())
(root/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit))
