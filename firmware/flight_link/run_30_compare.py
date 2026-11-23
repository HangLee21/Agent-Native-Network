"""Compile actual frozen and current C cores; deterministic host events, no devices."""
import datetime, hashlib, json, pathlib, subprocess, sys, time
root=pathlib.Path(__file__).resolve().parents[2]
out=(root/'simulation/outputs/E1-032/20261115-27-probe-paired').resolve()
out.mkdir(parents=True,exist_ok=False)
base=root/'.local/mid/E1-032/20261114-29-recovery-candidate/source/mid_baseline'
new=root/'firmware/flight_link/mid_baseline';fixture=new/'field_agent/test_30_event.c'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources=[fixture,new/'field_agent/peer_manager.c',new/'field_agent/peer_manager.h',new/'field_agent/reliable_route.c',new/'field_agent/reliable_route.h']
for tree in (base,new):
 for f in ['mid.c','mid.h','field_agent/source_route.c','field_agent/source_route.h','field_agent/reliable.c','field_agent/reliable.h','field_agent/lora_ref/flight_control.c','field_agent/lora_ref/flight_control.h']:sources.append(tree/f)
manifest={'task_id':'E1-032','run_id':out.name,'started_at':datetime.datetime.now().astimezone().isoformat(),'timezone':'Asia/Shanghai','worktree':str(root),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'dirty_files_sha256':{str(p):sha(p) for p in sources},'command':'python firmware/flight_link/run_30_compare.py','python_executable':sys.executable,'dependency_snapshot':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'upstream_commit':None,'data_and_weights_sha256':{},'config_file':str(fixture),'seeds':[],'budget':{'wall_s':600,'workers':1,'nodes':30,'offered_each':30,'payload_bytes':16,'deadline_ms':1000,'step_ms':10},'output_directory':str(out),'process_id':__import__('os').getpid(),'status':'running','limitations':['deterministic host model; no RF collisions, real ESP-NOW callbacks, CPU scheduling, antenna or mobility physics','driver limit 20 peers including broadcast','loss keyed by logical message, hop, attempt; actual traces diverge as routing changes','no randomness','endpoint confirmation, not flight validation'],'review_reference':None}
def save(): (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
save();started=time.monotonic();results=[]
try:
 for label,tree,flags in [('historical',base,['-DHISTORICAL']),('default',new,['-DMID_ROUTE_FEEDBACK=0']),('experimental',new,['-DMID_ROUTE_FEEDBACK=1'])]:
  exe=out/('candidate-'+label+'.exe');extra=[str(new/'field_agent/reliable_route.c')] if label!='historical' else [];cmd=['gcc','-std=c99','-O2','-Wall','-Wextra',*flags,'-I'+str(tree),'-I'+str(tree/'field_agent'),'-I'+str(new/'field_agent'),str(fixture),str(tree/'mid.c'),str(tree/'field_agent/source_route.c'),str(tree/'field_agent/reliable.c'),str(tree/'field_agent/lora_ref/flight_control.c'),str(tree/'field_agent/peer_manager.c'),*extra,'-o',str(exe)]
  c=subprocess.run(cmd,text=True,capture_output=True,timeout=120);(out/(label+'-compile.log')).write_text(c.stdout+c.stderr,encoding='utf8');c.check_returncode()
  for scenario in ('dense','mobility','mobility1','mobility2'):
   p=subprocess.run([str(exe),scenario],text=True,capture_output=True,timeout=180);(out/(label+'-'+scenario+'.log')).write_text(p.stdout+p.stderr,encoding='utf8');p.check_returncode();results.append({'version':label,**json.loads(p.stdout)})
 (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8');manifest.update(status='complete',exit_code=0)
except BaseException as e:
 manifest.update(status='failed',exit_code=1,error=repr(e));raise
finally:
 manifest.update(finished_at=datetime.datetime.now().astimezone().isoformat(),elapsed_s=time.monotonic()-started);save()
print(json.dumps(results,indent=2))
