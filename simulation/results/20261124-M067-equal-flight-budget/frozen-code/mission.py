"""A-E causal mission engine with an injected delivered-message transport.

This module never reads a field array. A field object supplies only query at the
current node position/time. It is not a flight controller or a network model.
"""
from __future__ import annotations

import math
import numpy as np
from sampling import select_target, sensor_noise, segment_min_distance
from analysis import reconstruct


def _moves(position, target, max_distance):
    delta=np.asarray(target,dtype=float)-np.asarray(position,dtype=float)
    norm=float(np.linalg.norm(delta))
    return np.asarray(target,dtype=float) if norm<=max_distance else np.asarray(position,dtype=float)+delta*(max_distance/norm)


def _safe_moves(old,proposed,min_separation):
    """Conservative synchronized freeze, not a decentralized avoidance design."""
    old=np.asarray(old,dtype=float); result=np.asarray(proposed,dtype=float).copy()
    hazards=set()
    for i in range(len(old)):
        for j in range(i):
            if segment_min_distance(old[i],old[i],old[j],old[j]) < min_separation:
                raise ValueError('initial positions violate separation')
    while True:
        bad=[]
        for i in range(len(old)):
            for j in range(i):
                if segment_min_distance(old[i],result[i],old[j],result[j]) < min_separation:
                    hazards.add((j,i)); bad.append((j,i))
        if not bad: break
        before=result.copy()
        for i,j in bad: result[i]=old[i]; result[j]=old[j]
        if np.array_equal(before,result): raise RuntimeError('safety filter could not resolve conflict')
    return result,sorted(hazards)


