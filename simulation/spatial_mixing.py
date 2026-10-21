"""Prespecified spatial averaging sensitivity, not a sensor reproduction."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from simulation.route_pilot import episode, RouteConfig
from simulation.route_robustness import layouts, layout_for, write_csv
from simulation.feedback_audit import preplan, same_routes, score_plan
from simulation.validate_observation import prepare, patch_data, PATCHES, select_diverse


def block_average(patch, size):
    h,w,b=patch.shape
    if size<1 or h%size or w%size:
        raise ValueError('Block size must divide patch dimensions')
    avg=patch.reshape(h//size,size,w//size,size,b).mean(axis=(1,3))
    return np.repeat(np.repeat(avg,size,axis=0),size,axis=1)


def run(output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty')
    output.mkdir(parents=True,exist_ok=True)
    cube,response,qc=prepare(Path('data/cuprite/Cuprite_data_R188.mat'))
    dev,_,_=patch_data(cube,PATCHES['development']); dr=dev@response
    initial=dev[select_diverse(dr,dr.mean(axis=0,keepdims=True),4)]
    rows,details=[],[]
    for patch in ('A','B','C'):
        truth,evaluation,xy=patch_data(cube,PATCHES[patch]); y,x=PATCHES[patch]
        for scale in (1,2,4,8):
            averaged=block_average(cube[y:y+80,x:x+80],scale)@response
            remote,test,_=patch_data(averaged,(0,0))
            for axis,cut,reverse in layouts():
                name=f'{axis}-{cut}-'+('reverse' if reverse else 'forward')
                layout=layout_for(xy,axis,cut,reverse)
                for factor in (1.5,2.5):
                    cfg=RouteConfig(factor=factor)
                    fixed=preplan(remote,xy,initial@response,layout,cfg)
                    for noise in (0.,.002):
                        for seed in (range(1) if noise==0 else range(6)):
                            measured=np.maximum(truth+np.random.default_rng(seed).normal(0,noise,truth.shape),0)
                            runs={'preplanned':fixed}
                            for mode in ('static','local','ideal'):
                                _,runs[mode]=episode(remote,xy,initial,response,lambda s:measured[s],2,mode,cfg,layout=layout)
                            for mode,detail in runs.items():
                                for n in detail['nodes']:
                                    assert n['finish_time']<=n['budget']+1e-8
                                    np.testing.assert_allclose(n['path'][-1],layout[2][n['node']])
                                row=dict(patch=patch,scale=scale,layout=name,factor=factor,noise_std=noise,seed=seed,
                                         mode=mode,rmse=score_plan(detail,initial,measured,test,evaluation,response),
                                         samples=detail['samples'],same_as_preplan=same_routes(detail,fixed))
                                rows.append(row)
                                details.append(dict(**row,node_runs=detail['nodes'],sites=detail['sites']))
            print('Completed spatial',patch,scale,flush=True)
    write_csv(output/'metrics.csv',rows)
    (output/'episodes.json.gz').write_bytes(gzip.compress(json.dumps(details).encode(),mtime=0))
    groups={}
    for r in rows:
        key=tuple(r[k] for k in ('patch','scale','layout','factor','noise_std'))
        groups.setdefault(key,{})[(r['mode'],r['seed'])]=r
    paired=[]
    for (patch,scale,layout,factor,noise),group in groups.items():
        seeds=range(1) if noise==0 else range(6)
        for baseline in ('local','static','preplanned'):
            values=[100*(group[baseline,s]['rmse']-group['ideal',s]['rmse'])/group[baseline,s]['rmse'] for s in seeds]
            paired.append(dict(patch=patch,scale=scale,layout=layout,factor=factor,noise_std=noise,baseline=baseline,
                               mean_pct=float(np.mean(values))))
    write_csv(output/'layout_paired.csv',paired)
    summary=[]
    for patch in ('A','B','C'):
        for scale in (1,2,4,8):
            for factor in (1.5,2.5):
                for noise in (0.,.002):
                    group=[r for r in paired if (r['patch'],r['scale'],r['factor'],r['noise_std'])==(patch,scale,factor,noise)]
                    together={r['layout']:[] for r in group}
                    for r in group:together[r['layout']].append(r['mean_pct'])
                    for baseline in ('local','static','preplanned'):
                        vals=[r['mean_pct'] for r in group if r['baseline']==baseline]
                        summary.append(dict(patch=patch,scale=scale,factor=factor,noise_std=noise,baseline=baseline,
                                            mean_pct=float(np.mean(vals)),min_pct=min(vals),max_pct=max(vals),
                                            positive_layouts=sum(v>1e-8 for v in vals),
                                            layouts_better_than_all=sum(min(v)>1e-8 for v in together.values())))
    write_csv(output/'summary.csv',summary)
    sources=['simulation/spatial_mixing.py','simulation/feedback_audit.py','simulation/route_pilot.py',
             'simulation/route_robustness.py','simulation/validate_observation.py','simulation/SPATIAL_MIXING_PROTOCOL.md']
    metadata=dict(qc=qc,records=len(rows),scales=[1,2,4,8],noiseless_seeds=[0],noisy_seeds=list(range(6)),
                  source_sha256={s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources})
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
