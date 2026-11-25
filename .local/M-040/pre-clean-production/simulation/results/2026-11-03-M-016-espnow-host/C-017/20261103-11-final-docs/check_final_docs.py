"""Final static C review checks; no test runner, hardware, network or Git mutation."""
from datetime import datetime,timezone
import difflib,hashlib,json,re,sys,time
from pathlib import Path
from urllib.parse import unquote
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];SOURCE=HERE/'source'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
assert not (HERE/'RUN_MANIFEST.start.json').exists(),'refuse existing run'
hashes=read(HERE/'source_hashes.json')
m=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
m.update(template_only=False,task_id='C-017',run_id=HERE.name,started_at=now(),worktree=str(ROOT),
 git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',dirty_files_sha256={**hashes,'check_final_docs.py':sha(Path(__file__))},
 command=[sys.executable,'-B',str(Path(__file__))],python_executable=sys.executable,dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
 config_file=str(HERE/'source_hashes.json'),output_directory=str(HERE),status='running',
 budget={'prior_charged_s':39,'command_timeout_s':120,'task_cap_s':600,'output_cap_bytes':104857600},
 limitations=['Static frozen docs, local-link existence and prior evidence checks; no function tests rerun.',
 'Automation PAUSED state is recorded in H002 task/M declaration; app state not queried or changed by C.',
 'Publication/archive/Git/automation management after acceptance remains M responsibility.'])
write(HERE/'RUN_MANIFEST.start.json',m);start=time.monotonic();checks=[];issues=[];inputs={}
def check(p,expected,kind):
 actual=sha(p) if p.is_file() else None;row={'path':str(p),'expected':expected,'actual':actual,'kind':kind};checks.append(row)
 if actual!=expected:issues.append(row)
 if actual:inputs[str(p)]=actual
for n,d in hashes.items():check(SOURCE/n,d,'final doc snapshot')
registry=read(ROOT/'coordination/reviews/M-016-verification.json')
for key in ['E1_lifecycle_v4','E2_final_v3','H_docs_v6','D_final_v1']:
 for n,d in registry['frozen'][key].items():check(ROOT/n,d,'final live '+key)
anchor=ROOT/'simulation/outputs/H-001/20261103-21-docs-v6/freeze.json'
check(anchor,'74f46815a23aafeb44fe7568b0c29dc2b608312e5c30943ba22c0b9fb03dd6fb','H docs anchor')
old=read(HERE.parent/'20261103-09-h-capture-v5/source_hashes.json')
changed_H=[n for n,d in old.items() if hashes[n]!=d]
assert changed_H==['hardware/eora_hub_400tb/README.md'],changed_H
readme='hardware/eora_hub_400tb/README.md'
before=(HERE.parent/'20261103-09-h-capture-v5/source'/readme).read_text(encoding='utf-8')
after=(SOURCE/readme).read_text(encoding='utf-8')
(HERE/'H_README.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='H_capture_v5',tofile='H_docs_v6')),encoding='utf-8')
assert '当前不接尚未冻结E2分析器' not in after
assert '后续测量分析接口待M冻结后再集成' not in after
assert '本轮没有运行H-002' not in after
links=[]
for n in hashes:
 if not n.startswith('research/'):continue
 text=(SOURCE/n).read_text(encoding='utf-8')
 for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)',text):
  if target.startswith(('http://','https://','#')):continue
  target=unquote(target.split('#',1)[0]);p=(ROOT/n).parent/target
  row={'document':n,'target':target,'exists':p.exists()};links.append(row)
  if not p.exists():issues.append(row)
archive=ROOT/'simulation/results/2026-11-03-M-016-espnow-host'
expected=[('E2-015/20261103-13-final-core-contract/result.json',20),('E2-015/20261103-15-analyzer-v2-regression/result.json',44),('E2-015/20261103-17-final-H-capture-independent/result.json',6)]
for rel,count in expected:
 p=archive/rel;v=read(p);assert v['tests_run']==count and v['failures']==v['errors']==v['skipped']==0
 inputs[str(p)]=sha(p)
unit=archive/'H-001/20261103-18-final-v2-regression/stderr.txt'
assert 'Ran 35 tests' in unit.read_text(encoding='utf-8') and unit.read_text(encoding='utf-8').rstrip().endswith('OK')
inputs[str(unit)]=sha(unit)
summary={'hash_checks':len(checks),'local_links_checked':len(links),'issues':issues,'changed_H_files':changed_H,
 'H_doc_01':'closed','functional_tests_reexecuted':0,'stage_review':'pass_with_nonblocking_doc_clarification',
 'nonblocking_note':{'id':'D-doc-01','file':'research/agent_native_network/espnow_20261103/PROTOCOL_AND_BENCH_PLAN.md','line':214,
 'detail':'E1 before/after source checks belong to verify_host/verify_c_capture; bench finalize_capture rechecks E2 and raw/context/config inputs. Clarify wording that groups them.'},
 'elapsed_s':time.monotonic()-start}
write(HERE/'checks.json',checks);write(HERE/'local_links.json',links);write(HERE/'summary.json',summary)
m.update(finished_at=now(),exit_code=int(bool(issues)),status='static_checks_passed' if not issues else 'discrepancy',execution_elapsed_s=summary['elapsed_s'],data_and_weights_sha256=inputs)
write(HERE/'RUN_MANIFEST.json',m);print(json.dumps(summary,ensure_ascii=False));sys.exit(m['exit_code'])
