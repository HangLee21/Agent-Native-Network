"""Isolated, bounded ESP32-S3 full candidate build; never touches devices."""
import ctypes, datetime, hashlib, json, os, pathlib, re, shutil, subprocess, sys, time
import psutil

ROOT=pathlib.Path(__file__).resolve().parents[2]
SOURCE=ROOT/'firmware/flight_link/mid_baseline'
out=pathlib.Path(sys.argv[1]).resolve(); allowed=(ROOT/'.local/mid/E1-032').resolve()
mode=sys.argv[2] if len(sys.argv)>2 else 'default'
if mode not in ('default','experimental') or len(sys.argv)>3: raise ValueError('mode must be default or experimental')
if not out.is_relative_to(allowed) or out==allowed: raise ValueError('new isolated E1-032 output required')
out.mkdir(parents=True,exist_ok=False)
snap=out/'source'/'mid_baseline';shutil.copytree(SOURCE,snap)
project=snap/'field_agent/idf'; build=out/'build';config=out/'sdkconfig';tmp=out/'tmp';tmp.mkdir()
sdk=ROOT/'.local/espnow/E1-015';drive=next((x+':' for x in 'ZYXWVUTS' if not os.path.exists(x+':\\')),None)
if not drive: raise RuntimeError('no unused isolated drive letter')
subprocess.run(['subst',drive,str(sdk)],check=True)
env=dict(os.environ);saved=json.loads((sdk/'environment.json').read_text(encoding='utf8'))
for k,v in saved.items():env[k]=v.replace('R:',drive).replace('r:',drive)
for k in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(k,None)
env.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE='1',CMAKE_BUILD_PARALLEL_LEVEL='2',CCACHE_DISABLE='1',IDF_COMPONENT_CACHE_PATH=str(out/'cache'))
files=[x for x in snap.rglob('*') if x.is_file()]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest={'task_id':'E1-032','status':'running','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':{str(p.relative_to(snap)):sha(p) for p in files},'workers':2,'wall_cap_s':1200,'config':'full display; isolated new build and sdkconfig','route_feedback':mode,'limits':['No serial, flashing or RF','Configuration and NVS preserved on actual devices; not modified here']}
def save():(out/'BUILD_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
prev=ctypes.windll.kernel32.SetThreadExecutionState(0x80000001) if os.name=='nt' else 0;manifest['sleep_inhibition_set']=bool(prev);save();start=time.monotonic();child=None
try:
 cmds=[('configure',[drive+'/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe',drive+'/sdk/esp-idf-v5.5.1/tools/idf.py','-B',str(build),'-D','SDKCONFIG='+str(config),'-D','SDKCONFIG_DEFAULTS='+str(project/'sdkconfig.defaults'),'-D','MID_HEADLESS=OFF','-D','MID_ROUTE_FEEDBACK='+('ON' if mode=='experimental' else 'OFF'),'reconfigure']),('build',[drive+'/tools/tools/cmake/3.30.2/bin/cmake.exe','--build',str(build),'--parallel','2'])]
 for name,cmd in cmds:
  with (out/(name+'.log')).open('w',encoding='utf8') as log:
   child=subprocess.Popen(cmd,cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
   while child.poll() is None:
    if time.monotonic()-start>=1200 or psutil.virtual_memory().available<1073741824 or shutil.disk_usage(out).free<2147483648:
     parent=psutil.Process(child.pid)
     for p in reversed(parent.children(recursive=True)):
      try:p.terminate()
      except psutil.NoSuchProcess:pass
     parent.terminate();child.wait();raise RuntimeError('time or resource guard interrupted build')
    time.sleep(.5)
   if child.returncode:raise subprocess.CalledProcessError(child.returncode,cmd)
   child=None
 binary=build/'mid_edge.bin';elf=build/'mid_edge.elf';text=(build/'compile_commands.json').read_text(encoding='utf8');ids=set(re.findall(r'mid-lora-ref-v1-[0-9a-f]{64}',text))
 if len(ids)!=1:raise RuntimeError('unique build id not found in compile commands')
 partition=build/'partition_table/partition-table.bin'; raw=partition.read_bytes()
 if len(raw)>4096:raise RuntimeError('partition table exceeds 4096-byte comparison area')
 padded=out/'partition-table-4k.bin';padded.write_bytes(raw+b'\xff'*(4096-len(raw)))
 manifest.update(status='built',build_id=next(iter(ids)),app_offset='0x10000',app_sha256=sha(binary),app_bytes=binary.stat().st_size,elf_sha256=sha(elf),partition_table_sha256=sha(partition),partition_table_4k_sha256=sha(padded),partition_table_4k_bytes=4096)
except BaseException as e:manifest.update(status='failed',error=repr(e));raise
finally:
 if prev:ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
 subprocess.run(['subst',drive,'/D'],capture_output=True)
 manifest.update(elapsed_s=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),sleep_inhibition_released=bool(prev));save();print(json.dumps({'status':manifest['status'],'output':str(out),'elapsed_s':manifest['elapsed_s']}),flush=True)
