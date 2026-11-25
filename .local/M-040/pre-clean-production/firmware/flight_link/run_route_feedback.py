"""Bounded paired SR+FLW2 fault fixtures, no hardware."""
import datetime,hashlib,json,os,pathlib,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[2];out=root/'simulation/outputs/E1-032/20261115-26-probe-focused';out.mkdir(parents=True,exist_ok=False)
before=root/'.local/mid/E1-032/20261114-29-recovery-candidate/source/mid_baseline';after=root/'firmware/flight_link/mid_baseline';test=root/'firmware/flight_link/tests/test_route_feedback.c';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
sources=[test]
for tree in (before,after):
 for rel in ('mid.c','mid.h','field_agent/source_route.c','field_agent/source_route.h','field_agent/reliable.c','field_agent/reliable.h','field_agent/lora_ref/flight_control.c','field_agent/lora_ref/flight_control.h'):sources.append(tree/rel)
sources.extend([after/'field_agent/reliable_route.c',after/'field_agent/reliable_route.h'])
m={'task_id':'E1-032','run_id':out.name,'started_at':datetime.datetime.now().astimezone().isoformat(),'timezone':'Asia/Shanghai','worktree':str(root),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'dirty_files_sha256':{str(p):sha(p) for p in sources},'command':'python firmware/flight_link/run_route_feedback.py','python_executable':sys.executable,'dependency_snapshot':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'upstream_commit':None,'data_and_weights_sha256':{},'config_file':str(test),'seeds':[],'budget':{'wall_s':300,'workers':1,'fixed_deadline_ms':1000},'output_directory':str(out),'process_id':os.getpid(),'status':'running','limitations':['Host fixed graph and injected losses, not RF or real device','RERR and ACK loss model does not simulate collision or channel occupancy'],'review_reference':None}
def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf8')
save();start=time.monotonic();rows=[]
try:
 for label,tree,flag in [('historical',before,['-DHISTORICAL']),('default',after,['-DMID_ROUTE_FEEDBACK=0']),('experimental',after,['-DMID_ROUTE_FEEDBACK=1'])]:
  exe=out/('candidate-'+label+'.exe');files=[test,tree/'mid.c',tree/'field_agent/source_route.c',tree/'field_agent/reliable.c',tree/'field_agent/lora_ref/flight_control.c'];
  if label!='historical':files.append(tree/'field_agent/reliable_route.c')
  cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror',*flag,'-I'+str(tree),'-I'+str(tree/'field_agent'),*[str(x) for x in files],'-o',str(exe)];p=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(out/(label+'-compile.log')).write_text(p.stdout+p.stderr,encoding='utf8');p.check_returncode()
  for scenario in range(6):
   p=subprocess.run([str(exe),str(scenario)],capture_output=True,text=True,timeout=60);(out/(label+'-'+str(scenario)+'.log')).write_text(p.stdout+p.stderr,encoding='utf8');p.check_returncode();rows.append({'version':label,**json.loads(p.stdout)})
 (out/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
 d={(x['version'],x['case']):x for x in rows}
 assert d['default',1]['confirmed']==0 and d['experimental',1]['confirmed']==1 and d['experimental',1]['timeout_unknown']==2 and d['experimental',1]['third_confirmed_ms']<=1000
 for k in (3,4):assert d['experimental',k]['received']==0 and d['experimental',k]['confirmed']==0 and d['experimental',k]['timeout_unknown']==3
 for k in (0,2):assert d['experimental',k]['received']==3 and d['experimental',k]['confirmed']==3 and d['experimental',k]['first_confirmed_ms']<=1000 and d['experimental',k]['second_confirmed_ms']<=1000
 assert d['experimental',1]['feedback_probes']==1 and d['experimental',2]['feedback_probes']==0
 assert d['experimental',5]['received']==3 and d['experimental',5]['confirmed']==1 and d['experimental',5]['timeout_unknown']==2 and d['experimental',5]['feedback_probes']==1 and d['experimental',5]['cache_retained_during_probe']==1
 m.update(status='complete',exit_code=0)
except BaseException as e:m.update(status='failed',exit_code=1,error=repr(e));raise
finally:m.update(finished_at=datetime.datetime.now().astimezone().isoformat(),elapsed_s=time.monotonic()-start);save()
print(json.dumps(rows,indent=2))
