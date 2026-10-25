"""Read existing C-006 evidence only; never import or execute research code.

The sole output is C-006-verification.json beside this review script. This checks
recorded evidence using geometry, byte-service equations, and cache derivation;
it does not rerun a task policy, simulator, protocol, or unit test.
"""
import collections
import copy
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = Path(__file__).with_suffix('.json')
INPUT_HASHES = {}


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    INPUT_HASHES[str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
    return data


def load(path):
    data = raw(path)
    return json.loads(gzip.decompress(data) if Path(path).suffix == '.gz' else data)


def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def close(left, right):
    if isinstance(left, list):
        return isinstance(right, list) and len(left) == len(right) and all(close(x, y) for x, y in zip(left, right))
    return left == right or isinstance(left, (int, float)) and isinstance(right, (int, float)) and math.isclose(left, right, abs_tol=1e-9, rel_tol=1e-9)


def check_service(messages, ledger, deliveries, stats, config, horizon, delivery_hex=False):
    """Independently derive admission, serialization, cutoff costs and deliveries."""
    submitted = [e for e in ledger if e['event'] == 'submitted']
    admitted = {e['message_id']: e for e in ledger if e['event'] == 'admitted'}
    rejected = {e['message_id']: e for e in ledger if e['event'] == 'rejected'}
    by_delivery = collections.defaultdict(list)
    for d in deliveries:
        by_delivery[d['message_id']].append(d)
    assert len(submitted) == len(messages)
    mode = config['mode']
    rate = config['rate_bytes_per_time']
    delay = 0 if mode == 'instant' else config['delay']
    capacity = config.get('capacity_bytes')
    capacity = math.inf if capacity is None else capacity
    tail, served, maximum, delivered_messages, receiver_count = 0., 0., 0, 0, 0
    schedule, latencies = [], []
    all_bytes, refused_bytes = 0, 0
    for e, message in zip(submitted, messages):
        body = bytes.fromhex(e['payload_hex'])
        original = bytes.fromhex(message['payload_hex']) if 'payload_hex' in message else message['payload_utf8'].encode()
        assert body == original and len(body) == e['application_bytes']
        assert hashlib.sha256(body).hexdigest() == e['payload_sha256']
        assert e['time'] == message['generated_at'] <= horizon
        assert e['source'] == message['source'] and e['kind'] == message['kind']
        recipients = list(dict.fromkeys(message['recipients']))
        assert e['recipients'] == recipients
        size = len(body) + config.get('overhead_bytes', 0)
        assert size == e['service_bytes']
        all_bytes += size
        occupied = sum(b for _, finish, _, b, _ in schedule if finish > e['time']) if mode == 'fifo' else 0
        refusal = mode == 'fifo' and occupied + size > capacity
        if refusal:
            assert e['message_id'] in rejected and e['message_id'] not in admitted
            assert rejected[e['message_id']]['unmet_recipients'] == recipients
            assert not by_delivery[e['message_id']]
            refused_bytes += size
            continue
        a = admitted[e['message_id']]
        start = max(e['time'], tail) if mode == 'fifo' else e['time']
        finish = start + size / rate if mode == 'fifo' else start
        arrival = finish + delay
        assert a['service_start'] == start and a['service_finish'] == finish and a['arrival'] == arrival
        tail = finish
        schedule.append((start, finish, arrival, size, len(recipients)))
        maximum = max(maximum, occupied + size) if mode == 'fifo' else 0
        served += max(0, min(size, (horizon - start) * rate)) if mode == 'fifo' else size
        expected = recipients if arrival <= horizon else []
        actual = by_delivery[e['message_id']]
        assert [d['recipient'] for d in actual] == expected
        for d in actual:
            assert d['generated_at'] == e['time'] and d['delivered_at'] == arrival
            if delivery_hex:
                assert bytes.fromhex(d['payload_hex']) == body
            else:
                assert d['payload_sha256'] == e['payload_sha256']
        if expected:
            delivered_messages += 1
            receiver_count += len(expected)
            latencies.append(arrival-e['time'])
    assert math.isclose(served, stats['serviced_bytes'], abs_tol=1e-8)
    assert len(messages) == stats['demanded'] == stats['accepted'] + stats['dropped']
    assert all_bytes == stats['demand_service_bytes']
    assert refused_bytes == stats['rejected_service_bytes']
    assert delivered_messages == stats['delivered'] and receiver_count == stats['recipient_delivered']
    assert stats['recipient_unmet'] == sum(len(m['recipients']) for m in messages) - receiver_count
    assert stats['accepted'] - delivered_messages == stats['pending']
    occupied_h = sum(b for _, f, _, b, _ in schedule if f > horizon) if mode == 'fifo' else 0
    assert occupied_h == stats['buffer_occupied_bytes']
    assert math.isclose(stats['admitted_service_bytes'] - served, stats['remaining_service_bytes'], abs_tol=1e-8)
    if latencies:
        ordered = sorted(latencies)
        location = 0.95*(len(ordered)-1)
        low, high = math.floor(location), math.ceil(location)
        p95 = ordered[low] + (ordered[high]-ordered[low])*(location-low)
        assert math.isclose(p95, stats['latency_p95'], abs_tol=1e-9)
        assert math.isclose(sum(latencies)/len(latencies), stats['latency_mean'], abs_tol=1e-9)
        assert max(latencies) == stats['latency_max']
    else:
        assert stats['latency_p95'] is None and stats['latency_mean'] is None and stats['latency_max'] is None
    return dict(messages=len(messages), delivered=delivered_messages, serviced_bytes=served,
                peak_buffer_at_submission=maximum, pending=stats['pending'], rejected=stats['dropped'])


def observation_from_evidence(catalog, states, scenes, actor, now):
    """Pure calculation from already-read cache facts, with no world reference."""
    plans = {}
    for tid, task in catalog['tasks'].items():
        members = [i for i, s in states.items() if s['target'] == int(tid) and s['mode'] in ('travel', 'waiting', 'working')]
        scene = scenes.get(tid)
        confirmed = bool(scene and scene['phase'] in ('running', 'done'))
        if confirmed:
            members = [str(i) for i in scene['workers']]
        ability = [sum(catalog['agents'][i]['abilities'][j] for i in members) for j in range(5)]
        residual = [x-y for x, y in zip(task['requirements'], ability)]
        feasible = confirmed or all(x <= 0 for x in residual)
        start = scene['started_at'] if confirmed else max([states[i]['arrival'] for i in members], default=0.) if feasible else 0.
        plans[tid] = dict(residual=residual, feasible=feasible, start=start, duration=task['time'])
    mine = states[actor]
    loc = mine['destination']
    own = catalog['agents'][actor]
    velocity, depot = own['velocity'], own['depot']
    task_rows = [[0.]*5 + [-1.]*5 + [0., math.dist(loc, depot)/velocity] + [x-y for x, y in zip(loc, depot)] + [1.]]
    agent_rows, mask = [], [False]
    for tid, task in catalog['tasks'].items():
        plan = plans[tid]
        task_rows.append(plan['residual'] + task['requirements'] + [task['time'], math.dist(loc, task['location'])/velocity] + [x-y for x, y in zip(loc, task['location'])] + [plan['feasible']])
        useful = sum(max(min(x, y), 0) for x, y in zip(plan['residual'], own['abilities'])) > 0
        mask.append(plan['feasible'] or not useful)
    for i, info in catalog['agents'].items():
        state = states[i]
        travel = waiting = remaining = 0.
        if state['target'] >= 0:
            plan = plans[str(state['target'])]
            travel = max(state['arrival']-now, 0.)
            if now <= plan['start']:
                waiting = max(now-state['arrival'], 0.)
                remaining = max(plan['start']+plan['duration']-now, 0.)
        agent_rows.append(info['abilities'] + [travel, remaining, waiting] + [x-y for x, y in zip(loc, state['destination'])] + [state['mode'] == 'working'])
    all_feasible = all(p['feasible'] for p in plans.values())
    branch = 'no_choice' if all(mask[1:]) and not all_feasible else 'skip_at_depot' if all(mask[1:]) and all_feasible and mine['target'] < 0 else 'infer'
    return [[task_rows], [agent_rows], [mask]], branch


def check_closed_loop(base, row, manifest):
    case = base / row['case']
    result = load(case/'result.json')
    catalog, initial = load(case/'catalog.json'), load(case/'initial.json')
    events, decisions = load(case/'events.json'), load(case/'decisions.json')
    messages, deliveries = load(case/'messages.json'), load(case/'deliveries.json')
    evidence, final = load(case/'view_evidence.json'), load(case/'final.json')
    ledger = load(case/'service_ledger.json')
    reference_run = '20261023-02' if result['tasks'] == 15 else '20261023-03'
    original = ROOT/'simulation/results/2026-10-23-E1-002-heteromrta'/reference_run/f"seed-{result['seed']:03d}-policy"/'initial.json.gz'
    assert initial == load(original)
    assert result['executor_sha256'] == manifest['source_hashes']['heteromrta_causal.py']
    assert row['process_exit_code'] == 0 and all(row[k] == v for k, v in result.items())
    by_id = {m['message_id']: m for m in messages}
    by_local = {m['local_evidence']: m for m in messages}
    bodies = {mid: json.loads(m['payload_utf8']) for mid, m in by_id.items()}
    by_delivery = {(d['recipient'], d['message_id']): d for d in deliveries}
    assert len(by_id) == len(messages) and len(by_delivery) == len(deliveries)
    for m in messages:
        body = bodies[m['message_id']]
        event = events[m['local_evidence']]
        assert body['generated_at'] == m['generated_at'] == event['time']
        assert body['source'] == m['source'] == event['actor']
        field = 'state' if body['kind'] == 'self_state' else 'scene'
        assert body[field] == event[field]
    states, scenes, consumed = {}, {}, {}
    for actor in catalog['agents']:
        states[actor] = {i: dict(source=int(i), seq=0, target=-1, mode='idle', origin=a['depot'], destination=a['depot'], departure=0., arrival=0., changed_at=0., finish=None) for i, a in catalog['agents'].items()}
        scenes[actor], consumed[actor] = {}, 0
    local_wakes = collections.defaultdict(set)
    for event in events:
        if event['kind'] in ('arrival', 'local_retry_timer', 'local_wait_timeout'):
            local_wakes[event['time']].add(event['actor'])
        if event['kind'] == 'task_finish':
            local_wakes[event['time']].update(event['workers'])
    network_wakes = collections.defaultdict(set)
    for actor, rows in evidence.items():
        for e in rows:
            if e['via'] == 'network' and e['applied']:
                network_wakes[e['at']].add(int(actor))
    for decision in decisions:
        actor = str(decision['actor'])
        cache, observed = states[actor], scenes[actor]
        for e in evidence[actor][consumed[actor]:decision['evidence_count']]:
            message = by_id[e['evidence_id']] if e['via'] == 'network' else by_local[e['evidence_id']]
            body = bodies[message['message_id']]
            if e['via'] == 'network':
                assert by_delivery[(int(actor), message['message_id'])]['delivered_at'] == e['at']
            elif body['kind'] == 'self_state':
                assert body['source'] == int(actor)
            else:
                assert int(actor) in body['scene']['witnesses']
            assert message['generated_at'] <= e['at'] <= decision['time']
            if body['kind'] == 'self_state':
                key = str(body['source'])
                applied = body['state']['seq'] > cache[key]['seq']
                if applied:
                    cache[key] = copy.deepcopy(body['state'])
            else:
                scene = body['scene']
                key = str(scene['task'])
                previous = observed.get(key)
                applied = not previous or previous['phase'] != 'done' and scene['version'] > previous['version']
                if applied:
                    observed[key] = copy.deepcopy(scene)
            assert bool(applied) == e['applied']
        consumed[actor] = decision['evidence_count']
        assert hashlib.sha256(encode(dict(states=cache, scenes=observed))).hexdigest() == decision['view_sha256']
        assert {i: s['seq'] for i, s in cache.items()} == decision['source_versions']
        assert {i: s['version'] for i, s in observed.items()} == decision['task_versions']
        obs, branch = observation_from_evidence(catalog, cache, observed, actor, decision['time'])
        assert close(obs, decision['observation']) and branch == decision['branch']
        if decision['action'] is not None:
            assert not obs[2][0][decision['action']]
        assert decision['time'] == 0 or int(actor) in local_wakes[decision['time']] | network_wakes[decision['time']]
    positions = {i: a['depot'] for i, a in catalog['agents'].items()}
    moving, locked, starts, finished, last_decision = {}, {}, {}, {}, {}
    own_modes = {i: dict(mode='idle', target=-1) for i in catalog['agents']}
    first_return = None
    decision_events = 0
    for event in events:
        kind, actor, now = event['kind'], str(event.get('actor')), event['time']
        if kind == 'own_state':
            own_modes[actor] = event['state']
        if kind == 'decision':
            assert actor not in moving and actor not in locked
            last_decision[actor] = event
            decision_events += 1
        elif kind == 'departure':
            assert actor not in moving and actor not in locked
            assert last_decision[actor]['time'] == now == event['departure'] == event['decision_time']
            assert last_decision[actor]['action'] - 1 == event['target']
            assert close(positions[actor], event['origin'])
            assert math.isclose(math.dist(event['origin'], event['destination']), event['distance'], abs_tol=1e-9)
            assert math.isclose(now+event['distance']/catalog['agents'][actor]['velocity'], event['arrival'], abs_tol=1e-9)
            moving[actor] = event
        elif kind == 'arrival':
            leg = moving.pop(actor)
            assert math.isclose(now, leg['arrival'], abs_tol=1e-9) and close(event['position'], leg['destination'])
            positions[actor] = event['position']
        elif kind == 'task_start':
            tid = str(event['task'])
            assert tid not in starts
            starts[tid] = event
            for member in event['workers']:
                key = str(member)
                assert key not in moving and key not in locked
                assert close(positions[key], catalog['tasks'][tid]['location'])
                locked[key] = tid
            ability = [sum(catalog['agents'][str(i)]['abilities'][j] for i in event['workers']) for j in range(5)]
            assert ability == event['ability'] and all(x >= y for x, y in zip(ability, catalog['tasks'][tid]['requirements']))
        elif kind == 'task_finish':
            tid = str(event['task'])
            assert tid not in finished
            finished[tid] = event
            assert math.isclose(now, starts[tid]['time']+catalog['tasks'][tid]['time'], abs_tol=1e-9)
            for member in event['workers']:
                assert locked.pop(str(member)) == tid
        elif kind == 'onsite_observation':
            scene = event['scene']
            tid = str(scene['task'])
            assert int(actor) in scene['witnesses'] and set(scene['workers']).issubset(scene['witnesses'])
            assert scene['observed_at'] == now
            for member in scene['witnesses']:
                key = str(member)
                assert key not in moving and close(positions[key], catalog['tasks'][tid]['location'])
                assert close(positions[key], event['witness_positions'][key])
        if first_return is None and len(finished) == len(catalog['tasks']) and all(a['mode'] == 'idle' and a['target'] < 0 for a in own_modes.values()):
            first_return = now
    assert decision_events == len(decisions) == result['decisions']
    assert len(finished) == result['completed']
    assert result['completion_fraction'] == len(finished)/len(catalog['tasks'])
    returned = sum(a['mode'] == 'idle' and a['target'] < 0 for a in final['actors'].values())
    assert returned == result['returned']
    if result['success']:
        assert len(finished) == len(catalog['tasks']) and returned == len(catalog['agents'])
        assert result['makespan_return'] == result['end_time']
        assert all(close(positions[i], a['depot']) for i, a in catalog['agents'].items())
    else:
        assert result['makespan_return'] is None
    assert first_return == result['makespan_return']
    routes = [r for a in final['actors'].values() for r in a['route']]
    assert len(routes) == result['actions']
    actual = sum(r['distance']*min(max((result['end_time']-r['departure'])/(r['arrival']-r['departure']), 0.), 1.) if r['arrival'] > r['departure'] else 0. for r in routes)
    if 'actual_travel_distance' in result:
        assert math.isclose(actual, result['actual_travel_distance'], abs_tol=1e-9)
    service_check = check_service(messages, ledger, deliveries, result['network'],
        dict(mode=result['mode'], delay=result['delay'], rate_bytes_per_time=result['rate'], capacity_bytes=result['capacity'], overhead_bytes=0), result['end_time'])
    waiting_sites = {}
    for actor, state in final['actors'].items():
        if state['mode'] == 'waiting':
            waiting_sites.setdefault(str(state['target']), []).append(int(actor))
    waiting_details = []
    for tid, members in waiting_sites.items():
        waiting_details.append(dict(task=int(tid), members=members,
            capability=[sum(catalog['agents'][str(i)]['abilities'][j] for i in members) for j in range(5)],
            requirements=catalog['tasks'][tid]['requirements']))
    return dict(run=base.name, case=case.name, tasks=result['tasks'], seed=result['seed'],
                condition=row['condition'], task_wait=manifest['task_wait'], status=result['status'],
                completed=result['completed'], completion_fraction=result['completion_fraction'],
                returned=returned, makespan_return=result['makespan_return'], end_time=result['end_time'],
                decisions=len(decisions), actions=len(routes), messages=len(messages),
                delivered_recipients=len(deliveries), physical_starts=len(starts),
                application_bytes=sum(m['bytes'] for m in messages), service=service_check,
                serviced_bytes_per_completed_task=service_check['serviced_bytes']/result['completed'] if result['completed'] else None,
                initial_actions=[dict(actor=d['actor'], action=d['action']) for d in decisions if d['time'] == 0],
                wait_timeouts=sum(e['kind'] == 'local_wait_timeout' for e in events),
                late_visits=sum(e['kind'] == 'own_state' and e['cause'] == 'own_arrival_closed_task' for e in events),
                final_waiting_sites=waiting_details,
                checks='pass')


def main():
    results, replays, errors, runs, test_logs = [], [], [], [], []
    for summary_path in sorted((ROOT/'simulation/outputs/E1-004').glob('*/summary.json')):
        base = summary_path.parent
        summary, manifest = load(summary_path), load(base/'manifest.json')
        for name, expected in manifest['source_hashes'].items():
            assert sha(base/'source'/name) == expected
        assert sha(ROOT/'simulation/heteromrta_eval.py') == manifest['inherited_eval_sha256']
        for asset in manifest['assets']:
            assert sha(ROOT/'data/heteromrta/upstream'/asset['path']) == asset['sha256']
        runs.append(dict(run=base.name, planned=summary['planned'], recorded=len(summary['cases']), source_hashes=manifest['source_hashes']))
        for row in summary['cases']:
            try:
                results.append(check_closed_loop(base, row, manifest))
            except Exception as error:
                import traceback
                errors.append(dict(case=row['case'], run=base.name, error=repr(error), traceback=traceback.format_exc()))
    for test_manifest in sorted((ROOT/'simulation/outputs/E1-004').glob('*/unit-test-evidence.json')):
        test = load(test_manifest)
        assert test['exit_code'] == 0
        assert sha(test_manifest.parent/'unit-tests.txt') == test['log_sha256']
        for name, expected in test['source_hashes'].items():
            assert sha(test_manifest.parent/'source'/name) == expected
        test_logs.append(dict(path=str(test_manifest.relative_to(ROOT)), tests=test['tests'],
                              exit_code=0, provenance=test['provenance']))
    service_test_dir = ROOT/'simulation/outputs/E2-005/20261025-01-verification'
    test = load(service_test_dir/'manifest.json')
    assert test['exit_code'] == 0
    for name, expected in test['source_sha256'].items():
        assert sha(service_test_dir/'source_snapshot'/name) == expected
    test_text = raw(service_test_dir/'test_stderr.txt').decode()
    assert 'Ran 10 tests' in test_text and '\nOK' in test_text
    test_logs.append(dict(path=str((service_test_dir/'manifest.json').relative_to(ROOT)),
                         tests=test['checks_count'], exit_code=0, provenance='saved subprocess stderr'))
    replay_root = ROOT/'simulation/outputs/E2-005/20261025-02-frozen-pilot'
    for path in sorted(replay_root.glob('*/manifest.json')):
        base, manifest = path.parent, load(path)
        for name, expected in manifest['source_sha256'].items():
            assert sha(base/'source_snapshot'/name) == expected
            assert sha(ROOT/'simulation'/name) == expected
        assert sha(base/'input_catalogue.json') == manifest['input_sha256']
        for name, expected in manifest['output_sha256'].items():
            assert sha(base/name) == expected
        result = load(base/'result.json')
        check = check_service(load(base/'input_catalogue.json'), load(base/'ledger.json'), load(base/'deliveries.json'), result['stats'], manifest['config'], manifest['horizon'], delivery_hex=True)
        replays.append(dict(condition=base.name, checks='pass', **check))
    grouped = collections.defaultdict(list)
    for r in results:
        grouped[(r['run'], r['tasks'], r['condition'], r['task_wait'])].append(r)
    aggregate = []
    for (run, tasks, condition, wait), rows in grouped.items():
        success = [r for r in rows if r['status'] == 'success']
        aggregate.append(dict(run=run, tasks=tasks, condition=condition, task_wait=wait,
            cases=len(rows), successes=len(success), completion_mean=sum(r['completion_fraction'] for r in rows)/len(rows),
            success_makespan_mean=sum(r['makespan_return'] for r in success)/len(success) if success else None,
            application_bytes_mean=sum(r['application_bytes'] for r in rows)/len(rows)))
    figure_dir = ROOT/'simulation/results/2026-10-25-E1-004-causal/figures'
    figure_rows = list(csv.DictReader(io.StringIO(raw(figure_dir/'source_data.csv').decode('utf-8-sig'))))
    profile = load(figure_dir/'profile.json')
    for source in profile['sources']:
        assert sha(ROOT/source['path']) == source['sha256']
    for row in figure_rows:
        case = ROOT/row['source_case']
        result_path = case/'result.json'
        if not result_path.exists():
            result_path = case/'result.json.gz'
        result = load(result_path)
        for name in ('tasks', 'seed', 'completion_fraction', 'capped_makespan'):
            assert float(row[name]) == result[name]
        assert bool(int(row['success'])) == result['success'] and row['status'] == result['status']
        assert (float(row['makespan_return']) if row['makespan_return'] else None) == result['makespan_return']
        for name, key in (('messages','demanded'), ('application_bytes','demand_application_bytes'), ('delivered','delivered'), ('pending','pending'), ('dropped','dropped'), ('latency_p95','latency_p95')):
            assert float(row[name]) == result['network'][key]
        assert row['initial_sha256'] == result['initial_sha256']
    assert len(figure_rows) == profile['rows'] == 55
    assert sum(not r['makespan_return'] for r in figure_rows) == profile['missing_return_times'] == 11
    report = dict(scope='Read-only existing-evidence reconstruction; no policy, simulation, protocol or test execution',
        verifier_sha256=sha(Path(__file__)), runs=runs, closed_loop_cases=len(results),
        decisions=sum(r['decisions'] for r in results), messages=sum(r['messages'] for r in results),
        physical_starts=sum(r['physical_starts'] for r in results), cases=results,
        aggregates=aggregate, fixed_replays=replays, inspected_test_logs=test_logs,
        figure_data=dict(rows=55, missing_return_times=11, checks='pass'),
        errors=errors, input_sha256=INPUT_HASHES)
    OUTPUT.write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8', newline='\n')
    print(json.dumps({k:report[k] for k in ('closed_loop_cases','decisions','messages','physical_starts','errors')}, indent=2))
    print('fixed_replays:', len(replays), 'saved:', OUTPUT)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
