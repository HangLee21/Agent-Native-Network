"""Isolated ESP-IDF link smoke with and without the same core; never flash."""
import datetime,hashlib,json,os,pathlib,shutil,subprocess,sys,time
root=pathlib.Path(__file__).resolve().parents[3];here=pathlib.Path(__file__).resolve().parent
out=pathlib.Path(sys.argv[1]).resolve();allowed=(root/'.local/mid/E1-031').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('isolated output required')
out.mkdir(parents=True,exist_ok=False);project=out/'project';main=project/'main';main.mkdir(parents=True)
for name in ('aodv.c','aodv.h'):shutil.copy2(here/name,main/name)
(project/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.16)\nset(COMPONENTS main)\ninclude($ENV{IDF_PATH}/tools/cmake/project.cmake)\nproject(manet_link_smoke)\n')
(project/'sdkconfig.defaults').write_text('CONFIG_IDF_TARGET="esp32s3"\nCONFIG_ESPTOOLPY_FLASHSIZE_4MB=y\nCONFIG_ESP_MAIN_TASK_STACK_SIZE=8192\n')
(main/'CMakeLists.txt').write_text('idf_component_register(SRCS "main.c" "aodv.c" INCLUDE_DIRS ".")\nif(PROTOCOL_ENABLED)\n target_compile_definitions(${COMPONENT_LIB} PRIVATE PROTOCOL_ENABLED=1)\nendif()\n')
(main/'main.c').write_text('''#include "aodv.h"\n#ifdef PROTOCOL_ENABLED\nstatic ma_node node;static uint8_t buf[250];static uint32_t events[8];\n#endif\nvolatile int result;\nvoid app_main(void){\n#ifdef PROTOCOL_ENABLED\nint next,type;ma_init(&node,1,0);result=ma_submit(&node,2,1,buf,32,0);ma_tick(&node,10);result+=ma_next(&node,buf,&next,&type);ma_result(&node,0,20);result+=ma_receive(&node,2,buf,32,30);result+=ma_event_next(&node,events,buf);result+=ma_peer(&node,2,40);\n#else\nresult=0;\n#endif\n}\n''')
sdk=root/'.local/espnow/E1-015';drive=next((x+':' for x in 'ZYXWVUTS' if not os.path.exists(x+':\\')),None)
if not drive:raise RuntimeError('No available isolated drive letter')
subprocess.run(['subst',drive,str(sdk)],check=True);env=dict(os.environ);old=json.loads((sdk/'environment.json').read_text(encoding='utf8'))
for k,v in old.items():env[k]=v.replace('R:',drive).replace('r:',drive)
for k in ('PYTHONHOME','PYTHONPATH','VIRTUAL_ENV'):env.pop(k,None)
tmp=out/'tmp';tmp.mkdir();env.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE='1',CMAKE_BUILD_PARALLEL_LEVEL='1',CCACHE_DISABLE='1',IDF_COMPONENT_CACHE_PATH=str(out/'cache'))
start=time.monotonic();report={'status':'running','target':'esp32s3','source_sha256':{x:hashlib.sha256((main/x).read_bytes()).hexdigest() for x in ('aodv.c','aodv.h','main.c','CMakeLists.txt')},'cpu_jobs':1,'max_wall_s':1200,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limitations':['Minimal component project excludes ESP-NOW and unrelated LCD components','Link smoke only, no ESP-NOW integration, no flash, no actual runtime stack or heap','Code and data deltas include harness and linker effects; not fleet board measurements']}
def save():(out/'report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
save()
try:
 for enabled in (0,1):
  build=out/('with-core' if enabled else 'empty');config=out/('sdkconfig-core' if enabled else 'sdkconfig-empty')
  configure=[drive+'/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe',drive+'/sdk/esp-idf-v5.5.1/tools/idf.py','-B',str(build),'-D','SDKCONFIG='+str(config),'-D','SDKCONFIG_DEFAULTS='+str(project/'sdkconfig.defaults'),'-D',f'PROTOCOL_ENABLED={enabled}','reconfigure']
  commands=[configure,[drive+'/tools/tools/cmake/3.30.2/bin/cmake.exe','--build',str(build),'--parallel','1']]
  for index,cmd in enumerate(commands):
   rem=1200-(time.monotonic()-start)
   if rem<=0:raise TimeoutError('target build budget')
   with (out/(('configure-core.log' if enabled else 'configure-empty.log') if index==0 else ('with-core.log' if enabled else 'empty.log'))).open('w',encoding='utf8') as log:
    child=subprocess.Popen(cmd,cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT)
    try:code=child.wait(timeout=rem)
    except subprocess.TimeoutExpired:subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True);child.wait();raise
    if code:raise subprocess.CalledProcessError(code,cmd)
  bin=build/'manet_link_smoke.bin';elf=build/'manet_link_smoke.elf';size=drive+'/tools/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin/xtensa-esp32s3-elf-size.exe'
  sections=subprocess.check_output([size,'-A',str(elf)],env=env,text=True)
  (out/('with-core-size.txt' if enabled else 'empty-size.txt')).write_text(sections,encoding='utf8')
  report['with_core' if enabled else 'empty']={'binary_bytes':bin.stat().st_size,'binary_sha256':hashlib.sha256(bin.read_bytes()).hexdigest(),'elf_sha256':hashlib.sha256(elf.read_bytes()).hexdigest(),'sections_file':('with-core-size.txt' if enabled else 'empty-size.txt')};save()
 report['status']='built'
except BaseException as e:report.update(status='failed',error=repr(e));raise
finally:
 report.update(elapsed_seconds=time.monotonic()-start,finished_utc=datetime.datetime.now(datetime.timezone.utc).isoformat());save();subprocess.run(['subst',drive,'/D'],capture_output=True);print(json.dumps({'status':report['status'],'elapsed':report['elapsed_seconds'],'output':str(out)}),flush=True)
