"""Independent raw-event accounting for a completed engineering batch."""
import csv, hashlib, json, math, statistics, sys
from collections import defaultdict
from pathlib import Path
root=Path(sys.argv[1]);batch=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if batch['status']!='completed':raise RuntimeError('batch incomplete')
rows=[]; pairs={}
for i,spec in enumerate(batch['specs']):
 d=root/f'case-{i:04d}';summary=json.loads((d/'summary.json').read_text());offers={};received={};outcomes={};rejected=set()
 if not summary.get('event_recording_complete',True):raise RuntimeError(f'case {i} firmware event queue overflow; endpoint metrics incomplete')
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  for line in f:
   e=json.loads(line);key=(e['origin_id'],e['origin_boot_id'],e['seq'])
   if e['event']=='offered':
    assert key not in offers;offers[key]=(e['time_us'],e['dst_id'],e['payload_hex'])
   elif e['event']=='destination_received':
    assert key in offers and key not in received and offers[key][1]==e['dst_id'] and e['bytes_match']
    received[key]=e['time_us']
   elif e['event']=='submission_rejected':rejected.add(key)
   elif e['event']=='deadline_outcome':
    assert key in offers and key not in outcomes;outcomes[key]=e
 assert len(offers)==summary['offered'] and len(received)==summary['delivered']
 end=spec['seconds']*1000000;eligible={k for k,v in offers.items() if v[0]+1000000<=end}
 if outcomes:
  assert len(outcomes)==len(offers)
  for k,e in outcomes.items():
   for limit,label in ((500000,'status_500ms'),(1000000,'status_1s'),(2000000,'status_2s')):
    expected=('submission_rejected' if k in rejected else
     'received_on_time' if k in received and received[k]-offers[k][0]<=limit else
     'right_censored' if offers[k][0]+limit>end else 'no_endpoint_receipt_by_deadline')
    assert e[label]==expected,(i,k,label,e[label],expected)
 timely={k for k in received if k in eligible and received[k]-offers[k][0]<=1000000}
 per=defaultdict(lambda:[0,0])
 for k in eligible:per[k[0]][0]+=1;per[k[0]][1]+=k in timely
 worst=min((v[1]/v[0] for v in per.values() if v[0]),default=None)
 row=dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],
  rate=spec.get('rate',1),payload=spec.get('payload',32),phy_rate=spec.get('phy_rate',1),
  service_ms=spec.get('service_ms',10),geometry_ms=spec.get('geometry_ms',250),peer_eviction_us=spec.get('peer_eviction_us',0),
  offered=len(offers),received=len(received),pdr=len(received)/len(offers),eligible_1s=len(eligible),on_time_1s=len(timely),
  on_time_eligible=len(timely)/len(eligible) if eligible else None,right_censored_1s=len(offers)-len(eligible),
  worst_node_1s=worst,p95_ms=summary['delivery_p95_ms'],p99_ms=summary['delivery_p99_ms'],
  peer_rejected=summary['peer_rejected'],peer_evicted=summary['peer_evicted'],
  attempts=summary['attempts'],control_airtime_us=summary['control_airtime_us'],
  core_sr_overflows=summary.get('core_sr_overflows'),core_rreq_denied=summary.get('core_rreq_denied'),
  core_sr_rejected=summary.get('core_sr_rejected'),core_event_overflows=summary.get('core_event_overflows'),core_nd_table_full=summary.get('core_nd_table_full'))
 rows.append(row)
 if batch['suite'] in ('pilot','core','ablation','sensitivity','peer_cost','pressure','reverse_trial','reverse_speed'):
  pair=tuple(sorted((k,v) for k,v in spec.items() if k!='policy'));pairs.setdefault(pair,{})[spec['policy']]=(row,offers)
for key,values in pairs.items():
 baseline=0 if 0 in values else 7 if 7 in values else None
 if baseline is not None:
  for policy,value in values.items():assert values[baseline][1]==value[1],f'paired traffic mismatch {key} policy {policy}'
with (root/'audited_cases.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0].keys());w.writeheader();w.writerows(rows)
if pairs:
 with (root/'paired_differences.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['scenario','candidate_policy','delta_pdr','delta_on_time_1s','delta_p95_ms','delta_control_airtime_us']);w.writeheader()
  for key,v in sorted(pairs.items()):
   baseline=0 if 0 in v else 7 if 7 in v else None
   if baseline is None:continue
   x=v[baseline][0]
   for policy in sorted(set(v)-{baseline}):
    y=v[policy][0];w.writerow(dict(scenario=json.dumps(dict(key),sort_keys=True),candidate_policy=policy,delta_pdr=y['pdr']-x['pdr'],delta_on_time_1s=y['on_time_eligible']-x['on_time_eligible'],delta_p95_ms=(y['p95_ms']-x['p95_ms'] if y['p95_ms'] is not None and x['p95_ms'] is not None else None),delta_control_airtime_us=y['control_airtime_us']-x['control_airtime_us']))
checked_pairs=sum((0 in v or 7 in v) and len(v)>1 for v in pairs.values())
audit=dict(status='passed',cases=len(rows),paired_scenarios=checked_pairs,raw_endpoint_keys_checked=True,paired_exact_offers_checked=bool(checked_pairs),
 source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),batch_sha256=hashlib.sha256((root/'batch.json').read_bytes()).hexdigest())
(root/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8');print(json.dumps(audit))
