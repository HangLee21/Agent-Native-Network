"""Endpoint outcomes by submit-time synthetic shortest-hop bucket."""
import collections,hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'reach_audit.json'
if out.exists():raise FileExistsError(out)
m=json.loads((p/'manifest.json').read_text());s=json.loads((p/'summary.json').read_text());assert m['status']=='completed' and not s['core_event_overflows'];end=int(m['command'][m['command'].index('--seconds')+1])*1000000;off={};recv={};h=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for line in f:
  h.update(line);x=json.loads(line);k=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'))
  if x['event']=='offered':assert k not in off;off[k]=(x['time_us'],x['dst_id'],x['geometric_shortest_hops_at_submit'])
  elif x['event']=='destination_received':assert k in off and k not in recv and x['dst_id']==off[k][1] and x['bytes_match'];recv[k]=x['time_us']
assert len(off)==s['offered'] and len(recv)==s['delivered'];groups=collections.defaultdict(lambda:[0,0])
for k,(t,d,hops) in off.items():
 if t+1000000>end:continue
 label='disconnected' if hops is None else ('1' if hops==1 else '2' if hops==2 else '3-4' if hops<=4 else '5-8' if hops<=8 else '9-16' if hops<=16 else '17+')
 groups[label][0]+=1;groups[label][1]+=int(k in recv and recv[k]-t<=1000000)
x={'status':'passed','buckets':{k:{'eligible':v[0],'on_time':v[1],'rate':v[1]/v[0]} for k,v in groups.items()},'events_sha256':h.hexdigest(),'limitations':['Geometry at submission only; not persistent path or calibrated RF','Association is not a unique per-packet cause']};out.write_text(json.dumps(x,indent=2));print(json.dumps(x))
