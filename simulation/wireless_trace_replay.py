"""Replay archived natural task messages through a fixed competition service.

No task decisions execute. Preserves body generation time and input order,
reports service at the original task window and after draining the queues.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import math
import os
from pathlib import Path
import sys
import time

ROOT=Path(os.environ.get('ANN_REPO_ROOT',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(ROOT))
if __package__:
    from .heteromrta_wireless_eval import (SCALE_ROOT,CONTRACT,read_json,write_json,archived_file,service_factory,digest,percentile)
else:
    from heteromrta_wireless_eval import (SCALE_ROOT,CONTRACT,read_json,write_json,archived_file,service_factory,digest,percentile)


def replay_messages(messages,service,horizon):
    if any(messages[i]['generated_at']>messages[i+1]['generated_at'] for i in range(len(messages)-1)):
        raise ValueError('Input must preserve chronological source order')
    if messages and messages[-1]['generated_at']>horizon:
        raise ValueError('Messages exceed reference window')
    deliveries=[];mapping=[];last=0.;operations=0
    def collect(at):
        nonlocal operations,last
        operations+=1
        if operations>1000000:
            raise RuntimeError('Replay service event budget exhausted')
        last=max(last,at)
        for d in service.pop_due(at):
            body=read_body(d['payload'])
            deliveries.append(dict(**{k:v for k,v in d.items() if k!='payload'},
                body_generated_at=body['generated_at'],
                payload_sha256=hashlib.sha256(d['payload']).hexdigest(),
                fact_age_seconds=(d['delivered_at']-body['generated_at'])*20))
    pos=0
    while pos<len(messages):
        t=messages[pos]['generated_at']
        while service.next_event_time()<t:
            collect(service.next_event_time())
        end=pos+1
        while end<len(messages) and messages[end]['generated_at']==t:
            end+=1
        # Submit equal-time arrivals before collecting consequences at that time.
        for m in messages[pos:end]:
            raw=m['payload_utf8'].encode('utf-8')
            mid=service.submit(t,m['source'],m['recipients'],m['kind'],raw)
            mapping.append(dict(original_message_id=m['message_id'],message_id=mid,
                                generated_at=t,source=m['source'],kind=m['kind'],
                                application_bytes=len(raw),payload_sha256=hashlib.sha256(raw).hexdigest()))
        collect(t)
        pos=end
    while service.next_event_time()<=horizon:
        collect(service.next_event_time())
    collect(horizon)
    window_stats=service.stats(horizon)
    window_copies=len(deliveries)
    while math.isfinite(service.next_event_time()):
        collect(service.next_event_time())
    final=service.stats(last)
    ages=[d['fact_age_seconds'] for d in deliveries]
    return dict(reference_window_model=horizon,drained_at_model=last,
        drain_after_window_seconds=max(0.,last-horizon)*20,
        window_stats=window_stats,drained_stats=final,window_receiver_copies=window_copies,
        drained_receiver_copies=len(deliveries),fact_age_seconds_p95=percentile(ages),
        task_executed=False,service_operations=operations),deliveries,mapping


def read_body(raw):
    import json
    return json.loads(raw)


def run(output):
    out=Path(output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E2-007'):
        raise ValueError('Output outside E2-007')
    out.mkdir(parents=True,exist_ok=False);snap=out/'source';snap.mkdir()
    for name in ('wireless_trace_replay.py','heteromrta_wireless_eval.py','wireless_broadcast_service.py',
                 'heteromrta_demand_execution.py','heteromrta_causal.py','message_service.py'):
        (snap/name).write_bytes((ROOT/'simulation'/name).read_bytes())
    (out/'WIRELESS_SERVICE_CONTRACT.md').write_bytes(CONTRACT.read_bytes())
    source_cases=read_json(SCALE_ROOT/'summary.json')['cases']
    manifest=dict(command=sys.argv,source_summary=str(SCALE_ROOT/'summary.json'),
        source_summary_sha256=digest(SCALE_ROOT/'summary.json'),contract_sha256=digest(CONTRACT),
        source_hashes={p.name:digest(p) for p in snap.iterdir()},planned=60,task_episodes=0,
        mac_seeds=[0,1,2],policies=['fifo','latest_state'],seconds_per_model_unit=20,cases=[])
    write_json(out/'manifest.json',manifest)
    rows=[]
    for ref in source_cases:
        source_dir=SCALE_ROOT/ref['case_id']
        messages_path=archived_file(source_dir,'messages')
        result_path=archived_file(source_dir,'result')
        messages=read_json(messages_path);horizon=ref['end_time']
        for seed in (0,1,2):
            for policy in ('fifo','latest_state'):
                case_id=ref['case_id']+f'-mac{seed}-{policy}'
                case=out/case_id;case.mkdir()
                record=dict(case_id=case_id,source_case=ref['case_id'],task_seed=ref['seed'],
                    agents=ref['agents'],tasks=ref['tasks'],mac_seed=seed,policy=policy,
                    messages_path=str(messages_path),messages_sha256=digest(messages_path),
                    reference_result_path=str(result_path),reference_result_sha256=digest(result_path))
                write_json(case/'config.json',record)
                service=service_factory(policy,seed)
                began=time.perf_counter()
                try:
                    result,deliveries,mapping=replay_messages(messages,service,horizon)
                    result.update(status='completed',wall_seconds=time.perf_counter()-began,**record)
                    write_json(case/'deliveries.json',deliveries)
                    write_json(case/'mapping.json',mapping)
                except Exception:
                    import traceback
                    result=dict(status='error',error=traceback.format_exc(),**record)
                write_json(case/'service_ledger.json',service.ledger)
                write_json(case/'result.json',result)
                manifest['cases'].append(record);write_json(out/'manifest.json',manifest)
                stats=result.get('drained_stats',{})
                row=dict(case_id=case_id,agents=ref['agents'],tasks=ref['tasks'],task_seed=ref['seed'],
                    mac_seed=seed,policy=policy,status=result['status'],
                    demanded=stats.get('demanded'),delivered=stats.get('delivered'),
                    collided=stats.get('collided'),replaced=stats.get('replaced'),dropped=stats.get('dropped'),
                    pending_at_window=result.get('window_stats',{}).get('pending'),
                    recipient_delivered=stats.get('recipient_delivered'),
                    application_bytes=stats.get('demand_application_bytes'),
                    airtime_attempt_us=stats.get('airtime_attempt_us'),channel_busy_us=stats.get('channel_busy_us'),
                    fact_age_seconds_p95=result.get('fact_age_seconds_p95'),
                    drain_after_window_seconds=result.get('drain_after_window_seconds'))
                rows.append(row);write_json(out/'summary.json',dict(planned=60,cases=rows))
                print(case_id,result['status'],stats.get('collided'),stats.get('replaced'),flush=True)
    with (out/'cases.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return 0 if len(rows)==60 and all(r['status']=='completed' for r in rows) else 1


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args()
    return run(args.output)

if __name__=='__main__':
    raise SystemExit(main())
