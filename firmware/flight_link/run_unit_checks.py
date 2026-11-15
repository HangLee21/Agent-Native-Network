import datetime,hashlib,json,pathlib,subprocess,sys,time,os
root=pathlib.Path(__file__).resolve().parents[2];tree=root/'firmware/flight_link/mid_baseline';f=tree/'field_agent';run_id=sys.argv[1] if len(sys.argv)>1 else '20261114-19-recovery-tests';assert pathlib.Path(run_id).name==run_id;out=root/'simulation/outputs/E1-032'/run_id;out.mkdir(parents=True,exist_ok=False)
common=[tree/'mid.c',f/'source_route.c'];fc=f/'lora_ref/flight_control.c';rel=f/'reliable.c';disp=f/'display/mid_display';cases={
 'peer':[f/'test_peer_manager.c',f/'peer_manager.c'],
 'route':[f/'test_source_route.c',*common],
 'reliable':[f/'test_reliable.c',rel,fc],
 'reliable_route':[f/'test_reliable_route.c',*common,rel,fc],
 'identity':[f/'test_node_identity.c',f/'node_identity.c',disp/'src/mid_display_model.c',disp/'src/mid_display_render.c'],
 'control':[f/'lora_ref/test_flight_control.c',fc],
 'recovery':[f/'lora_ref/test_recovery.c',f/'lora_ref/recovery.c',fc],
 'lora_worker':[root/'firmware/flight_link/tests/test_lora_worker.c',f/'lora_ref/recovery.c',fc],
 'boot_catalog':[f/'test_boot_catalog.c',f/'boot_catalog.c'],
 'route_config':[f/'test_route_config_store.c',f/'route_config_store.c',fc],
 'progress_health':[f/'test_progress_health.c',f/'progress_health.c'],
 'lrn1':[f/'test_lrn1.c',f/'lrn1_frame.c',f/'neighbors.c',tree/'mid.c'],
}
paths={p for group in cases.values() for p in group};paths.update([f/'lora_ref/runtime.c',f/'lora_ref/port.h',f/'lora_ref/recovery.h',f/'reliable.h',f/'source_route.h',f/'boot_catalog.h',f/'route_config_store.h',f/'progress_health.h',f/'idf/main/app_main.c',f/'idf/main/field_runtime.inc']);paths.update(p for p in (root/'firmware/flight_link/tests/stubs').rglob('*') if p.is_file());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
m={'task_id':'E1-032','run_id':out.name,'started_at':datetime.datetime.now().astimezone().isoformat(),'timezone':'Asia/Shanghai','worktree':str(root),'git_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'dirty_files_sha256':{str(p):sha(p) for p in paths},'command':'python firmware/flight_link/run_unit_checks.py '+run_id,'python_executable':sys.executable,'dependency_snapshot':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0],'upstream_commit':None,'data_and_weights_sha256':{},'config_file':None,'seeds':[],'budget':{'wall_s':300,'workers':1},'output_directory':str(out),'process_id':os.getpid(),'status':'running','limitations':['Host fixtures only; no serial, board or RF','lora_worker includes actual worker with fake scheduler and driver; other runtime functions excluded for host test','app_main and field_runtime hashes are provenance, not host-executed integration'],'review_reference':None}
def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf8')
save();start=time.monotonic();results=[]
try:
 for name,files in cases.items():
  exe=out/(name+'.exe');special=['-DLREF_WORKER_TEST','-Wno-unused-function','-Wno-unused-variable'] if name=='lora_worker' else (['-DMID_ROUTE_FEEDBACK=1'] if name=='route' else []);cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror',*special,'-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-I'+str(root/'firmware/flight_link/tests/stubs'),'-I'+str(f/'lora_ref/vendor/lr11xx/src'),'-I'+str(tree),'-I'+str(f),'-I'+str(disp/'include'),*[str(p) for p in files],'-o',str(exe)]
  c=subprocess.run(cmd,capture_output=True,text=True,timeout=60);(out/(name+'-compile.log')).write_text(c.stdout+c.stderr,encoding='utf8');c.check_returncode()
  r=subprocess.run([str(exe)],capture_output=True,text=True,timeout=60);(out/(name+'.log')).write_text(r.stdout+r.stderr,encoding='utf8');r.check_returncode();results.append({'name':name,'returncode':r.returncode,'exe_sha256':sha(exe)})
 (out/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8');m.update(status='complete',exit_code=0)
except BaseException as e:m.update(status='failed',exit_code=1,error=repr(e));raise
finally:m.update(finished_at=datetime.datetime.now().astimezone().isoformat(),elapsed_s=time.monotonic()-start);save()
print(json.dumps(results,indent=2))
