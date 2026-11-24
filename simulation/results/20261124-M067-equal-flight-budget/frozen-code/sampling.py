"""Causal, local sampling primitives for M-067; no field truth access."""
from __future__ import annotations

import math
import numpy as np


def variance_scores(position, candidates, observations, now, *, max_history=32):
    """Compute fixed-kernel GP posterior variance per metre from locally held data.

    Observations are dictionaries with x_m, y_m, h_m, t_s. No hidden field
    object is accepted. A bounded recent history limits per-decision cost.
    """
    hist = observations[-max_history:]
    candidates = np.asarray(candidates, dtype=float)
    if len(candidates) == 0:
        return np.empty(0)
    if not hist:
        variance = np.ones(len(candidates))
    else:
        x = np.asarray([[o['x_m'],o['y_m'],o['h_m'],o['t_s']] for o in hist], dtype=float)
        q = np.column_stack((candidates, np.full(len(candidates), now)))
        scales = np.array([100.,100.,30.,120.])
        def cov(a,b):
            d=(a[:,None,:]-b[None,:,:])/scales
            return np.exp(-0.5*np.sum(d*d,axis=2))
        k=cov(x,x); k.flat[::len(k)+1] += 0.04
        cross=cov(x,q)
        factor=np.linalg.cholesky(k)
        projection=np.linalg.solve(factor,cross)
        variance=np.maximum(0.,1.-np.sum(projection*projection,axis=0))
    travel=np.linalg.norm(candidates[:,:2]-np.asarray(position[:2]),axis=1)
    return variance/(1.+travel/100.)


def select_target(position, candidates, observations, now, *, intents=(), summaries=(), node_id=None):
    """Local posterior-variance score; received non-expired intents avoid overlap.

    The receiver yields to lower-ID senders to keep the rule deterministic.
    This is a heuristic, not a centralized optimum or a strict performance bound.
    """
    scores=variance_scores(position,candidates,observations,now)
    base=scores.copy()
    for summary in summaries:
        if summary['expires_s'] < now or summary['height_m'] != float(position[2]):
            continue
        idx=int(summary['target_index'])
        if 0<=idx<len(scores):
            scores[idx] += 0.1*math.sqrt(max(0.,summary['variance']))/10.
    for intent in intents:
        if intent['expires_s'] < now or intent.get('height_m') != float(position[2]) or (node_id is not None and intent['sender'] >= node_id):
            continue
        idx=int(intent['target_index'])
        if 0<=idx<len(scores):
            scores[idx] -= 2.0
    selected=int(np.argmax(scores))
    local=int(np.argmax(base))
    return selected, local, [float(x) for x in scores]


def sensor_noise(seed, node_id, step, sigma):
    """Key noise to physical node and time step, independent of network RNG."""
    if sigma==0: return 0.0
    return float(np.random.default_rng(np.random.SeedSequence([int(seed),int(node_id),int(step)])).normal(0,sigma))


def segment_min_distance(a0,a1,b0,b1):
    """Minimum simultaneous distance on two linearly traversed 3-D segments."""
    a0=np.asarray(a0,float); a1=np.asarray(a1,float); b0=np.asarray(b0,float); b1=np.asarray(b1,float)
    rel=a0-b0; v=(a1-a0)-(b1-b0); vv=float(v@v)
    t=0. if vv==0 else min(1.,max(0.,-float(rel@v)/vv))
    return math.sqrt(float((rel+t*v)@(rel+t*v)))
