"""Read frozen causal-task logs; no environment, policy, or network execution.

Counts protocol publications and syntactic cache references, not necessary or
useful information. Output is exclusive-create beneath outputs/E1-005.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / 'simulation/results/2026-10-25-E1-004-causal'
RUNS = ('20261025-02-delay', '20261025-03-fifo')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json(base, sources):
    matches = [p for p in (base, base.with_suffix(base.suffix + '.gz')) if p.is_file()]
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one input: {base}')
    path = matches[0]
    stored = path.read_bytes()
    raw = gzip.decompress(stored) if path.suffix == '.gz' else stored
    sources.append(dict(path=path.relative_to(ROOT).as_posix(), stored_sha256=sha(stored),
                        raw_sha256=sha(raw), stored_bytes=len(stored), raw_bytes=len(raw)))
    return json.loads(raw)


def coalition_requirement(agents, requirements):
    """Exhaustive static feasibility; ignores location, availability, and time."""
    ids = sorted(agents, key=int)
    for size in range(1, len(ids) + 1):
        feasible = []
        for members in itertools.combinations(ids, size):
            ability = [sum(agents[i]['abilities'][k] for i in members)
                       for k in range(len(requirements))]
            if all(a >= r for a, r in zip(ability, requirements)):
                feasible.append(members)
        if feasible:
            species_counts = [len({agents[i]['species'] for i in members}) for members in feasible]
            return dict(min_members=size, min_size_coalitions=len(feasible),
                        min_species_among_min_size=min(species_counts),
                        max_species_among_min_size=max(species_counts))
    return dict(min_members=None, min_size_coalitions=0,
                min_species_among_min_size=None, max_species_among_min_size=None)


def body_key(body):
    if body['kind'] == 'self_state':
        return ('self_state', str(body['source'])), body['state']['seq']
    return ('task_scene', str(body['scene']['task'])), body['scene']['version']


def cache_reference_counts(decisions, evidence, messages, events):
    """Replay each local evidence prefix; trace which cache origin was referenced.

    The frozen observation builder iterates all source states and all task scenes.
    Reference means present in that cache when constructing obs/mask/branch. It
    does not imply an action change or causal necessity. Local observations remain
    separate even when the identical body also arrives through the network.
    """
    by_mid = {m['message_id']: m for m in messages}
    by_eid = {e['id']: e for e in events}
    actor_decisions = defaultdict(list)
    for d in decisions:
        actor_decisions[str(d['actor'])].append(d)
    counts = Counter()
    referenced = Counter()
    for actor, dd in actor_decisions.items():
        state, pos = {}, 0
        evs = evidence[actor]
        for d in dd:
            end = d['evidence_count']
            if not pos <= end <= len(evs):
                raise ValueError('Invalid local evidence prefix')
            for e in evs[pos:end]:
                if not e['applied']:
                    continue
                if e['via'] == 'network':
                    m = by_mid[e['evidence_id']]
                    body = json.loads(m['payload_utf8'])
                    origin = (m['message_id'], int(actor))
                else:
                    event = by_eid[e['evidence_id']]
                    body = dict(kind=e['kind'], source=e['source'])
                    body['state' if e['kind'] == 'self_state' else 'scene'] = event[
                        'state' if e['kind'] == 'self_state' else 'scene']
                    origin = None
                key, version = body_key(body)
                state[key] = (version, origin)
            pos = end
            for source, version in d['source_versions'].items():
                if str(source) == actor:
                    continue
                counts['remote_state_slots'] += 1
                if version == 0:
                    counts['initial_remote_state_slots'] += 1
                    continue
                entry = state[('self_state', str(source))]
                if entry[0] != version or entry[1] is None:
                    raise ValueError('Remote source version origin mismatch')
                counts['network_state_references'] += 1
                referenced[entry[1]] += 1
            for task, version in d['task_versions'].items():
                entry = state[('task_scene', str(task))]
                if entry[0] != version:
                    raise ValueError('Scene version mismatch')
                if entry[1] is None:
                    counts['local_scene_references'] += 1
                else:
                    counts['network_scene_references'] += 1
                    referenced[entry[1]] += 1
    return counts, referenced


def intent_graph(events):
    """Observed same-target intentions, not required communication dependencies."""
    active = {}
    previous_edges = set()
    unique = set()
    added = removed = peak = 0
    for event in events:
        if event['kind'] != 'own_state':
            continue
        s, actor = event['state'], event['actor']
        if s['target'] >= 0 and s['mode'] in ('travel', 'waiting', 'working'):
            active[actor] = s['target']
        else:
            active.pop(actor, None)
        edges = {tuple(sorted((a, b))) for a, b in itertools.combinations(active, 2)
                 if active[a] == active[b]}
        added += len(edges - previous_edges)
        removed += len(previous_edges - edges)
        peak = max(peak, len(edges))
        unique |= edges
        previous_edges = edges
    return dict(intent_pair_births=added, intent_pair_deaths=removed,
                distinct_intent_pairs=len(unique), peak_concurrent_intent_pairs=peak)


def csv_write(path, rows):
    if not rows:
        raise ValueError(f'No rows for {path}')
    with path.open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def case_analysis(base, config, sources):
    data = {name: read_json(base / f'{name}.json', sources) for name in
            ('catalog', 'messages', 'events', 'decisions', 'deliveries', 'view_evidence', 'result')}
    catalog, messages, events = data['catalog'], data['messages'], data['events']
    decisions, deliveries, result = data['decisions'], data['deliveries'], data['result']
    if result['status'] not in ('success', 'horizon_incomplete'):
        raise ValueError('Unexpected case status')
    case_id = base.name
    stage = 'native_instant' if config['condition'] == 'instant' else 'service_diagnostic'
    common = dict(case=case_id, sample_role=stage, tasks=config['tasks'], seed=config['seed'],
                  condition=config['condition'])
    tasks = []
    starts = {e['task']: e for e in events if e['kind'] == 'task_start'}
    finishes = {e['task']: e for e in events if e['kind'] == 'task_finish'}
    co_work_pairs = set()
    worker_incidences = 0
    for tid, task in catalog['tasks'].items():
        minimum = coalition_requirement(catalog['agents'], task['requirements'])
        start = starts.get(int(tid))
        workers = start['workers'] if start else []
        co_work_pairs |= set(itertools.combinations(sorted(workers), 2))
        worker_incidences += len(workers)
        tasks.append({**common, 'task_id': int(tid), 'requirements': json.dumps(task['requirements']),
                      **minimum, 'actual_workers': len(workers),
                      'actual_worker_species': len({catalog['agents'][str(i)]['species'] for i in workers}),
                      'worker_ids': json.dumps(workers), 'start_time': start['time'] if start else None,
                      'finish_time': finishes[int(tid)]['time'] if int(tid) in finishes else None})
    refs, referenced = cache_reference_counts(decisions, data['view_evidence'], messages, events)
    event_lookup = {e['id']: e for e in events}
    delivered_by_mid, applied_by_mid = Counter(), Counter()
    delivered_pairs, applied_pairs = set(), set()
    for d in deliveries:
        key = (d['message_id'], d['recipient'])
        if key in delivered_pairs:
            raise ValueError('Duplicate receiver delivery')
        delivered_pairs.add(key)
        delivered_by_mid[d['message_id']] += 1
        if d['applied']:
            applied_by_mid[d['message_id']] += 1
            applied_pairs.add(key)
    if not set(referenced) <= applied_pairs:
        raise ValueError('Reference without network cache application')
    mr = []
    for m in messages:
        mid = m['message_id']
        raw = m['payload_utf8'].encode('utf-8')
        if len(raw) != m['bytes'] or sha(raw) != m['payload_sha256']:
            raise ValueError('Payload accounting mismatch')
        body = json.loads(raw)
        cause = event_lookup[m['local_evidence']]['cause']
        target = body['state']['target'] if m['kind'] == 'self_state' else body['scene']['task']
        mr.append({**common, 'message_id': mid, 'generated_at': m['generated_at'],
                   'kind': m['kind'], 'cause': cause, 'source': m['source'], 'target': target,
                   'application_bytes': m['bytes'], 'recipient_copies_requested': len(m['recipients']),
                   'recipient_copies_delivered': delivered_by_mid[mid],
                   'recipient_copies_cache_applied': applied_by_mid[mid],
                   'recipient_copies_referenced': sum((mid, i) in referenced for i in m['recipients']),
                   'cache_reference_occurrences': sum(referenced[(mid, i)] for i in m['recipients'])})
    n_agents = len(catalog['agents'])
    if any(set(m['recipients']) != set(range(n_agents)) - {m['source']} for m in messages):
        raise ValueError('Unexpected publication recipient rule')
    app_bytes = sum(m['bytes'] for m in messages)
    if (len(messages) != result['network']['demanded'] or app_bytes != result['network']['demand_application_bytes']
            or len(deliveries) != result['network']['recipient_delivered']):
        raise ValueError('Result and raw logs disagree')
    own_events = [e for e in events if e['kind'] == 'own_state']
    target_changes = 0
    last = {}
    for e in own_events:
        actor, target = e['actor'], e['state']['target']
        if actor in last and target != last[actor]:
            target_changes += 1
        last[actor] = target
    row = {**common, 'agents': n_agents, 'species': len({a['species'] for a in catalog['agents'].values()}),
           'ability_dimensions': len(next(iter(catalog['agents'].values()))['abilities']),
           'success': int(result['success']), 'completed': result['completed'], 'end_time': result['end_time'],
           'makespan_return': result['makespan_return'],
           'static_tasks_requiring_team': sum(t['min_members'] is not None and t['min_members'] > 1 for t in tasks),
           'static_infeasible_tasks': sum(t['min_members'] is None for t in tasks),
           'tasks_started_multi_worker': sum(t['actual_workers'] > 1 for t in tasks),
           'tasks_started_multi_species': sum(t['actual_worker_species'] > 1 for t in tasks),
           'worker_task_incidences': worker_incidences, 'distinct_co_work_pairs': len(co_work_pairs),
           'target_changes_after_first_state': target_changes, **intent_graph(events),
           'messages': len(messages), 'application_bytes': app_bytes,
           'self_state_messages': sum(m['kind'] == 'self_state' for m in messages),
           'task_scene_messages': sum(m['kind'] == 'task_scene' for m in messages),
           'self_state_bytes': sum(m['bytes'] for m in messages if m['kind'] == 'self_state'),
           'task_scene_bytes': sum(m['bytes'] for m in messages if m['kind'] == 'task_scene'),
           'bytes_per_completed_task': app_bytes / result['completed'] if result['completed'] else None,
           'recipient_copies_requested': sum(len(m['recipients']) for m in messages),
           'recipient_copies_delivered': len(deliveries), 'recipient_copies_cache_applied': len(applied_pairs),
           'recipient_copies_referenced': len(referenced),
           'reference_occurrences': sum(referenced.values()),
           'delivered_not_cache_applied': len(delivered_pairs - applied_pairs),
           'applied_not_referenced_by_end': len(applied_pairs - set(referenced)),
           'decisions': len(decisions), 'policy_inferences': sum(d['branch'] == 'infer' for d in decisions),
           'remote_state_slots': refs['remote_state_slots'], 'initial_remote_state_slots': refs['initial_remote_state_slots'],
           'network_state_references': refs['network_state_references'],
           'network_scene_references': refs['network_scene_references'], 'local_scene_references': refs['local_scene_references'],
           'late_closed_task_arrivals': sum(e['kind'] == 'own_state' and e['cause'] == 'own_arrival_closed_task' for e in events)}
    return row, tasks, mr


def aggregate(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in keys)].append(row)
    output = []
    for key, gg in sorted(groups.items()):
        totals = {f'total_{field}': sum(r[field] for r in gg) for field in
                  ('tasks', 'completed', 'messages', 'application_bytes', 'self_state_bytes', 'task_scene_bytes',
                   'recipient_copies_requested', 'recipient_copies_delivered', 'recipient_copies_cache_applied',
                   'recipient_copies_referenced', 'static_tasks_requiring_team', 'tasks_started_multi_worker',
                   'tasks_started_multi_species', 'decisions', 'policy_inferences', 'remote_state_slots',
                   'initial_remote_state_slots', 'network_state_references', 'network_scene_references',
                   'local_scene_references', 'reference_occurrences', 'late_closed_task_arrivals')}
        output.append({**dict(zip(keys, key)), 'cases': len(gg), 'successes': sum(r['success'] for r in gg),
                       'mean_application_bytes': sum(r['application_bytes'] for r in gg) / len(gg),
                       'mean_messages': sum(r['messages'] for r in gg) / len(gg), **totals})
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to(ROOT / 'simulation/outputs/E1-005'):
        parser.error('Output must be beneath simulation/outputs/E1-005')
    out.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    sources, cases, task_rows, message_rows = [], [], [], []
    for run in RUNS:
        folder = ARCHIVE / run
        summary = read_json(folder / 'summary.json', sources)
        manifest = read_json(folder / 'manifest.json', sources)
        if len(summary['cases']) != summary['planned'] or manifest.get('task_wait', 200.) != 200.:
            raise ValueError('Unexpected input run')
        snapshot = folder / 'source/heteromrta_causal.py'
        sources.append(dict(path=snapshot.relative_to(ROOT).as_posix(), stored_sha256=sha(snapshot.read_bytes()),
                            raw_sha256=sha(snapshot.read_bytes()), stored_bytes=snapshot.stat().st_size,
                            raw_bytes=snapshot.stat().st_size))
        for config in summary['cases']:
            row, tt, mm = case_analysis(folder / config['case'], config, sources)
            cases.append(row); task_rows.extend(tt); message_rows.extend(mm)
    if len(cases) != 45 or sum(r['sample_role'] == 'native_instant' for r in cases) != 10:
        raise ValueError('Scope mismatch')
    # Ensure all experimental conditions use the same source task instance.
    catalogs = defaultdict(set)
    for s in sources:
        if '/catalog.json' in s['path']:
            case = Path(s['path']).parent.name
            catalogs['_'.join(case.split('_')[:2])].add(s['raw_sha256'])
    if any(len(hashes) != 1 for hashes in catalogs.values()):
        raise ValueError('Paired catalogs differ')
    csv_write(out / 'cases.csv', cases)
    csv_write(out / 'task_coalitions.csv', task_rows)
    csv_write(out / 'messages.csv', message_rows)
    grouped = aggregate(cases, ('sample_role', 'tasks', 'condition'))
    csv_write(out / 'groups.csv', grouped)
    cause_groups = defaultdict(lambda: Counter())
    for m in message_rows:
        key = (m['sample_role'], m['tasks'], m['condition'], m['kind'], m['cause'])
        cause_groups[key].update(messages=1, application_bytes=m['application_bytes'],
                                 requested_copies=m['recipient_copies_requested'],
                                 delivered_copies=m['recipient_copies_delivered'],
                                 referenced_copies=m['recipient_copies_referenced'])
    cause_rows = [dict(zip(('sample_role', 'tasks', 'condition', 'kind', 'cause'), k), **v)
                  for k, v in sorted(cause_groups.items())]
    csv_write(out / 'message_causes.csv', cause_rows)
    definitions = {
        'native_instant': '10 unique source task instances under resource-relaxed instantaneous information; not field data.',
        'service_diagnostic': '35 paired delayed/FIFO runs; not independent task instances or measured scale degradation.',
        'application_bytes': 'Serialized UTF-8 payload bytes, one publication counted once; no MAC/PHY/ACK/route costs.',
        'recipient_copies': 'Per-message receiver fanout; eight copies per publication at N=9, not eight radio transmissions.',
        'static_min_members': 'Minimum subset size satisfying capability sums with all catalog robots available; not runtime optimum.',
        'actual_co_work_pairs': 'Robot pairs present together in a physical task_start event; undirected, distinct within a case.',
        'intent_pairs': 'Same-target travel/waiting/working states after each own_state event; not consumer dependencies.',
        'cache_reference': 'Applied network body version present when obs/mask/branch reads cache; no causal usefulness claim.',
        'not_referenced': 'No logged decision cache reference before run end; may be overwritten, terminal, or locally known; not useless bytes.',
        'catalog': 'All capabilities, task requirements/locations/durations and depot states are shared free at initialization.',
        'scope': 'Static known task catalog, three capability species, equal-speed abstract robots; no sensor payload, contact geometry, task discovery or new entrants.'}
    output = dict(groups=grouped, role_totals=aggregate(cases, ('sample_role',)),
                  cases=len(cases), task_rows=len(task_rows), message_rows=len(message_rows),
                  unique_task_instances=len(catalogs), definitions=definitions)
    (out / 'summary.json').write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    manifest = dict(command=sys.argv, python=sys.executable, python_version=platform.python_version(),
                    source_script=dict(path=Path(__file__).relative_to(ROOT).as_posix(), sha256=sha(Path(__file__).read_bytes())),
                    input_files=sources, output_files={p.name:sha(p.read_bytes()) for p in out.iterdir() if p.is_file()},
                    analysis_seconds=time.perf_counter()-started, policy_executions=0, environment_executions=0,
                    scope='read-only census of 45 frozen main episodes; all original evidence untouched')
    (out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(output['role_totals'], ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
