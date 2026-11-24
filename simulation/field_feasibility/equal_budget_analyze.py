"""Derive per-pair motion, communication and per-height summaries from saved results."""
import argparse,csv,gzip,hashlib,json,pathlib,time
import numpy as np
from scipy import stats

def ci(values):
 a=np.asarray(values,float)
 if not len(a):return {'count':0,'mean':None,'sd':None,'ci95':None,'pvalue':None}
 r={'count':len(a),'mean':float(a.mean()),'sd':float(a.std(ddof=1)) if len(a)>1 else None,'ci95':None,'pvalue':None}
 if len(a)>1:
  s=float(stats.sem(a));r['ci95']=list(map(float,stats.t.interval(.95,len(a)-1,loc=float(a.mean()),scale=s))) if s else [float(a.mean()),float(a.mean())];r['pvalue']=float(stats.ttest_1samp(a,0).pvalue) if s else None
 return r

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);start=time.time();rows=list(csv.DictReader((a.source/'pairs.csv').open(encoding='utf8')));records=[];per_height=[]
 for row in rows:
  if row['status']!='completed':continue
  n=int(row['nodes']);seed=int(row['seed']);entry={}
  for policy in ('C','D'):
   with gzip.open(a.source/f'n{n:02d}-seed{seed}-{policy}.json.gz','rt',encoding='utf8') as f:entry[policy]=json.load(f)
  r={'nodes':n,'seed':seed,'distance_difference_m':float(row['distance_difference_m']),'time_difference_s':float(row['time_difference_s']),'sample_difference':int(row['sample_difference']),'raw_rmse_delta':float(row['delta_offline_rmse']),'masked_rmse_delta':float(row['delta_floor_excluded_rmse']),'online_rmse_delta':float(row['d_online_rmse'])-float(row['c_online_rmse']),'d_message_affected_decisions':int(row['message_affected_decisions'])}
  for policy in ('C','D'):
   v=entry[policy]['result'];samples=v['samples'];cells={(int(np.floor(x['x_m']/5+.5)),int(np.floor(x['y_m']/5+.5)),x['h_m']) for x in samples};r[policy.lower()+'_revisit_fraction']=1-len(cells)/len(samples);r[policy.lower()+'_rejected_candidate_fraction']=v['candidate_rejections']/(24*20*n);r[policy.lower()+'_tx_bytes']=v['network']['metrics']['total']['tx_bytes'] if policy=='D' else 0
  records.append(r)
  for h in ('2','25','50','80'):
   c=entry['C']['evaluation']['per_height'][h];d=entry['D']['evaluation']['per_height'][h];assert c['floor_count']==d['floor_count'];row_h={'nodes':n,'seed':seed,'height_m':int(h),'floor_count':c['floor_count'],'raw_delta':d['raw']['rmse_db']-c['raw']['rmse_db'],'filtered_support':c['floor_excluded']['support'],'masked_delta':None}
   if c['floor_excluded']['rmse_db'] is not None and d['floor_excluded']['rmse_db'] is not None:row_h['masked_delta']=d['floor_excluded']['rmse_db']-c['floor_excluded']['rmse_db']
   per_height.append(row_h)
 for name,items in [('metrics.csv',records),('heights.csv',per_height)]:
  if items:
   with (a.out/name).open('w',newline='',encoding='utf8') as f:w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
 summary=[]
 for n in sorted({int(r['nodes']) for r in rows}):
  items=[r for r in records if r['nodes']==n];entry={'nodes':n,'attempted_pairs':sum(int(r['nodes'])==n for r in rows),'complete_pairs':len(items)}
  for key in ('raw_rmse_delta','masked_rmse_delta','online_rmse_delta','d_message_affected_decisions','c_revisit_fraction','d_revisit_fraction','c_rejected_candidate_fraction','d_rejected_candidate_fraction','d_tx_bytes'):entry[key]=ci([r[key] for r in items])
  entry['height']={str(h):{'raw_delta':ci([r['raw_delta'] for r in per_height if r['nodes']==n and r['height_m']==h]),'masked_delta':ci([r['masked_delta'] for r in per_height if r['nodes']==n and r['height_m']==h and r['masked_delta'] is not None])} for h in (2,25,50,80)};summary.append(entry)
 (a.out/'metrics-summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');manifest={'template_only':False,'task_id':'E2-045','run_id':a.out.name,'started_at':start,'finished_at':time.time(),'timezone':'Asia/Shanghai','worktree':None,'git_commit':None,'upstream_commit':None,'dirty_files_sha256':{pathlib.Path(__file__).name:hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()},'command':'equal_budget_analyze.py --source <run> --out <new dir>','python_executable':None,'dependency_snapshot':{'numpy':np.__version__},'data_and_weights_sha256':{'pairs.csv':hashlib.sha256((a.source/'pairs.csv').read_bytes()).hexdigest(),'run_manifest':hashlib.sha256((a.source/'RUN_MANIFEST.json').read_bytes()).hexdigest()},'config_file':str(a.source/'config.json'),'seeds':list(range(2000,2020)),'budget':'completed paired seeds only; failed pairs excluded and counted','output_directory':str(a.out),'process_id':None,'exit_code':0,'status':'completed','review_reference':'coordination/tasks/E2-045.md','limitations':['same V2 scene and four static heights','candidate rejection is candidate-level, not mission failure rate','per-seed repeated spatial cell fraction includes sampling at different times']};(a.out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
if __name__=='__main__':main()
