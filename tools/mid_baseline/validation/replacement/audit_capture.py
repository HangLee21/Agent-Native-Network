"""Supplement already analyzed captures with raw mechanism/software evidence.

Does not call analyze(), capture devices, solve, or modify upstream contexts.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

import analysis


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    with path.open('x', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write('\n')


def audit(source):
    data = analysis.strict(source.read_bytes())
    assert not data['issues'], 'capture issues must remain unresolved, do not promote pair'
    log = Path(data['source_logs'][0]['path'])
    context = Path(data['source_context']['path'])
    ctx = analysis.strict(context.read_bytes())
    rows = [analysis.strict(line) for line in log.read_bytes().splitlines()]
    events = [(i, r) for i, r in enumerate(rows, 1) if r.get('kind') == 'device_rx']
    t0 = ctx['schedule_t0_ns']
    infos_file = context.parent / 'infos.json'
    infos = analysis.strict(infos_file.read_bytes())
    config, info_sources = {}, {}
    for label, info in sorted(infos.items()):
        matches = [(i, r) for i, r in events if r.get('event') == info and r['host_monotonic_ns'] <= t0]
        assert matches and info.get('ok') is True and info.get('cmd') == 'info'
        mac = info['node_id']
        assert info['boot_id'] == ctx['boots'][mac] and type(info.get('uart_baud')) is int
        config[mac] = dict(build_id=info['build_id'], uart_baud=info['uart_baud'])
        info_sources[label] = dict(path=str(log), line=matches[0][0])
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':')).encode()
    software_id = 'sha256:' + hashlib.sha256(canonical).hexdigest()
    annotations = data['annotations']
    times = {}
    raw_proofs = {}
    for name in ('retire_effective', 'spare_active'):
        note = next(a for a in annotations if a['name'] == name)
        ref = note['raw_source']
        assert Path(ref['path']).resolve() == log.resolve()
        row = rows[ref['line'] - 1]
        event = row['event']
        assert row['kind'] == 'device_rx' and event['ok'] is True
        assert row['host_monotonic_ns'] == note['original_host_ns']
        if name == 'retire_effective':
            assert event['radio'] is False and event['stopping'] is False
        else:
            assert event['radio'] is True
        times[name] = (row['host_monotonic_ns'] - t0) / 1e9
        raw_proofs[name] = dict(path=str(log), line=ref['line'], event=event)
    labels = {label: info['node_id'] for label, info in infos.items()}
    event_index = {}
    for line, envelope in events:
        event = envelope['event']
        identity = tuple(event.get(k) for k in ('origin', 'origin_boot', 'seq', 'dst'))
        event_index.setdefault(identity, []).append((line, envelope))

    def complete_path(packet, chain, low, high):
        if not packet['delivered'] or not packet['identity']:
            return None
        candidates = event_index.get(tuple(packet['identity']), [])
        found = []
        requirements = [(chain[0], 'tx_submit', chain[1])]
        for a, b in zip(chain[1:-1], chain[2:]):
            requirements.extend([(a, 'rx_relay', None), (a, 'tx_submit', b)])
        requirements.append((chain[-1], 'rx_local', None))
        for node, event_name, next_hop in requirements:
            matches = [(line, r) for line, r in candidates if low <= r['host_monotonic_ns'] < high
                       and r['event'].get('node_id') == labels[node] and r['event'].get('event') == event_name
                       and (next_hop is None or r['event'].get('next_hop') == labels[next_hop])]
            if not matches:
                return None
            line, row = matches[0]
            found.append(dict(path=str(log), line=line, event=event_name, node=node,
                              next_hop=next_hop, host_ns=row['host_monotonic_ns']))
        return dict(direction=packet['direction'], slot=packet['slot'], identity=packet['identity'], chain=chain, evidence=found)

    trigger_ns = t0 + round(times['retire_effective'] * 1e9)
    pre_paths = []
    for direction, chain in ((0, list('ACDB')), (1, list('BDCA'))):
        paths = [complete_path(p, chain, trigger_ns - 10000000000, trigger_ns)
                 for p in data['packets'] if p['direction'] == direction]
        paths = [p for p in paths if p]
        assert paths, 'retired C and D must actually relay before trigger'
        pre_paths.append(paths[-1])
    after_paths = []
    solve = None
    if data['arm'] == 'replan':
        begin = next(a for a in annotations if a['name'] == 'solve_start')
        end = next(a for a in annotations if a['name'] == 'solve_end')
        assert begin['host_monotonic_ns'] >= trigger_ns and end['exit_code'] == 0
        assert begin['request']['members'] == list('ABDE') and begin['request']['phase'] == 'after'
        solved = analysis.strict((context.parent/'after-solve/result.json').read_bytes())
        assert solved['status'] == 'optimal'
        during = [p for p in data['packets'] if begin['host_monotonic_ns'] <= p['planned_ns'] < end['host_monotonic_ns']]
        assert during and all(p['planned_logged'] and p['dispatched'] and p['source_accepted'] for p in during)
        solve = dict(start_s=(begin['host_monotonic_ns']-t0)/1e9, end_s=(end['host_monotonic_ns']-t0)/1e9,
                     duration_s=(end['host_monotonic_ns']-begin['host_monotonic_ns'])/1e9,
                     source_slots_during_solve=[dict(direction=p['direction'], slot=p['slot'],
                       dispatch_lateness_ns=p['dispatch_lateness_ns']) for p in during],
                     result_path=str(context.parent/'after-solve/result.json'), status=solved['status'])
        for direction, chain in ((0, list('AEDB')), (1, list('BDEA'))):
            paths = [complete_path(p, chain, trigger_ns, t0 + 60000000000)
                     for p in data['packets'] if p['direction'] == direction]
            paths = [p for p in paths if p]
            assert paths, 'replacement E must actually relay, not merely be planned'
            after_paths.append(paths[0])
    augmented = dict(data)
    augmented['shared_inputs'] = dict(data['shared_inputs'], software_configuration_id=software_id)
    augmented['supplemental_fields'] = dict(software_configuration_id=dict(value=software_id, mapping=config,
        source_info_file=dict(path=str(infos_file), sha256=digest(infos_file)), raw_evidence=info_sources,
        basis='Observed info build_id and application uart_baud, canonical MAC-keyed JSON; excludes per-run boot',
        original_context_unchanged=True), source_analysis=dict(path=str(source), sha256=digest(source)))
    return augmented, dict(arm=data['arm'], source_analysis=str(source), source_log=str(log),
        software_configuration_id=software_id, observed_configuration=config, info_sources=info_sources,
        actual_event_times_s=times, raw_event_proofs=raw_proofs, pretrigger_paths=pre_paths,
        after_replan_paths=after_paths, online_solve=solve,
        original_shared_software_fingerprint_present='software_configuration_id' in data['shared_inputs'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixed', required=True)
    parser.add_argument('--replan', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    out = Path(args.output).resolve()
    assert out.is_relative_to(root/'simulation/outputs/E2-017') and not out.exists()
    sources = [Path(args.fixed).resolve(), Path(args.replan).resolve()]
    augmented, audits = zip(*(audit(source) for source in sources))
    assert audits[0]['software_configuration_id'] == audits[1]['software_configuration_id']
    out.mkdir(parents=True, exist_ok=False)
    for run in augmented:
        write(out/(run['arm']+'.paired.json'), run)
    paired = analysis.pairs(augmented)
    paired['source_runs'] = [dict(path=str(s),sha256=digest(s)) for s in sources]
    paired['supplemental_software_mapping'] = audits
    paired['limitations'].append('Original contexts lack software_configuration_id; matched only with explicit raw-info supplement, no upstream overwrite or capture rerun.')
    write(out/'pairs.json', paired)
    write(out/'mechanism-audit.json', audits)
    manifest = analysis.strict((root/'coordination/templates/RUN_MANIFEST.json').read_bytes())
    manifest.update(template_only=False, task_id='E2-017', run_id=out.name,
        finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), worktree=str(root),
        python_executable=sys.executable, command=sys.argv, status='first_pair_verified_with_explicit_supplement',
        output_directory=str(out), dirty_files_sha256={str(Path(__file__).relative_to(root)):digest(__file__)},
        data_and_weights_sha256={str(s):digest(s) for s in sources},
        budget=dict(raw_analyzer_runs=0, offline_capture_audits=2, RF_operations=0),
        limitations=paired['limitations'])
    write(out/'RUN_MANIFEST.json',manifest)
    print(json.dumps(dict(status=paired['pairs'][0]['status'], directions=paired['pairs'][0]['directions'])))


if __name__ == '__main__':
    main()
