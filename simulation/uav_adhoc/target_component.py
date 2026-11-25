"""Cross-compile both protocol components, preserving ESP32-S3 target sizes."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,sys
R=Path(__file__).resolve().parents[2]; here=Path(__file__).resolve().parent
out=Path(sys.argv[1]).resolve(); allowed=(R/'.local/mid/E1-030-engineering').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('isolated build path required')
out.mkdir(parents=True,exist_ok=False)
sdk=R/'.local/espnow/E1-015/tools/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin'
gcc=sdk/'xtensa-esp32s3-elf-gcc.exe';size=sdk/'xtensa-esp32s3-elf-size.exe';nm=sdk/'xtensa-esp32s3-elf-nm.exe'
if not gcc.exists():raise FileNotFoundError(gcc)
env=dict(os.environ,PATH=str(sdk)+os.pathsep+os.environ['PATH'])
src=out/'src';src.mkdir()
files=[here/'candidate/source_route.c',here/'candidate/peer_cache_mac.c',here/'candidate/peer_cache_mac.h',R/'firmware/mid_baseline/field_agent/source_route.h',R/'firmware/mid_baseline/field_agent/neighbors.c',R/'firmware/mid_baseline/field_agent/neighbors.h',R/'firmware/mid_baseline/mid.c',R/'firmware/mid_baseline/mid.h']
for f in files:shutil.copy2(f,src/f.name)
probe='''#include "source_route.h"\n#include "neighbors.h"\n#include "peer_cache_mac.h"\nchar size_e1_peer_cache[sizeof(e1_peer_cache)];\nchar size_sr_node[sizeof(sr_node)];\nchar size_nd_node[sizeof(nd_node)];\nchar size_sr_out[sizeof(sr_out)];\nchar size_sr_events[sizeof(((sr_node*)0)->events)];\nchar size_sr_seen[sizeof(((sr_node*)0)->seen)];\nchar size_sr_pending[sizeof(((sr_node*)0)->pending)];\nchar size_sr_rounds[sizeof(((sr_node*)0)->rounds)];\nchar size_sr_routes[sizeof(((sr_node*)0)->routes)];\nchar size_sr_outqueue[sizeof(((sr_node*)0)->out)];\nchar size_sr_peers[sizeof(((sr_node*)0)->peers)];\n'''
(src/'size_probe.c').write_text(probe,encoding='utf-8')
flags=['-Os','-std=c99','-ffunction-sections','-fdata-sections','-Wall','-Wextra','-Werror','-I'+str(src)]
report={'target':'esp32s3','compiler':subprocess.check_output([str(gcc),'--version'],env=env,text=True).splitlines()[0],
        'flags':flags,'sources':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
        'limits':['relocatable component only; not complete firmware image or actual runtime heap/stack measurements']}
for policy in (0,1):
 d=out/('baseline' if policy==0 else 'candidate');d.mkdir();objects=[]
 for name in ('source_route.c','neighbors.c','mid.c','peer_cache_mac.c','size_probe.c'):
  obj=d/(name+'.o');cmd=[str(gcc),*flags,'-DENGINEERING_RREQ_DEDUP='+str(policy),'-c',str(src/name),'-o',str(obj)]
  x=subprocess.run(cmd,env=env,capture_output=True,text=True);(d/(name+'.log')).write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode();objects.append(obj)
 # Probe symbols are excluded from the relocatable code-size artifact.
 x=subprocess.run([str(gcc),'-nostdlib','-Wl,-r,-Map='+str(d/'component.map'),*[str(o) for o in objects[:4]],'-o',str(d/'component.o')],env=env,capture_output=True,text=True)
 (d/'link.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
 st=subprocess.check_output([str(size),'-A',str(d/'component.o')],env=env,text=True)
 symbols=subprocess.check_output([str(nm),'-S','--size-sort',str(objects[4])],env=env,text=True)
 (d/'size.txt').write_text(st,encoding='utf-8');(d/'struct_sizes_nm.txt').write_text(symbols,encoding='utf-8')
 report['candidate' if policy else 'baseline']={'size_text':st,'probe_symbols':symbols,'component_sha256':hashlib.sha256((d/'component.o').read_bytes()).hexdigest()}
(out/'target_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))
