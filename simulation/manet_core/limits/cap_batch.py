"""Five paired seeds for 8/16/32 hop caps, fixed 6000ms pending, 2 workers."""
import argparse,datetime,json,pathlib,shutil,subprocess,sys,time
import psutil
from collections import deque
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--workers',type=int,choices=[1,2],default=2);p.add_argument('--deadline-utc',required=True);p.add_argument('--seconds',type=int,default=600);a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[3];here=pathlib.Path(__file__).resolve().parent;out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('new output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));todo=deque((seed,cap) for seed in range(5) for cap in (8,16,32));running={};done=[];start=time.monotonic();meta={'status':'running','tasks':list(todo),'workers':a.workers,'max_wall_seconds':1200,'deadline':a.deadline_utc,'pending_ms':6000}
def save():(out/'batch.json').write_text(json.dumps(meta,indent=2),encoding='utf8')
save()
try:
 while todo or running:
  if time.monotonic()-start>=1200 or datetime.datetime.now(datetime.timezone.utc)>=deadline:raise TimeoutError('batch or stage deadline')
  if psutil.virtual_memory().available<1073741824 or shutil.disk_usage(out).free<2147483648:raise RuntimeError('host resource lower bound')
  while todo and len(running)<a.workers:
   seed,cap=todo.popleft();name=f'seed-{seed:02}-cap-{cap}';log=(out/(name+'.log')).open('w',encoding='utf8');cmd=[sys.executable,'-B',str(here/'run.py'),'--output',str(out/name),'--seconds',str(a.seconds),'--seed',str(seed),'--mode','crossing','--speed','25','--density','sparse','--policy','1','--ring-cap',str(cap),'--hop-limit',str(cap),'--pending-ms','6000'];q=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT);running[q.pid]=(q,log,name)
  for pid,(q,log,name) in list(running.items()):
   if q.poll() is not None:
    log.close();done.append({'name':name,'exit_code':q.returncode});del running[pid];print(name,q.returncode,flush=True)
    if q.returncode:raise RuntimeError(name+' failed')
  time.sleep(.2)
 meta['status']='completed'
except BaseException as e:
 meta.update(status='interrupted',error=repr(e))
 for q,log,name in running.values():q.terminate();q.wait(timeout=10);log.close();done.append({'name':name,'interrupted':True,'exit_code':q.returncode})
 raise
finally:meta.update(results=done,remaining=list(todo),elapsed_seconds=time.monotonic()-start);save()
