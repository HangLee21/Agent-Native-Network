"""Small host-only reverse-cache fixture, without changing active campaign."""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,time
R=Path(__file__).resolve().parents[3];H=Path(__file__).resolve().parent;out=Path(sys.argv[1]).resolve();allowed=(R/'simulation/outputs/E1-030').resolve()
if not out.is_relative_to(allowed) or out==allowed:raise ValueError('E1 output scope required')
out.mkdir(parents=True,exist_ok=False);src=out/'source';src.mkdir()
files=[H/'source_route_reverse.c',H/'test_reverse.c',H.parent/'candidate/test_chain.c',R/'firmware/mid_baseline/field_agent/source_route.h',R/'firmware/mid_baseline/mid.c',R/'firmware/mid_baseline/mid.h']
for f in files:shutil.copy2(f,src/f.name)
r={'status':'running','source_hashes':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'checks':[],'limitations':['Experimental host-only fixture; no simulated performance or target build']}
def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
save();start=time.monotonic()
try:
 for mode in (0,1):
  name=f'reverse-{mode}';exe=out/(name+'.exe');cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-DENGINEERING_RREQ_DEDUP=1','-DENGINEERING_REVERSE_CACHE='+str(mode),'-I'+str(src),str(src/'test_reverse.c'),str(src/'source_route_reverse.c'),str(src/'mid.c'),'-o',str(exe)]
  x=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/(name+'-compile.log')).write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
  x=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);(out/(name+'.log')).write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode();r['checks'].append(name);save()
  chain=out/f'chain-{mode}.exe';cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-DENGINEERING_RREQ_DEDUP=1','-DENGINEERING_REVERSE_CACHE='+str(mode),'-I'+str(src),str(src/'test_chain.c'),str(src/'source_route_reverse.c'),str(src/'mid.c'),'-o',str(chain)]
  x=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/f'chain-{mode}-compile.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
  x=subprocess.run([str(chain)],capture_output=True,text=True,timeout=30);(out/f'chain-{mode}.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode();r['checks'].append(f'chain-{mode}');save()
 r['status']='passed'
except Exception as e:r.update(status='failed',error=repr(e));raise
finally:r['elapsed_seconds']=time.monotonic()-start;save();print(json.dumps({'status':r['status'],'checks':r['checks']}),flush=True)
