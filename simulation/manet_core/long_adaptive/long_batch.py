"""Three bounded six-hour simulated runs, one worker, no retries."""
import argparse,ctypes,datetime,hashlib,json,os,pathlib,shutil,subprocess,sys,time
import psutil
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);p.add_argument('--seeds',default='0,1,2');a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[3];here=pathlib.Path(__file__).resolve().parent;out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('new E1-031 output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));report={'status':'running','cases':[],'deadline':deadline.isoformat(),'workers':1,'max_case_wall_s':1200,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def save():(out/'long_batch.json').write_text(json.dumps(report,indent=2),encoding='utf8')
prev=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001) if os.name=='nt' else 0;report['sleep_inhibition_set']=bool(prev);save();child=None
try:
 for seed in map(int,a.seeds.split(',')):
  if datetime.datetime.now(datetime.timezone.utc)>=deadline:report['status']='deadline_reached';break
  name=f'seed-{seed:02}';case=out/name;cmd=[sys.executable,'-B',str(here/'run.py'),'--output',str(case),'--seconds','21600','--seed',str(seed),'--policy','5','--mode','crossing','--speed','50','--density','compact'];start=time.monotonic();report['active']=name;save()
  with (out/(name+'.log')).open('w',encoding='utf8') as log:
   child=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
   reason=None
   while child.poll() is None:
    if time.monotonic()-start>=1200:reason='case wall cap';break
    if datetime.datetime.now(datetime.timezone.utc)>=deadline:reason='stage deadline';break
    if psutil.virtual_memory().available<1073741824:reason='host available RAM below 1GiB';break
    if shutil.disk_usage(out).free<2147483648:reason='disk free below 2GiB';break
    time.sleep(.5)
   if reason:
    child.terminate()
    try:child.wait(timeout=10)
    except subprocess.TimeoutExpired:child.kill();child.wait()
    report.update(status='interrupted',reason=reason);report['cases'].append({'name':name,'status':'interrupted','exit':child.returncode});child=None;break
   if child.returncode:report.update(status='failed',reason='case failed');report['cases'].append({'name':name,'exit':child.returncode});child=None;break
   child=None
  result={'name':name,'run':'completed'}
  for script in ('resource_audit.py','endpoint_audit.py'):
   if datetime.datetime.now(datetime.timezone.utc)>=deadline:result['audit_incomplete']='deadline';break
   rc=subprocess.run([sys.executable,'-B',str(here/script),str(case)],cwd=root,capture_output=True,text=True)
   (out/(name+'-'+script+'.log')).write_text(rc.stdout+rc.stderr,encoding='utf8')
   if rc.returncode:raise RuntimeError(f'{name} {script} failed {rc.returncode}')
   result[script]='passed'
  report['cases'].append(result);report.pop('active',None);save();print(json.dumps(result),flush=True)
  if result.get('audit_incomplete'):report['status']='deadline_reached';break
 else:report['status']='completed'
except BaseException as e:
 report.update(status='failed',error=repr(e))
 if child and child.poll() is None:child.terminate();child.wait()
 raise
finally:
 if prev:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
 report.update(sleep_inhibition_released=bool(prev),finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
