import argparse,csv,hashlib,json,statistics,sys
from pathlib import Path
from collections import defaultdict
p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[2];src=root/'simulation/results/2026-10-22-agent-collab-v1/metrics.csv'
out=Path(a.output);out.mkdir(parents=True,exist_ok=False)
h=lambda:hashlib.sha256(src.read_bytes()).hexdigest()
before=h();rows=list(csv.DictReader(src.open(encoding='utf-8-sig')))
fields=['rate','background','result_size','need','intermittent','horizon']
key=lambda r:tuple(r[k] for k in fields)
lookup={}
for r in rows:
 k=key(r)+(r['policy'],r['seed']);assert k not in lookup;lookup[k]=r
policies=sorted({r['policy'] for r in rows});groups=defaultdict(list)
for r in rows:
 local=lookup[key(r)+('independent',r['seed'])]
 groups[key(r)+(r['policy'],)].append(float(r['mean_completion'])-float(local['mean_completion']))
assert len(rows)==8640 and len(groups)==360
assert all(len(v)==24 for v in groups.values())
with (out/'paired.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.writer(f);w.writerow(fields+['policy','n','mean_delta_seconds','seed_sd_seconds','min_delta','max_delta'])
 for k,v in sorted(groups.items()):w.writerow(list(k)+[len(v),statistics.mean(v),statistics.stdev(v),min(v),max(v)])
counts={p:{'faster':0,'equal':0,'slower':0} for p in policies}
for k,v in groups.items():
 d=statistics.mean(v);counts[k[-1]]['faster' if d < -1e-9 else 'slower' if d>1e-9 else 'equal']+=1
assert before==h()
report={'source':str(src),'source_sha256':before,'python':sys.version,'rows':len(rows),'conditions':len(groups)//len(policies),'seeds_per_group':24,'policy_condition_counts':counts,'scope':'Historical CSV reanalysis, not new simulation or independent reproduction','source_unchanged':True}
(out/'manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))
