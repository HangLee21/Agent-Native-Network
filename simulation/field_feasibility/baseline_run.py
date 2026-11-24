"""Controlled local IDW, ordinary kriging and GPR comparison on audited V2.

Target points are held out spatially. Temporal mode trains on the same spatial
sample positions 10 seconds earlier; no future data enters the predictor.
"""
import argparse,csv,json,os,pathlib,sys,time
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')
os.environ.setdefault('MKL_NUM_THREADS','1')
os.environ.setdefault('OMP_NUM_THREADS','1')
import numpy as np
from scipy.spatial import cKDTree
from scipy.linalg import cho_factor,cho_solve

ROOT=pathlib.Path(__file__).resolve().parents[2]

def predictions(train_xy,train_y,test_xy,k=16,length_m=75.0,signal_var=400.0,noise_var=4.0):
    tree=cKDTree(train_xy);_,indices=tree.query(test_xy,k=k)
    pred=np.empty((len(test_xy),3));variances=np.empty(len(test_xy))
    for i,ids in enumerate(indices):
        coords=train_xy[ids];values=train_y[ids];distance=np.linalg.norm(coords-test_xy[i],axis=1)
        weights=1/np.maximum(distance,1e-9)**2;pred[i,0]=weights@values/weights.sum()
        pair=np.linalg.norm(coords[:,None,:]-coords[None,:,:],axis=2)
        cov=signal_var*np.exp(-pair/length_m)+np.eye(k)*noise_var
        cross=signal_var*np.exp(-distance/length_m)
        factor=cho_factor(cov,lower=True,check_finite=False)
        solved=cho_solve(factor,np.column_stack((cross,np.ones(k))),check_finite=False)
        ck,one=solved[:,0],solved[:,1];ordinary=ck+one*((1-ck.sum())/one.sum())
        pred[i,1]=ordinary@values
        center=values.mean();pred[i,2]=center+ck@(values-center)
        variances[i]=max(0.0,signal_var-cross@ck)
    return pred,variances

def run(out,pilot):
    root=ROOT/'data/field_feasibility_v2';out.mkdir(parents=True,exist_ok=False)
    heights=[50] if pilot else [2,25,50,80];times=[99] if pilot else [99,299,599]
    rates=[.01,.05] if pilot else [.01,.02,.05,.10,.20];n_test=16 if pilot else 128
    records=[];start=time.time();seed=20261124
    with (out/'scores.csv').open('w',newline='',encoding='utf8') as f:
        writer=csv.DictWriter(f,fieldnames=['height_m','target_t','train_t','kind','rate','n_train','n_test','method','mae','rmse','p95_abs','mean_predictive_variance']);writer.writeheader()
        for h in heights:
            a=np.load(root/f'dynamic_h{h}m_f64.npy',mmap_mode='r')
            for t in times:
                rng=np.random.default_rng(seed+h*1000+t);order=rng.permutation(250*250);test=order[:n_test];pool=order[n_test:];test_xy=np.column_stack((test//250,test%250))*5.0;target=a[test//250,test%250,t]
                for rate in rates:
                    n=int(250*250*rate);train=pool[:n];assert len(set(test)&set(train))==0
                    xy=np.column_stack((train//250,train%250))*5.0
                    for kind,train_t in [('spatial',t),('temporal',t-10)]:
                        values=a[train//250,train%250,train_t];pred,var=predictions(xy,values,test_xy)
                        for j,name in enumerate(('idw','ordinary_kriging','gpr')):
                            err=pred[:,j]-target;row=dict(height_m=h,target_t=t,train_t=train_t,kind=kind,rate=rate,n_train=n,n_test=n_test,method=name,mae=float(np.abs(err).mean()),rmse=float(np.sqrt(np.mean(err**2))),p95_abs=float(np.percentile(np.abs(err),95)),mean_predictive_variance=float(var.mean()) if name=='gpr' else '')
                            assert np.isfinite([row['mae'],row['rmse'],row['p95_abs']]).all() and (var>=0).all();writer.writerow(row);records.append(row)
                    f.flush()
                print('completed height',h,'time',t,flush=True)
    manifest={'task_id':'E2-044','run_id':out.name,'started_at_epoch':start,'finished_at_epoch':time.time(),'seed':seed,'heights':heights,'relative_target_seconds':times,'training_offsets':{'spatial':0,'temporal':-10},'test_points_per_height_time':n_test,'sample_rates':rates,'rate_denominator':62500,'test_holdout_excluded_from_training':True,'local_neighbors':16,'covariance':'400 exp(-distance_m/75), independent noise variance 4; GP local sample mean','missing_policy':'all raw finite values included; repeated -240.969 minimum unclassified','source_doi':'10.17632/bn6n2639xh.2','data_ready':str(root/'data_ready.json'),'scores_rows':len(records),'limitations':['single deterministic split per height/time, not multi-seed uncertainty','temporal experiment compares against held-out positions 10 seconds later','sampled test points, not full-grid metric']}
    (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);p.add_argument('--pilot',action='store_true');args=p.parse_args();run(args.out,args.pilot)
