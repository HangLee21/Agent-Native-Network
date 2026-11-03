"""Bounded host-only builds/tests. Never opens hardware or installs packages."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,time
ROOT=Path(__file__).resolve().parents[2]
SRC=Path(__file__).resolve().parent
def write(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
 out=Path(a.output).resolve();base=ROOT/'simulation/outputs/E1-014'
 if not out.is_relative_to(base.resolve()) or out==base.resolve(): raise ValueError('new task run directory required')
 out.mkdir(parents=True,exist_ok=False)
 ledger=base/'execution_ledger.jsonl'
 rows=[json.loads(x) for x in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
 charged=sum(r.get('wall_seconds',r['timeout_s']) for r in rows if r['event']=='command_reserved')
 finished={r['id']:r for r in rows if r['event']=='command_finished'}
 charged=sum(finished[r['id']]['wall_seconds'] if r['id'] in finished else r['timeout_s'] for r in rows if r['event']=='command_reserved')
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
 m.update(template_only=False,task_id='E1-014',run_id=out.name,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),command=[sys.executable,*sys.argv],python_executable=sys.executable,output_directory=str(out),status='running',evidence_kind='synthetic',budget=dict(per_command_s=120,total_execution_s=600,output_bytes=104857600),source_hashes={},limitations=['Host event harness only; no ESP target compilation or hardware/RF measurements'])
 snap=out/'source';snap.mkdir()
 for f in SRC.rglob('*'):
  if f.is_file() and '__pycache__' not in f.parts:
   rel=f.relative_to(SRC);dst=snap/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dst);m['source_hashes'][rel.as_posix()]=hashlib.sha256(f.read_bytes()).hexdigest()
 (out/'task-card-snapshot.md').write_bytes((ROOT/'coordination/tasks/E1-014.md').read_bytes())
 def append(row):
  with ledger.open('a',encoding='utf-8') as s:s.write(json.dumps(row)+'\n')
 def run(label,cmd,input=None):
  nonlocal charged
  if charged>=600:raise RuntimeError('cumulative execution budget exhausted')
  timeout=min(120,600-charged);identity=f'{out.name}-{label}'
  append(dict(event='command_reserved',id=identity,command=cmd,timeout_s=timeout))
  start=time.monotonic()
  try:
   with (out/(label+'.txt')).open('w',encoding='utf-8') as log:
    r=subprocess.run(cmd,input=input,text=True,stdout=log,stderr=subprocess.STDOUT,timeout=timeout,cwd=ROOT)
   code=r.returncode
  except subprocess.TimeoutExpired:
   code=-999
  wall=time.monotonic()-start;charged+=wall;append(dict(event='command_finished',id=identity,exit_code=code,wall_seconds=wall))
  if code:raise RuntimeError(f'{label} failed: exit {code}; see preserved log')
 try:
  gcc=shutil.which('gcc');cmake=shutil.which('cmake');ninja=shutil.which('ninja')
  write(out/'tools.json',dict(gcc=gcc,cmake=cmake,ninja=ninja,idf_py=shutil.which('idf.py'),target_compilation='not_performed',hardware='not_available'))
  if not all((gcc,cmake,ninja)):raise RuntimeError('host build tool missing; no auto-install')
  run('compiler',[gcc,'--version'])
  run('configure',[cmake,'-S',str(SRC),'-B',str(out/'build'),'-G','Ninja','-DCMAKE_C_COMPILER='+gcc,'-DCMAKE_MAKE_PROGRAM='+ninja])
  run('build',[cmake,'--build',str(out/'build')])
  run('scenarios',[str(out/'build/ann_host.exe'),'--scenario','all'])
  records=[json.loads(x) for x in (out/'scenarios.txt').read_text(encoding='utf-8').splitlines() if x.startswith('{')]
  tests=[r for r in records if r.get('schema')=='ann.test.v1' and 'scenario' in r]
  assert len(tests)==12 and all(r['passed'] for r in tests)
  summary=records[-1];assert summary['failures']==0
  run('console',[str(out/'build/ann_host.exe'),'--console'],input='{"cmd":"info","nonce":"probe123"}\n{"cmd":"stats","nonce":"s"}\n')
  console=[json.loads(s) for s in (out/'console.txt').read_text(encoding='utf-8').splitlines()]
  assert len(console)==2 and console[0]['nonce']=='probe123' and console[0]['mode']=='idle' and console[0]['chip']=='host-synthetic'
  write(out/'result.json',dict(status='host_passed',tests=tests,summary=summary,json_records=len(records),console_idle_passed=True,hardware_measurements=dict(status='not_measured',reason='hardware_not_available',source=None,range_m=None,pdr=None,goodput_bps=None,rtt_p95_ms=None),target_compilation='not_performed'))
  m.update(status='host_passed',exit_code=0)
 except Exception as e:
  write(out/'failure.json',dict(error=repr(e)));m.update(status='failed',exit_code=1)
 m.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),cumulative_execution_seconds=charged)
 write(out/'manifest.json',m)
 size=sum(f.stat().st_size for f in base.rglob('*') if f.is_file())
 print(json.dumps(dict(status=m['status'],output=str(out),cumulative_execution_seconds=charged,output_bytes=size)))
 if size>104857600:raise RuntimeError('output size cap exceeded; stop')
 return m['exit_code']
if __name__=='__main__':sys.exit(main())
