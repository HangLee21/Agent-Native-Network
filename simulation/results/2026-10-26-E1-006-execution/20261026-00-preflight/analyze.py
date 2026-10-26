"""Summarize the completed 30 episodes without executing a policy."""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
root=Path.cwd(); out=Path(a.output); out.mkdir(parents=True,exist_ok=False)
sources=[]; rows=[]
def read(path):
    raw=path.read_bytes(); sources.append({'path':str(path.relative_to(root)), 'sha256':hashlib.sha256(raw).hexdigest()})
    return json.loads(raw)
for group,run in [('legacy','20261026-01-legacy'),('recovery','20261026-02-recovery'),('scale','20261026-03-scale')]:
    folder=root/'simulation/outputs/E1-006'/run
    summary=read(folder/'summary.json')
    assert summary['planned']==len(summary['cases'])==10
    for s in summary['cases']:
        case=folder/s['case_id']; r=read(case/'result.json'); config=read(case/'config.json')
        events=read(case/'events.json'); messages=read(case/'messages.json'); ledger=read(case/'information_ledger.json')
        kinds=Counter(x['kind'] for x in ledger); facts={x['id']:x for x in ledger if x['kind']=='information_acquired'}
        origins=Counter(); unknown=0
        for c in ledger:
            if c['kind']!='information_consulted': continue
            for ref in c['references']:
                if ref['fact_id'] is None:
                    assert ref['knowledge']=='unknown'; unknown+=1
                else:
                    fact=facts[ref['fact_id']]
                    assert fact['actor']==c['actor'] and fact['ordinal']<c['ordinal']
                    origins[fact['origin']]+=1
        net=r['network']
        rows.append(dict(group=group,case_id=s['case_id'],seed=r['seed'],agents=r['agents'],tasks=r['tasks'],
                         condition=r['condition'],recovery=r['recovery'],status=r['status'],
                         completed=r['completed'],makespan_return=r['makespan_return'],end_time=r['end_time'],
                         messages=net['demanded'],application_bytes=net['demand_application_bytes'],
                         recipient_copies=net['recipient_demand'],delivered_copies=net['recipient_delivered'],
                         decisions=r['decisions'],policy_calls=sum(x['kind']=='decision' and x['branch']=='infer' for x in events),
                         task_starts=sum(x['kind']=='task_start' for x in events),
                         wait_cancels=sum(x['kind']=='local_wait_cancel' for x in events),
                         legacy_wait_timeouts=sum(x['kind']=='local_wait_timeout' for x in events),
                         late_closed_task_arrivals=sum(x['kind']=='own_state' and x['cause']=='own_arrival_closed_task' for x in events),
                         information_records=len(ledger),information_log_bytes=(case/'information_ledger.json').stat().st_size,
                         information_consultations=kinds['information_consulted'],unknown_scene_references=unknown,
                         initial_references=origins['initial'],local_references=origins['local'],network_references=origins['network'],
                         counted_event_records=r['budget_event_records'],wall_seconds=r['wall_seconds'],
                         legacy_equal=all(v['equal'] for v in r.get('legacy_comparison',{}).values()) if group=='legacy' else None,
                         catalog_sha256=r['catalog_sha256'],families=';'.join(config.get('families',[]))))
with (out/'cases.csv').open('x',encoding='utf8',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=[]
for group in ('legacy','recovery','scale'):
    subset=[r for r in rows if r['group']==group]
    groups.append(dict(group=group,cases=len(subset),statuses=dict(Counter(r['status'] for r in subset)),
                       messages=sum(r['messages'] for r in subset),application_bytes=sum(r['application_bytes'] for r in subset),
                       information_records=sum(r['information_records'] for r in subset),
                       information_log_bytes=sum(r['information_log_bytes'] for r in subset),
                       decisions=sum(r['decisions'] for r in subset),task_starts=sum(r['task_starts'] for r in subset),
                       wait_cancels=sum(r['wait_cancels'] for r in subset),
                       max_counted_event_records=max(r['counted_event_records'] for r in subset)))
body=dict(cases=30,groups=groups,source_files=sources,analysis_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          definitions=dict(information_references='syntactic references to logged initial/local/network cache origins, not causal usefulness',
                           application_bytes='one serialized publication, receiver fanout charged once, not airtime',
                           wall_seconds='includes Python imports and model loading; not robot inference latency',
                           scope='recovery package and instantaneous-information workload feasibility; no wireless scale effect'))
(out/'summary.json').write_text(json.dumps(body,indent=2)+'\n',encoding='utf8')
print(json.dumps(groups,indent=2))
