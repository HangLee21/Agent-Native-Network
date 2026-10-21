"""Synthetic rescue-reporting task pilot; no fire, PHY, or Agent model."""
from dataclasses import dataclass, asdict
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np

POLICIES=('ideal','fifo','priority','return','relay','relay_return')


@dataclass(frozen=True)
class Config:
    horizon: int = 600
    reach: int = 3
    rate: int = 4000
    evidence: int = 0
    return_period: int = 120
    rooms: int = 12
    travel: int = 20
    scan: int = 10
    deploy: int = 10


def episode(cfg, policy, seed, keep_events=False):
    if policy not in POLICIES or min(cfg.horizon,cfg.reach,cfg.rate,cfg.rooms,cfg.travel,cfg.scan)<=0 or cfg.evidence<0:
        raise ValueError('Invalid configuration')
    rng=np.random.default_rng(seed)
    targets=[set(rng.choice(np.arange(1,cfg.rooms+1),min(4,cfg.rooms),replace=False).tolist()) for _ in range(2)]
    robots=[dict(node=i,pos=0.,phase='idle',remaining=0,target=0.,next_room=1,relay=None,
                 queue=[],last_contact=0,distance=0.,returns=0,visited=[],finish=None) for i in range(2)]
    reports=[];events=[];sent=0.;link_bytes=0.;turn=0
    def log(time,event,node,**kwargs):
        if keep_events:events.append(dict(time=time,event=event,node=node,**kwargs))
    def hops(robot):
        if robot['pos']<=cfg.reach+1e-8:return 1
        if robot['relay'] is not None and robot['pos']<=robot['relay']+cfg.reach+1e-8:return 2
        return 0
    def pending_summary(robot):
        return any(m['kind']=='summary' for m in robot['queue'])
    def move(robot,phase,target):
        robot.update(phase=phase,target=float(target),remaining=int(round(abs(robot['pos']-target)*cfg.travel)))
    for t in range(cfg.horizon):
        for r in robots:
            if hops(r):r['last_contact']=t
            if r['phase']=='sync' and not pending_summary(r):r['phase']='idle'
            if r['phase']!='idle':continue
            nxt=r['next_room']
            drop=policy in ('relay','relay_return') and r['relay'] is None and nxt==cfg.reach
            cost=abs(nxt-r['pos'])*cfg.travel+cfg.scan+(cfg.deploy if drop else 0)+nxt*cfg.travel
            if nxt>cfg.rooms or t+cost>cfg.horizon:
                if r['pos']>0:move(r,'home',0)
                else:r.update(phase='done',finish=t)
            elif policy in ('return','relay_return') and pending_summary(r) and t-r['last_contact']>=cfg.return_period:
                r['returns']+=1;move(r,'return',0);log(t,'return_start',r['node'])
            else:move(r,'out',nxt);log(t,'move',r['node'],room=nxt)
        # Network serves only data available at interval start. Link availability
        # is sampled at start; boundary crossing error is bounded by one tick.
        reachable=[hops(r) for r in robots]
        for report in reports:
            if report['first_contact'] is None and reachable[report['node']]:report['first_contact']=t
        capacity=float(cfg.rate)
        while capacity>1e-8:
            active=[i for i in range(2) if reachable[i] and robots[i]['queue']]
            if not active:break
            node=next((i for i in (turn,1-turn) if i in active))
            turn=1-node;r=robots[node];queue=r['queue']
            index=0 if policy=='fifo' else next((i for i,m in enumerate(queue) if m['kind']=='summary'),0)
            message=queue[index]
            amount=min(1024.,message['remaining'],capacity/reachable[node])
            message['remaining']-=amount;capacity-=amount*reachable[node]
            sent+=amount;link_bytes+=amount*reachable[node]
            if message['remaining']<1e-8:
                report=reports[message['report']]
                report['received' if message['kind']=='summary' else 'evidence_received']=t+1
                log(t+1,'receive_'+message['kind'],node,report=message['report'])
                queue.pop(index)
        for r in robots:
            phase=r['phase']
            if phase in ('out','return','home'):
                old=r['pos'];step=np.sign(r['target']-old)/cfg.travel
                r['pos']=old+step;r['distance']+=abs(step);r['remaining']-=1
                if r['remaining']==0:
                    r['pos']=r['target']
                    if phase=='home':r.update(phase='done',finish=t+1)
                    elif phase=='return':r['phase']='sync'
                    elif policy in ('relay','relay_return') and r['relay'] is None and r['pos']==cfg.reach:
                        r.update(phase='deploy',remaining=cfg.deploy)
                    else:r.update(phase='scan',remaining=cfg.scan)
            elif phase in ('scan','deploy'):
                r['remaining']-=1
                if r['remaining']==0:
                    if phase=='deploy':
                        r['relay']=r['pos'];r.update(phase='scan',remaining=cfg.scan)
                        log(t+1,'deploy',r['node'],position=r['pos'])
                    else:
                        room=r['next_room'];r['visited'].append(room);r['next_room']+=1;r['phase']='idle'
                        log(t+1,'scan',r['node'],room=room)
                        if room in targets[r['node']]:
                            rid=len(reports)
                            body=dict(id=f'{r["node"]}:{room}',node=r['node'],room=room,time=t+1,kind='target')
                            size=len(json.dumps(body,separators=(',',':')).encode('utf8'))
                            report=dict(id=rid,node=r['node'],room=room,discovered=t+1,summary_bytes=size,
                                        first_contact=None,received=None,evidence_received=None)
                            reports.append(report);log(t+1,'discover',r['node'],report=rid,room=room)
                            if policy=='ideal':
                                report.update(first_contact=t+1,received=t+1,evidence_received=t+1 if cfg.evidence else None)
                            else:
                                r['queue'].append(dict(report=rid,kind='summary',remaining=float(size)))
                                if cfg.evidence:r['queue'].append(dict(report=rid,kind='evidence',remaining=float(cfg.evidence)))
    for r in robots:
        assert abs(r['pos'])<1e-8 and r['finish'] is not None and r['finish']<=cfg.horizon
    cap_delays=[(r['received'] if r['received'] is not None else cfg.horizon)-r['discovered'] for r in reports]
    contact_wait=[(r['first_contact'] if r['first_contact'] is not None else cfg.horizon)-r['discovered'] for r in reports]
    auc=sum(cfg.horizon-r['received'] for r in reports if r['received'] is not None)/(sum(map(len,targets))*cfg.horizon)
    row=dict(**asdict(cfg),policy=policy,seed=seed,discovered=len(reports),
             received=sum(r['received'] is not None for r in reports),
             evidence_received=sum(r['evidence_received'] is not None for r in reports),
             report_auc=auc,capped_delay=float(np.mean(cap_delays)) if reports else 0.,
             contact_wait=float(np.mean(contact_wait)) if reports else 0.,
             after_contact_wait=float(np.mean(np.array(cap_delays)-contact_wait)) if reports else 0.,
             distance=sum(r['distance'] for r in robots),returns=sum(r['returns'] for r in robots),
             relays=sum(r['relay'] is not None for r in robots),application_bytes=sent,link_bytes=link_bytes,
             rooms_visited=sum(len(r['visited']) for r in robots))
    return row,dict(reports=reports,robots=[{k:v for k,v in r.items() if k!='queue'} for r in robots],events=events)


