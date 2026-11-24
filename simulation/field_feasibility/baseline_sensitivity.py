"""Offline sensitivity: hypothetically omit values <= -200 dBm, not a missing-data claim."""
import argparse,csv,json,pathlib,sys,time
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from simulation.field_feasibility.baseline_run import predictions

def run(out):
 out.mkdir(parents=True,exist_ok=False);start=time.time();fields=['height_m','target_t','train_t','kind','rate','n_train','n_test','method','mae','rmse','p95_abs']
 with (out/'scores.csv').open('w',newline='',encoding='utf8') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
  for h in (2,25,50,80):
   a=np.load(ROOT/f'data/field_feasibility_v2/dynamic_h{h}m_f64.npy',mmap_mode='r')
   for t in (99,299,599):
    rng=np.random.default_rng(20261124+h*1000+t);order=rng.permutation(62500);test=order[:128];pool=order[128:];target=a[test//250,test%250,t];keep=target>-200;test=test[keep];target=target[keep];test_xy=np.column_stack((test//250,test%250))*5.
    for kind,tt in [('spatial',t),('temporal',t-10)]:
     pool_values=a[pool//250,pool%250,tt];mask=pool_values>-200;eligible=pool[mask];values=pool_values[mask]
     for rate in (.01,.02,.05,.10,.20):
      n=int(62500*rate)
      if len(eligible)<n:raise ValueError('insufficient eligible training data')
      train=eligible[:n];xy=np.column_stack((train//250,train%250))*5.;pred,_=predictions(xy,values[:n],test_xy)
      for j,name in enumerate(('idw','ordinary_kriging','gpr')):
       err=pred[:,j]-target;writer.writerow(dict(height_m=h,target_t=t,train_t=tt,kind=kind,rate=rate,n_train=n,n_test=len(test),method=name,mae=float(np.abs(err).mean()),rmse=float(np.sqrt(np.mean(err**2))),p95_abs=float(np.percentile(np.abs(err),95))))
    print('completed',h,t,flush=True)
 (out/'RUN_MANIFEST.json').write_text(json.dumps({'task_id':'E2-044','run_id':out.name,'seed':20261124,'start_epoch':start,'end_epoch':time.time(),'hypothesis':'exclude raw values <= -200 dBm; threshold is a sensitivity assumption only, not established invalidity','train_filter':'only values observed at train_t; sample target count rate*62500','test_filter':'posthoc target truth excludes <=-200; held-out locations otherwise same as unfiltered experiment','rate_denominator':62500,'test_sample_count_before_filter':128,'source_doi':'10.17632/bn6n2639xh.2','limitations':['posthoc scoring subset; no claims for removed regions','not a sampling-policy run','single split per height/time']},indent=2),encoding='utf8')
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);args=p.parse_args();run(args.out)
