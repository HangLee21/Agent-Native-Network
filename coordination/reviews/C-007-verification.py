"""Independent read-only reconstruction of the E1-005 census from frozen archives.

Does not import the research executor/census or run a task policy.
Only writes C-007-verification.json beside this script.
"""
from collections import Counter, defaultdict
from bisect import bisect_left
import csv
import gzip
import hashlib
from itertools import combinations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / 'simulation/results/2026-10-25-E1-004-causal'
INPUTS = {}


def read(path):
    raw = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def load(directory, stem):
    path = directory / (stem + '.json')
    return read(path if path.exists() else path.with_suffix('.json.gz'))


def sha_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def reference_audit(evidence, messages, events, decisions):
    """Index applied evidence by key, then seek each decision's prefix independently."""
    mids = {m['message_id']: m for m in messages}
    counts = Counter()
    references = Counter()
    histories = {}
    for actor, stream in evidence.items():
        hh = defaultdict(list)
        for index, e in enumerate(stream):
            if not e['applied']:
                continue
            network = e['via'] == 'network'
            b = json.loads(mids[e['evidence_id']]['payload_utf8']) if network else events[e['evidence_id']]
            if e['kind'] == 'self_state':
                key, version = ('state', str(e['source'])), b['state']['seq']
            else:
                key, version = ('scene', str(b['scene']['task'])), b['scene']['version']
            hh[key].append((index, version, e['evidence_id'] if network else None))
        histories[str(actor)] = hh
    for d in decisions:
        actor = str(d['actor'])
        hh = histories[actor]
        for field, kind in (('source_versions', 'state'), ('task_versions', 'scene')):
            for key, version in d[field].items():
                if kind == 'state' and str(key) == actor:
                    continue
                if kind == 'state':
                    counts['remote_state_slots'] += 1
                    if version == 0:
                        counts['initial_remote_state_slots'] += 1
                        continue
                timeline = hh[(kind, str(key))]
                j = bisect_left([x[0] for x in timeline], d['evidence_count']) - 1
                assert j >= 0
                _, expected, message_id = timeline[j]
                assert version == expected
                if message_id is None:
                    assert kind == 'scene'
                    counts['local_scene_references'] += 1
                else:
                    references[(message_id, int(actor))] += 1
                    counts['network_state_references' if kind == 'state' else 'network_scene_references'] += 1
    counts['recipient_copies_referenced'] = len(references)
    counts['reference_occurrences'] = sum(references.values())
    for key in ('remote_state_slots', 'initial_remote_state_slots', 'local_scene_references',
                'network_state_references', 'network_scene_references'):
        counts.setdefault(key, 0)
    return counts, references


