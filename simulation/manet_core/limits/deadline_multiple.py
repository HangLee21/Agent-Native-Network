"""Independent endpoint deadline counts for 0.5/1/2/5 sec, right-censored."""
import hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'deadline_multitime.json'
if out.exists():raise FileExistsError(out)
m=json.loads((p/'manifest.json').read_text());s=json.loads((p/'summary.json').read_text());assert m['status']=='completed' and not s['core_event_overflows'];seconds=int(m['command'][m['command'].index('--seconds')+1]);end=seconds*1000000;off={};rec={};h=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for line in f:
  h.update(line);x=json.loads(line);k=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'))
  if x['event']=='offered':assert k not in off;off[k]=(x['time_us'],x['dst_id'],x['payload_hex'])
  elif x['event']=='destination_received':assert k in off and k not in rec and x['dst_id']==off[k][1] and x['bytes_match'];rec[k]=x['time_us']
assert len(off)==s['offered'] and len(rec)==s['delivered'];outcomes={}
for lim in (500000,1000000,2000000,5000000):
 keys=[k for k,v in off.items() if v[0]+lim<=end];ok=sum(k in rec and rec[k]-off[k][0]<=lim for k in keys);outcomes[str(lim//1000)]={'eligible':len(keys),'on_time':ok,'rate':ok/len(keys),'immature':len(off)-len(keys)}
x={'status':'passed','deadlines_ms':outcomes,'events_sha256':h.hexdigest()};out.write_text(json.dumps(x,indent=2));print(json.dumps(x))
