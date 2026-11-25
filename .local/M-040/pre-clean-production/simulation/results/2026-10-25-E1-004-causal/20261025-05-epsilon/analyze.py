"""Read saved episodes, create one new derived JSON; never rerun a simulation."""
import collections
import gzip
import hashlib
import json
from pathlib import Path
import statistics
import sys

BASE=Path(__file__).resolve().parent.parent
inputs=[]

def read(path):
    actual=path if path.exists() else path.with_suffix(path.suffix+'.gz')
    raw=actual.read_bytes()
    inputs.append(dict(path=str(actual.relative_to(BASE)),sha256=hashlib.sha256(raw).hexdigest()))
    return json.loads(gzip.decompress(raw) if actual.suffix=='.gz' else raw)

groups=[]
paired=[]
all_cases=[]
for run in ['20261025-02-delay','20261025-03-fifo','20261025-04-wait20','20261025-05-epsilon']:
    cases=read(BASE/run/'summary.json')['cases']
    all_cases+=cases
    grouped=collections.defaultdict(list)
    for c in cases: grouped[(c['tasks'],c['condition'])].append(c)
    for (tasks,condition),cc in grouped.items():
        ok=[c for c in cc if c['success']]
        groups.append(dict(run=run,tasks=tasks,condition=condition,attempts=len(cc),successes=len(ok),
          mean_completion=statistics.mean(c['completion_fraction'] for c in cc),
          mean_success_makespan=statistics.mean(c['makespan_return'] for c in ok) if ok else None,
          mean_capped_makespan=statistics.mean(c['capped_makespan'] for c in cc),
          mean_published_bytes=statistics.mean(c['network']['demand_application_bytes'] for c in cc),
          mean_serviced_bytes=statistics.mean(c['network']['serviced_bytes'] for c in cc),
          mean_messages=statistics.mean(c['network']['demanded'] for c in cc),
          rejected=sum(c['network']['dropped'] for c in cc),
          pending_recipient_copies=sum(c['network']['recipient_unmet'] for c in cc),
          mean_episode_delivered_p95=statistics.mean(c['network']['latency_p95'] for c in cc)))
    if run=='20261025-03-fifo':
        for c in cases:
            if c['seed'] not in (0,1,4): continue
            events=read(BASE/run/c['case']/'events.json')
            paired.append(dict(seed=c['seed'],condition=c['condition'],makespan=c['makespan_return'],
                published_bytes=c['network']['demand_application_bytes'],serviced_bytes=c['network']['serviced_bytes'],
                actions=c['actions'],messages=c['network']['demanded'],
                late_visits=sum(e['kind']=='own_state' and e.get('cause')=='own_arrival_closed_task' for e in events),
                delivered_p95=c['network']['latency_p95'],pending_recipient_copies=c['network']['recipient_unmet'],
                message_classes=c['network']['by_kind']))
out=dict(groups=groups,fifo_same_success_seeds=paired,formal_and_diagnostic_cases=len(all_cases),
         original_initial_equal=all(c['original_reference']['initial_equal'] for c in all_cases),
         process_exit_codes=sorted(set(c['process_exit_code'] for c in all_cases)),
         max_event_records=max(c['budget_event_records'] for c in all_cases),
         inputs=inputs,analysis_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
with Path(sys.argv[1]).open('x',encoding='utf-8') as f:
    json.dump(out,f,indent=2); f.write('\n')
print(json.dumps(out,indent=2))
