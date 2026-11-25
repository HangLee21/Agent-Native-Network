"""Stream-audit sampled bounded state; samples are not peak or heap measurements."""
import collections,hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'resource_audit.json'
if out.exists():raise FileExistsError(out)
summary=json.loads((p/'summary.json').read_text());manifest=json.loads((p/'manifest.json').read_text());secs=int(manifest['command'][manifest['command'].index('--seconds')+1]);bounds=[40,40,16,128,32,64,20,1];names=['routes','discoveries','pending','seen','outgoing','events','peers','inflight'];counts=collections.Counter();peaks=[0]*8;timeline={};digest=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for raw in f:
  digest.update(raw);x=json.loads(raw)
  if x['event']!='resource_sample':continue
  node=x['observer_id'];v=x['values'];assert 0<=node<30 and len(v)==8 and all(0<=z<=b for z,b in zip(v,bounds));counts[node]+=1
  peaks=[max(a,b) for a,b in zip(peaks,v)];bucket=x['time_us']//3600000000;agg=timeline.setdefault(str(bucket),[0]*8)
  for i,z in enumerate(v):agg[i]=max(agg[i],z)
assert len(counts)==30 and all(v==(secs+59)//60 for v in counts.values()) and summary['core_event_overflows']==0
x={'status':'passed','counts_per_node':dict(counts),'maxima':dict(zip(names,peaks)),'hourly_sampled_maxima':{h:dict(zip(names,v)) for h,v in timeline.items()},'bounds':dict(zip(names,bounds)),'events_sha256':digest.hexdigest(),'limitations':['60s simulated sampling can miss peaks','No board heap, stack, energy or RF measurements']}
out.write_text(json.dumps(x,indent=2));print(json.dumps(x))
