"""Finite E2-016 host checks, unique output and cumulative 1200s ledger."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2];OWN=Path(__file__).resolve().parent
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output');ap.add_argument('--child');ap.add_argument('--pattern',default='test_validation.py');a=ap.parse_args()
    if '/' in a.pattern or '\\' in a.pattern or not a.pattern.startswith('test_') or not a.pattern.endswith('.py'):raise ValueError('local test filename required')
    if a.child:
        os.environ['E2_MID_TEST_OUTPUT']=str(Path(a.child).resolve().parent)
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.discover(str(OWN),pattern=a.pattern))
        save(Path(a.child),dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),successful=result.wasSuccessful(),evidence_kind='synthetic',physical_ports_opened=0,RF_runs=0,E1_H_integration_verified=False))
        return int(not result.wasSuccessful())
    if not a.output:ap.error('--output required')
    out=(ROOT/a.output).resolve();base=(ROOT/'simulation/outputs/E2-016').resolve()
    if out==base or not out.is_relative_to(base) or out.exists():raise ValueError('unique E2-016 run required')
    ledger=OWN/'execution_budget.jsonl';history=[json.loads(x) for x in ledger.read_text().splitlines()] if ledger.exists() else []
    if any(x.get('protection_stopped') for x in history):raise RuntimeError('prior protection stop; no automatic restart')
    done={x['run_id']:x for x in history if x['event']=='finished'}
    used=sum(done[x['run_id']]['elapsed_s'] if x['run_id'] in done else 120 for x in history if x['event']=='reserved')
    cap=min(120,1200-used)
    if cap<=0:raise RuntimeError('task execution budget exhausted')
    out.mkdir(parents=True)
    files=list(OWN.glob('*.py'))+list(OWN.glob('*.md'))+list(OWN.glob('*.json'))+list(OWN.glob('*.c'))+list((ROOT/'tools/mid_baseline/validation').glob('*.py'))
    hashes={str(p.relative_to(ROOT)):sha(p) for p in files}
    for p in files:
        target=out/'source'/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
    for name in ['coordination/tasks/E2-016.md','coordination/handoffs/M-018-contract.md']:shutil.copyfile(ROOT/name,out/Path(name).name)
    template=ROOT/'coordination/templates/RUN_MANIFEST.json';shutil.copyfile(template,out/'RUN_MANIFEST.template.json');m=json.loads(template.read_text('utf-8-sig'))
    command=[sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'--child',str(out/'result.json'),'--pattern',a.pattern]
    m.update(template_only=False,task_id='E2-016',run_id=out.name,started_at=datetime.now(timezone.utc).isoformat(),worktree=str(ROOT),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),command=command,python_executable=sys.executable,dirty_files_sha256=hashes,dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},output_directory=str(out),evidence_kind='synthetic',budget={'command_seconds':cap,'task_execution_seconds':1200,'prior_charged_seconds':used,'CPU_concurrency':1},status='running',limitations=['candidate author probes with fake OS/socket objects','no E1/H frozen integration, target build, physical serial or RF measurement'])
    save(out/'RUN_MANIFEST.started.json',m)
    with ledger.open('a') as f:f.write(json.dumps(dict(event='reserved',run_id=out.name,timeout_s=cap))+'\n')
    start=time.monotonic();protection=False
    with (out/'unittest.txt').open('w',encoding='utf-8') as f:
        try:code=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=cap).returncode
        except subprocess.TimeoutExpired:code=124;protection=True
    elapsed=time.monotonic()-start
    with ledger.open('a') as f:f.write(json.dumps(dict(event='finished',run_id=out.name,elapsed_s=elapsed,exit_code=code,protection_stopped=protection))+'\n')
    m.update(finished_at=datetime.now(timezone.utc).isoformat(),elapsed_s=elapsed,exit_code=code,protection_stopped=protection,status='host_checks_passed' if code==0 else 'host_checks_failed');save(out/'RUN_MANIFEST.json',m)
    print(json.dumps(dict(output=str(out),exit_code=code,elapsed_s=elapsed)))
    return code
if __name__=='__main__':raise SystemExit(main())