def main():
    rows = []
    catalogue_fingerprints = {}
    census_dir = ROOT / 'simulation/results/2026-10-26-E1-005-demand/20261026-01-census'
    if not census_dir.exists():
        census_dir = ROOT / 'simulation/outputs/E1-005/20261026-01-census'
    csv_inputs = {}
    for name, key in (('cases', lambda r: r['case']),
                      ('messages', lambda r: (r['case'], r['message_id'])),
                      ('task_coalitions', lambda r: (r['case'], r['task_id']))):
        path = census_dir / (name + '.csv')
        raw = path.read_bytes()
        INPUTS[path.relative_to(ROOT).as_posix()] = hashlib.sha256(raw).hexdigest()
        rr = list(csv.DictReader(raw.decode('utf-8').splitlines()))
        csv_inputs[name] = {key(r): r for r in rr}
        assert len(csv_inputs[name]) == len(rr)
    message_matches = task_matches = case_field_matches = 0
    for run in ('20261025-02-delay', '20261025-03-fifo'):
        for case in sorted((ARCHIVE / run).glob('tasks*')):
            result = load(case, 'result')
            catalog = load(case, 'catalog')
            messages = load(case, 'messages')
            events = load(case, 'events')
            deliveries = load(case, 'deliveries')
            decisions = load(case, 'decisions')
            evidence = load(case, 'view_evidence')
            reference_counts, references = reference_audit(evidence, messages, events, decisions)
            group = 'instant' if result['mode'] == 'instant' else 'diagnostic'
            agent_ids = set(map(int, catalog['agents']))
            assert len(agent_ids) == 9
            key = (result['tasks'], result['seed'])
            digest = sha_json(catalog)
            if key in catalogue_fingerprints:
                assert catalogue_fingerprints[key] == digest
            catalogue_fingerprints[key] = digest
            min_size = Counter()
            abilities = [a['abilities'] for a in catalog['agents'].values()]
            for tid, task in catalog['tasks'].items():
                requirement = task['requirements']
                feasible = [k for k in range(1, 10) if any(
                    all(sum(a[j] for a in team) >= requirement[j] for j in range(len(requirement)))
                    for team in combinations(abilities, k))]
                assert feasible
                min_size[min(feasible)] += 1
                assert int(csv_inputs['task_coalitions'][(case.name, tid)]['min_members']) == min(feasible)
                task_matches += 1
            by_id = {}
            kinds, causes = Counter(), Counter()
            kind_bytes = Counter()
            for m in messages:
                assert m['message_id'] not in by_id
                by_id[m['message_id']] = m
                raw = m['payload_utf8'].encode('utf-8')
                assert m['bytes'] == len(raw)
                assert m['payload_sha256'] == hashlib.sha256(raw).hexdigest()
                assert len(m['recipients']) == len(set(m['recipients'])) == 8
                assert set(m['recipients']) == agent_ids - {m['source']}
                evidence = events[m['local_evidence']]
                assert evidence['id'] == m['local_evidence']
                kinds[m['kind']] += 1
                kind_bytes[m['kind']] += m['bytes']
                causes[evidence['cause']] += 1
                reported = csv_inputs['messages'][(case.name, m['message_id'])]
                for field, expected in (
                    ('application_bytes', m['bytes']), ('recipient_copies_requested', 8),
                    ('recipient_copies_referenced', sum((m['message_id'], i) in references for i in m['recipients'])),
                    ('cache_reference_occurrences', sum(references[(m['message_id'], i)] for i in m['recipients']))):
                    assert int(reported[field]) == expected, (case.name, m['message_id'], field)
                message_matches += 1
            unique_deliveries = set()
            for d in deliveries:
                pair = (d['message_id'], d['recipient'])
                assert pair not in unique_deliveries
                unique_deliveries.add(pair)
                m = by_id[d['message_id']]
                assert d['recipient'] in m['recipients']
                assert d['payload_sha256'] == m['payload_sha256']
            for d in decisions:
                assert set(map(int, d['source_versions'])) == agent_ids
            starts = [e for e in events if e['kind'] == 'task_start']
            multi = sum(len(e['workers']) > 1 for e in starts)
            multi_species = sum(len({catalog['agents'][str(i)]['species'] for i in e['workers']}) > 1 for e in starts)
            row = dict(case=case.name, run=run, group=group,
                       tasks=result['tasks'], seed=result['seed'], nodes=len(agent_ids),
                       success=result['success'], messages=len(messages),
                       application_bytes=sum(m['bytes'] for m in messages),
                       receiver_copies=sum(len(m['recipients']) for m in messages),
                       delivered_copies=len(deliveries),
                       applied_copies=sum(d['applied'] for d in deliveries),
                       decisions=len(decisions), starts=len(starts),
                       tasks_started_multi_worker=multi, tasks_started_multi_species=multi_species,
                       policy_inferences=sum(d['branch'] == 'infer' for d in decisions),
                       **reference_counts,
                       kinds=dict(kinds), kind_bytes=dict(kind_bytes), causes=dict(causes),
                       capability_minimum_histogram=dict(min_size), catalog_sha256=digest)
            rows.append(row)
            reported = csv_inputs['cases'][case.name]
            mapping = {'messages': 'messages', 'application_bytes':'application_bytes',
                       'receiver_copies':'recipient_copies_requested', 'delivered_copies':'recipient_copies_delivered',
                       'applied_copies':'recipient_copies_cache_applied', 'decisions':'decisions',
                       'tasks_started_multi_worker':'tasks_started_multi_worker',
                       'tasks_started_multi_species':'tasks_started_multi_species',
                       'policy_inferences':'policy_inferences'}
            mapping.update({k:k for k in reference_counts})
            for independent, published in mapping.items():
                assert row[independent] == int(reported[published]), (case.name, independent)
                case_field_matches += 1
    assert len(rows) == 45
    assert len(catalogue_fingerprints) == 10
    groups = {}
    for group in ('instant', 'diagnostic'):
        selected = [r for r in rows if r['group'] == group]
        totals = dict(cases=len(selected))
        for field in ('tasks', 'messages', 'application_bytes', 'receiver_copies',
                      'delivered_copies', 'applied_copies', 'decisions', 'starts',
                      'tasks_started_multi_worker', 'tasks_started_multi_species', 'policy_inferences',
                      'recipient_copies_referenced', 'reference_occurrences', 'remote_state_slots',
                      'initial_remote_state_slots', 'network_state_references', 'network_scene_references',
                      'local_scene_references'):
            totals[field] = sum(r[field] for r in selected)
        hist = Counter()
        for r in selected:
            hist.update(r['capability_minimum_histogram'])
        totals['capability_minimum_histogram'] = dict(hist)
        groups[group] = totals
    assert groups['instant']['cases'] == 10 and groups['diagnostic']['cases'] == 35
    output = dict(status='independent_raw_checks_passed',
                  scope='45 archived episodes; no new policy runs; fixed 9 nodes',
                  groups=groups, cases=rows, source_sha256=INPUTS)
    output['csv_comparison'] = dict(case_field_matches=case_field_matches,
                                   message_rows_matched=message_matches, task_rows_matched=task_matches)
    manifest = read(census_dir / 'manifest.json')
    for item in manifest['input_files']:
        raw = (ROOT / item['path']).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == item['stored_sha256']
        decoded = gzip.decompress(raw) if item['path'].endswith('.gz') else raw
        assert hashlib.sha256(decoded).hexdigest() == item['raw_sha256']
    for name, expected in manifest['output_files'].items():
        assert hashlib.sha256((census_dir / name).read_bytes()).hexdigest() == expected
    assert hashlib.sha256((ROOT / manifest['source_script']['path']).read_bytes()).hexdigest() == manifest['source_script']['sha256']
    output['manifest_check'] = dict(input_entries=len(manifest['input_files']),
                                    output_files=len(manifest['output_files']), all_hashes_match=True)
    contract = read(ROOT / 'research/agent_native_network/demand_20261026/WORKLOAD_CONTRACT.json')
    assert contract['execution_ready'] is False
    sources = {s['id'] for s in contract['sources']}
    assert len(sources) == 4 and len(contract['workflows']) == 3
    for workflow in contract['workflows']:
        assert set(workflow['source_ids']) <= sources
        assert workflow['adaptation_status'] == 'not_implemented'
        assert all(value is None for value in workflow['adaptation_null'].values())
        for param in workflow['native_record_params']:
            assert param['source_id'] in sources and param['is_deadline'] is False
    native_params = contract['workflows'][1]['native_record_params']
    assert [(p['value'],p['unit']) for p in native_params] == [(45,'s'),(20,'m')]
    for item in contract['local_inputs']:
        assert hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest() == item['sha256']
    output['contract_check'] = dict(source_ids_resolve=True, adaptation_parameters_null=True,
                                    execution_ready=False, native_45s_20m_not_deadlines=True,
                                    local_input_hashes_match=True)
    for name in ('simulation/demand_census.py', 'simulation/test_demand_census.py',
                 'research/agent_native_network/DEMAND_CENSUS.md',
                 'research/agent_native_network/DEMAND_DRIVEN_RESEARCH_CHAIN.md',
                 'research/agent_native_network/demand_20261026/APPLICATION_REQUIREMENTS.md',
                 'research/agent_native_network/demand_20261026/WORKLOAD_CONTRACT.json'):
        p = ROOT / name
        if p.exists():
            output.setdefault('reviewed_artifact_sha256', {})[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    target = Path(__file__).with_suffix('.json')
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(groups, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
