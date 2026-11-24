"""Diagnostic figures from frozen M-067 outputs, no policy re-execution."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from data_v2 import FieldV2
from analysis import reconstruct


def read(path):
    with gzip.open(str(path)+'.gz','rt',encoding='utf8') as f: return json.load(f)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--data',required=True); ap.add_argument('--analysis',default='analysis')
    args=ap.parse_args(); root=Path(args.root); out=root/args.analysis; out.mkdir(exist_ok=True)
    with (out/'summary.csv').open(encoding='utf8',newline='') as f: rows=list(csv.DictReader(f))
    fig,axes=plt.subplots(1,3,figsize=(14,4),constrained_layout=True)
    for ax,metric,title in zip(axes,['offline_rmse_db','masked_blind_rmse_db','sent_bytes'],
                               ['Raw blind RMSE','Floor-excluded blind RMSE','Transmitted bytes']):
        for policy in ['A','B','C','D','D_degraded','E']:
            data=sorted([r for r in rows if r['metric']==metric and r['policy']==policy],key=lambda x:int(x['nodes']))
            xx=np.array([int(r['nodes']) for r in data]); yy=np.array([float(r['mean']) for r in data])
            low=np.array([float(r['ci95_low']) for r in data]); high=np.array([float(r['ci95_high']) for r in data])
            ax.errorbar(xx,yy,yerr=[yy-low,high-yy],marker='o',capsize=2,label=policy)
        ax.set(title=title,xlabel='Nodes',ylabel='Bytes' if metric=='sent_bytes' else 'RMSE (dB)',xticks=[5,10,20,30]); ax.grid(alpha=.2)
    axes[1].legend(fontsize=8,ncol=2); fig.suptitle('20 paired seeds; error bars are seed-level 95% t intervals')
    fig.savefig(out/'scale_error_and_bytes.png',dpi=170); plt.close(fig)
    run=root/'n30'/'seed-2000'/'D'; mission=read(run/'mission.json'); net=read(run/'network.json')
    fig,axes=plt.subplots(1,3,figsize=(15,5),constrained_layout=True)
    for node in range(30):
        track=[p for p in mission['trajectory'] if p['node_id']==node]
        axes[0].plot([p['x_m'] for p in track],[p['y_m'] for p in track],lw=.7,alpha=.6)
    axes[0].set_title('D: simulated XY trajectories')
    for h in [2,25,50,80]:
        s=[p for p in mission['samples'] if p['h_m']==h]
        axes[1].scatter([p['x_m'] for p in s],[p['y_m'] for p in s],s=5,alpha=.45,label=f'{h} m')
    axes[1].set_title('D: recorded sample positions'); axes[1].legend(fontsize=7)
    graph=net['topologies'][-1]; positions=graph['positions']
    for a,b in graph['edges']:
        p=positions[str(a)]; q=positions[str(b)]
        axes[2].plot([p[0],q[0]],[p[1],q[1]],color='gray',alpha=.13,lw=.6)
    for node,p in positions.items(): axes[2].scatter(p[0],p[1],s=16,c={2:'#b22',25:'#28a',50:'#292',80:'#c82'}[int(p[2])])
    axes[2].set_title('D: structural graph at 600 s')
    for ax in axes: ax.set(xlim=(375,875),ylim=(375,875),xlabel='x (m)',ylabel='y (m)'); ax.set_aspect('equal')
    fig.suptitle('Representative 30-node seed 2000; abstract grid, no obstacle geometry')
    fig.savefig(out/'example_paths_samples_topology.png',dpi=170); plt.close(fig)
    # This dense map is post-hoc visual diagnosis, not the held-out scoring set.
    field=FieldV2(args.data); grid=np.arange(375,876,25); queries=np.array([[x,y,50,570] for x in grid for y in grid])
    actual=np.array([field.query(*q) for q in queries]); observed=[s for s in mission['samples'] if s['t_s']<=570 and s['value_dbm'] is not None]
    predicted,_=reconstruct(observed,queries); images=[actual,predicted,np.abs(predicted-actual)]
    fig,axes=plt.subplots(1,3,figsize=(14,4.5),constrained_layout=True)
    for idx,(ax,data,title) in enumerate(zip(axes,images,['V2 field (50 m, 570 s)','Offline reconstructed mean','Absolute error (dB)'])):
        im=ax.imshow(data.reshape(len(grid),len(grid)).T,origin='lower',extent=(375,875,375,875),
                     vmin=0 if idx==2 else -110,vmax=30 if idx==2 else -40,cmap='magma' if idx==2 else 'viridis')
        ax.set(title=title,xlabel='x (m)',ylabel='y (m)'); fig.colorbar(im,ax=ax,shrink=.8)
    fig.suptitle('Post-hoc diagnostic map; display limits saturate extreme values; not held-out error')
    fig.savefig(out/'example_field_reconstruction_error.png',dpi=170); plt.close(fig)

if __name__=='__main__': main()
