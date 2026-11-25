"""Compare non-resource event stream plus final summary for two smoke runs."""
import hashlib,json,pathlib,sys
base=pathlib.Path(sys.argv[1]);sample=pathlib.Path(sys.argv[2]);out=pathlib.Path(sys.argv[3]);out.mkdir(parents=True,exist_ok=False)
def stream(p):
 h=hashlib.sha256();count=0
 with (p/'events.jsonl').open('rb') as f:
  for line in f:
   if json.loads(line)['event']=='resource_sample':continue
   h.update(line);count+=1
 return h.hexdigest(),count
b=stream(base);s=stream(sample);a=json.loads((base/'summary.json').read_text());c=json.loads((sample/'summary.json').read_text());assert b==s and a==c,(b,s)
x={'status':'passed','base_non_sample_event_sha256':b[0],'sample_non_sample_event_sha256':s[0],'events':b[1],'summary_equal':True,'limitations':['One input only, not formal equivalence']};(out/'equality.json').write_text(json.dumps(x,indent=2));print(json.dumps(x))
