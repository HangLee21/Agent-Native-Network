"""Compare v2/v3 without restarts; verify no protocol-event changes, one worker."""
import argparse,datetime,hashlib,json,pathlib,psutil,shutil,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);a=p.parse_args();here=pathlib.Path(__file__).resolve().parent;root=here.parents[2];out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('new output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));start=time.monotonic();report={'status':'running','results':[],'workers':1,'max_wall_s':1200,'deadline_utc':a.deadline_utc,'limitations':['No restart occurs','Wire versions differ; actual packets are incompatible even if endpoint event logs match']}
def save():(out/'batch.json').write_text(json.dumps(report,indent=2),encoding='utf8')
def sha(p):
 x=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):x.update(b)
 return x.hexdigest()
save()
try:
 for seed in range(5):
  dirs=[]
  for version in (2,3):
   if datetime.datetime.now(datetime.timezone.utc)>=deadline or time.monotonic()-start>=1200:raise TimeoutError('stage/batch limit')
   if psutil.virtual_memory().available<1073741824 or shutil.disk_usage(out).free<2147483648:raise RuntimeError('host resource guard')
   name=f'seed-{seed:02}-v{version}';folder=out/name;program=(here.parent/'adaptive'/'run.py') if version==2 else (here/'run.py');cmd=[sys.executable,'-B',str(program),'--output',str(folder),'--seconds','600','--seed',str(seed),'--policy','5','--mode','crossing','--speed','25','--density','compact'];report['active']=name;save()
   with (out/(name+'.log')).open('w',encoding='utf8') as log:
    q=subprocess.Popen(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT)
    while q.poll() is None:
     if datetime.datetime.now(datetime.timezone.utc)>=deadline or time.monotonic()-start>=1200 or psutil.virtual_memory().available<1073741824:
      q.terminate();q.wait(timeout=10);raise TimeoutError('case terminated on guard')
     time.sleep(.5)
    if q.returncode:raise RuntimeError(f'{name} exit {q.returncode}')
   dirs.append(folder)
  s=[json.loads((d/'summary.json').read_text()) for d in dirs];same=(sha(dirs[0]/'events.jsonl')==sha(dirs[1]/'events.jsonl') and s[0]==s[1]);report['results'].append({'seed':seed,'events_and_summary_identical':same});report.pop('active',None);save();print('seed',seed,'same',same,flush=True)
 report['status']='completed'
except BaseException as e:report.update(status='interrupted',error=repr(e));raise
finally:report.update(elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
