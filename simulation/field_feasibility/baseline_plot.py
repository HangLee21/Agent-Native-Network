import argparse,csv,pathlib,sys
import numpy as np,matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=pathlib.Path.cwd();sys.path.insert(0,str(ROOT))
from simulation.field_feasibility.baseline_run import predictions
parser=argparse.ArgumentParser();parser.add_argument('--scores',required=True,type=pathlib.Path);parser.add_argument('--out',required=True,type=pathlib.Path);args=parser.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=False);rows=list(csv.DictReader(args.scores.open(encoding='utf8')))
fig,axes=plt.subplots(2,4,figsize=(15,7),constrained_layout=True,sharex=True)
for i,kind in enumerate(['spatial','temporal']):
 for j,h in enumerate((2,25,50,80)):
  ax=axes[i,j]
  for method in ['idw','ordinary_kriging','gpr']:
   vals=[r for r in rows if r['kind']==kind and r['method']==method and int(r['height_m'])==h];xs=sorted(set(float(r['rate']) for r in vals));ys=[np.mean([float(r['rmse']) for r in vals if float(r['rate'])==x]) for x in xs];ax.plot(np.array(xs)*100,ys,marker='o',label=method)
  ax.set_title(f'{h}m {kind}');ax.set_xlabel('training sample rate / full grid (%)');ax.set_ylabel('RMSE (dB)');ax.grid(alpha=.2)
axes[0,0].legend(fontsize=8);fig.suptitle('Single deterministic split; each curve averages three target times');fig.savefig(out/'rmse_by_height_and_rate.png',dpi=150);plt.close(fig)
h=50;t=299;rng=np.random.default_rng(20261124+h*1000+t);order=rng.permutation(62500);test=order[:128];train=order[128:128+3125];a=np.load(ROOT/f'data/field_feasibility_v2/dynamic_h{h}m_f64.npy',mmap_mode='r');xy=np.column_stack((train//250,train%250))*5.;values=a[train//250,train%250,t];ii,jj=np.meshgrid(np.arange(0,250,5),np.arange(0,250,5),indexing='ij');q=np.column_stack((ii.ravel(),jj.ravel()))*5.;pred,var=predictions(xy,values,q);truth=a[ii,jj,t];fig,axes=plt.subplots(1,6,figsize=(19,3.5),constrained_layout=True);panels=[truth,truth]+[pred[:,i].reshape(ii.shape) for i in range(3)]+[np.abs(pred[:,2].reshape(ii.shape)-truth)];titles=['truth (sampled grid)','training locations','IDW','ordinary kriging','GPR mean','GPR absolute error']
for k,(ax,grid,title) in enumerate(zip(axes,panels,titles)):
 im=ax.imshow(grid.T,origin='lower',extent=[0,1245,0,1245],cmap='magma' if k==5 else 'viridis',vmin=0 if k==5 else -120,vmax=40 if k==5 else -40);ax.set_title(title);ax.set_xlabel('x (m)');ax.set_ylabel('y (m)')
 if k==1:ax.scatter(xy[:,0],xy[:,1],s=.5,c='white',alpha=.4)
 fig.colorbar(im,ax=ax,shrink=.7,label='dB' if k==5 else 'dBm')
fig.suptitle('V2 50m, frame 300, 5% training; visualized on every fifth cell');fig.savefig(out/'example_reconstructions.png',dpi=130);plt.close(fig)
