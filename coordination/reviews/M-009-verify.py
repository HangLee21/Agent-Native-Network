"""Verify historical preservation, raw/compressed archives and staged blobs."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'coordination/reviews'
ALLOWED = {'.gitattributes', 'README.md', 'START_HERE.md', 'coordination/CURRENT.md',
           'coordination/TASKS.md', 'coordination/WINDOWS.md', 'coordination/DECISIONS.md',
           'research/agent_native_network/README.md', 'research/agent_native_network/NEXT_STEPS.md',
           'research/agent_native_network/EVIDENCE_LOG.md'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def index_hashes(names):
    if not names:
        return {}
    data = subprocess.check_output(['git', 'cat-file', '--batch'],
                                   input=''.join(':' + n + '\n' for n in names).encode(), cwd=ROOT)
    offset, hashes = 0, {}
    for name in names:
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        assert header[1] == b'blob', (name, header)
        size = int(header[2]); begin = end + 1
        hashes[name] = sha(data[begin:begin + size])
        assert data[begin + size:begin + size + 1] == b'\n'
        offset = begin + size + 1
    assert offset == len(data)
    return hashes


def main():
    base = load(REVIEW / 'M-009-baseline.json')
    preserved = 0
    for name, expected in base['files'].items():
        if name not in ALLOWED:
            assert sha((ROOT / name).read_bytes()) == expected, name
            preserved += 1
    rows = []
    for name in ('2026-10-26-E1-007-wireless', '2026-10-26-E2-007-wireless'):
        rows.extend(load(ROOT / 'simulation/results' / name / 'ARCHIVE_MANIFEST.json')['files'])
    for row in rows:
        stored = (ROOT / row['stored']).read_bytes()
        assert sha(stored) == row['stored_sha256'], row['stored']
        raw = gzip.decompress(stored) if row['gzip'] else stored
        assert sha(raw) == row['raw_sha256'], row['stored']
        assert sha((ROOT / row['source']).read_bytes()) == row['raw_sha256'], row['source']
    audit = load(REVIEW / 'C-009-verification.json')
    assert not audit['errors'] and not audit['pending']
    assert len(audit['replay_cases']) == 60 and len(audit['task_cases']) == 18
    assert sha((REVIEW / 'C-009-verification.py').read_bytes()) == audit['verifier_sha256']
    for name, expected in audit['input_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    staged = [r['stored'] for r in rows if r['stored'] in tracked]
    hashes = index_hashes(staged)
    for row in rows:
        if row['stored'] in hashes:
            assert hashes[row['stored']] == row['stored_sha256'], row['stored']
    new_sources = ['simulation/' + name for name in (
        'wireless_broadcast_service.py', 'test_wireless_broadcast_service.py',
        'heteromrta_wireless_eval.py', 'test_heteromrta_wireless_eval.py', 'wireless_trace_replay.py')]
    hashes = index_hashes([n for n in new_sources if n in tracked])
    for name in new_sources:
        ast.parse((ROOT / name).read_text(encoding='utf-8'))
        if name in hashes:
            assert hashes[name] == sha((ROOT / name).read_bytes()), name
    changed = subprocess.check_output(['git', 'diff', base['base'], '--name-only'], cwd=ROOT).decode().splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    missing, count, snapshot_links = [], 0, 0
    for name in set(changed + untracked):
        if not name.endswith('.md'):
            continue
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = target.strip().strip('<>')
            if re.match(r'^[a-zA-Z]+://', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0])
            if not target:
                continue
            count += 1
            origin = path.parent
            if name.startswith('simulation/results/2026-10-26-E2-007-wireless/') and path.name == 'WIRELESS_SERVICE_CONTRACT.md':
                source = ROOT / 'research/agent_native_network/WIRELESS_SERVICE_CONTRACT.md'
                assert path.read_bytes() == source.read_bytes(), name
                origin = source.parent
                snapshot_links += 1
            resolved = (origin / target).resolve()
            if not resolved.exists() and resolved != REVIEW / 'M-009-consistency.json':
                missing.append([name, target])
    assert not missing, missing
    report = dict(status='passed', base=base['base'], old_files=len(base['files']),
                  preserved_unchanged=preserved, allowed_navigation_changes=sorted(ALLOWED),
                  archive_files=len(rows), archive_raw_bytes=sum(r['bytes'] for r in rows),
                  archive_stored_bytes=sum(r['stored_bytes'] for r in rows), archive_index_verified=len(staged),
                  audited_input_hashes=len(audit['input_sha256']), audited_replays=60, audited_tasks=18,
                  local_links_checked=count, immutable_snapshot_links_at_source=snapshot_links,
                  missing_links=missing, additional_task_runs=0)
    (REVIEW / 'M-009-consistency.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
