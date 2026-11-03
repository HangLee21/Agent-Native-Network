"""Resolve selective archive omissions against retained original evidence only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
ARCHIVE=ROOT/'simulation/results/2026-11-03-M-016-espnow-host'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()

m=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
m.update(template_only=False,task_id='C-017',run_id=HERE.name+'-archive-supplement',
         started_at=now(),worktree=str(ROOT),git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',
         command=[sys.executable,'-B',str(Path(__file__))],python_executable=sys.executable,
         dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
         dirty_files_sha256={'audit_archive_supplement.py':sha(Path(__file__))},
         config_file=str(HERE/'summary.json'),output_directory=str(HERE),status='running',
         budget={'command_timeout_s':120,'task_cap_s':600,'prior_charged_s':30,'output_cap_bytes':104857600},
         limitations=['Reads only archived E2 entries and the 16 original E2 files absent from the selective archive.',
                      'No author test rerun, C binary execution, serial or RF; initial discrepancy record retained.'])
write(HERE/'SUPPLEMENT_MANIFEST.start.json',m)
start=time.monotonic(); checks=[];issues=[]; inputs={}
for missing in read(HERE/'summary.json')['issues']:
    relative=Path(missing['path']).relative_to(ARCHIVE/'E2-015')
    p=ROOT/'simulation/outputs/E2-015'/relative
    actual=sha(p) if p.is_file() else None
    checks.append({'original':str(p),'archived':missing['path'],'expected':missing['expected'],'actual':actual})
    if actual!=missing['expected']:issues.append(checks[-1])
    if actual:inputs[str(p)]=actual
for entry in read(ARCHIVE/'ARCHIVE_INDEX.json')['files']:
    if not entry['archived'].replace('\\','/').startswith('E2-015/'):continue
    p=ARCHIVE/entry['archived'];actual=sha(p) if p.is_file() else None
    record={'archived':str(p),'expected':entry['sha256'],'actual':actual,'bytes':p.stat().st_size if p.exists() else None}
    checks.append(record)
    if actual!=entry['sha256'] or record['bytes']!=entry['bytes']:issues.append(record)
    if actual:inputs[str(p)]=actual
summary={'checks':len(checks),'original_omissions_checked':16,'issues':issues,
         'archive_scope':'Executable omission documented in archive README; Kconfig.projbuild and sdkconfig.defaults are present only in retained original E2 snapshots.',
         'new_author_tests_executed':0,'new_C_binaries_executed':0,'elapsed_s':time.monotonic()-start}
write(HERE/'supplement_checks.json',checks);write(HERE/'supplement_summary.json',summary)
m.update(finished_at=now(),exit_code=int(bool(issues)),status='supplement_passed' if not issues else 'supplement_failed',
         execution_elapsed_s=summary['elapsed_s'],data_and_weights_sha256=inputs)
write(HERE/'SUPPLEMENT_MANIFEST.json',m)
print(json.dumps(summary));sys.exit(m['exit_code'])
