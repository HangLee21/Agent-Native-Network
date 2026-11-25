"""Run a finite, two-process engineering batch; every case has its own manifest."""
import argparse, concurrent.futures, hashlib, itertools, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; RUNNER=Path(__file__).with_name('engineering_run.py')
def main():
 global ROOT
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--suite',choices=['pilot','ablation','sensitivity','peer_cost','core','pressure','sync','verify_opt','verify_cached','verify_cached_pressure','verify_final_cache'],required=True)
 p.add_argument('--start',type=int,default=0);p.add_argument('--count',type=int,default=0);p.add_argument('--sync-mode',choices=['periodic','cached'],default='periodic');p.add_argument('--repo-root',default=None);a=p.parse_args()
 if a.repo_root:
  ROOT=Path(a.repo_root).resolve()
  if not (ROOT/'coordination/templates/RUN_MANIFEST.json').is_file():p.error('repo root missing manifest template')
 out=Path(a.output).resolve();allowed=[(ROOT/'simulation/outputs/E1-030').resolve(),(ROOT/'simulation/outputs/E2-033').resolve()]
 if not any(out.is_relative_to(x) and out!=x for x in allowed):p.error('new output under task output root required')
 out.mkdir(parents=True,exist_ok=False);start=time.monotonic()
 if a.suite=='pilot':
  specs=[dict(mode=m,speed=s,density=d,policy=p,seed=0,seconds=60) for m,s,d,p in itertools.product(('formation','crossing','reorganize'),(5,25,50),('compact','sparse'),(0,7))]
 elif a.suite=='ablation':
  specs=[dict(mode='crossing',speed=25,density='compact',policy=p,seed=s,seconds=60) for p,s in itertools.product(range(8),range(3))]
 elif a.suite=='sensitivity':
  specs=[dict(mode='crossing',speed=25,density='compact',policy=p,seed=0,seconds=60,phy_rate=r,service_ms=z,geometry_ms=g) for p,r,z,g in itertools.product((0,7),(1,2),(10,20),(125,250))]
 elif a.suite=='peer_cost':
  specs=[dict(mode='crossing',speed=25,density='compact',policy=p,seed=s,seconds=60,peer_eviction_us=c) for p,s,c in itertools.product((0,7),range(3),(0,1000,10000))]
 elif a.suite=='core':
  # Seed outermost: each complete 60-case prefix covers all motion/speed/density
  # combinations, so an enforced wall cap does not leave whole scenarios absent.
  specs=[dict(mode=m,speed=s,density=d,policy=p,seed=q,seconds=600) for q,m,s,d,p in itertools.product(range(20),('formation','crossing','reorganize'),(5,15,25,35,50),('compact','sparse'),(0,7))]
 elif a.suite=='pressure':
  specs=[dict(mode='crossing',speed=25,density='compact',policy=p,seed=q,seconds=60,rate=r,payload=z) for r,z,q,p in itertools.product((.2,1,2,5),(16,160),range(2),(0,7))]
 elif a.suite=='sync':
  specs=[dict(mode=m,speed=25,density=d,policy=p,seed=0,seconds=60,sync_mode=y) for m,d,p,y in itertools.product(('formation','crossing','reorganize'),('compact','sparse'),(0,3),('event','periodic'))]
 elif a.suite=='verify_opt':
  specs=[dict(mode=m,speed=25,density=d,policy=p,seed=0,seconds=60,sync_mode='periodic') for m,d,p in itertools.product(('formation','crossing','reorganize'),('compact','sparse'),(0,3))]
 elif a.suite=='verify_cached':
  specs=[dict(mode=m,speed=25,density=d,policy=p,seed=0,seconds=60,sync_mode='cached') for m,d,p in itertools.product(('formation','crossing','reorganize'),('compact','sparse'),(0,3))]
 elif a.suite=='verify_cached_pressure':
  specs=[dict(mode='crossing',speed=25,density='compact',policy=p,seed=0,seconds=60,rate=r,payload=z,sync_mode=y) for r,z,p,y in itertools.product((.2,1,2,5),(16,160),(0,3),('periodic','cached'))]
 else:
  specs=[dict(mode=m,speed=25,density=d,policy=7,seed=0,seconds=60,sync_mode=y) for m,d,y in itertools.product(('formation','crossing','reorganize'),('compact','sparse'),('periodic','cached'))]
 if a.start<0 or a.start>=len(specs) or a.count<0:p.error('invalid batch slice')
 total_specs=len(specs);specs=specs[a.start:a.start+a.count] if a.count else specs[a.start:]
 for spec in specs:spec.setdefault('sync_mode',a.sync_mode)
 status={'suite':a.suite,'status':'running','planned':len(specs),'full_suite_cases':total_specs,'slice_start':a.start,'completed':0,'failed':0,'wall_cap_seconds':1200,'workers':2,'runner_sha256':hashlib.sha256(RUNNER.read_bytes()).hexdigest(),'specs':specs}
 def save():(out/'batch.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
 save()
 builds={}
 try:
  for policy in sorted({s['policy'] for s in specs}):
   build=out/f'_prepared-policy-{policy}';cmd=[sys.executable,'-B',str(RUNNER),'--repo-root',str(ROOT),'--output',str(build),'--policy',str(policy),'--prepare-only']
   remaining=1200-(time.monotonic()-start)
   if remaining<=0:raise TimeoutError('batch deadline before preparation')
   proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,cwd=ROOT)
   try:output,_=proc.communicate(timeout=remaining)
   except subprocess.TimeoutExpired:
    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,text=True,check=False);proc.communicate();raise
   (out/f'_prepared-policy-{policy}.log').write_text(output,encoding='utf-8')
   if proc.returncode:raise RuntimeError('preparation failed: '+output[-1200:])
   builds[policy]=build
  status['prepared_policies']=sorted(builds);save()
 except Exception as exc:
  status.update(status='preparation_failed',error=repr(exc),elapsed_seconds=time.monotonic()-start);save();raise
 def run(item):
  i,s=item;cmd=[sys.executable,'-B',str(RUNNER),'--repo-root',str(ROOT),'--output',str(out/f'case-{i:04d}'),'--reuse-build',str(builds[s['policy']])]
  for k,v in s.items():cmd.extend(['--'+k.replace('_','-'),str(v)])
  remaining=1200-(time.monotonic()-start)
  if remaining<=0:return i,False,'batch deadline'
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,cwd=ROOT)
  try:
   output,_=proc.communicate(timeout=remaining)
   (out/f'case-{i:04d}.log').write_text(output,encoding='utf-8')
   return i,proc.returncode==0,('' if proc.returncode==0 else output[-1200:])
  except subprocess.TimeoutExpired:
   subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,text=True,check=False)
   proc.communicate();return i,False,'batch deadline; process tree stopped'
 pending=iter(enumerate(specs));inflight={};fatal=False
 try:
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
   for item in itertools.islice(pending,2):inflight[pool.submit(run,item)]=item
   while inflight:
    done,_=concurrent.futures.wait(inflight,return_when=concurrent.futures.FIRST_COMPLETED)
    for f in done:
     item=inflight.pop(f);i,ok,error=f.result();status['completed' if ok else 'failed']+=1
     if not ok:fatal=True
     if error:status.setdefault('errors',[]).append(dict(case=i,error=error))
     status['elapsed_seconds']=time.monotonic()-start;save()
     print(json.dumps(dict(case=i,ok=ok,completed=status['completed'],total=len(specs),elapsed=round(status['elapsed_seconds'],1))),flush=True)
     if not fatal and time.monotonic()-start<1200:
      try:nxt=next(pending)
      except StopIteration:pass
      else:inflight[pool.submit(run,nxt)]=nxt
  status['status']='completed' if status['completed']==len(specs) and not status['failed'] else 'incomplete'
 finally:status['elapsed_seconds']=time.monotonic()-start;save()
 if status['status']!='completed':raise SystemExit(1)
if __name__=='__main__':main()
