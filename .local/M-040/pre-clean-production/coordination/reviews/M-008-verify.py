"""Check old-file preservation, archive bytes, independent audit and navigation."""
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
ALLOWED = {
    '.gitattributes', 'README.md', 'START_HERE.md',
    'coordination/CURRENT.md', 'coordination/TASKS.md', 'coordination/WINDOWS.md',
    'coordination/DECISIONS.md', 'research/agent_native_network/README.md',
    'research/agent_native_network/NEXT_STEPS.md', 'research/agent_native_network/EVIDENCE_LOG.md',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    baseline = load(REVIEW / 'M-008-baseline.json')
    preserved = 0
    for name, expected in baseline['files'].items():
        if name not in ALLOWED:
            assert sha((ROOT / name).read_bytes()) == expected, name
            preserved += 1
    rows = []
    for archive in ('2026-10-26-E1-006-execution', '2026-10-26-E2-006-scale'):
        rows.extend(load(ROOT / 'simulation/results' / archive / 'ARCHIVE_MANIFEST.json')['files'])
    for row in rows:
        stored = (ROOT / row['stored']).read_bytes()
        assert sha(stored) == row['stored_sha256'], row['stored']
        raw = gzip.decompress(stored) if row['gzip'] else stored
        assert sha(raw) == row['raw_sha256'], row['stored']
        assert sha((ROOT / row['source']).read_bytes()) == row['raw_sha256'], row['source']
    audit = load(REVIEW / 'C-008-verification.json')
    assert not audit['errors'] and not audit['pending']
    assert len(audit['cases']) == 30 and audit['scale']['configurations'] == 10
    assert sha((REVIEW / 'C-008-verification.py').read_bytes()) == audit['verifier_sha256']
    for name, expected in audit['input_sha256'].items():
        assert sha((ROOT / name).read_bytes()) == expected, name
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    index_verified = 0
    for row in rows:
        if row['stored'] in tracked:
            blob = subprocess.check_output(['git', 'show', ':' + row['stored']], cwd=ROOT)
            assert sha(blob) == row['stored_sha256'], row['stored']
            index_verified += 1
    modified = subprocess.check_output(['git', 'diff', baseline['base'], '--name-only'], cwd=ROOT).decode().splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    missing, links = [], 0
    for name in set(modified + untracked):
        if not name.endswith('.md'):
            continue
        path = ROOT / name
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = target.strip().strip('<>')
            if re.match(r'^[a-zA-Z]+://', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0])
            if target:
                links += 1
                resolved = (path.parent / target).resolve()
                if not resolved.exists() and resolved != REVIEW / 'M-008-consistency.json':
                    missing.append([name, target])
    assert not missing, missing
    for name in ('heteromrta_demand_execution.py', 'test_heteromrta_demand_execution.py',
                 'heteromrta_scale_catalog.py', 'test_heteromrta_scale_catalog.py'):
        p = ROOT / 'simulation' / name
        ast.parse(p.read_text(encoding='utf-8'))
        if p.relative_to(ROOT).as_posix() in tracked:
            assert subprocess.check_output(['git', 'show', ':' + p.relative_to(ROOT).as_posix()], cwd=ROOT) == p.read_bytes()
    report = dict(status='passed', base=baseline['base'], old_files=len(baseline['files']),
                  preserved_unchanged=preserved, allowed_navigation_changes=sorted(ALLOWED),
                  archive_files=len(rows), archive_raw_bytes=sum(r['bytes'] for r in rows),
                  archive_stored_bytes=sum(r['stored_bytes'] for r in rows), archive_index_verified=index_verified,
                  audited_input_hashes=len(audit['input_sha256']), audited_episodes=len(audit['cases']),
                  scale_configurations=audit['scale']['configurations'], saved_tests=audit['saved_test_evidence'],
                  local_links_checked=links, missing_links=missing, additional_task_runs=0)
    (REVIEW / 'M-008-consistency.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
