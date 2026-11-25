"""C read-only provenance audit. Never invokes E2 runners, C binaries or hardware."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = HERE / 'source/tests/espnow'
ARCHIVE = ROOT / 'simulation/results/2026-11-03-M-016-espnow-host/E2-015'

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def read(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def write(p, value):
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def now():
    return datetime.now(timezone.utc).isoformat()

manifest = read(ROOT / 'coordination/templates/RUN_MANIFEST.json')
manifest.update(template_only=False, task_id='C-017', run_id=HERE.name,
                started_at=now(), worktree=str(ROOT),
                git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',
                dirty_files_sha256={'audit_evidence.py': sha(Path(__file__)), **read(HERE/'source_hashes.json')},
                command=[sys.executable, '-B', str(Path(__file__))],
                python_executable=sys.executable,
                dependency_snapshot={'python': sys.version, 'libraries': 'stdlib only'},
                config_file=str(HERE/'source_hashes.json'),
                budget={'task_cap_s': 600, 'prior_charged_s': 27, 'command_timeout_s': 120, 'output_cap_bytes': 104857600},
                output_directory=str(HERE), status='running',
                limitations=['Read-only provenance audit; no new execution of author tests, C binaries, ESP, serial or RF.',
                             '23 source copies were verified before this manifest was created; copy start time not recorded.',
                             'Archived absolute paths are mapped by original E2 run-relative suffix; original bytes remain unchanged.'],
                evidence_kind='source_and_historical_evidence_audit')
write(HERE/'RUN_MANIFEST.start.json', manifest)
start = time.monotonic()
issues = []
checks = []
inputs = {}

def check(path, expected, kind):
    path = Path(path)
    actual = sha(path) if path.is_file() else None
    checks.append({'path':str(path), 'kind':kind, 'expected':expected, 'actual':actual})
    if actual != expected:
        issues.append({'path':str(path), 'kind':kind, 'expected':expected, 'actual':actual})
    if actual:
        inputs[str(path)] = actual

def mapped(original):
    return ARCHIVE / original.replace('\\','/').split('simulation/outputs/E2-015/', 1)[1]

for name, expected in read(HERE/'source_hashes.json').items():
    check(HERE/'source'/name, expected, 'C frozen source copy')

runs=[]
for entry in read(SOURCE/'RUN_INDEX.json')['runs']:
    run=ARCHIVE/entry['run_id']
    check(run/'manifest.json', entry['manifest_sha256'], 'indexed manifest')
    check(run/'result.json', entry['result_sha256'], 'indexed result')
    m=read(run/'manifest.json'); result=read(run/'result.json')
    if result != entry['result']:
        issues.append({'run':run.name,'kind':'result object mismatch'})
    for original, expected in m['dirty_files_sha256'].items():
        relative=original.replace('\\','/').split('tests/espnow/',1)[1]
        check(run/'source'/relative, expected, 'run source snapshot')
    check(run/'M-016-contract.md',m['contract_sha256'],'contract snapshot')
    check(run/'E2-015.md',m['task_card_sha256'],'task snapshot')
    if (run/'core_build.json').is_file():
        build=read(run/'core_build.json')
        for name, expected in build['frozen_source_sha256'].items():
            check(run/'E1-frozen-source'/name,expected,'compiled E1 source')
        for name, expected in build['binaries_sha256'].items():
            check(run/name,expected,'compiled host binary')
        if any(c['exit_code'] != 0 for c in build['commands']):
            issues.append({'run':run.name,'kind':'nonzero compiler exit'})
    runs.append({'run':run.name,'result':result,'exit_code':m['exit_code'],
                 'protection_stopped':m['protection_stopped'],
                 'historical_limitations_note':entry.get('historical_limitations_note')})

context_path=ARCHIVE/'20261103-16-v2-v4-capture-context/CAPTURE_CONTEXT.json'
context=read(context_path)
check(mapped(context['source_core_manifest']),context['source_core_manifest_sha256'],'context source C manifest')
check(ARCHIVE/'20261103-13-final-core-contract/core_build.json',context['source_core_build_sha256'],'context C build')
for original, expected in context['log_sha256'].items():
    check(mapped(original),expected,'immutable context log')
for filename in ['actual-C-v4-analysis.json','H-envelope-v4-analysis.json']:
    p=context_path.parent/filename; a=read(p)
    for log in a['source_logs']:
        check(mapped(log['path']),log['sha256'],'analysis source log')
    for origin in a['source_manifests']:
        check(mapped(origin['path']),origin['sha256'],'analysis context digest')

summary={'source_freeze_sha256':sha(SOURCE/'E2_FINAL_FREEZE.json'),
         'checks':len(checks),'issues':issues,'runs':runs,
         'new_author_tests_executed':0,'new_C_binaries_executed':0,
         'elapsed_s':time.monotonic()-start}
write(HERE/'checks.json',checks)
write(HERE/'summary.json',summary)
manifest.update(finished_at=now(), exit_code=0 if not issues else 1,
                status='provenance_checks_passed' if not issues else 'provenance_discrepancy',
                execution_elapsed_s=summary['elapsed_s'], data_and_weights_sha256=inputs,
                source_snapshot_hashes_unchanged=all(sha(HERE/'source'/n)==v for n,v in read(HERE/'source_hashes.json').items()))
write(HERE/'RUN_MANIFEST.json',manifest)
print(json.dumps({'checks':len(checks),'issues':issues,'elapsed_s':summary['elapsed_s']},ensure_ascii=False))
sys.exit(manifest['exit_code'])
