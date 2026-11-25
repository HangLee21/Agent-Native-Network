"""Audit one sampled long case from raw event identities and deadlines."""
import collections,hashlib,json,pathlib,sys
p=pathlib.Path(sys.argv[1]);out=p/'endpoint_audit.json'
if out.exists():raise FileExistsError(out)
m=json.loads((p/'manifest.json').read_text());s=json.loads((p/'summary.json').read_text());assert m['status']=='completed' and s['core_event_overflows']==0;secs=int(m['command'][m['command'].index('--seconds')+1]);end=secs*1000000;off={};rec={};outcomes=collections.Counter();h=hashlib.sha256()
with (p/'events.jsonl').open('rb') as f:
 for line in f:
  h.update(line);x=json.loads(line);kind=x['event'];k=(x.get('origin_id'),x.get('origin_boot_id'),x.get('seq'))
  if kind=='offered':assert k not in off;off[k]=(x['time_us'],x['dst_id'],x['payload_hex'])
  elif kind=='destination_received':assert k in off and k not in rec and x['dst_id']==off[k][1] and x['bytes_match'];rec[k]=x['time_us']
  elif kind=='deadline_outcome':outcomes[x['status_1s']]+=1
mature=[k for k,v in off.items() if v[0]+1000000<=end];ontime=sum(k in rec and rec[k]-off[k][0]<=1000000 for k in mature)
assert len(off)==s['offered'] and len(rec)==s['delivered'] and len(mature)==s['eligible_1s'] and ontime==s['eligible_within_1s'] and sum(outcomes.values())==len(off)
x={'status':'passed','offered':len(off),'delivered':len(rec),'mature':len(mature),'on_time':ontime,'on_time_rate':ontime/len(mature),'outcomes':dict(outcomes),'events_sha256':h.hexdigest(),'limits':['Single synthetic model, no RF']} ;out.write_text(json.dumps(x,indent=2));print(json.dumps(x))
