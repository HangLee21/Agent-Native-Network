"""Verify preservation, archive copies, source provenance and local navigation."""
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
ARCHIVE = ROOT / 'simulation/results/2026-10-26-E1-005-demand'
ALLOWED_OLD = {
    '.gitattributes', 'README.md', 'START_HERE.md',
    'coordination/CURRENT.md', 'coordination/TASKS.md',
    'coordination/WINDOWS.md', 'coordination/DECISIONS.md',
    'research/agent_native_network/README.md',
    'research/agent_native_network/NEXT_STEPS.md',
    'research/agent_native_network/EVIDENCE_LOG.md',
    'research/agent_native_network/SCALABILITY_COMPREHENSIVE_ANALYSIS.md',
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    baseline = read(REVIEW / 'M-007-baseline.json')
    unexpected = [p for p, h in baseline['files'].items()
                  if p not in ALLOWED_OLD and sha((ROOT / p).read_bytes()) != h]
    assert not unexpected, unexpected
    archived = read(ARCHIVE / 'ARCHIVE_MANIFEST.json')['files']
    for row in archived:
        assert sha((ROOT / row['source']).read_bytes()) == row['sha256']
        assert sha((ROOT / row['stored']).read_bytes()) == row['sha256']
    run = ARCHIVE / '20261026-01-census'
    manifest = read(run / 'manifest.json')
    for row in manifest['input_files']:
        stored = (ROOT / row['path']).read_bytes()
        assert sha(stored) == row['stored_sha256'], row['path']
        raw = gzip.decompress(stored) if row['path'].endswith('.gz') else stored
        assert sha(raw) == row['raw_sha256'], row['path']
    for name, h in manifest['output_files'].items():
        assert sha((run / name).read_bytes()) == h, name
    assert sha((ROOT / manifest['source_script']['path']).read_bytes()) == manifest['source_script']['sha256']
    verification = ARCHIVE / '20261026-02-verification'
    tests = read(verification / 'verification.json')
    assert tests['exit_code'] == 0
    for name, h in tests['files'].items():
        assert sha((verification / name).read_bytes()) == h, name
    for name in ('demand_census.py', 'test_demand_census.py'):
        assert sha((ROOT / 'simulation' / name).read_bytes()) == tests['files'][name]
    c = read(REVIEW / 'C-007-verification.json')
    for p, h in c['reviewed_artifact_sha256'].items():
        assert sha((ROOT / p).read_bytes()) == h, p
    modified = subprocess.check_output(['git', 'diff', 'HEAD', '--name-only'], cwd=ROOT).decode().splitlines()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    documents = [ROOT / p for p in set(modified + untracked) if p.endswith('.md')]
    missing, link_count = [], 0
    for path in documents:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = target.strip().strip('<>')
            if re.match(r'^[a-zA-Z]+://', target) or target.startswith('#'):
                continue
            target = unquote(target.split('#')[0])
            if not target:
                continue
            link_count += 1
            resolved = (path.parent / target).resolve()
            if resolved == (REVIEW / 'M-007-consistency.json'):
                continue  # This invocation writes the verification record below.
            if not resolved.exists():
                missing.append([str(path.relative_to(ROOT)), target])
    assert not missing, missing
    for p in (ROOT / 'simulation/demand_census.py', ROOT / 'simulation/test_demand_census.py',
              REVIEW / 'M-007-archive.py', Path(__file__)):
        ast.parse(p.read_text(encoding='utf-8'))
    index_verified = 0
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    for row in archived:
        if row['stored'] in tracked:
            blob = subprocess.check_output(['git', 'show', ':' + row['stored']], cwd=ROOT)
            assert sha(blob) == row['sha256'], row['stored']
            index_verified += 1
    report = dict(status='passed', base=baseline['base'], old_files=len(baseline['files']),
                  preserved_unchanged=len(baseline['files']) - len(ALLOWED_OLD),
                  allowed_navigation_changes=sorted(ALLOWED_OLD),
                  archive_files=len(archived), archive_bytes=sum(r['bytes'] for r in archived),
                  archive_index_verified=index_verified,
                  input_hashes_checked=len(manifest['input_files']),
                  local_links_checked=link_count, missing_links=missing,
                  independent_audit=c['status'], reviewed_artifacts=len(c['reviewed_artifact_sha256']),
                  semantic_tests_recorded_exit=tests['exit_code'], new_task_executions=0)
    (REVIEW / 'M-007-consistency.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
