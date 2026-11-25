"""Bounded adaptive node-count scaling campaign, fixed spacing, 5 paired seeds."""
import argparse,ctypes,datetime,hashlib,json,os,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);a=p.parse_args();root=pathlib.Path(__file__).resolve().parents[3];here=pathlib.Path(__file__).resolve().parent;out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('new output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));start=time.monotonic();cases=[(n,d) for n in (5,10,20,40) for d in ('compact','sparse')];sources=[here/x for x in ('run.py','batch.py','engine.py','engine_diagnostic.py','motion.py','radio_model.py','audit_pair.py')]+[here.parent/'adaptive'/x for x in ('aodv.c','aodv.h','host_bridge.c','CONTRACT.md')]
hashes={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources};report={'status':'running','cases':cases,'results':[],'source_sha256':hashes,'deadline_utc':a.deadline_utc,'workers':2,'scope':'fixed initial spacing, not fixed area; 30-node results in adaptive matrix','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def save():(out/'campaign.json').write_text(json.dumps(report,indent=2),encoding='utf8')
prev=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001) if os.name=='nt' else 0;report['sleep_inhibition_set']=bool(prev);save()
try:
 for n,d in cases:
  if datetime.datetime.now(datetime.timezone.utc)>=deadline:report['status']='deadline_reached';break
  if any(hashlib.sha256(f.read_bytes()).hexdigest()!=hashes[str(f.relative_to(root))] for f in sources):raise RuntimeError('source changed during campaign')
  name=f'n{n}-{d}';folder=out/name;report['active']=name;save();cmd=[sys.executable,'-B',str(here/'batch.py'),'--output',str(folder),'--nodes',str(n),'--mode','crossing','--speed','25','--density',d,'--baseline','1','--candidate','5','--deadline-utc',a.deadline_utc]
  with (out/(name+'.log')).open('w',encoding='utf8') as f:rc=subprocess.run(cmd,cwd=root,stdout=f,stderr=subprocess.STDOUT).returncode
  if rc:report.update(status='interrupted',error=f'{name} batch exit {rc}');break
  metrics=[]
  for seed in range(5):
   if datetime.datetime.now(datetime.timezone.utc)>=deadline:break
   res=subprocess.run([sys.executable,'-B',str(here/'audit_pair.py'),str(folder/f'seed-{seed:02}-policy-1'),str(folder/f'seed-{seed:02}-policy-5'),'--output',str(folder/f'audit-seed-{seed:02}')],cwd=root,text=True,capture_output=True)
   if res.returncode:raise RuntimeError(res.stderr[:1000])
   x=json.loads((folder/f'audit-seed-{seed:02}'/'comparison.json').read_text());assert x['same_source_hashes'];metrics.append({'seed':seed,'base':x['base']['rate'],'candidate':x['candidate']['rate'],'delta':x['paired_rate_difference'],'base_control':x['base']['control_airtime_us'],'candidate_control':x['candidate']['control_airtime_us'],'worst_base_destination':x['base']['node_rates']['destination']['worst'],'worst_candidate_destination':x['candidate']['node_rates']['destination']['worst']})
  report['results'].append({'name':name,'audited_pairs':metrics});report.pop('active',None);save();print(json.dumps({'case':name,'audited':len(metrics)}),flush=True)
  if len(metrics)<5:report['status']='deadline_reached';break
 else:report['status']='completed'
except BaseException as e:report.update(status='failed',error=repr(e));raise
finally:
 if prev:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
 report.update(elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sleep_inhibition_released=bool(prev));save()