def initial_positions(n,region,heights,min_separation,seed):
    xmin,ymin,xmax,ymax=region; columns=math.ceil(math.sqrt(n)); rows=math.ceil(n/columns)
    result=[]; rng=np.random.default_rng(np.random.SeedSequence([int(seed),1831]))
    for i in range(n):
        x=xmin+(i%columns+0.5+rng.uniform(-.15,.15))*(xmax-xmin)/columns
        y=ymin+(i//columns+0.5+rng.uniform(-.15,.15))*(ymax-ymin)/rows
        result.append([x,y,float(heights[i%len(heights)])])
    _safe_moves(result,result,min_separation)
    return np.array(result,dtype=float)


def _candidate_grid(region,height):
    xmin,ymin,xmax,ymax=region
    return [[x,y,float(height)] for y in np.linspace(ymin,ymax,5) for x in np.linspace(xmin,xmax,5)]


def _fixed_target(node_id,n,step,region,height):
    """Parallel lane sweeps within each node's fixed horizontal strip."""
    xmin,ymin,xmax,ymax=region; lo=xmin+(xmax-xmin)*node_id/n; hi=xmin+(xmax-xmin)*(node_id+1)/n
    x=(lo+hi)/2
    y=ymax if (step//4)%2==0 else ymin
    return [x,y,float(height)]


def simulate(field,config,*,policy,seed,transport=None,allow_observation=None):
    """Return causal samples, decisions and trajectories for one mission.

    Transport's advance(t_s, positions) returns {receiver:[delivered_msg]},
    and send(t_s, positions, outgoing) enqueues newly generated messages at
    their actual creation time. Only returned envelopes are visible to nodes.
    """
    if policy not in 'ABCDE' or len(policy)!=1: raise ValueError('unknown policy')
    if policy in 'BD' and transport is None: raise ValueError('B and D require delivered-message transport')
    n=int(config['nodes']); dt=float(config['dt_s']); duration=float(config['duration_s'])
    speed=float(config['speed_m_s']); safety=float(config['min_separation_m']); sigma=float(config['noise_sigma_db'])
    region=config['region_m']; heights=config['heights_m']
    if n<1 or dt<=0 or duration<=0 or speed<0 or safety<0: raise ValueError('invalid mission config')
    pos=initial_positions(n,region,heights,safety,seed)
    candidates=[_candidate_grid(region,p[2]) for p in pos]
    own=[[] for _ in range(n)]; received=[{} for _ in range(n)]; intents=[{} for _ in range(n)]; summaries=[{} for _ in range(n)]
    samples=[]; decisions=[]; trajectory=[]; events=[]; total_dist=[0.]*n
    for step in range(math.ceil(duration/dt)):
        now=step*dt
        if now>=duration: break
        incoming=transport.advance(now,pos.copy()) if transport is not None else {}
        outgoing=[]
        for receiver,envelopes in incoming.items():
            receiver=int(receiver)
            for msg in envelopes:
                if int(msg['receiver'])!=receiver or float(msg['delivered_s'])>now or float(msg['created_s'])>float(msg['delivered_s']):
                    raise ValueError('invalid delivery envelope')
                events.append(dict(msg))
                if msg['kind']=='SAMPLE':
                    obs=msg['payload']
                    if int(obs['node_id'])!=int(msg['sender']) or float(obs['t_s'])>float(msg['created_s']):
                        raise ValueError('sender identity or observation creation time invalid')
                    if float(obs['t_s'])>now or obs['value_dbm'] is None or not np.isfinite(obs['value_dbm']):
                        raise ValueError('future or invalid observation delivered')
                    received[receiver][obs['sample_id']]=obs
                elif msg['kind']=='TASK_INTENT':
                    intent=dict(msg['payload']); intent['sender']=int(msg['sender'])
                    intents[receiver][intent['sender']]=intent
                elif msg['kind']=='TASK_UPDATE':
                    p=msg['payload']; sender=int(msg['sender'])
                    if int(p['owner'])!=sender: raise ValueError('task owner does not match source')
                    if p['status']=='active':
                        intents[receiver][sender]={'target_index':int(p['region_id']),'height_m':float(p['height_m']),
                                                   'expires_s':float(p['expires_at']),'sender':sender}
                    elif sender in intents[receiver]: del intents[receiver][sender]
                elif msg['kind']=='MAP_SUMMARY':
                    p=msg['payload']; sender=int(msg['sender'])
                    summaries[receiver][sender]={'target_index':int(p['region_id']),'height_m':float(p['height_m']),
                                                 'variance':float(p['variance']),'expires_s':float(p['expires_at']),'sender':sender}
        # Only current position/current simulated time is passed to the field.
        for i,p in enumerate(pos):
            allowed=allow_observation is None or bool(allow_observation(float(p[0]),float(p[1]),float(p[2]),float(now)))
            value=field.query(float(p[0]),float(p[1]),float(p[2]),float(now)) if allowed else None
            record={'sample_id':f'{i}:{step}','node_id':i,'step':step,'x_m':float(p[0]),'y_m':float(p[1]),
                    'h_m':float(p[2]),'t_s':float(now),'value_dbm':None,'observation_allowed':allowed}
            if value is not None and np.isfinite(value):
                record['value_dbm']=float(value)+sensor_noise(seed,i,step,sigma)
                own[i].append(record)
                if policy in 'BD': outgoing.append({'kind':'SAMPLE','sender':i,'created_s':now,'payload':record})
            samples.append(record)
            trajectory.append({'node_id':i,'step':step,'t_s':now,'x_m':float(p[0]),'y_m':float(p[1]),'h_m':float(p[2])})
        all_actual=[s for node in own for s in node] if policy=='E' else None
        global_intents=[]
        proposed=[]
        for i,p in enumerate(pos):
            local=own[i]
            if policy in 'AB':
                target=_fixed_target(i,n,step,region,p[2]); chosen=counter=None
                visible=local+list(received[i].values()) if policy=='B' else local
                decisions.append({'node_id':i,'step':step,'t_s':now,'position':p.tolist(),
                                  'selected_target_index':None,'local_counterfactual_index':None,
                                  'received_sample_ids':sorted(received[i]),'received_intents':[],
                                  'visible_sample_ids':[s['sample_id'] for s in visible],
                                  'history_count':len(visible),'scores':[]})
            else:
                if policy=='E': history=all_actual
                elif policy=='D': history=local+list(received[i].values())
                else: history=local
                history=sorted(history,key=lambda x:(x['t_s'],x['node_id'],x['sample_id']))
                usable=list(intents[i].values()) if policy=='D' else list(global_intents) if policy=='E' else []
                summaries_available=list(summaries[i].values()) if policy=='D' else []
                chosen,_,scores=select_target(p,candidates[i],history,now,intents=usable,summaries=summaries_available,node_id=i)
                counter,_,_=select_target(p,candidates[i],local,now,node_id=i)
                target=candidates[i][chosen]
                if policy=='E': global_intents.append({'target_index':chosen,'sender':i,'height_m':float(p[2]),'expires_s':now+2*dt})
                if policy=='D':
                    outgoing.append({'kind':'TASK_INTENT','sender':i,'created_s':now,
                                     'payload':{'target_index':chosen,'expires_s':now+2*dt,'height_m':float(p[2]),
                                                'utility':scores[chosen],
                                                'eta_s':now+float(np.linalg.norm(np.asarray(target)-p))/speed if speed>0 else None}})
                    mean,std=reconstruct(history,[[*target,now]])
                    outgoing.append({'kind':'MAP_SUMMARY','sender':i,'created_s':now,
                                     'payload':{'region_id':chosen,'mean':float(mean[0]),
                                                'variance':float(std[0]**2),'sample_count':len(history),'timestamp':now,
                                                'height_m':float(p[2]),'expires_at':now+2*dt}})
                    outgoing.append({'kind':'TASK_UPDATE','sender':i,'created_s':now,
                                     'payload':{'region_id':chosen,'owner':i,'status':'active','expires_at':now+2*dt,'height_m':float(p[2])}})
                decisions.append({'node_id':i,'step':step,'t_s':now,'position':p.tolist(),
                                  'selected_target_index':chosen,'local_counterfactual_index':counter,
                                  'received_sample_ids':sorted(received[i]),'received_intents':usable,'received_summaries':summaries_available,
                                  'visible_sample_ids':[s['sample_id'] for s in history],
                                  'history_count':len(history),'scores':scores})
            proposed.append(_moves(p,target,speed*dt))
        if transport is not None: transport.send(now,pos.copy(),outgoing)
        moved,hazards=_safe_moves(pos,proposed,safety)
        for i in range(n): total_dist[i]+=float(np.linalg.norm(moved[i]-pos[i]))
        if hazards: events.append({'kind':'SAFETY_FREEZE','t_s':now,'pairs':hazards})
        pos=moved
    return {'policy':policy,'seed':int(seed),'samples':samples,'trajectory':trajectory,
            'decisions':decisions,'events':events,'flight_distance_m':total_dist,
            'final_positions':pos.tolist(),
            'limitations':['centralized geometric safety freeze, not real collision avoidance','no ground truth is available to planners',
                           'time-stepped point observations; no obstacle or flight dynamics model']}
