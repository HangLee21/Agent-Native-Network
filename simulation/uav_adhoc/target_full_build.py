"""Create an isolated full ESP32-S3 target candidate; never flash."""
import datetime,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[2]; H=Path(__file__).resolve().parent
work=Path(sys.argv[1]).resolve();root=(R/'.local/mid/E1-030-engineering').resolve()
if not work.is_relative_to(root) or work==root:raise ValueError('isolated build directory required')
work.mkdir(parents=True,exist_ok=False); base=work/'firmware/mid_baseline';base.mkdir(parents=True)
for f in ('mid.c','mid.h'):shutil.copy2(R/'firmware/mid_baseline'/f,base/f)
shutil.copytree(R/'firmware/mid_baseline/field_agent',base/'field_agent')
f=base/'field_agent';shutil.copy2(H/'candidate/source_route.c',f/'source_route.c')
shutil.copy2(H/'candidate/neighbors_engineering.c',f/'neighbors.c')
for name in ('peer_cache_mac.c','peer_cache_mac.h','neighbor_sync.c','neighbor_sync.h'):shutil.copy2(H/'candidate'/name,f/name)
cm=f/'idf/main/CMakeLists.txt';s=cm.read_text(encoding='utf-8');s=s.replace('"../../source_route.c"','"../../source_route.c" "../../peer_cache_mac.c"',1)
s=s.replace('"../../neighbors.c"','"../../neighbors.c" "../../neighbor_sync.c"',1)
s=s.replace('set(IDENTITIES "MID_DISPLAY_ENABLED=${DISPLAY_ENABLED}")','set(IDENTITIES "MID_DISPLAY_ENABLED=${DISPLAY_ENABLED};ENGINEERING_RREQ_DEDUP=1;ENGINEERING_RECLAIM_LOST=1")',1)
s=s.replace('../../source_route.h ../../telemetry.c','../../source_route.h ../../peer_cache_mac.c ../../peer_cache_mac.h ../../neighbor_sync.c ../../neighbor_sync.h ../../telemetry.c',1)
s+='\ntarget_compile_definitions(${COMPONENT_LIB} PRIVATE ENGINEERING_RREQ_DEDUP=1 ENGINEERING_RECLAIM_LOST=1)\n';cm.write_text(s,encoding='utf-8')
app=f/'idf/main/app_main.c';s=app.read_text(encoding='utf-8');s=s.replace('#include "source_route.h"','#include "source_route.h"\n#include "peer_cache_mac.h"\n#include "neighbor_sync.h"',1)
needle='static uint64_t millis(void){return (uint64_t)esp_timer_get_time()/1000;}'
wrapper=(H/'candidate/sdk_peer_adapter.inc').read_text(encoding='utf-8')
assert s.count(needle)==1;s=s.replace(needle,needle+wrapper,1)
needle='static void route_tick(void){uint64_t start=(uint64_t)esp_timer_get_time();'
assert s.count(needle)==1;s=s.replace(needle,needle+'e1_clear_absent_neighbors(&router,&neighbors);',1)
old='r=esp_now_register_recv_cb(receive_cb);'
assert s.count(old)==1;s=s.replace(old,'memset(&e1_peers,0,sizeof(e1_peers));r=esp_now_register_recv_cb(receive_cb);',1)
old='if(r==ESP_OK&&!esp_now_is_peer_exist(route_pending.next.mac)){esp_now_peer_info_t p={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};memcpy(p.peer_addr,route_pending.next.mac,6);r=esp_now_add_peer(&p);}'
assert s.count(old)==1;s=s.replace(old,'if(r==ESP_OK)r=e1_ensure_peer(route_pending.next.mac);',1)
old='if(!esp_now_is_peer_exist(broadcast)){esp_now_peer_info_t p={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};memcpy(p.peer_addr,broadcast,6);r=esp_now_add_peer(&p);}'
assert s.count(old)==1;s=s.replace(old,'r=e1_ensure_peer(broadcast);',1)
old='if(r==ESP_OK&&!esp_now_is_peer_exist(pending.next.mac)){esp_now_peer_info_t peer={.channel=CHANNEL,.ifidx=WIFI_IF_STA,.encrypt=false};memcpy(peer.peer_addr,pending.next.mac,6);r=esp_now_add_peer(&peer);}'
assert s.count(old)==1;s=s.replace(old,'if(r==ESP_OK)r=e1_ensure_peer(pending.next.mac);',1)
app.write_text(s,encoding='utf-8')
sdk=R/'.local/espnow/E1-015';mapping=subprocess.check_output(['subst'],text=True);line=[x for x in mapping.splitlines() if x.upper().startswith('R:')]
created=False
if line:
 if str(sdk).casefold() not in line[0].casefold():raise RuntimeError('R: already assigned elsewhere')
