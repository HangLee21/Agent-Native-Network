import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import csv, json, math, hashlib
from pathlib import Path
import numpy as np
from scipy.io import loadmat
from scipy.spatial import cKDTree

root=Path('simulation/outputs/E1-034/20261124-01-necessity')
source=Path('simulation/outputs/E1-033/20261124-01-pilot/source')
cfg=json.loads((root/'config.json').read_text(encoding='utf8'))
files=[source/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat' for h in (20,30,40)]
field=np.stack([loadmat(p)['rem'] for p in files]); valid=np.isfinite(field)&(field>-250)
gx,gy=np.indices((61,61)); blind=(gx//5+2*(gy//5))%5==0
out=[]
for folder in sorted(root.glob('region-*/*')):
    if not folder.is_dir(): continue
    region=int(folder.parent.name[-2:]); cx,cy=cfg['centers_index'][region-1]; x0,y0=cx-30,cy-30
    with (folder/'samples.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    with (folder/'trajectory.csv').open(newline='') as f: trajectory=list(csv.DictReader(f))
    ds=json.loads((folder/'decisions.json').read_text(encoding='utf8')); m=json.loads((folder/'metrics.json').read_text(encoding='utf8'))
    assert len(rows)==96 and len(ds)==12
    xyz=np.array([[int(s['x'])*5,int(s['y'])*5,int(s['height_m'])] for s in rows]); vals=np.array([float(s['dbm']) for s in rows])
    for s in rows:
        a,x,y,r=map(int,(s['aircraft'],s['x'],s['y'],s['round']))
        assert valid[a,x,y] and not blind[x-x0,y-y0] and vals[rows.index(s)]==field[a,x,y]
    lengths=[]
    for a in range(3):
        p=[(int(t['x']),int(t['y'])) for t in trajectory if int(t['aircraft'])==a]
        lengths.append(sum(5*math.dist(u,v) for u,v in zip(p,p[1:])))
    assert np.allclose(lengths,m['travel_m_per_aircraft'])
    for d in ds:
        a,r=d['aircraft'],d['round']
        for view in ('local','delayed','timely'):
            expected=[s for s in rows if int(s['round'])<r and (int(s['aircraft'])==a or (view=='timely' and int(s['round'])<=r-1) or (view=='delayed' and int(s['round'])<=r-2))]
            assert d['views'][view]['sample_ids']==[s['sample_id'] for s in expected]
            assert d['views'][view]['external_age_rounds']==[r-1-int(s['round']) for s in expected if int(s['aircraft'])!=a]
    vm=valid[:,x0:x0+61,y0:y0+61]; mask=vm & blind[None,:,:]; idx=np.argwhere(mask)
    q=np.column_stack(((idx[:,1]+x0)*5,(idx[:,2]+y0)*5,np.array([20,30,40])[idx[:,0]]))
    scale=np.array([150.,150.,20.]); k=100*np.exp(-0.5*np.sum(((xyz[:,None,:]-xyz[None,:,:])/scale)**2,axis=2)); k+=np.eye(len(rows))
    cross=100*np.exp(-0.5*np.sum(((q[:,None,:]-xyz[None,:,:])/scale)**2,axis=2))
    pred=-65+cross@np.linalg.solve(k,vals+65); truth=field[:,x0:x0+61,y0:y0+61][tuple(idx.T)]
    weak=truth < -75; guessed=pred < -75
    fn=int((weak & ~guessed).sum()); fp=int((~weak & guessed).sum()); rmse=float(np.sqrt(np.mean((truth-pred)**2)))
    cover=0; blindcover=0
    for a in range(3):
        coords=np.argwhere(vm[a]); positions=coords+np.array([x0,y0]); nearest=cKDTree(xyz[xyz[:,2]==(20+10*a),:2]/5).query(positions)[0]
        cover+=int((nearest<=5).sum()); blindcover+=int(((nearest<=5)&blind[coords[:,0],coords[:,1]]).sum())
    actual={'fn':fn,'fp':fp,'weak_count':int(weak.sum()),'blind_count':len(idx),'valid_count':int(vm.sum()),'rmse_db':rmse,'coverage25_valid_numerator':cover,'coverage25_blind_numerator':blindcover,'unique_locations':len(set(map(tuple,xyz))),'unique_weak_observations':len(set(map(tuple,xyz[vals < -75])))}
    for key,v in actual.items(): assert np.isclose(v,m[key],atol=1e-8), (folder,key,v,m[key])
    out.append({'region':region,'policy':folder.name,**actual,'travel_m_total':sum(lengths),'observation_count':len(rows),'local_vs_timely_counterfactual_changes':sum(d['counterfactual_ids']['local']!=d['counterfactual_ids']['timely'] for d in ds)})
with (root/'summary.csv').open(newline='') as f: summary=list(csv.DictReader(f))
with (root/'paired_differences.csv').open(newline='') as f: pairs=list(csv.DictReader(f))
for p in pairs:
    a=next(s for s in summary if s['region']==p['region'] and s['policy']=='timely')
    b=next(s for s in summary if s['region']==p['region'] and s['policy']==p['comparison'].replace('timely_minus_',''))
    for k in list(p)[2:]:
        assert (not p[k] and (not a[k] or not b[k])) or abs(float(p[k])-(float(a[k])-float(b[k])))<1e-9
totals={policy:{k:sum(int(s[k]) for s in summary if s['policy']==policy) for k in ('fn','fn_denominator','fp','fp_denominator')} for policy in cfg['policies']}
result={'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files},'runs':out,'paired_rows_verified':len(pairs),'pooled_counts_completed_regions':totals,'checks':'independent saved samples, trajectories, delayed/timely visibility, GP mean, FN/FP/RMSE, nearest-sample coverage; no strategy run; boundary metric not recomputed'}
Path('simulation/outputs/C-050/20261124-01-audit/result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
