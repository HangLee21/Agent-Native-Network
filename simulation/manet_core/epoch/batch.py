"""Finite 5-seed paired batch: two workers, hard 20-minute cap, no overwrite."""
import argparse,datetime,json,os,pathlib,subprocess,sys,time,shutil
import psutil
from collections import deque
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--workers',type=int,choices=[1,2],default=2);p.add_argument('--mode',default='crossing',choices=['formation','crossing','reorganize']);p.add_argument('--speed',default=25,type=int);p.add_argument('--density',default='compact',choices=['compact','sparse']);p.add_argument('--seconds',default=600,type=int);p.add_argument('--seeds',default='0,1,2,3,4');p.add_argument('--baseline',default=1,type=int,choices=[0,1]);p.add_argument('--candidate',default=5,type=int,choices=[2,3,4,5]);p.add_argument('--rate',default=1.0,type=float);p.add_argument('--payload',default=32,type=int);p.add_argument('--deadline-utc',default=None);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[3];out=pathlib.Path(a.output).resolve();base=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(base) or out==base:raise SystemExit('new E1-031 output required')
out.mkdir(parents=True,exist_ok=False);seeds=[int(x) for x in a.seeds.split(',')];tasks=deque((s,p) for s in seeds for p in (a.baseline,a.candidate));running={};results=[];start=time.monotonic();meta={'status':'running','workers':a.workers,'wall_cap_seconds':1200,'tasks':list(tasks),'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def save(): (out/'batch.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
save()
try:
 while tasks or running:
  if time.monotonic()-start>=1200:raise TimeoutError('batch wall cap')
  if psutil.virtual_memory().available < 1073741824:raise RuntimeError('host available RAM below 1 GiB')
  if shutil.disk_usage(out).free < 2147483648:raise RuntimeError('output disk free below 2 GiB')
  if a.deadline_utc and datetime.datetime.now(datetime.timezone.utc)>=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00')):raise TimeoutError('stage deadline')
  while tasks and len(running)<a.workers:
   seed,policy=tasks.popleft();name=f'seed-{seed:02d}-policy-{policy}';log=(out/(name+'.log')).open('w',encoding='utf8')
   cmd=[sys.executable,'-B',str(root/'simulation/manet_core/epoch/run.py'),'--output',str(out/name),'--seconds',str(a.seconds),'--seed',str(seed),'--policy',str(policy),'--mode',a.mode,'--speed',str(a.speed),'--density',a.density,'--rate',str(a.rate),'--payload',str(a.payload)]
   child=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT);running[child.pid]=(child,log,name)
  for pid,(child,log,name) in list(running.items()):
   rc=child.poll()
   if rc is not None:
    log.close();results.append({'name':name,'exit_code':rc});del running[pid];print(name,rc,flush=True)
    if rc:raise RuntimeError('case failed: '+name)
  time.sleep(.2)
 meta['status']='completed'
except BaseException as e:
 meta.update(status='interrupted',error=repr(e))
 for child,log,name in running.values():
  child.terminate()
  try:child.wait(timeout=10)
  except subprocess.TimeoutExpired:child.kill();child.wait()
  log.close();results.append({'name':name,'exit_code':child.returncode,'interrupted':True})
 raise
finally:
 meta.update(results=results,remaining=list(tasks),elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
