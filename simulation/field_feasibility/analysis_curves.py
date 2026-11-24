"""Time, observation-count, and actual-distance curves from saved 30-node runs."""
import argparse
import csv
import math
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--analysis',default='analysis_v2'); args=ap.parse_args()
    root=Path(args.root); out=root/args.analysis
    with (root/'n30'/'checkpoints.csv').open(encoding='utf8',newline='') as f: time=list(csv.DictReader(f))
    with (root/'n30'/'distance_checkpoints.csv').open(encoding='utf8',newline='') as f: dist=list(csv.DictReader(f))
    policies=['A','B','C','D','D_degraded','E']
    fig,axes=plt.subplots(2,3,figsize=(15,9),constrained_layout=True)
    def moments(values):
        arr=np.array(values,float); mean=float(arr.mean())
        margin=float(stats.t.ppf(.975,len(arr)-1)*arr.std(ddof=1)/math.sqrt(len(arr))) if len(arr)>1 else 0.
        return mean,margin
    for row,metric in enumerate(['offline_rmse_db','masked_blind_rmse_db']):
        for policy in policies:
            for column,(data,group,xxlabel) in enumerate([(time,'step','t_s'),(time,'step','attempts'),(dist,'fraction_of_shared_ceiling','observed_team_m')]):
                subset=[r for r in data if r['policy']==policy]
                groups=sorted(set(float(r[group]) for r in subset)); x=[]; y=[]; err=[]
                for g in groups:
                    part=[r for r in subset if float(r[group])==g and r[metric]!='']
                    if not part: continue
                    x.append(float(np.mean([float(r[xxlabel]) for r in part])))
                    mean,margin=moments([float(r[metric]) for r in part]);y.append(mean);err.append(margin)
                axes[row,column].errorbar(x,y,yerr=err,marker='o',capsize=2,label=policy)
        for ax in axes[row]: ax.grid(alpha=.2); ax.set_ylabel('Raw RMSE (dB)' if row==0 else 'Floor-excluded RMSE (dB)')
    axes[0,0].set_title('Common mission time');axes[0,1].set_title('Common sample attempts');axes[0,2].set_title('Actual distance at common upper budget')
    axes[1,0].set_xlabel('Last observation time (s)'); axes[1,1].set_xlabel('Sample attempts'); axes[1,2].set_xlabel('Recorded team distance (m)')
    axes[0,0].legend(fontsize=8,ncol=2)
    fig.suptitle('30 nodes, 20 paired seeds; 95% t intervals. Distance uses last sampled tick not exceeding common budget.')
    fig.savefig(out/'rmse_time_samples_distance_n30.png',dpi=170)

if __name__=='__main__':main()