def write_csv(path,rows):
    with path.open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def run(output):
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be empty')
    output.mkdir(parents=True,exist_ok=True);rows=[];details=[]
    for reach in (3,6,99):
        for rate in (4000,64000):
            for evidence in (0,65536,524288):
                for horizon in (600,900):
                    cfg=Config(horizon=horizon,reach=reach,rate=rate,evidence=evidence)
                    for seed in range(24):
                        for policy in POLICIES:
                            row,detail=episode(cfg,policy,seed,keep_events=seed==0);rows.append(row)
                            if seed==0:details.append(dict(metrics=row,**detail))
        print('Completed coverage',reach,flush=True)
    write_csv(output/'metrics.csv',rows)
    summary=[]
    for reach in (3,6,99):
        for rate in (4000,64000):
            for evidence in (0,65536,524288):
                for horizon in (600,900):
                    for policy in POLICIES:
                        group=[r for r in rows if (r['reach'],r['rate'],r['evidence'],r['horizon'],r['policy'])==(reach,rate,evidence,horizon,policy)]
                        row=dict(reach=reach,rate=rate,evidence=evidence,horizon=horizon,policy=policy)
                        for k in ('discovered','received','evidence_received','report_auc','capped_delay','contact_wait','after_contact_wait','distance','returns','relays','application_bytes','link_bytes','rooms_visited'):
                            row[k]=float(np.mean([r[k] for r in group]))
                        summary.append(row)
    write_csv(output/'summary.csv',summary)
    (output/'episodes_seed0.json.gz').write_bytes(gzip.compress(json.dumps(details).encode(),mtime=0))
    sources=['simulation/rescue_reporting.py','simulation/RESCUE_REPORT_PROTOCOL.md']
    metadata=dict(records=len(rows),seeds=list(range(24)),tick_seconds=1,
                  source_sha256={s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources},
                  caveat='Synthetic two-corridor task, uncalibrated reliable byte service, no fire or Agent simulation')
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
