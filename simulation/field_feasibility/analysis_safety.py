"""Recompute point-node continuous minimum separation for all saved runs."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import numpy as np


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--analysis',default='analysis_v2'); args=ap.parse_args()
    root=Path(args.root); cfg=json.loads((root/'config_main.json').read_text(encoding='utf8')); rows=[]
    for n in cfg['node_counts']:
        ij=np.triu_indices(n,1)
        for seed in cfg['seeds']:
            for policy in cfg['policies']:
                path=root/f'n{n:02d}'/f'seed-{seed}'/policy/'mission.json.gz'
                with gzip.open(path,'rt',encoding='utf8') as f: mission=json.load(f)
                positions=np.array([[p['x_m'],p['y_m'],p['h_m']] for p in mission['trajectory']],float).reshape(-1,n,3)
                endpoints=np.concatenate((positions[1:],np.array(mission['final_positions'])[None,:,:]),axis=0)
                rel=positions[:,ij[0],:]-positions[:,ij[1],:]
                vel=(endpoints-positions)[:,ij[0],:]-(endpoints-positions)[:,ij[1],:]
                vv=np.einsum('ijk,ijk->ij',vel,vel); dot=np.einsum('ijk,ijk->ij',rel,vel)
                t=np.clip(np.divide(-dot,vv,out=np.zeros_like(dot),where=vv>0),0,1)
                ds=np.linalg.norm(rel+t[:,:,None]*vel,axis=2)
                rows.append({'nodes':n,'seed':seed,'policy':policy,'segments':len(positions),
                             'pair_intervals':int(ds.size),'min_continuous_separation_m':float(ds.min()),
                             'separation_violation_pair_intervals':int((ds<cfg['min_separation_m']-1e-8).sum()),
                             'point_collision_pair_intervals':int((ds<1e-8).sum()),
                             'safety_freeze_steps':sum(e['kind']=='SAFETY_FREEZE' for e in mission['events'])})
        print('checked N=',n,flush=True)
    target=root/args.analysis/'safety_all_runs.csv'
    with target.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print('checked runs',len(rows),'separation violations',sum(r['separation_violation_pair_intervals'] for r in rows),
          'point collisions',sum(r['point_collision_pair_intervals'] for r in rows))

if __name__=='__main__':main()
