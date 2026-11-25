"""One bounded 6-hour simulated run, with host RAM and occupancy monitoring."""
import argparse,ctypes,datetime,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import psutil
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
p=argparse.ArgumentParser();p.add_argument('--repo-root',required=True);p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);p.add_argument('--seed',type=int,required=True);p.add_argument('--seconds',type=int,default=21600);a=p.parse_args()
ROOT=Path(a.repo_root).resolve();out=Path(a.output).resolve();allowed=[(ROOT/'simulation/outputs/E1-030').resolve(),(ROOT/'simulation/outputs/E2-033').resolve()]
if not any(out.is_relative_to(x) and out!=x for x in allowed):p.error('task output subtree required')
if not (0<=a.seed<20):p.error('seed outside bounds')
if not (1<=a.seconds<=21600):p.error('duration outside bounds')
end=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'))
if end.tzinfo is None:p.error('deadline must include timezone')
out.mkdir(parents=True,exist_ok=False);started=time.monotonic();run=HERE/'engineering_run.py';prepare=out/'_prepared-policy-15';case=out/'case-0000'
spec=dict(mode='crossing',speed=50,density='compact',policy=15,seed=a.seed,seconds=a.seconds,sync_mode='cached',rate=1,payload=32,resource_sample_ms=60000)
batch={'suite':'long','status':'running','planned':1,'completed':0,'failed':0,'specs':[spec],'host_min_available_bytes':1073741824,'batch_wall_cap_s':1200,'stage_deadline_utc':end.isoformat(),'workers':1,
 'source_runner_sha256':hashlib.sha256(run.read_bytes()).hexdigest(),'note':'Simulated duration only, not hardware endurance'}
def save():(out/'batch.json').write_text(json.dumps(batch,indent=2),encoding='utf-8')
def remaining():return min(1200-(time.monotonic()-started),(end-datetime.datetime.now(datetime.timezone.utc)).total_seconds())
def stop_tree(proc):
 try:children=psutil.Process(proc.pid).children(recursive=True)
 except (psutil.NoSuchProcess,psutil.AccessDenied):children=[]
 for child in reversed(children):
  try:child.kill()
  except psutil.NoSuchProcess:pass
  except psutil.AccessDenied:batch.setdefault('cleanup_errors',[]).append('child kill denied: '+str(child.pid))
 if proc.poll() is None:proc.kill()
 proc.wait(timeout=10)
 if children:psutil.wait_procs(children,timeout=5)
def run_guarded(cmd,name,monitor_ram=False):
 if remaining()<=0:return -1,'deadline_before_start'
 with (out/(name+'.log')).open('w',encoding='utf-8') as log:
  proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT);batch['active_pid']=proc.pid;save();reason=None;next_sample=0
  try:
   with (out/(name+'-host-resources.jsonl')).open('w',encoding='utf-8') as samples:
    while proc.poll() is None:
     t=time.monotonic()-started;available=psutil.virtual_memory().available
     if t>=next_sample:
      try:rss=psutil.Process(proc.pid).memory_info().rss
      except (psutil.NoSuchProcess,psutil.AccessDenied):rss=None
      samples.write(json.dumps({'elapsed_s':t,'system_available_bytes':available,'child_rss_bytes':rss})+'\n');samples.flush();next_sample=t+5
     if remaining()<=0:reason='wall_or_stage_deadline'
     elif monitor_ram and available<batch['host_min_available_bytes']:reason='host_ram_guard'
     if reason:stop_tree(proc);break
     time.sleep(.5)
  except BaseException:
   stop_tree(proc);raise
  batch.pop('active_pid',None);save();return proc.returncode,reason
kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetThreadExecutionState.argtypes=[ctypes.c_uint];kernel.SetThreadExecutionState.restype=ctypes.c_uint;held=False
save()
try:
 if not kernel.SetThreadExecutionState(0x80000001):raise OSError(ctypes.get_last_error(),'sleep inhibition failed')
 held=True;batch['temporary_sleep_inhibition']=True;save()
 command=[sys.executable,'-B',str(run),'--repo-root',str(ROOT),'--output',str(prepare),'--policy','15','--prepare-only']
 code,reason=run_guarded(command,'prepare')
 if code!=0:batch.update(status='preparation_failed',failed=1,reason=reason or 'nonzero_prepare_exit');raise RuntimeError(batch['status'])
 command=[sys.executable,'-B',str(run),'--repo-root',str(ROOT),'--output',str(case),'--reuse-build',str(prepare)]
 for k,v in spec.items():command.extend(['--'+k.replace('_','-'),str(v)])
 code,reason=run_guarded(command,'case',True)
 if code!=0:
  batch.update(status='interrupted',failed=1,reason=reason or 'nonzero_case_exit')
  if case.exists():(case/'INTERRUPTION.json').write_text(json.dumps({'reason':batch['reason'],'process_reaped':True,'note':'Original running manifest preserved; not a completed run.'},indent=2),encoding='utf-8')
  raise RuntimeError(batch['status'])
 batch.update(status='completed',completed=1);save()
 for name in ('audit_batch_v2.py','deadline_audit.py','resource_audit.py'):
  if remaining()<=0:batch['status']='analysis_incomplete';raise TimeoutError('analysis deadline')
  target=case if name=='resource_audit.py' else out
  x=subprocess.run([sys.executable,'-B',str(HERE/name),str(target)],capture_output=True,text=True,timeout=remaining(),cwd=ROOT)
  (out/(name+'.log')).write_text(x.stdout+x.stderr,encoding='utf-8');batch[name+'_exit_code']=x.returncode;save()
  if x.returncode:batch['status']='analysis_failed';raise RuntimeError(name+' failed')
 batch['status']='completed_and_audited'
except Exception as e:
 batch.setdefault('error',repr(e))
 if batch['status']=='running':batch['status']='failed'
 raise
finally:
 if held:batch['sleep_inhibition_released']=bool(kernel.SetThreadExecutionState(0x80000000))
 batch['elapsed_seconds']=time.monotonic()-started;batch['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps({'status':batch['status'],'elapsed_seconds':batch['elapsed_seconds'],'output':str(out)}),flush=True)
