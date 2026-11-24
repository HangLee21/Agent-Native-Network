"""E1-034 deterministic offline experiment; protocol must already exist on disk."""
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path

os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import numpy as np
import scipy
from scipy.io import loadmat
from scipy.linalg import cho_factor, cho_solve
from scipy.spatial import cKDTree

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def savejson(p,v):
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def csvwrite(p,rows):
    if rows:
        with p.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)

def kernel(a,b):
    delta=(a[:,None,:]-b[None,:,:])/np.array([150.,150.,20.])
    return 100*np.exp(-.5*np.sum(delta*delta,axis=2))

def predict(history,query):
    if not history: return np.full(len(query),-65.),np.full(len(query),10.)
    x=np.array([[s['x']*5,s['y']*5,s['height_m']] for s in history]); y=np.array([s['dbm'] for s in history])
    k=kernel(x,x); k.flat[::len(k)+1]+=1
    c=cho_factor(k,lower=True,check_finite=False); q=kernel(x,query)
    mu=-65+q.T@cho_solve(c,y+65,check_finite=False)
    sd=np.sqrt(np.maximum(100-np.sum(q*cho_solve(c,q,check_finite=False),axis=0),0))
    return mu,sd

def blind(x,y,c):
    return (((x-(c[0]-30))//5+2*((y-(c[1]-30))//5))%5)==0

def candidates(c,anchor,round_y,layer,valid,vectors):
    cy=c[1]+round_y; out=[]
    for idx,(dx,dy) in enumerate(vectors):
        points=[]
        for t in range(-10,11):
            x=anchor[0]+round(dx*t/10); y=cy+round(dy*t/10)
            p=(x,y)
            if not (c[0]-30<=x<=c[0]+30 and c[1]-30<=y<=c[1]+30): continue
            if p not in points and valid[layer,x,y] and not blind(x,y,c): points.append(p)
        if len(points)<8: continue
        # Strictly increasing indexes whenever there are at least eight candidates.
        indices=np.rint(np.linspace(0,len(points)-1,8)).astype(int)
        out.append({'id':idx,'center':[anchor[0],cy],'vector':[dx,dy],
                    'eligible_count':len(points),'points':[points[i] for i in indices]})
    return out

def choose(opts,history,height):
    scores={}
    for option in opts:
        q=np.array([[x*5,y*5,height] for x,y in option['points']],dtype=float)
        mu,sd=predict(history,q)
        scores[str(option['id'])]=float(np.mean(sd+12*np.exp(-.5*((mu+75)/np.sqrt(sd**2+4))**2)))
    best=min(opts,key=lambda v:(-scores[str(v['id'])],v['id']))
    return best,scores

def boundary(mask,cl,height):
    result=[]
    for axis in (0,1):
        a=[slice(None),slice(None)]; b=[slice(None),slice(None)]
        a[axis]=slice(None,-1); b[axis]=slice(1,None); a,b=tuple(a),tuple(b)
        for x,y in np.argwhere(mask[a]&mask[b]&(cl[a]!=cl[b])):
            result.append([5*(x+.5*(axis==0)),5*(y+.5*(axis==1)),height])
    return result

def evaluate(c,field,valid,samples):
    xmin,ymin=c[0]-30,c[1]-30
    xs=slice(xmin,xmin+61); ys=slice(ymin,ymin+61)
    gx,gy=np.indices((61,61)); hold=((gx//5+2*(gy//5))%5)==0
    vm=valid[:,xs,ys]; mask=vm&hold[None,:,:]; pts=np.argwhere(mask)
    if not len(pts): raise RuntimeError('No valid blind points in fixed region')
    query=np.column_stack(((pts[:,1]+xmin)*5,(pts[:,2]+ymin)*5,np.array([20,30,40])[pts[:,0]]))
    pred=np.empty(len(pts))
    for start in range(0,len(pts),1000): pred[start:start+1000]=predict(samples,query[start:start+1000])[0]
    truthfield=field[:,xs,ys]; actual=truthfield[tuple(pts.T)]; weak=actual< -75; estimated=pred < -75
    tpden=int(weak.sum()); negden=int((~weak).sum()); fn=int((weak&~estimated).sum()); fp=int((~weak&estimated).sum())
    pg=np.zeros_like(vm,dtype=bool); pg[tuple(pts.T)]=estimated; tg=truthfield< -75
    tb=[]; pb=[]
    for i,h in enumerate([20,30,40]): tb+=boundary(mask[i],tg[i],h); pb+=boundary(mask[i],pg[i],h)
    bd=None
    if tb and pb:
        aa=np.array(tb); bb=np.array(pb)
        bd=float((cKDTree(aa).query(bb)[0].mean()+cKDTree(bb).query(aa)[0].mean())/2)
    valid_count=int(vm.sum()); blind_count=int(mask.sum())
    cover_total=cover_num=blind_cover=0; stripe=[]
    for i in range(3):
        smp=np.array([[s['x'],s['y']] for s in samples if s['aircraft']==i])
        coords=np.argwhere(vm[i]); xy=coords+np.array([xmin,ymin]); distances=cKDTree(smp).query(xy)[0]*5
        cover_num+=int((distances<=25).sum()); cover_total+=len(xy)
        blind_cover+=int(((distances<=25)&hold[coords[:,0],coords[:,1]]).sum())
        # Disjoint 20/20/21 index stripes, matching the allocation at shared boundaries.
        limits=[(0,20),(20,40),(40,61)]; lo,hi=limits[i]
        assigned=(coords[:,0]>=lo)&(coords[:,0]<hi)
        stripe.append({'aircraft':i,'numerator':int(((distances<=25)&assigned).sum()),'denominator':int(assigned.sum())})
    return {'valid_count':valid_count,'blind_count':blind_count,'blind_fraction_valid':blind_count/valid_count,
            'weak_count':tpden,'weak_fraction_blind':tpden/blind_count,'fn':fn,'fn_denominator':tpden,
            'fnr':fn/tpden if tpden else None,'fp':fp,'fp_denominator':negden,'fpr':fp/negden if negden else None,
            'rmse_db':float(np.sqrt(np.mean((actual-pred)**2))),'boundary_symmetric_distance_m':bd,
            'true_boundary_edge_count':len(tb),'pred_boundary_edge_count':len(pb),
            'coverage25_valid_numerator':cover_num,'coverage25_valid_denominator':cover_total,
            'coverage25_valid_fraction':cover_num/cover_total,'coverage25_blind_numerator':blind_cover,
            'coverage25_blind_denominator':blind_count,'coverage25_blind_fraction':blind_cover/blind_count,
            'coverage25_assigned_stripes':stripe}

def run_one(group,policy,c,field,valid,opts_by_round,cfg,out):
    folder=out/f'region-{group+1:02d}'/policy; folder.mkdir(parents=True,exist_ok=False)
    anchors=[(c[0]+dx,c[1]) for dx in cfg['stripe_anchor_offsets_x']]
    allsamples=[]; decisions=[]; trajectories=[]
    def waypoint(i,r,label,x,y):
        trajectories.append({'aircraft':i,'round':r,'label':label,'x':x,'y':y,'height_m':cfg['heights_m'][i]})
    for i,a in enumerate(anchors): waypoint(i,-1,'anchor',*a)
    for r,ry in enumerate(cfg['round_offsets_y']):
        selected=[]
        for i in range(3):
            local=[s for s in allsamples if s['aircraft']==i]
            timely=[s for s in allsamples if s['aircraft']==i or s['round']<=r-1]
            delayed=[s for s in allsamples if s['aircraft']==i or s['round']<=r-2]
            views={'local':local,'delayed':delayed,'timely':timely}; chosen={}; scores={}
            for name,history in views.items(): chosen[name],scores[name]=choose(opts_by_round[r][i],history,cfg['heights_m'][i])
            if policy=='partition': option=next(o for o in opts_by_round[r][i] if o['id']==0)
            else: option=chosen[policy]
            selected.append(option)
            def detail(history):
                ext=[s for s in history if s['aircraft']!=i]
                return {'sample_ids':[s['sample_id'] for s in history], 'external_count':len(ext),
                        'external_age_rounds':[r-1-s['round'] for s in ext]}
            decisions.append({'round':r,'aircraft':i,'selected_id':option['id'],
                              'counterfactual_ids':{k:v['id'] for k,v in chosen.items()},
                              'scores':scores,'views':{k:detail(v) for k,v in views.items()},
                              'options':opts_by_round[r][i]})
        # Every observation is created only after all aircraft have selected the round.
        for i,option in enumerate(selected):
            x,y=option['center']; dx,dy=option['vector']
            for label,xx,yy in [('transfer',x,y),('line_start',x-dx,y-dy),('line_end',x+dx,y+dy),('line_return',x,y)]:
                waypoint(i,r,label,xx,yy)
            for j,(xx,yy) in enumerate(option['points']):
                assert valid[i,xx,yy] and not blind(xx,yy,c)
                allsamples.append({'sample_id':f'r{r}-a{i}-p{j}','aircraft':i,'round':r,'order':j,
                                   'x':xx,'y':yy,'height_m':cfg['heights_m'][i],'dbm':float(field[i,xx,yy])})
    for i,a in enumerate(anchors): waypoint(i,4,'home',*a)
    distances=[]
    for i in range(3):
        pts=[(p['x'],p['y']) for p in trajectories if p['aircraft']==i]
        distances.append(sum(math.hypot(b[0]-a[0],b[1]-a[1])*5 for a,b in zip(pts,pts[1:])))
    m=evaluate(c,field,valid,allsamples)
    m.update({'region':group+1,'policy':policy,'observation_count':len(allsamples),
              'unique_locations':len({(s['height_m'],s['x'],s['y']) for s in allsamples}),
              'unique_weak_observations':len({(s['height_m'],s['x'],s['y']) for s in allsamples if s['dbm']< -75}),
              'travel_m_per_aircraft':distances,'travel_m_total':sum(distances)})
    savejson(folder/'metrics.json',m); savejson(folder/'decisions.json',decisions)
    csvwrite(folder/'samples.csv',allsamples); csvwrite(folder/'trajectory.csv',trajectories)
    return m

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); source=Path(args.source).resolve(); out=Path(args.out).resolve()
    config_path=out/'config.json'; protocol=out/'PROTOCOL.md'
    if not config_path.is_file() or not protocol.is_file(): raise RuntimeError('Pre-registered protocol and config required')
    if (out/'RUN_MANIFEST.json').exists() or any(out.glob('region-*')): raise RuntimeError('Output has prior execution; use a fresh pre-registered output')
    cfg=json.loads(config_path.read_text(encoding='utf8')); started=datetime.now().astimezone().isoformat()
    files=[source/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat' for h in cfg['heights_m']]
    # Protocol and configuration must already have been persisted before this read.
    source_hashes={p.name:sha(p) for p in files}
    field=np.stack([loadmat(p)['rem'].astype(float) for p in files]); assert field.shape==(3,250,250)
    valid=np.isfinite(field)&(field> -250)
    summaries=[]; skipped=[]
    for g,c in enumerate(cfg['centers_index']):
        anchors=[(c[0]+dx,c[1]) for dx in cfg['stripe_anchor_offsets_x']]
        options=[[candidates(c,anchors[i],ry,i,valid,cfg['line_vectors_grid']) for i in range(3)] for ry in cfg['round_offsets_y']]
        failures=[{'round':r,'aircraft':i,'reason':'fixed horizontal unavailable'} for r in range(4) for i in range(3) if not any(v['id']==0 for v in options[r][i])]
        if failures:
            skipped.append({'region':g+1,'failures':failures}); print('Skipped region',g+1,failures,flush=True); continue
        for policy in cfg['policies']:
            print('Running region',g+1,policy,flush=True)
            summaries.append(run_one(g,policy,c,field,valid,options,cfg,out))
    simple=[{k:v for k,v in m.items() if k not in ['coverage25_assigned_stripes','travel_m_per_aircraft']} for m in summaries]
    csvwrite(out/'summary.csv',simple)
    differences=[]
    for g in range(1,5):
        relevant=[m for m in summaries if m['region']==g]
        if len(relevant)!=4: continue
        for other in ['partition','local','delayed']:
            a=next(m for m in relevant if m['policy']=='timely'); b=next(m for m in relevant if m['policy']==other)
            row={'region':g,'comparison':'timely_minus_'+other}
            for key in ['fn','fnr','fp','fpr','rmse_db','boundary_symmetric_distance_m','unique_locations','coverage25_valid_fraction']:
                row[key]=None if a[key] is None or b[key] is None else a[key]-b[key]
            differences.append(row)
    csvwrite(out/'paired_differences.csv',differences); savejson(out/'skipped_regions.json',skipped)
    savejson(out/'RUN_MANIFEST.json',{'template_only':False,'task_id':'E1-034','run_id':out.name,
        'started_at':started,'finished_at':datetime.now().astimezone().isoformat(),'timezone':'Asia/Shanghai',
        'worktree':str(Path.cwd()),'git_commit':subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip(),
        'dirty_files_sha256':{str(Path(__file__).resolve()):sha(__file__),str(config_path):sha(config_path),str(protocol):sha(protocol)},
        'command':f'python simulation/field_reconstruction/necessity/run.py --source "{source}" --out "{out}"',
        'python_executable':sys.executable,'dependency_snapshot':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
        'upstream_commit':'7614b7a5fde3035a7f10a01714a6fdcced135080','data_and_weights_sha256':source_hashes,
        'config_file':str(config_path),'seeds':[],'budget':{'official_max':16,'official_completed':len(summaries),'smoke':0},
        'output_directory':str(out),'process_id':os.getpid(),'exit_code':0,'status':'completed' if not skipped else 'completed_with_skips',
        'limitations':['static RT field, not real RF','-250 value semantics unknown; assumed mask known','virtual paths and no obstacle or safety validation','ideal timely/delayed message visibility, no actual network','one physical environment, four areas','evaluation boundary only on within-blind adjacent grid edges'],
        'review_reference':'coordination/tasks/E1-034.md'})
    print('Completed',len(summaries),'runs; skipped regions:',len(skipped),flush=True)

if __name__=='__main__': main()
