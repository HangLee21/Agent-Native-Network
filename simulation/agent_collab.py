"""Local request/observation/result state machines over a fixed contact network."""
from dataclasses import dataclass, asdict
from pathlib import Path
from collections import defaultdict
import csv
import gzip
import hashlib
import json
import random

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'simulation/results/2026-10-22-agent-collab-v1'
POLICIES = ('independent', 'ideal', 'fifo', 'priority', 'on_demand')


@dataclass(frozen=True)
class Config:
    rate: int = 1024
    background: int = 65536
    result_size: int = 512
    need: float = 0.5
    intermittent: bool = True
    horizon: int = 600


def episode(cfg, policy, seed, keep=False):
    assert policy in POLICIES and cfg.rate > 0 and cfg.horizon >= 510
    rng = random.Random(seed)
    # Separate RNG streams keep tasks invariant under network parameters.
    phases = {i: random.Random(seed*31+i+1000).randrange(120) for i in range(3)}
    tasks = [dict(id=i, owner=i//6, release=(i%6)*60, need=rng.random()<cfg.need,
                  request_arrival=None, service_start=None, result_created=None,
                  result_arrival=None, completed=None, mode=None)
             for i in range(12)]
    queues = [[] for _ in range(4)]
    arrivals, services = defaultdict(list), defaultdict(list)
    events = []; serial = 0; next_service = 0; cursor = 0; total_bytes = 0

    def log(t, event, **kw):
        if keep: events.append(dict(time=t, event=event, **kw))

    def receive(m, t):
        nonlocal next_service
        log(t, 'receive', message=m['id'], kind=m['kind'], task=m['task'], node=m['path'][-1])
        if m['kind'] == 'map': return
        task = tasks[m['task']]
        if m['kind'] == 'request':
            task['request_arrival'] = t
            task['service_start'] = max(t, next_service)
            next_service = task['service_start'] + 5
            services[next_service].append(task['id'])
        else:
            task['result_arrival'] = t
            if task['mode'] is None:
                task.update(mode='collaborative', completed=t+10)

    def send(t, kind, task_id, source, destination, size):
        nonlocal serial
        m = dict(id=serial, kind=kind, task=task_id, created=t, size=size,
                 path=[source, 3, destination])
        serial += 1
        log(t, 'create', message=m['id'], kind=kind, task=task_id, node=source)
        if policy == 'ideal': receive(m, t)
        else: queues[source].append(dict(message=m, hop=0, remaining=size, enqueued=t))

    for t in range(cfg.horizon+1):
        for entry in arrivals.pop(t, []):
            m = entry['message']; hop = entry['hop']; node = m['path'][hop]
            log(t, 'hop_receive', message=m['id'], node=node, hop=hop)
            if hop == 2: receive(m, t)
            else:
                entry.update(remaining=m['size'], enqueued=t)
                queues[node].append(entry)
        for task in tasks:
            if task['release'] == t:
                if not task['need']:
                    task.update(mode='local_easy', completed=t+10)
                elif policy == 'independent':
                    task.update(mode='local', completed=t+90)
                else:
                    send(t, 'request', task['id'], task['owner'], 2, 160)
            if task['mode'] is None and t == task['release']+120:
                task.update(mode='fallback', completed=t+90)
                log(t, 'fallback', task=task['id'], node=task['owner'])
        for task_id in services.pop(t, []):
            task = tasks[task_id]; task['result_created'] = t
            send(t, 'result', task_id, 2, task['owner'], cfg.result_size)
        if t%30 == 0 and cfg.background and policy in ('fifo','priority'):
            for owner in (0,1): send(t, 'map', None, 2, owner, cfg.background)
        if t == cfg.horizon: break
        budget = cfg.rate
        used = 0
        while budget:
            chosen = None
            for offset in range(4):
                node = (cursor+offset)%4
                eligible = []
                for idx, entry in enumerate(queues[node]):
                    dest = entry['message']['path'][entry['hop']+1]
                    endpoint = dest if node == 3 else node
                    connected = not cfg.intermittent or (t+phases[endpoint])%120 < 40
                    if connected:
                        priority = int(entry['message']['kind']=='map') if policy != 'fifo' else 0
                        eligible.append((priority, entry['enqueued'], entry['message']['id'], idx))
                if eligible:
                    chosen = node, min(eligible)[-1]; break
            if chosen is None: break
            node, idx = chosen; entry = queues[node][idx]
            size = min(1024, budget, entry['remaining'])
            entry['remaining'] -= size; budget -= size; used += size
            cursor = (node+1)%4
            if entry['remaining'] == 0:
                queues[node].pop(idx); entry['hop'] += 1
                arrivals[t+1].append(entry)
        assert used <= cfg.rate
        total_bytes += used
    assert all(x['completed'] is not None and x['completed']<=cfg.horizon for x in tasks)
    requests = [x for x in tasks if x['request_arrival'] is not None]
    results = [x for x in tasks if x['result_arrival'] is not None]
    row = dict(mean_completion=sum(x['completed']-x['release'] for x in tasks)/12,
               collaborative=sum(x['mode']=='collaborative' for x in tasks),
               fallback=sum(x['mode']=='fallback' for x in tasks),
               need_count=sum(x['need'] for x in tasks), link_bytes=total_bytes,
               requests_received=len(requests), results_received=len(results),
               request_delay_sum=sum(x['request_arrival']-x['release'] for x in requests),
               service_wait_sum=sum(x['service_start']-x['request_arrival'] for x in requests),
               result_delay_sum=sum(x['result_arrival']-x['result_created'] for x in results),
               pending_messages=sum(map(len,queues))+sum(map(len,arrivals.values())))
    return row, dict(tasks=tasks, events=events, phases=phases)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows, traces = [], []
    for need in (0., .5, 1.):
        for result_size in (512,65536):
            for background in (0,65536):
                for rate in (1024,8192,65536):
                    for intermittent in (False,True):
                        cfg = Config(rate, background, result_size, need, intermittent)
                        for policy in POLICIES:
                            for seed in range(24):
                                row, trace = episode(cfg,policy,seed,seed==0)
                                key = asdict(cfg) | dict(policy=policy,seed=seed)
                                rows.append(key | row)
                                if seed==0: traces.append(key | trace)
    with (OUT/'metrics.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with gzip.open(OUT/'traces_seed0.json.gz','wt',encoding='utf-8') as f: json.dump(traces,f)
    sources=[Path(__file__),ROOT/'simulation/AGENT_COLLAB_PROTOCOL.md']
    (OUT/'metadata.json').write_text(json.dumps(dict(rows=len(rows),seeds=list(range(24)),
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}),indent=2)+'\n')
    print(f'Saved {len(rows)} episodes and {len(traces)} traces to {OUT}')


if __name__=='__main__': main()
