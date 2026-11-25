"""Prespecified geometry sweep; no policy tuning or link impairment."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from simulation.route_pilot import RouteConfig, episode
from simulation.validate_observation import prepare, patch_data, PATCHES, select_diverse, reconstruct, rmse


def layout_for(xy, axis, cut, reverse):
    if axis not in ('x','y') or cut not in (30,40,50):
        raise ValueError('Unsupported prespecified layout')
    starts=[np.array([0.,0.]),np.array([79.,0.])]
    ends=[np.array([cut-1.,79.]),np.array([float(cut),79.])]
    dimension=0 if axis=='x' else 1
    regions=[np.flatnonzero(xy[:,dimension]<cut),np.flatnonzero(xy[:,dimension]>=cut)]
    if axis=='y':
        starts=[p[::-1].copy() for p in starts];ends=[p[::-1].copy() for p in ends]
    if reverse:starts,ends=ends,starts
    return regions,starts,ends


def layouts():
    return [(axis,cut,reverse) for axis in ('x','y') for cut in (30,40,50) for reverse in (False,True)]


def write_csv(path,rows):
    with path.open('w',newline='',encoding='utf8') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(output):
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be empty')
    output.mkdir(parents=True,exist_ok=True)
    cube,response,qc=prepare(Path('data/cuprite/Cuprite_data_R188.mat'))
    dev,_,_=patch_data(cube,PATCHES['development']);dr=dev@response
    initial=dev[select_diverse(dr,dr.mean(axis=0,keepdims=True),4)]
    rows=[];trajectories=[]
    for patch in ('A','B','C'):
        truth,evaluation,xy=patch_data(cube,PATCHES[patch]);remote=truth@response;test=evaluation@response
        for axis,cut,reverse in layouts():
            name=f'{axis}-{cut}-'+('reverse' if reverse else 'forward')
            layout=layout_for(xy,axis,cut,reverse)
            for factor in (1.5,2.5):
                for noise in (0.,.002):
                    for seed in range(12):
                        measured=np.maximum(truth+np.random.default_rng(seed).normal(0,noise,truth.shape),0)
                        for mode in ('static','local','ideal'):
                            library,detail=episode(remote,xy,initial,response,lambda s:measured[s],2,mode,
                                                   RouteConfig(factor=factor),layout=layout)
                            for n in detail['nodes']:
                                assert n['finish_time']<=n['budget']+1e-8
                                np.testing.assert_allclose(n['path'][-1],layout[2][n['node']])
                            row=dict(patch=patch,layout=name,factor=factor,noise_std=noise,seed=seed,mode=mode,
                                     rmse=rmse(reconstruct(test,library,response),evaluation),samples=detail['samples'],
                                     distance=sum(n['distance'] for n in detail['nodes']))
                            rows.append(row)
                            detail['node_runs']=detail.pop('nodes');detail.pop('events')
                            detail.update(row);trajectories.append(detail)
            print(patch,name,flush=True)
    write_csv(output/'metrics.csv',rows)
    (output/'episodes.json.gz').write_bytes(gzip.compress(json.dumps(trajectories).encode(),mtime=0))
    groups={}
    for r in rows:
        key=tuple(r[k] for k in ('patch','layout','factor','noise_std'))
        groups.setdefault(key,{})[(r['mode'],r['seed'])]=r
    paired=[]
    for (patch,layout,factor,noise),group in groups.items():
        a=np.array([group['ideal',s]['rmse'] for s in range(12)])
        improvements=[]
        for b in ('local','static'):
            base=np.array([group[b,s]['rmse'] for s in range(12)])
            values=100*(base-a)/base;improvements.append(values.mean())
            paired.append(dict(patch=patch,layout=layout,factor=factor,noise_std=noise,comparison='ideal vs '+b,
                               mean_improvement_pct=float(values.mean()),min_improvement_pct=float(values.min()),
                               max_improvement_pct=float(values.max()),seed_wins=int(np.sum(values>1e-8))))
    write_csv(output/'layout_paired.csv',paired)
    summary=[]
    for patch in ('A','B','C'):
        for factor in (1.5,2.5):
            for noise in (0.,.002):
                subset=[r for r in paired if (r['patch'],r['factor'],r['noise_std'])==(patch,factor,noise)]
                both={r['layout']:[] for r in subset}
                for r in subset:both[r['layout']].append(r['mean_improvement_pct'])
                for comparison in ('ideal vs local','ideal vs static'):
                    vals=np.array([r['mean_improvement_pct'] for r in subset if r['comparison']==comparison])
                    summary.append(dict(patch=patch,factor=factor,noise_std=noise,comparison=comparison,
                                        mean_pct=float(vals.mean()),median_pct=float(np.median(vals)),
                                        min_pct=float(vals.min()),max_pct=float(vals.max()),
                                        positive_layouts=int(np.sum(vals>1e-8)),
                                        layouts_better_than_both=sum(min(v)>1e-8 for v in both.values())))
    write_csv(output/'summary.csv',summary)
    # Ensure the original geometry reproduces all earlier science-policy results.
    oldpath=Path('simulation/results/2026-10-21-cuprite-route-v1/metrics.csv')
    with oldpath.open(encoding='utf8') as stream:old=list(csv.DictReader(stream))
    oldmap={(r['patch'],float(r['factor']),float(r['noise_std']),int(r['seed']),r['mode']):r
            for r in old if r['nodes']=='2' and r['mode']!='nearest'}
    matched=0
    for r in rows:
        if r['layout']=='x-40-forward':
            previous=oldmap[r['patch'],r['factor'],r['noise_std'],r['seed'],r['mode']]
            assert abs(r['rmse']-float(previous['rmse']))<1e-14
            assert r['samples']==int(previous['samples']);matched+=1
    metadata=dict(qc=qc,seeds=list(range(12)),layouts=layouts(),factors=[1.5,2.5],noise_std=[0,.002],
                  records=len(rows),matched_original_geometry=matched,
                  source_sha256={str(p).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [Path('simulation/route_robustness.py'),Path('simulation/route_pilot.py'),
                   Path('simulation/validate_observation.py'),Path('simulation/ROBUSTNESS_PROTOCOL.md')]},
                  caveat='Layouts and seeds are not independent geological sites. No wireless impairment.')
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    fig,axes=plt.subplots(1,3,figsize=(13,4),layout='constrained')
    for ax,patch in zip(axes,('A','B','C')):
        for factor,marker in ((1.5,'o'),(2.5,'x')):
            subset=[r for r in paired if r['patch']==patch and r['noise_std']==.002 and r['factor']==factor and r['comparison']=='ideal vs local']
            ax.plot(range(12),[r['mean_improvement_pct'] for r in subset],marker=marker,label=f'Budget {factor}')
        ax.axhline(0,color='black',linewidth=.8);ax.set_title('Patch '+patch)
        ax.set_xlabel('Prespecified layout index (see metadata)');ax.set_ylabel('Ideal vs local improvement (%)')
        ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Cuprite geometry sensitivity | positive = lower error with sharing')
    fig.savefig(output/'geometry_sensitivity.png',dpi=160);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
