"""C provenance-only audit of E2 run17 and H002 preflight; no test execution."""
from datetime import datetime,timezone
import hashlib,json,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
ARCHIVE=ROOT/'simulation/results/2026-11-03-M-016-espnow-host'
SOURCE=HERE/'source/tests/espnow'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
m=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
m.update(template_only=False,task_id='C-017',run_id=HERE.name,started_at=now(),worktree=str(ROOT),
 git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',dirty_files_sha256={'verify_increment.py':sha(Path(__file__)),**read(HERE/'source_hashes.json')},
 command=[sys.executable,'-B',str(Path(__file__))],python_executable=sys.executable,dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
 config_file=str(HERE/'source_hashes.json'),output_directory=str(HERE),status='running',
 budget={'prior_charged_s':37,'task_cap_s':600,'command_timeout_s':120,'output_cap_bytes':104857600},
 limitations=['Historical execution/source checks only; no new E2/H tests or OS enumeration/serial execution.',
 'H002 local inventory intentionally omitted from archive; no board identity or wireless readiness inferred.'])
write(HERE/'RUN_MANIFEST.start.json',m);start=time.monotonic();checks=[];issues=[];inputs={}
def check(path,expected,kind):
 actual=sha(path) if path.is_file() else None
 r={'path':str(path),'expected':expected,'actual':actual,'kind':kind};checks.append(r)
 if actual!=expected:issues.append(r)
 if actual:inputs[str(path)]=actual
for n,d in read(HERE/'source_hashes.json').items():check(HERE/'source'/n,d,'C E2 final copy')
old=read(HERE.parent/'20261103-07-e2-comprehensive/source_hashes.json');current=read(HERE/'source_hashes.json')
changes=[n for n,d in current.items() if old.get(n)!=d]
for n in ['analyze_logs.py','ANALYZER_API.md','ANALYZER_FREEZE.json','README.md']:
 assert current['tests/espnow/'+n]==old['tests/espnow/'+n]
index=read(SOURCE/'RUN_INDEX.json');record=index['runs'][-1];run=ARCHIVE/'E2-015'/record['run_id']
assert record['run_id']=='20261103-17-final-H-capture-independent'
for entry in index['runs']:
 check(ARCHIVE/'E2-015'/entry['run_id']/'manifest.json',entry['manifest_sha256'],'indexed manifest')
 check(ARCHIVE/'E2-015'/entry['run_id']/'result.json',entry['result_sha256'],'indexed result')
decl=read(SOURCE/'E2_FINAL_FREEZE.json');check(run/'manifest.json',decl['final_H_run_manifest_sha256'],'final H integration declaration')
manifest=read(run/'manifest.json')
for n,d in manifest['dirty_files_sha256'].items():
 check(run/'source'/n.replace('\\','/').split('tests/espnow/',1)[1],d,'E2 execution source')
integration=read(run/'integration_inputs.json')
check(run/'H-freeze.json',integration['H_freeze_sha256'],'executed H anchor')
for n,d in integration['H_source_hashes'].items():check(run/'H-frozen-source'/n,d,'executed H source')
source=ARCHIVE/'E2-015'/integration['source_run']
check(source/'manifest.json',integration['source_C_manifest_sha256'],'C source manifest')
check(source/'core_build.json',integration['source_C_build_sha256'],'C build record')
check(source/'telemetry.jsonl',integration['raw_C_trace_sha256'],'original C trace')
check(run/'actual-v4-C-telemetry.jsonl',integration['raw_C_trace_sha256'],'copied C trace')
for n,d in integration['E2_analyzer_hashes'].items():check(HERE/'source'/n,d,'API unchanged')
result=read(run/'result.json');assert result['tests_run']==6 and result['failures']==result['errors']==result['skipped']==0
assert result['hardware_measurements'] is False and result['actual_E1_core_compiled'] is False
hdir=ARCHIVE/'H-002/20261103-01-preflight';preflight=read(hdir/'preflight_verification.json')
check(hdir/'RUN_MANIFEST.json',preflight['run_manifest_sha256'],'preflight manifest binding')
assert preflight['opened_ports']==0 and preflight['metrics_all_null'] and preflight['tool_status']=='waiting_hardware'
assert not preflight['probe'] and not preflight['bench'] and not preflight['automation_modified']
freeze=read(hdir/'freeze_verification.json');assert len(freeze['source_files'])==38 and freeze['all_matched_before_and_after']
for n,row in freeze['source_files'].items():
 assert row['actual']==row['expected'],n
ledger=read(hdir/'measurements.json');assert len(ledger['metrics'])==6
assert all(x['value'] is None and x['source'] is None and x['status']=='not_measured' for x in ledger['metrics'].values())
for entry in read(ARCHIVE/'ARCHIVE_INDEX.json')['files']:
 if entry['archived'].replace('\\','/').startswith('H-002/20261103-01-preflight/'):
  check(ARCHIVE/entry['archived'],entry['sha256'],'preflight archive index')
summary={'checks':len(checks),'issues':issues,'changed_or_added_E2_files':changes,
 'E2_tests_recorded':6,'E2_tests_reexecuted':0,'H002_reexecuted':False,'H002_frozen_hashes_recorded':38,
 'H002_opened_ports':0,'H002_metrics_all_null':True,'elapsed_s':time.monotonic()-start}
write(HERE/'checks.json',checks);write(HERE/'summary.json',summary)
m.update(finished_at=now(),exit_code=int(bool(issues)),status='increment_verified' if not issues else 'discrepancy',
 execution_elapsed_s=summary['elapsed_s'],data_and_weights_sha256=inputs)
write(HERE/'RUN_MANIFEST.json',m);print(json.dumps(summary));sys.exit(m['exit_code'])
