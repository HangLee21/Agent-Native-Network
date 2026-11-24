"""Plot audited fixed-budget C/D supplement from saved run outputs."""
import argparse,csv,gzip,json,pathlib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
summary=json.loads((a.source/'summary.json').read_text(encoding='utf8'));fig,ax=plt.subplots(figsize=(8,5),constrained_layout=True)
for j,(name,key,ci,color) in enumerate([('raw ground truth','mean_D_minus_C_rmse','ci95','#2467ad'),('exact floor excluded from blind scoring','floor_excluded_mean_D_minus_C_rmse','floor_excluded_ci95','#cf7a22')]):
 for row in summary:
  if key not in row or ci not in row:continue
  n=row['nodes'];mean=row[key];lo,hi=row[ci];ax.errorbar(n+(-.4 if j==0 else .4),mean,yerr=[[mean-lo],[hi-mean]],fmt='o',capsize=4,color=color,label=name if n==summary[0]['nodes'] else None)
ax.axhline(0,color='black',linewidth=.8);ax.set_xticks([5,10,20,30]);ax.set_xlabel('nodes');ax.set_ylabel('paired offline RMSE D − C (dB)');ax.set_title('Fixed-distance, fixed-time paired trials; 95% paired t intervals');ax.legend();ax.grid(alpha=.2);fig.savefig(a.out/'paired_delta.png',dpi=150);plt.close(fig)
fig,axes=plt.subplots(2,4,figsize=(16,8),constrained_layout=True)
for i,policy in enumerate(('C','D')):
 path=a.source/f'n30-seed2000-{policy}.json.gz'
 if not path.exists():continue
 with gzip.open(path,'rt',encoding='utf8') as f:entry=json.load(f)
 r=entry['result'];n=r['nodes'];arr=np.array([[x['x_m'],x['y_m'],x['h_m']] for x in r['trajectory']]).reshape(20,n,3);arr=np.concatenate((arr,np.array(r['final_positions'])[None,:,:]),axis=0)
 for j,height in enumerate((2,25,50,80)):
  ax=axes[i,j];ids=np.flatnonzero(arr[0,:,2]==height)
  for node in ids:
   ax.plot(arr[:,node,0],arr[:,node,1],linewidth=.8,alpha=.7);ax.scatter(arr[0,node,0],arr[0,node,1],s=8,c='black')
  blind=[x for x in entry['blind'] if x[2]==height];ax.scatter([v[0] for v in blind],[v[1] for v in blind],marker='x',s=18,c='red',label='blind cell')
  ax.set(xlim=(375,875),ylim=(375,875),aspect='equal',title=f'{policy}, {height} m',xlabel='x (m)',ylabel='y (m)')
axes[0,0].legend(fontsize=7);fig.suptitle('Representative N=30, seed 2000; lines are simulated paths, not flights');fig.savefig(a.out/'representative_trajectories.png',dpi=140);plt.close(fig)
