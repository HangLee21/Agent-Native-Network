"""Analyze observed route invalidation -> next selected route, with censoring.

This measures local route reselection, not recovery of end-to-end delivery.
"""
import csv,hashlib,json,math,sys
from pathlib import Path
root=Path(sys.argv[1]);batch=json.loads((root/'batch.json').read_text(encoding='utf-8'))
if batch['status']!='completed':raise RuntimeError('batch incomplete')
rows=[];intervals=[]
for i,spec in enumerate(batch['specs']):
 d=root/f'case-{i:04d}';summary=json.loads((d/'summary.json').read_text(encoding='utf-8'))
 if not summary.get('event_recording_complete',False):raise RuntimeError(f'case {i}: no complete core event record')
 opened={};completed=[];invalidation_events=0
 with (d/'events.jsonl').open(encoding='utf-8') as f:
  last=-1
  for line in f:
   e=json.loads(line);t=e['time_us'];assert t>=last;last=t
   if e['event'] not in ('sr_8','sr_5'):continue
   observer=e.get('observer_id');dst=e.get('dst_id')
   if observer is None or dst is None or not (0<=observer<30 and 0<=dst<30):continue
   key=(observer,dst)
   if e['event']=='sr_8':
    invalidation_events+=1
    if key not in opened:opened[key]=t
   elif key in opened:
    start=opened.pop(key);duration=t-start;assert duration>=0
    completed.append(duration);intervals.append(dict(case=i,observer_id=observer,dst_id=dst,start_us=start,end_us=t,duration_us=duration,censored=False))
 end=spec['seconds']*1000000
 for (observer,dst),start in opened.items():intervals.append(dict(case=i,observer_id=observer,dst_id=dst,start_us=start,end_us=end,duration_us=end-start,censored=True))
 completed.sort()
 def quantile(q):return completed[math.ceil(q*len(completed))-1]/1000 if completed else None
 rows.append(dict(case=i,mode=spec['mode'],speed=spec['speed'],density=spec['density'],seed=spec['seed'],policy=spec['policy'],
  invalidation_events=invalidation_events,completed_reselections=len(completed),right_censored=len(opened),
  reselection_p50_ms=quantile(.5),reselection_p95_ms=quantile(.95),reselection_p99_ms=quantile(.99)))
with (root/'route_reselection_cases.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
with (root/'route_reselection_intervals.jsonl').open('w',encoding='utf-8') as f:
 for x in intervals:f.write(json.dumps(x,separators=(',',':'))+'\n')
a={'status':'passed','cases':len(rows),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
   'batch_sha256':hashlib.sha256((root/'batch.json').read_bytes()).hexdigest(),
   'limitation':'Local invalidation to route selection; no claim of end-to-end recovery; outstanding intervals right-censored.'}
(root/'route_reselection_audit.json').write_text(json.dumps(a,indent=2),encoding='utf-8');print(json.dumps(a))
