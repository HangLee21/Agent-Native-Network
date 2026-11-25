"""Render the frozen E1-033 group-1 trajectories; no simulation is run."""
import argparse
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.io import loadmat

ap=argparse.ArgumentParser()
ap.add_argument('--source', default='simulation/outputs/E1-033/20261124-01-pilot/source')
ap.add_argument('--out', default='simulation/outputs/E1-033/20261124-01-pilot/results')
args=ap.parse_args()
out=Path(args.out)
field=loadmat(Path(args.source)/'Static_REM_1.25km_h30m_2.45GHz_100s.mat')['rem']
gx,gy=np.indices(field.shape)
blind=((gx//10+2*(gy//10))%5)==0
weak=np.isfinite(field)&(field>-250)&(field < -75)
fig,axes=plt.subplots(1,3,figsize=(15,5),sharex=True,sharey=True,constrained_layout=True)
for ax,policy in zip(axes,['partition','local','shared']):
    ax.imshow(weak.T,origin='lower',cmap='Greys',alpha=.25,extent=(0,1250,0,1250))
    ax.contourf((gx*5).T,(gy*5).T,blind.T,levels=[.5,1.5],colors=['#dfbd48'],alpha=.18)
    with (out/'group-01'/policy/'trajectory.csv').open(newline='') as f: rows=list(csv.DictReader(f))
    for i,(height,color) in enumerate(zip([20,30,40],['#d62728','#1f77b4','#2ca02c'])):
        for rnd in range(4):
            seg=[r for r in rows if int(r['aircraft'])==i and int(r['round'])==rnd]
            ax.plot([int(r['x'])*5 for r in seg],[int(r['y'])*5 for r in seg],color=color,alpha=.72,lw=1.5)
        ax.scatter(int(seg[0]['x'])*5,int(seg[0]['y'])*5,c=color,s=20,label=f'{height} m')
    ax.set(title=policy,xlim=(350,800),ylim=(350,800),xlabel='x (m)',ylabel='y (m)')
    ax.set_aspect('equal'); ax.legend()
fig.suptitle('Group 1: paths; gold = blind blocks; grey = valid weak at 30 m (post-hoc truth)')
fig.savefig(out/'paired_paths_group1.png',dpi=180)
plt.close(fig)
