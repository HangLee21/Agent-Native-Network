"""Fixed-configuration wireless task execution on archived scale catalogs.

Reuses DemandWorld recovery and policy. Optional refresh repeats only locally
originated immutable bodies, never generating a new observation or version.
"""
from __future__ import annotations
import argparse
import copy
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import traceback

ROOT = Path(os.environ.get('ANN_REPO_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(ROOT))
if __package__:
    from .heteromrta_demand_execution import DemandWorld, RECOVERY, read_json, normalize_catalog
    from .heteromrta_causal import CausalWorld, encode
else:
    from heteromrta_demand_execution import DemandWorld, RECOVERY, read_json, normalize_catalog
    from heteromrta_causal import CausalWorld, encode
from simulation.heteromrta_eval import ASSETS, COMMIT, asset_manifest, load_checkpoint, plain, digest

SCALE_ROOT = ROOT/'simulation/results/2026-10-26-E1-006-execution/20261026-03-scale'
CATALOG_ROOT = ROOT/'simulation/results/2026-10-26-E2-006-scale/20261026-01'
CONTRACT = ROOT/'research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md'
CONDITIONS = ('event_fifo','event_latest','refresh_latest')
MODEL_SECONDS = 20.
REFRESH_PERIOD = 1.


def write_json(path,value):
    Path(path).write_bytes((json.dumps(plain(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8'))


def archived_file(directory,name):
    p=Path(directory)/(name+'.json')
    if p.exists():
        return p
    p=p.with_suffix('.json.gz')
    if not p.exists():
        raise FileNotFoundError(p)
    return p


def percentile(values,q=.95):
    if not values:
        return None
    x=sorted(values); pos=(len(x)-1)*q; lo=math.floor(pos); hi=math.ceil(pos)
    return x[lo]+(x[hi]-x[lo])*(pos-lo)


def service_factory(policy,seed):
    if __package__:
        from .wireless_broadcast_service import WirelessBroadcastService
    else:
        from wireless_broadcast_service import WirelessBroadcastService
    return WirelessBroadcastService(policy=policy,seed=seed,capacity_bytes=65536)


class WirelessWorld(DemandWorld):
    def __init__(self,*args,refresh=False,**kwargs):
        self.refresh_enabled=bool(refresh)
        self.refresh_cache={}
        super().__init__(*args,**kwargs)
        if self.refresh_enabled:
            count=len(self.actors)
            for actor in self.actors:
                self._schedule_refresh(actor/count*REFRESH_PERIOD,actor)

    def _schedule_refresh(self,when,actor):
        CausalWorld.schedule(self,when,'refresh_timer',actor=actor)
        self.info('local_timer_scheduled',event_kind='refresh_timer',actor=actor,due_at=when)

    def publish(self,body,local_receivers,local_evidence):
        # Parent applies only genuine observations and submits their original body.
        super().publish(body,local_receivers,local_evidence)
        message=self.messages[-1]
        message.update(enqueued_at=self.now,body_generated_at=body['generated_at'],
                       publication_reason='event',refresh_origin_message_id=None)
        source=body['source']
        object_id=body['state']['source'] if body['kind']=='self_state' else body['scene']['task']
        key=(source,body['kind'],object_id)
        self.refresh_cache[key]=dict(payload_utf8=message['payload_utf8'],kind=body['kind'],
            source=source,recipients=list(message['recipients']),body_generated_at=body['generated_at'],
            origin_message_id=message['message_id'],origin_local_evidence=local_evidence)

    def handle(self,kind,data):
        if kind!='refresh_timer':
            return super().handle(kind,data)
        actor=data['actor']
        self.info('local_timer_fired',event_kind=kind,actor=actor)
        for key,record in sorted(self.refresh_cache.items()):
            if key[0]!=actor:
                continue
            raw=record['payload_utf8'].encode('utf-8')
            mid=self.service.submit(self.now,actor,record['recipients'],record['kind'],raw)
            self.messages.append(dict(message_id=mid,source=actor,recipients=list(record['recipients']),
                kind=record['kind'],generated_at=self.now,enqueued_at=self.now,
                body_generated_at=record['body_generated_at'],payload_utf8=record['payload_utf8'],
                payload_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),
                local_evidence=None,origin_local_evidence=record['origin_local_evidence'],
                refresh_origin_message_id=record['origin_message_id'],publication_reason='refresh'))
            self.event('refresh_submitted',actor=actor,message_id=mid,object_key=list(key),
                       origin_message_id=record['origin_message_id'])
        self._schedule_refresh(self.now+REFRESH_PERIOD,actor)

    def summary(self):
        result=super().summary()
        message_by_id={m['message_id']:m for m in self.messages}
        age=[(d['delivered_at']-message_by_id[d['message_id']]['body_generated_at'])*MODEL_SECONDS
             for d in self.deliveries]
        queue=[(d['delivered_at']-message_by_id[d['message_id']]['enqueued_at'])*MODEL_SECONDS
               for d in self.deliveries]
        result['publication_counts']={k:sum(m['publication_reason']==k for m in self.messages)
                                      for k in ('event','refresh')}
        result['publication_bytes']={k:sum(m['bytes'] for m in self.messages if m['publication_reason']==k)
                                     for k in ('event','refresh')}
        result['delivery_metrics']=dict(receiver_copies=len(self.deliveries),
            cache_applied=sum(d['applied'] for d in self.deliveries),
            cache_unchanged=sum(not d['applied'] for d in self.deliveries),
            queue_delay_seconds_p95=percentile(queue),fact_age_seconds_p95=percentile(age),
            fact_age_seconds_max=max(age,default=None))
        result.update(refresh_enabled=self.refresh_enabled,refresh_period_model=REFRESH_PERIOD if self.refresh_enabled else None,
                      model_seconds=MODEL_SECONDS)
        return result


def child(spec_path,output):
    spec=read_json(spec_path); out=Path(output); world=None; began=time.perf_counter()
    result=dict(case_id=spec['case_id'],seed=spec['seed'],condition=spec['condition'],
                mac_seed=spec['mac_seed'],status='error',task_executed=True)
    try:
        sys.path.insert(0,str(ASSETS))
        import numpy as np
        import torch
        from attention import AttentionNet
        from parameters import TrainParams
        torch.set_num_threads(1); torch.set_num_interop_threads(1)
        torch.manual_seed(spec['seed']); np.random.seed(spec['seed']); random.seed(spec['seed'])
        catalog=normalize_catalog(read_json(out/'catalog.json'))
        result.update(agents=len(catalog['agents']),tasks=len(catalog['tasks']),
                      catalog_sha256=hashlib.sha256(encode(catalog)).hexdigest())
        net=AttentionNet(TrainParams.AGENT_INPUT_DIM,TrainParams.TASK_INPUT_DIM,TrainParams.EMBEDDING_DIM)
        net.load_state_dict(load_checkpoint(torch),strict=True); net.eval()
        def choose(obs,actor):
            with torch.no_grad():
                values=[torch.tensor(a,dtype=torch.float) for a in obs]
                probs,_=net(*values,torch.LongTensor([actor]).reshape(1,1,1))
                return int(torch.argmax(probs,dim=1).item())
        service=service_factory('fifo' if spec['condition']=='event_fifo' else 'latest_state',spec['mac_seed'])
        world=WirelessWorld(catalog,service,choose,seed=spec['seed'],recovery=True,
            refresh=spec['condition']=='refresh_latest',horizon=200.,event_budget=1000000,wall_budget=90.)
        result.update(world.run())
        result['instant_reference']=spec['instant_reference']
        if result['makespan_return'] is not None:
            result['makespan_to_instant_ratio']=result['makespan_return']/spec['instant_reference']['makespan_return']
    except Exception:
        result['error']=traceback.format_exc()
        if world is not None:
            world.status='error'; result.update(world.summary())
    finally:
        result['wall_seconds']=time.perf_counter()-began
        result['executor_sha256']=digest(__file__)
        if world is not None:
            values=[('events',world.trace),('decisions',world.decisions),('messages',world.messages),
                    ('deliveries',world.deliveries),('service_ledger',world.service.ledger),
                    ('view_evidence',{i:v.evidence for i,v in world.views.items()}),
                    ('information_ledger',world.info_ledger),
                    ('final',dict(actors=world.actors,tasks={i:{**t,'present':sorted(t['present'])} for i,t in world.tasks.items()}))]
            for name,value in values:
                write_json(out/(name+'.json'),value)
        write_json(out/'result.json',result)
    return 0 if result['status'] in ('success','horizon_incomplete') else 1


def prepare(output):
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E2-007'):
        raise ValueError('Output outside E2-007')
    out.mkdir(parents=True,exist_ok=False)
    index_path=CATALOG_ROOT/'catalog_index.json'
    index=read_json(index_path)
    specs=[]
    for row in index['cases']:
        if row['tasks']*3!=row['agents']*5:
            continue
        catalog_path=CATALOG_ROOT/'catalogs'/row['case_id']/'catalog.json'
        if digest(catalog_path)!=row['catalog_sha256']:
            raise AssertionError('Archived catalog hash mismatch')
        reference_dir=SCALE_ROOT/(row['case_id']+'-instant-recovery')
        reference_path=archived_file(reference_dir,'result')
        reference=read_json(reference_path)
        for condition in CONDITIONS:
            specs.append(dict(case_id=row['case_id']+'-'+condition,seed=row['seed'],
                agents=row['agents'],tasks=row['tasks'],condition=condition,mac_seed=0,recovery=True,
                catalog_path=str(catalog_path),expected_catalog_sha256=digest(catalog_path),
                instant_reference=dict(path=str(reference_path),sha256=digest(reference_path),
                                       makespan_return=reference['makespan_return'],status=reference['status'])))
    if len(specs)!=18:
        raise AssertionError('Expected exactly 18 planned episodes')
    write_json(out/'task_cases.json',specs)
    write_json(out/'preflight.json',dict(status='planned_not_executed',task_cases=len(specs),
        recovery=RECOVERY,contract_path=str(CONTRACT),contract_sha256=digest(CONTRACT),
        catalog_index_path=str(index_path),catalog_index_sha256=digest(index_path),
        physical_scale=dict(seconds_per_model_unit=20,meters_per_model_unit=100),
        refresh_period_model=1,mac_seed=0,source_hashes={name:digest(ROOT/'simulation'/name)
            for name in ('heteromrta_wireless_eval.py','test_heteromrta_wireless_eval.py','wireless_trace_replay.py')}))
    return 0


def run(spec_path,output):
    specs=read_json(spec_path)
    if not isinstance(specs,list) or not 1<=len(specs)<=24:
        raise ValueError('1..24 cases; global task-card cap also applies')
    if len({s['case_id'] for s in specs})!=len(specs):
        raise ValueError('Repeated case id')
    for s in specs:
        if s['condition'] not in CONDITIONS or s['mac_seed']!=0:
            raise ValueError('Outside frozen task conditions')
        if Path(s['case_id']).name!=s['case_id'] or s['case_id'] in ('.','..'):
            raise ValueError('Invalid case id')
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E2-007'):
        raise ValueError('Output outside E2-007')
    out.mkdir(parents=True,exist_ok=False); snap=out/'source'; snap.mkdir()
    names=('heteromrta_wireless_eval.py','test_heteromrta_wireless_eval.py',
           'heteromrta_demand_execution.py','heteromrta_causal.py','message_service.py',
           'wireless_broadcast_service.py','heteromrta_eval.py')
    for name in names:
        (snap/name).write_bytes((ROOT/'simulation'/name).read_bytes())
    (out/'WIRELESS_SERVICE_CONTRACT.md').write_bytes(CONTRACT.read_bytes())
    manifest=dict(command=sys.argv,author_commit=COMMIT,assets=asset_manifest(),cases=specs,
        case_spec_sha256=digest(spec_path),python=sys.executable,python_version=platform.python_version(),
        source_hashes={p.name:digest(p) for p in snap.iterdir()},contract_sha256=digest(CONTRACT),
        recovery_config=RECOVERY,horizon=200,event_budget=1000000,internal_wall_seconds=90,
        external_wall_seconds=120,cpu_threads=1,full_task_episodes_planned=len(specs),
        refresh_period_model=1,seconds_per_model_unit=20,meters_per_model_unit=100)
    write_json(out/'manifest.json',manifest)
    results=[]
    for spec in specs:
        case=out/spec['case_id'];case.mkdir()
        if digest(spec['catalog_path'])!=spec['expected_catalog_sha256']:
            raise ValueError('Source catalog changed')
        write_json(case/'catalog.json',read_json(spec['catalog_path']))
        write_json(case/'config.json',spec)
        cmd=[sys.executable,'-B','-X','utf8',str(snap/'heteromrta_wireless_eval.py'),
             '--child','--case-spec',str(case/'config.json'),'--output',str(case)]
        env=dict(os.environ,ANN_REPO_ROOT=str(ROOT),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',
                 OPENBLAS_NUM_THREADS='1',NUMEXPR_NUM_THREADS='1',MPLBACKEND='Agg')
        with (case/'stdout.txt').open('w',encoding='utf-8') as log:
            try:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=120)
                code=proc.returncode
            except subprocess.TimeoutExpired:
                code=-999
        result=read_json(case/'result.json') if (case/'result.json').exists() else dict(status='missing_result_or_external_timeout')
        result.update(case_id=spec['case_id'],process_exit_code=code)
        results.append(result)
        write_json(out/'summary.json',dict(planned=len(specs),cases=results))
        print(spec['case_id'],result['status'],result.get('completed'),result.get('makespan_return'),flush=True)
    return 0 if all(r['process_exit_code']==0 for r in results) else 1


def analyze(run_dir,output):
    src=Path(run_dir);out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E2-007'):
        raise ValueError('Output outside E2-007')
    out.mkdir(parents=True,exist_ok=False)
    results=read_json(src/'summary.json')['cases'];rows=[]
    for r in results:
        n=r.get('network',{});d=r.get('delivery_metrics',{})
        completed=r.get('completed',0)
        rows.append(dict(case_id=r['case_id'],seed=r.get('seed'),agents=r.get('agents'),tasks=r.get('tasks'),
            condition=r.get('condition'),status=r['status'],completion_fraction=r.get('completion_fraction'),
            makespan_model=r.get('makespan_return'),makespan_seconds=(r['makespan_return']*20 if r.get('makespan_return') is not None else None),
            ratio_instant=r.get('makespan_to_instant_ratio'),generated_bytes=n.get('demand_application_bytes'),
            event_bytes=r.get('publication_bytes',{}).get('event'),refresh_bytes=r.get('publication_bytes',{}).get('refresh'),
            demanded=n.get('demanded'),delivered=n.get('delivered'),collided=n.get('collided'),
            dropped=n.get('dropped'),replaced=n.get('replaced'),coalesced=n.get('coalesced'),pending=n.get('pending'),
            recipient_delivered=n.get('recipient_delivered'),airtime_attempt_us=n.get('airtime_attempt_us'),
            channel_busy_us=n.get('channel_busy_us'),
            airtime_us_per_completed_task=(n['airtime_attempt_us']/completed if completed and n.get('airtime_attempt_us') is not None else None),
            channel_busy_fraction=(n['channel_busy_us']/(r['end_time']*20000000) if r.get('end_time') and n.get('channel_busy_us') is not None else None),
            queue_delay_seconds_p95=d.get('queue_delay_seconds_p95'),fact_age_seconds_p95=d.get('fact_age_seconds_p95'),
            cache_applied=d.get('cache_applied'),cache_unchanged=d.get('cache_unchanged')))
    with (out/'cases.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    write_json(out/'analysis.json',dict(input=str(src),input_summary_sha256=digest(src/'summary.json'),
                                      rows=rows,interpretation='two task seeds; no independent task replication from MAC replay'))
    return 0


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True);p.add_argument('--case-spec')
    p.add_argument('--child',action='store_true');p.add_argument('--prepare',action='store_true')
    p.add_argument('--analyze')
    args=p.parse_args()
    if args.prepare:return prepare(args.output)
    if args.analyze:return analyze(args.analyze,args.output)
    if not args.case_spec:p.error('--case-spec required')
    return child(args.case_spec,args.output) if args.child else run(args.case_spec,args.output)

if __name__=='__main__':
    raise SystemExit(main())
