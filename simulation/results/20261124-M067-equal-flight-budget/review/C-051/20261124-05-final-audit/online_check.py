import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import csv,gzip,json,math,hashlib
from pathlib import Path
import numpy as np
from scipy.stats import t,ttest_1samp
from scipy.spatial import cKDTree
root=Path('simulation/outputs/E1-035/20261124-10-main');data=Path('data/field_feasibility_v2');ap=root/'analysis_v2'
with (ap/'online_floor_sensitivity.csv').open(newline='') as f: rows=list(csv.DictReader(f))
with (ap/'online_floor_paired.csv').open(newline='') as f: pairs=list(csv.DictReader(f))
assert len(rows)==480
for r in pairs:
 n=int(r['nodes']);a,b=r['comparison'].split(' minus ');key=r['metric'];left={int(x['seed']):float(x[key]) for x in rows if int(x['nodes'])==n and x['policy']==a and x[key]};right={int(x['seed']):float(x[key]) for x in rows if int(x['nodes'])==n and x['policy']==b and x[key]};d=np.array([left[s]-right[s] for s in sorted(left.keys()&right.keys())]);mean=d.mean();sd=d.std(ddof=1);margin=t.ppf(.975,len(d)-1)*sd/math.sqrt(len(d))
 assert len(d)==int(r['seed_count'])
 for k,v in [('mean_difference',mean),('sd_difference',sd),('ci95_low',mean-margin),('ci95_high',mean+margin)]:assert np.isclose(float(r[k]),v,atol=1e-8),(r,k,v)
 if sd>0:assert np.isclose(float(r['paired_t_p']),ttest_1samp(d,0).pvalue,atol=1e-10)
sc=np.array([100.,100.,30.,120.]);results=[]
for n in (5,30):
 sp=root/f'n{n:02}'/'seed-2000';blind=json.loads((sp/'common_unvisited_points.json').read_text());q=np.array([[x,y,h,570.] for x,y,h,_ in blind]);truth=np.array([np.load(data/f'dynamic_h{int(h)}m_f64.npy',mmap_mode='r')[int(x/5),int(y/5),570] for x,y,h,_ in blind]);mask=truth!=-240.96910013008056
 for pol in ('A','B','C','D','D_degraded'):
  with gzip.open(sp/pol/'mission.json.gz','rt') as f:run=json.load(f)
  errs=[]
  for node in range(n):
   d=next(x for x in run['decisions'] if x['node_id']==node and x['step']==19);ids=set(d['visible_sample_ids']);samples=[x for x in run['samples'] if x['sample_id'] in ids and x['t_s']<=570];x=np.array([[s['x_m'],s['y_m'],s['h_m'],s['t_s']] for s in samples]);y=np.array([s['value_dbm'] for s in samples]);near=cKDTree(x/sc).query(q/sc,k=min(32,len(x)))[1]
   if near.ndim==1:near=near[:,None]
   pred=[]
   for point,idx in zip(q,near):
    a=x[idx];k=100*np.exp(-.5*np.sum(((a[:,None]-a[None,:])/sc)**2,axis=2))+4*np.eye(len(a));v=100*np.exp(-.5*np.sum(((a-point)/sc)**2,axis=1));pred.append(-65+v@np.linalg.solve(k,y[idx]+65))
   e=np.array(pred)-truth;errs.append([np.sqrt(np.mean(e**2)),np.sqrt(np.mean(e[mask]**2))])
  raw,filtered=np.mean(errs,axis=0);r=next(x for x in rows if int(x['nodes'])==n and x['seed']=='2000' and x['policy']==pol)
  assert np.isclose(raw,float(r['raw_online_mean_rmse_db']),atol=1e-8) and np.isclose(filtered,float(r['masked_online_mean_rmse_db']),atol=1e-8)
  results.append({'nodes':n,'policy':pol,'seed':2000,'raw':raw,'masked':filtered,'support':int(mask.sum())})
out={'paired_rows_verified':len(pairs),'independent_reconstruction':results,'limits':'fixed seed 2000 across 2 scales; all paired stats from saved per-seed table'}
Path('simulation/outputs/C-051/20261124-05-final-audit/online_result.json').write_text(json.dumps(out,indent=2),encoding='utf8');print('online paired rows',len(pairs),'representative online scores',len(results))
