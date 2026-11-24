"""E1-033: bounded, offline three-aircraft radio-map sampling pilot."""
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

os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import scipy
from scipy.io import loadmat
from scipy.linalg import cho_factor, cho_solve
from scipy.spatial import cKDTree

HEIGHTS = [20, 30, 40]
TAU = -75.0
PRIOR, SIGMA, NOISE = -65.0, 10.0, 1.0
LENGTHS = np.array([150., 150., 20.])
VECTORS = [(15,0),(12,9),(9,12),(0,15),(-9,12),(-12,9),
           (-15,0),(-12,-9),(-9,-12),(0,-15),(9,-12),(12,-9)]
OFFSETS = [(0,0),(12,0),(0,12),(12,12)]
BASES = [(100,100),(115,100),(105,115)]
POLICIES = ['partition', 'local', 'shared']

def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def xyz(x, y, h):
    return np.array([5.0*x, 5.0*y, float(h)])

def is_blind(x,y):
    return ((x//10 + 2*(y//10)) % 5) == 0

def kernel(a,b):
    delta = (a[:,None,:]-b[None,:,:])/LENGTHS
    return SIGMA**2*np.exp(-0.5*np.sum(delta*delta,axis=2))

def posterior(train, query):
    if not train:
        return np.full(len(query),PRIOR), np.full(len(query),SIGMA)
    x = np.array([s['xyz'] for s in train]); y = np.array([s['dbm'] for s in train])
    k = kernel(x,x); k.flat[::len(k)+1] += NOISE**2
    factor = cho_factor(k, lower=True, check_finite=False)
    q = kernel(x,query)
    mu = PRIOR + q.T @ cho_solve(factor, y-PRIOR, check_finite=False)
    variance = SIGMA**2-np.sum(q*cho_solve(factor,q,check_finite=False),axis=0)
    return mu, np.sqrt(np.maximum(variance,0.0))

def candidates(base, layer, valid):
    result=[]
    for idx,(dx,dy) in enumerate(VECTORS):
        points=[]
        for step in range(1,16):
            x=base[0]+round(dx*step/15); y=base[1]+round(dy*step/15)
            if (x,y) not in points and valid[layer,x,y] and not is_blind(x,y):
                points.append((x,y))
        if len(points)>=6:
            result.append({'id':idx,'endpoint':[base[0]+dx,base[1]+dy], 'points':points[:6]})
    if not result:
        raise RuntimeError(f'No valid candidate for {base}, layer {layer}')
    return result

def nearest_base(base, layer, valid):
    # Geometric and validity-only correction; no signal values are consulted.
    for radius in range(20):
        for dx in range(-radius,radius+1):
            for dy in range(-radius,radius+1):
                if abs(dx)+abs(dy)!=radius: continue
                x,y=base[0]+dx,base[1]+dy
                if valid[layer,x,y] and not is_blind(x,y): return (x,y)
    raise RuntimeError('no valid launch point')

def choose(cands, history, layer):
    scores=[]
    for c in cands:
        q=np.array([xyz(x,y,HEIGHTS[layer]) for x,y in c['points']])
        mu,sd=posterior(history,q)
        score=float(np.mean(sd+12*np.exp(-0.5*((mu-TAU)/np.sqrt(sd*sd+4))**2)))
        scores.append((score,c['id']))
    winner=max(scores,key=lambda z:(z[0],-z[1]))[1]
    return next(c for c in cands if c['id']==winner), {str(i):s for s,i in scores}

def fixed(cands, aircraft, rnd):
    # Three fixed angular sectors; within each sector use a repeated sweep.
    target=(aircraft*4+[0,1,2,3][rnd])%12
    return min(cands,key=lambda c:(min((c['id']-target)%12,(target-c['id'])%12),c['id']))

def boundary_points(mask, classes, height):
    # Edge midpoints only when BOTH cells belong to the common blind set.
    coords=[]
    for axis in (0,1):
        left=[slice(None),slice(None)]; right=[slice(None),slice(None)]
        left[axis]=slice(None,-1); right[axis]=slice(1,None)
        left,right=tuple(left),tuple(right)
        indices=np.argwhere(mask[left]&mask[right]&(classes[left]!=classes[right]))
        for x,y in indices:
            coords.append([5*(x+(axis==0)*0.5),5*(y+(axis==1)*0.5),height])
    return coords

def evaluate(field, valid, samples):
    gx,gy=np.indices(field.shape[1:]); blind=((gx//10+2*(gy//10))%5)==0
    masks=valid & blind[None,:,:]
    pts=np.argwhere(masks); query=np.column_stack((pts[:,1]*5,pts[:,2]*5,np.array(HEIGHTS)[pts[:,0]]))
    prediction=np.empty(len(pts))
    for begin in range(0,len(pts),1500):
        prediction[begin:begin+1500]=posterior(samples,query[begin:begin+1500])[0]
    actual=field[tuple(pts.T)]; truth=actual<TAU; estimated=prediction<TAU
    fn=int(np.sum(truth & ~estimated)); tpden=int(np.sum(truth))
    fp=int(np.sum(~truth & estimated)); negden=int(np.sum(~truth))
    pred_grid=np.zeros_like(valid,dtype=bool); pred_grid[tuple(pts.T)]=estimated
    true_grid=field<TAU
    tb=[]; pb=[]
    for layer,h in enumerate(HEIGHTS):
        tb.extend(boundary_points(masks[layer],true_grid[layer],h))
        pb.extend(boundary_points(masks[layer],pred_grid[layer],h))
    distance=None
    if tb and pb:
        tb=np.array(tb); pb=np.array(pb)
        distance=float((cKDTree(pb).query(tb)[0].mean()+cKDTree(tb).query(pb)[0].mean())/2)
    return {'blind_count':len(pts),'weak_count':tpden,'nonweak_count':negden,
            'fn':fn,'fn_denominator':tpden,'fnr':fn/tpden if tpden else None,
            'fp':fp,'fp_denominator':negden,'fpr':fp/negden if negden else None,
            'rmse_db':float(np.sqrt(np.mean((actual-prediction)**2))),
            'boundary_symmetric_distance_m':distance,'true_boundary_edge_count':len(tb),
            'pred_boundary_edge_count':len(pb),
            'boundary_support':'midpoints of horizontal grid edges with both endpoints in blind mask; 3-D Euclidean distance; null when either boundary is empty'}

def write_csv(path, rows):
    if not rows: return
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

def run(group,policy,field,valid,output):
    folder=output/f'group-{group+1:02d}'/policy; folder.mkdir(parents=True,exist_ok=False)
    offset=OFFSETS[group]
    bases=[nearest_base((b[0]+offset[0],b[1]+offset[1]),i,valid) for i,b in enumerate(BASES)]
    options=[candidates(base,i,valid) for i,base in enumerate(bases)]
    histories=[[] for _ in range(3)]; samples=[]; decisions=[]; routes=[]
    def take(i,x,y,rnd):
        assert not is_blind(x,y) and valid[i,x,y]
        s={'aircraft':i,'round':rnd,'x':x,'y':y,'height_m':HEIGHTS[i],
           'xyz':xyz(x,y,HEIGHTS[i]).tolist(),'dbm':float(field[i,x,y])}
        histories[i].append(s); samples.append(s)
    for i,(x,y) in enumerate(bases): take(i,x,y,-1)
    for rnd in range(4):
        # All choices are made before any observation from this round is added.
        picked=[]
        for i,base in enumerate(bases):
            local,local_scores=choose(options[i],histories[i],i)
            pool=list(samples)
            shared,shared_scores=choose(options[i],pool,i)
            selected=fixed(options[i],i,rnd) if policy=='partition' else (local if policy=='local' else shared)
            picked.append(selected)
            decisions.append({'round':rnd,'aircraft':i,'base':base,'selected':selected['id'],
                              'local_counterfactual':local['id'],'shared_counterfactual':shared['id'],
                              'changed_from_local':shared['id']!=local['id'],
                              'local_history_count':len(histories[i]),'pooled_history_count':len(pool),
                              'local_scores':local_scores,'shared_scores':shared_scores})
        for i,c in enumerate(picked):
            base=bases[i]; end=c['endpoint']
            routes.extend([{'round':rnd,'aircraft':i,'order':0,'x':base[0],'y':base[1], 'height_m':HEIGHTS[i]},
                           {'round':rnd,'aircraft':i,'order':1,'x':end[0],'y':end[1], 'height_m':HEIGHTS[i]},
                           {'round':rnd,'aircraft':i,'order':2,'x':base[0],'y':base[1], 'height_m':HEIGHTS[i]}])
            for x,y in c['points']: take(i,x,y,rnd)
    metrics=evaluate(field,valid,samples)
    metrics.update({'group':group+1,'policy':policy,'measurement_count':len(samples),
                    'unique_measurements':len({(s['height_m'],s['x'],s['y']) for s in samples}),
                    'travel_m_per_aircraft':[600.,600.,600.], 'travel_m_total':1800.,
                    'bases':bases,'candidate_count_per_aircraft':[len(c) for c in options]})
    (folder/'metrics.json').write_text(json.dumps(metrics,ensure_ascii=False,indent=2),encoding='utf8')
    (folder/'decisions.json').write_text(json.dumps(decisions,ensure_ascii=False,indent=2),encoding='utf8')
    write_csv(folder/'samples.csv',[{k:v for k,v in s.items() if k!='xyz'} for s in samples])
    write_csv(folder/'trajectory.csv',routes)
    return metrics, routes, decisions

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--source',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); source=Path(args.source).resolve(); out=Path(args.out).resolve()
    out.mkdir(parents=True,exist_ok=False)
    started=datetime.now().astimezone().isoformat(); files=[source/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat' for h in HEIGHTS]
    field=np.stack([loadmat(p)['rem'].astype(float) for p in files]); assert field.shape==(3,250,250)
    valid=np.isfinite(field)&(field>-250.)
    config={'threshold_dbm':TAU,'threshold_rationale':'fixed illustrative weak-signal threshold, declared before evaluating any values; not a receiver sensitivity claim',
            'domain':'250x250 cells, 5 m spacing; 20,30,40 m layers; no building geometry available',
            'unknown_value_assumption':'exclude values <= -250 dBm and nonfinite; semantics not established',
            'holdout':'((x//10 + 2*(y//10)) % 5)==0; excluded from every possible measurement',
            'policy':'synchronous rounds; local sees own past; shared sees all actual past; final all observations pooled',
            'sampling':'one initial point plus six grid-cell observations on each of four out-and-back rays per aircraft; along each continuous ray round sample positions to the nearest grid cell and use the cell value; this is a grid observation model, not a flown detour',
            'ray_vectors_grid':VECTORS,'group_offsets_grid':OFFSETS,'nominal_bases_grid':BASES,
            'kernel':'Gaussian process, fixed prior -65 dBm, signal std 10 dB, noise std 1 dB, length scales 150,150,20 m',
            'score':'mean posterior std + 12*exp(-0.5*((mean - threshold)/sqrt(std^2+4))^2)',
            'seed':'deterministic, no random draws','official_runs':12,'hardware':'none; offline CPU only'}
    (out/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf8')
    summaries=[]; allroutes={}; changed=[]
    for group in range(4):
        for policy in POLICIES:
            print(f'Running group {group+1} {policy}',flush=True)
            m,r,d=run(group,policy,field,valid,out); summaries.append(m); allroutes[(group,policy)]=r
            if policy=='shared':
                changed.extend([{'group':group+1,**e} for e in d if e['changed_from_local']])
    flat=[{k:v for k,v in m.items() if k not in ('bases','candidate_count_per_aircraft','travel_m_per_aircraft','boundary_support')} for m in summaries]
    write_csv(out/'summary.csv',flat)
    paired=[]
    for group in range(1,5):
        ref=next(x for x in summaries if x['group']==group and x['policy']=='partition')
        for policy in ('local','shared'):
            m=next(x for x in summaries if x['group']==group and x['policy']==policy)
            row={'group':group,'comparison':policy+'_minus_partition'}
            for key in ('fnr','fpr','rmse_db','boundary_symmetric_distance_m'):
                row[key]=None if m[key] is None or ref[key] is None else m[key]-ref[key]
            paired.append(row)
        a=next(x for x in summaries if x['group']==group and x['policy']=='shared')
        b=next(x for x in summaries if x['group']==group and x['policy']=='local')
        row={'group':group,'comparison':'shared_minus_local'}
        for key in ('fnr','fpr','rmse_db','boundary_symmetric_distance_m'):
            row[key]=None if a[key] is None or b[key] is None else a[key]-b[key]
        paired.append(row)
    write_csv(out/'paired_differences.csv',paired)
    (out/'changed_examples.json').write_text(json.dumps(changed,ensure_ascii=False,indent=2),encoding='utf8')
    # Visualization is post-hoc only; the underlay never enters the planners.
    fig,axes=plt.subplots(1,3,figsize=(15,5),sharex=True,sharey=True,constrained_layout=True)
    gx,gy=np.indices((250,250)); blind=((gx//10+2*(gy//10))%5)==0
    for ax,policy in zip(axes,POLICIES):
        ax.imshow((field[1]<TAU).T,origin='lower',cmap='Greys',alpha=.25,extent=(0,1250,0,1250))
        ax.contourf((gx*5).T,(gy*5).T,blind.T,levels=[.5,1.5],colors=['#dfbd48'],alpha=.18)
        rr=allroutes[(0,policy)]
        for i,color in enumerate(['#d62728','#1f77b4','#2ca02c']):
            for rnd in range(4):
                segment=[s for s in rr if s['aircraft']==i and s['round']==rnd]
                ax.plot([s['x']*5 for s in segment],[s['y']*5 for s in segment],color=color,alpha=.72,lw=1.5)
            base=segment[0]; ax.scatter(base['x']*5,base['y']*5,c=color,s=20,label=f'{HEIGHTS[i]} m')
        ax.set(title=policy,xlim=(350,800),ylim=(350,800),xlabel='x (m)',ylabel='y (m)'); ax.set_aspect('equal'); ax.legend()
    fig.suptitle('Group 1: paths; gold = blind blocks; grey = weak at 30 m (post-hoc truth)')
    fig.savefig(out/'paired_paths_group1.png',dpi=180); plt.close(fig)
    commit=subprocess.run(['git','rev-parse','HEAD'],capture_output=True,text=True).stdout.strip()
    manifest={'template_only':False,'task_id':'E1-033','run_id':out.parent.name,'started_at':started,
              'timezone':'Asia/Shanghai','worktree':str(Path.cwd()),'git_commit':commit,
              'dirty_files_sha256':{str(Path(__file__).resolve()):digest(__file__)},
              'command':f'python simulation/field_reconstruction/pilot.py --source "{source}" --out "{out}"',
              'python_executable':sys.executable,'dependency_snapshot':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__,'matplotlib':matplotlib.__version__},
              'upstream_commit':'7614b7a5fde3035a7f10a01714a6fdcced135080',
              'data_and_weights_sha256':{p.name:digest(p) for p in files},'config_file':str(out/'config.json'),
              'source_urls':[f'https://github.com/qiuming-nuaa/Dataset-for-RSSI-radio-map-under-urban-scenario/blob/7614b7a5fde3035a7f10a01714a6fdcced135080/{p.name}' for p in files],
              'seeds':[],'budget':{'official_runs':12,'smoke_groups':0,'aircraft':3,'rounds':4,'observations_per_run':75,'travel_m_per_run':1800},
              'output_directory':str(out),'process_id':os.getpid(),'finished_at':datetime.now().astimezone().isoformat(),
              'exit_code':0,'status':'completed','limitations':['simulated static field; ideal zero-noise observations','unknown -250 dBm values conservatively masked','virtual routes: obstacle safety and physical flyability not established','ideal instantaneous information exchange, no communication protocol or RF link validation','boundary is computed only on blind-cell adjacency edges'],
              'review_reference':'coordination/tasks/E1-033.md'}
    (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    print('Completed:',out,'changed decisions:',len(changed),flush=True)

if __name__=='__main__': main()
