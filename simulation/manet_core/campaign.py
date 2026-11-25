"""Finite M-037 5-seed/600s matrix, bounded batches and saved audits."""
import argparse,ctypes,datetime,hashlib,json,os,pathlib,subprocess,sys,time
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--deadline-utc',required=True);a=p.parse_args()
root=pathlib.Path(__file__).resolve().parents[2];out=pathlib.Path(a.output).resolve();allowed=(root/'simulation/outputs/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise SystemExit('new E1-031 output required')
out.mkdir(parents=True,exist_ok=False);deadline=datetime.datetime.fromisoformat(a.deadline_utc.replace('Z','+00:00'));start=time.monotonic();here=pathlib.Path(__file__).resolve().parent
cases=[(mode,speed,density) for mode in ('formation','crossing','reorganize') for speed in (5,25,50) for density in ('compact','sparse') if (mode,speed,density)!=('crossing',25,'compact')]
files=['aodv.c','aodv.h','host_bridge.c','engine_diagnostic.py','run.py','batch.py','audit_pair.py','CONTRACT.md']
report={'status':'running','deadline_utc':deadline.isoformat(),'cases':cases,'results':[],'source_sha256':{f:hashlib.sha256((here/f).read_bytes()).hexdigest() for f in files},'seed_count':5,'simulation_seconds':600,'workers':2,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
def save():(out/'campaign.json').write_text(json.dumps(report,indent=2),encoding='utf8')
prev=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001) if os.name=='nt' else 0;report['sleep_inhibition_set']=bool(prev);save()
try:
 for mode,speed,density in cases:
  if datetime.datetime.now(datetime.timezone.utc)>=deadline:report['status']='deadline_reached';break
  if any(hashlib.sha256((here/f).read_bytes()).hexdigest()!=report['source_sha256'][f] for f in files):raise RuntimeError('source changed during campaign')
  name=f'{mode}-{speed}-{density}';folder=out/name;log=out/(name+'.log');cmd=[sys.executable,'-B',str(here/'batch.py'),'--output',str(folder),'--mode',mode,'--speed',str(speed),'--density',density,'--baseline','1','--candidate','3','--deadline-utc',a.deadline_utc]
  report['active']=name;save()
  with log.open('w',encoding='utf8') as stream: code=subprocess.run(cmd,cwd=root,stdout=stream,stderr=subprocess.STDOUT).returncode
  if code:
   report.update(status='interrupted',error=f'{name} batch exited {code}');break
  audited=[]
  for seed in range(5):
   if datetime.datetime.now(datetime.timezone.utc)>=deadline:break
   result=subprocess.run([sys.executable,'-B',str(here/'audit_pair.py'),str(folder/f'seed-{seed:02}-policy-1'),str(folder/f'seed-{seed:02}-policy-3'),'--output',str(folder/f'audit-seed-{seed:02}')],cwd=root,capture_output=True,text=True)
   if result.returncode:raise RuntimeError(f'{name} seed {seed} audit: {result.stderr[:1000]}')
   audit=json.loads((folder/f'audit-seed-{seed:02}'/'comparison.json').read_text());assert audit['same_source_hashes'];audited.append({'seed':seed,'base':audit['base']['rate'],'candidate':audit['candidate']['rate'],'delta':audit['paired_rate_difference'],'base_control':audit['base']['control_airtime_us'],'candidate_control':audit['candidate']['control_airtime_us'],'worst_base_destination':audit['base']['node_rates']['destination']['worst'],'worst_candidate_destination':audit['candidate']['node_rates']['destination']['worst']})
  report['results'].append({'name':name,'audited_pairs':audited});report.pop('active',None);save();print(json.dumps({'case':name,'audited':len(audited)}),flush=True)
  if len(audited)<5:report['status']='deadline_reached';break
 else:report['status']='completed'
except BaseException as e:report.update(status='failed',error=repr(e));raise
finally:
 if prev:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
 report.update(sleep_inhibition_released=bool(prev),elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