else:subprocess.run(['subst','R:',str(sdk)],check=True);created=True
env=dict(os.environ);env.update(json.loads((sdk/'environment.json').read_text(encoding='utf-8')))
for name in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(name,None)
tmp=work/'tmp';tmp.mkdir();env.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE='1',CMAKE_BUILD_PARALLEL_LEVEL='2',CCACHE_DISABLE='1',IDF_COMPONENT_CACHE_PATH=str(work/'cache'))
project=f/'idf';build=work/'build';config=work/'sdkconfig';start=time.monotonic()
cmd=['R:/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe','R:/sdk/esp-idf-v5.5.1/tools/idf.py','-B',str(build),'-D','SDKCONFIG='+str(config),'-D','SDKCONFIG_DEFAULTS='+str(project/'sdkconfig.defaults'),'-D','MID_HEADLESS=OFF','reconfigure']
report={'status':'running','started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'project':str(project),'build':str(build),'command':cmd,'limit_seconds':1200,'cpu_jobs':2,
 'candidate_source_hash':hashlib.sha256((f/'source_route.c').read_bytes()).hexdigest(),'peer_source_hash':hashlib.sha256((f/'peer_cache_mac.c').read_bytes()).hexdigest(),'nd_source_hash':hashlib.sha256((f/'neighbors.c').read_bytes()).hexdigest(),'sync_source_hash':hashlib.sha256((f/'neighbor_sync.c').read_bytes()).hexdigest(),
 'app_source_hash':hashlib.sha256(app.read_bytes()).hexdigest(),'cmake_source_hash':hashlib.sha256(cm.read_bytes()).hexdigest(),
 'limitations':['Isolated target build only; no flash, serial, board RAM watermarks or RF measurements','SDK peer adapter failures need host/integration and physical validation']}
def save():(work/'target_build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
save()
try:
 for name,command in [('configure',cmd),('build',['R:/tools/tools/cmake/3.30.2/bin/cmake.exe','--build',str(build),'--parallel','2'])]:
  remaining=1200-(time.monotonic()-start)
  if remaining<=0:raise TimeoutError('build budget')
  with (work/(name+'.log')).open('w',encoding='utf-8') as log:
   proc=subprocess.Popen(command,cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
   try:code=proc.wait(timeout=remaining)
   except subprocess.TimeoutExpired:
    subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],check=False);proc.wait();raise
   if code:raise subprocess.CalledProcessError(code,command)
 artifacts=[build/'mid_edge.bin',build/'mid_edge.elf',build/'mid_edge.map',build/'partition_table/partition-table.bin']
 report.update(status='built',artifacts={str(x.relative_to(build)):dict(bytes=x.stat().st_size,sha256=hashlib.sha256(x.read_bytes()).hexdigest()) for x in artifacts})
except Exception as e:report.update(status='failed',error=repr(e));raise
finally:
 report.update(elapsed_seconds=time.monotonic()-start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());save()
 if created:subprocess.run(['subst','R:','/D'],check=False)
 print(json.dumps({'status':report['status'],'elapsed_seconds':report['elapsed_seconds'],'path':str(work)}),flush=True)
