"""Aggregate only complete, audited batches; seeds remain distinct."""
import csv,datetime,hashlib,json,statistics,sys
from pathlib import Path
root=Path(sys.argv[1]);seed0=Path(sys.argv[2]);meta=json.loads((root/'campaign.json').read_text(encoding='utf-8'))
paths=[seed0]
for b in meta['batches']:
 if b.get('audit_batch_v2.py_exit_code')==0 and b.get('deadline_audit.py_exit_code')==0:paths.append(root/b['name'])
groups={}
for p in paths:
 m=json.loads((p/'batch.json').read_text(encoding='utf-8'));rows=list(csv.DictReader((p/'audited_cases.csv').open(encoding='utf-8')));assert len(rows)==len(m['specs'])
 for spec,row in zip(m['specs'],rows):
  key=(spec['seed'],spec['mode'],spec['speed'],spec['density']);policy=spec['policy']
  assert policy not in groups.setdefault(key,{})
  groups[key][policy]=row
records=[]
for seed in sorted({k[0] for k in groups}):
 pairs=[v for k,v in groups.items() if k[0]==seed and set(v)=={0,7}]
 if len(pairs)!=30:continue
 base=[float(v[0]['on_time_eligible']) for v in pairs];cand=[float(v[7]['on_time_eligible']) for v in pairs];diff=[b-a for a,b in zip(base,cand)]
 records.append(dict(seed=seed,scenarios=30,base_mean=statistics.mean(base),candidate_mean=statistics.mean(cand),
  mean_paired_difference=statistics.mean(diff),minimum_difference=min(diff),maximum_difference=max(diff),
  improved=sum(x>0 for x in diff),worse=sum(x<0 for x in diff),equal=sum(x==0 for x in diff)))
report={'generated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'campaign_status_at_read':meta['status'],
 'completed_cases':sum(len(v) for v in groups.values()),'completed_pairs':sum(set(v)=={0,7} for v in groups.values()),
 'complete_seed_summaries':records,'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
 'scope':'Only audited cases; 30 scenarios share a seed and are not 30 independent replicates.','caveat':'Synthetic uncalibrated radio model; 1s 95% is an internal screening goal.'}
(root/'progress_overview.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
