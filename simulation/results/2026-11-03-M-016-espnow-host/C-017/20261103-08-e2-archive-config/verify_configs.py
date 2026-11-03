"""Read-only C follow-up: eight newly archived ESP config files, no test reruns."""
from datetime import datetime,timezone
import hashlib,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
ARCHIVE=ROOT/'simulation/results/2026-11-03-M-016-espnow-host'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
m=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
m.update(template_only=False,task_id='C-017',run_id=HERE.name,started_at=now(),
         worktree=str(ROOT),git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',
         command=[sys.executable,'-B',str(Path(__file__))],python_executable=sys.executable,
         dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
         dirty_files_sha256={'verify_configs.py':sha(Path(__file__))},
         config_file=str(ARCHIVE/'ARCHIVE_INDEX.json'),budget={'prior_charged_s':32,'task_cap_s':600,'command_timeout_s':120,'output_cap_bytes':104857600},
         output_directory=str(HERE),status='running',limitations=['Source/hash checks only, no author tests or binary execution.',
         'Generated exe/build caches intentionally not archived; original exe hashes already checked in previous C stage.'])
write(HERE/'RUN_MANIFEST.start.json',m)
start=time.monotonic();records=[];issues=[];inputs={}
def check(p,expected,kind,expected_size=None):
    actual=sha(p) if p.is_file() else None
    r={'path':str(p),'kind':kind,'expected':expected,'actual':actual}
    if expected_size is not None:r.update(expected_size=expected_size,actual_size=p.stat().st_size if p.is_file() else None)
    records.append(r)
    if actual!=expected or (expected_size is not None and r['actual_size']!=expected_size):issues.append(r)
    if actual:inputs[str(p)]=actual
entries=[e for e in read(ARCHIVE/'ARCHIVE_INDEX.json')['files'] if e['archived'].replace('\\','/').startswith('E2-015/') and Path(e['archived']).name in {'sdkconfig.defaults','Kconfig.projbuild'}]
assert len(entries)==8, len(entries)
for e in entries:check(ARCHIVE/e['archived'],e['sha256'],'new config archive index',e['bytes'])
for name in ['20261103-07-real-core-independent','20261103-08-v3-regression-and-telemetry','20261103-12-lifecycle-v4-independent','20261103-13-final-core-contract']:
    run=ARCHIVE/'E2-015'/name
    for name,expected in read(run/'core_build.json')['frozen_source_sha256'].items():
        check(run/'E1-frozen-source'/name,expected,'complete historical E1 source set')
index=read(HERE.parent/'20261103-07-e2-comprehensive/source/tests/espnow/RUN_INDEX.json')
for run in index['runs']:
    check(ARCHIVE/'E2-015'/run['run_id']/'manifest.json',run['manifest_sha256'],'historical manifest unchanged')
    check(ARCHIVE/'E2-015'/run['run_id']/'result.json',run['result_sha256'],'historical result unchanged')
summary={'checks':len(records),'new_configs':8,'issues':issues,'elapsed_s':time.monotonic()-start,
         'remaining_missing_source_files':0 if not issues else None,'intentional_exe_omissions':8,
         'author_tests_executed':0,'C_binaries_executed':0}
write(HERE/'checks.json',records);write(HERE/'summary.json',summary)
m.update(finished_at=now(),exit_code=int(bool(issues)),status='config_archive_verified' if not issues else 'discrepancy',execution_elapsed_s=summary['elapsed_s'],data_and_weights_sha256=inputs)
write(HERE/'RUN_MANIFEST.json',m)
print(json.dumps(summary));sys.exit(m['exit_code'])
