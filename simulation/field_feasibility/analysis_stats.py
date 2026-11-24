"""Seed-level paired summaries and physically recorded checkpoint matching."""
from __future__ import annotations
from collections import defaultdict
import math
import numpy as np
from scipy import stats


def paired_summary(a_by_seed,b_by_seed):
    """A minus B; each matched seed, not each voxel/message, is one unit."""
    seeds=sorted(set(a_by_seed)&set(b_by_seed))
    pairs=[(s,a_by_seed[s],b_by_seed[s]) for s in seeds
           if a_by_seed[s] is not None and b_by_seed[s] is not None]
    if not pairs:
        return {'matched_seeds':[],'n':0,'mean_difference':None,'sd_difference':None,'ci95':None,'paired_t_p':None}
    diff=np.array([float(a)-float(b) for _,a,b in pairs]); n=len(diff)
    mean=float(np.mean(diff))
    if n<2: return {'matched_seeds':[s for s,_,_ in pairs],'n':n,'mean_difference':mean,'sd_difference':None,'ci95':None,'paired_t_p':None}
    sd=float(np.std(diff,ddof=1))
    if sd==0:
        ci=[mean,mean]; p=None  # t statistic is undefined with zero variance.
    else:
        margin=float(stats.t.ppf(.975,n-1)*sd/math.sqrt(n)); ci=[mean-margin,mean+margin]
        p=float(stats.ttest_1samp(diff,0).pvalue)
    return {'matched_seeds':[s for s,_,_ in pairs],'n':n,'mean_difference':mean,
            'sd_difference':sd,'ci95':ci,'paired_t_p':p}


def trajectory_distances(trajectory):
    """Actual team distance accumulated before each saved observation tick."""
    by_step=defaultdict(list)
    for p in trajectory: by_step[int(p['step'])].append(p)
    last={}; total=0.; rows=[]
    for step in sorted(by_step):
        entries=by_step[step]
        for p in entries:
            node=p['node_id']; xyz=np.array([p['x_m'],p['y_m'],p['h_m']],float)
            if node in last: total+=float(np.linalg.norm(xyz-last[node]))
            last[node]=xyz
        rows.append({'step':step,'t_s':entries[0]['t_s'],'distance_m':total})
    return rows


def latest_not_exceeding(rows,key,budget):
    """Nearest recorded checkpoint not over budget; expose shortfall explicitly."""
    feasible=[r for r in rows if r[key]<=budget]
    if not feasible: return None
    selected=max(feasible,key=lambda r:r[key])
    return {**selected,'requested_budget':budget,'unused_budget':float(budget-selected[key])}
