"""Offline scoring helpers. Never used by online mission planners."""
from __future__ import annotations
import numpy as np
from scipy.spatial import cKDTree
from scipy.linalg import cho_factor,cho_solve


SCALES=np.array([100.,100.,30.,120.])


def reconstruct(observations, queries, *, max_neighbours=32):
    """Bounded-neighbour GP mean/std; callers must enforce causal time support.

    `queries` are (x_m,y_m,h_m,t_s). Unlike the planner, this function may be
    used with a held-out set, but it never reads the field by itself.
    """
    queries=np.asarray(queries,float)
    valid=[s for s in observations if s['value_dbm'] is not None]
    if not valid: return np.full(len(queries),-65.),np.full(len(queries),10.)
    x=np.array([[s['x_m'],s['y_m'],s['h_m'],s['t_s']] for s in valid],float)
    y=np.array([s['value_dbm'] for s in valid],float)
    tree=cKDTree(x/SCALES)
    _,nearest=tree.query(queries/SCALES,k=min(max_neighbours,len(x)))
    if nearest.ndim==1: nearest=nearest[:,None]
    mean=[]; std=[]
    for q,index in zip(queries,nearest):
        local=x[index]; delta=(local[:,None,:]-local[None,:,:])/SCALES
        k=100*np.exp(-.5*np.sum(delta*delta,axis=2)); k.flat[::len(k)+1]+=4.
        d=(local-q)/SCALES; v=100*np.exp(-.5*np.sum(d*d,axis=1))
        factor=cho_factor(k,lower=True,check_finite=False)
        mean.append(float(-65+v@cho_solve(factor,y[index]+65,check_finite=False)))
        var=100-float(v@cho_solve(factor,v,check_finite=False))
        std.append(float(np.sqrt(max(0,var))))
    return np.asarray(mean),np.asarray(std)


def score(queries,truth,observations,*,max_neighbours=32):
    """MAE/RMSE/P95 on explicit held-out points; no unsupported value is zero-filled."""
    queries=np.asarray(queries,float); truth=np.asarray(truth,float)
    mask=np.isfinite(truth)
    if not np.any(mask): return {'support':0,'mae_db':None,'rmse_db':None,'p95_abs_error_db':None}
    if any(s['t_s']>float(np.min(queries[mask,3])) for s in observations):
        raise ValueError('future observations are not allowed in a checkpoint score')
    pred,_=reconstruct(observations,queries[mask],max_neighbours=max_neighbours)
    err=np.abs(pred-truth[mask])
    return {'support':int(len(err)),'mae_db':float(np.mean(err)),
            'rmse_db':float(np.sqrt(np.mean(err*err))),'p95_abs_error_db':float(np.percentile(err,95))}


def observations_at(result,node_id,step,*,offline=False):
    """Recover only observations actually visible at a recorded decision."""
    decision=next(d for d in result['decisions'] if d['node_id']==node_id and d['step']==step)
    t=decision['t_s']
    if offline:
        return [s for s in result['samples'] if s['t_s']<=t and s['value_dbm'] is not None]
    ids=set(decision['visible_sample_ids'])
    return [s for s in result['samples'] if s['sample_id'] in ids and s['t_s']<=t and s['value_dbm'] is not None]
