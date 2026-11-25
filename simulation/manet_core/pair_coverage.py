"""Per ordered pair deadline coverage. No assumption that every pair can connect."""
import collections,hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'pair_coverage.json'
if out.exists():raise FileExistsError(out)
m=json.loads((p/'manifest.json').read_text());s=json.loads((p/'summary.json').read_text());assert m['status']=='completed' and not s['core_event_overflows'];end=int(m['command'][m['command'].index('--seconds')+1])*1000000;off={};rec={};h=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for line in f:
  h.update(line);x=json.loads(line);k=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'))
  if x['event']=='offered':assert k not in off;off[k]=(x['time_us'],x['dst_id'])
  elif x['event']=='destination_received':assert k in off and k not in rec and x['dst_id']==off[k][1] and x['bytes_match'];rec[k]=x['time_us']
pairs=collections.defaultdict(lambda:[0,0]);nodes=set()
for k,(t,d) in off.items():
 nodes.add(k[0]);nodes.add(d)
 if t+1000000>end:continue
 counts=pairs[(k[0],d)];counts[0]+=1;counts[1]+=int(k in rec and rec[k]-t<=1000000)
records=[{'origin':i,'destination':j,'eligible':pairs[(i,j)][0],'on_time':pairs[(i,j)][1],'rate':pairs[(i,j)][1]/pairs[(i,j)][0] if pairs[(i,j)][0] else None} for i in sorted(nodes) for j in sorted(nodes) if i!=j]
x={'status':'passed','nodes':len(nodes),'possible_ordered_pairs':len(records),'tested_pairs':sum(r['eligible']>0 for r in records),'tested_but_no_on_time_receipt':sum(r['eligible']>0 and not r['on_time'] for r in records),'untested':sum(not r['eligible'] for r in records),'pairs':records,'events_sha256':h.hexdigest(),'limitations':['Each direction counted separately; not physical RF','No on-time receipt does not identify a unique loss cause or prove persistent disconnection']};out.write_text(json.dumps(x,indent=2));print(json.dumps({k:v for k,v in x.items() if k!='pairs'}))
