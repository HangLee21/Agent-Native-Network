"""Check bounded per-node simulated table/queue occupancy over time."""
import csv,hashlib,json,sys
from collections import defaultdict
from pathlib import Path
case=Path(sys.argv[1]);config=json.loads((case/'config.json').read_text(encoding='utf-8'));summary=json.loads((case/'summary.json').read_text(encoding='utf-8'))
if not summary.get('event_recording_complete',False):raise RuntimeError('core event overflow: incomplete endpoint evidence')
bounds={'live_sr_peers':32,'routes':32,'rounds':4,'pending':16,'sr_out':12,'nd_peers':32,'sdk_peers':20,'sr_events':32,'nd_queue':16}
groups=defaultdict(dict);maxima={k:0 for k in bounds}
with (case/'events.jsonl').open(encoding='utf-8') as f:
 for line in f:
  e=json.loads(line)
  if e['event']!='resource_sample':continue
  t=e['time_us'];n=e['node_id'];assert 0<=n<30 and n not in groups[t]
  for k,limit in bounds.items():assert isinstance(e[k],int) and 0<=e[k]<=limit;maxima[k]=max(maxima[k],e[k])
  groups[t][n]=e
assert groups and all(len(v)==30 for v in groups.values())
expected=range(0,config['seconds']*1000000,config['resource_sample_ms']*1000)
assert sorted(groups)==list(expected)
rows=[]
for t,nodes in sorted(groups.items()):
 row={'time_s':t/1e6}
 for k in bounds:
  vals=[x[k] for x in nodes.values()];row['max_'+k]=max(vals);row['mean_'+k]=sum(vals)/len(vals)
 rows.append(row)
with (case/'resource_timeseries.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
digest=hashlib.sha256()
with (case/'events.jsonl').open('rb') as f:
 for block in iter(lambda:f.read(1024*1024),b''):digest.update(block)
r={'status':'passed','samples_per_node':len(groups),'bounds':bounds,'observed_maxima':maxima,
 'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'events_sha256':digest.hexdigest(),
 'limitations':['Simulation data structures only, not measured board heap, stack or energy',
 '60s samples can miss short occupancy peaks; core high-water counters recorded separately']}
(case/'resource_audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
