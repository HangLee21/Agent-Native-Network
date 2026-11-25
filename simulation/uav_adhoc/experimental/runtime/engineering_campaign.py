"""Finite 600s-case campaign with 20min per batch and absolute stage deadline."""
import argparse,ctypes,datetime,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True)
p.add_argument('--repo-root',default=None)
p.add_argument('--start',type=int,default=0);p.add_argument('--stop',type=int,default=1200);p.add_argument('--batch-size',type=int,default=30)
p.add_argument('--sync-mode',choices=['periodic','cached'],default='periodic');a=p.parse_args()
if a.repo_root:
 ROOT=Path(a.repo_root).resolve()
 if not (ROOT/'coordination/templates/RUN_MANIFEST.json').is_file():p.error('repo root missing manifest template')
out=Path(a.output).resolve();allowed=(ROOT/'simulation/outputs/E1-030').resolve()
if not out.is_relative_to(allowed) or out==allowed:p.error('E1 output subtree required')
if not (0<=a.start<a.stop<=1200 and 2<=a.batch_size<=60 and a.batch_size%2==0 and a.start%2==0 and a.stop%2==0):p.error('use paired even case bounds')
end=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'))
if end.tzinfo is None:p.error('deadline must include UTC offset')
out.mkdir(parents=True,exist_ok=False);begin=time.monotonic()
report={'status':'running','start_index':a.start,'stop_index':a.stop,'next_index':a.start,'deadline_utc':end.isoformat(),'batch_size':a.batch_size,'sync_mode':a.sync_mode,'batches':[],
 'batch_script_sha256':hashlib.sha256((HERE/'engineering_batch.py').read_bytes()).hexdigest(),'run_script_sha256':hashlib.sha256((HERE/'engineering_run.py').read_bytes()).hexdigest(),'budget':'two workers, each batch <=1200s, absolute stage deadline'}
def save():(out/'campaign.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
def run_tree(cmd,timeout,path):
 with path.open('w',encoding='utf-8') as log:
  proc=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  try:return proc.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,text=True,check=False);proc.wait();return -1
  except BaseException:
   subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True,text=True,check=False);proc.wait();raise
save()
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.SetThreadExecutionState.argtypes=[ctypes.c_uint];kernel.SetThreadExecutionState.restype=ctypes.c_uint
sleep_held=False
try:
 if not kernel.SetThreadExecutionState(0x80000001):
  report['status']='sleep_inhibit_failed';raise OSError(ctypes.get_last_error(),'cannot inhibit sleep')
 sleep_held=True;report['temporary_sleep_inhibition']=True;save()
 while report['next_index']<a.stop:
  remain=(end-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
  if remain<60:report['status']='budget_exhausted';break
  first=report['next_index'];count=min(a.batch_size,a.stop-first);name=f'batch-{first:04d}-{first+count-1:04d}';dest=out/name
  cmd=[sys.executable,'-B',str(HERE/'engineering_batch.py'),'--repo-root',str(ROOT),'--output',str(dest),'--suite','core','--start',str(first),'--count',str(count),'--sync-mode',a.sync_mode]
  report['active_batch']=name;save();code=run_tree(cmd,min(1200,remain),out/(name+'.log'))
  batch_path=dest/'batch.json';batch=json.loads(batch_path.read_text(encoding='utf-8')) if batch_path.exists() else {}
  row={'name':name,'start':first,'planned':count,'completed':batch.get('completed',0),'status':batch.get('status','missing'),'exit_code':code}
  report['batches'].append(row);report.pop('active_batch',None)
  print(json.dumps(row),flush=True)
  if code!=0 or row['completed']!=count:report['status']='incomplete';save();break
  remain=(end-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
  if remain<10:report['next_index']=first+count;report['status']='budget_exhausted';save();break
  for analyzer in ('audit_batch_v2.py','deadline_audit.py'):
   remain=(end-datetime.datetime.now(datetime.timezone.utc)).total_seconds()
   if remain<10:report['status']='budget_exhausted';break
   acmd=[sys.executable,'-B',str(HERE/analyzer),str(dest)]
   acode=run_tree(acmd,min(120,remain),out/(name+'.'+analyzer+'.log'))
   row[analyzer+'_exit_code']=acode
   if acode!=0:report['status']='audit_failed';break
  if report['status']!='running':save();break
  report['next_index']=first+count;report['elapsed_seconds']=time.monotonic()-begin;save()
 if report['next_index']==a.stop:report['status']='completed'
finally:
 if sleep_held:
  report['sleep_inhibition_released']=bool(kernel.SetThreadExecutionState(0x80000000))
 report['elapsed_seconds']=time.monotonic()-begin;report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
