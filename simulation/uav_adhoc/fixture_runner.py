"""Build finite protocol and adapter fixtures against frozen C candidate."""
import argparse,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
R=Path(__file__).resolve().parents[2];H=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--repo-root');a=p.parse_args()
if a.repo_root:R=Path(a.repo_root).resolve()
out=Path(a.output).resolve();allowed=[(R/'simulation/outputs/E1-030').resolve(),(R/'simulation/outputs/E2-033').resolve()]
if not any(out.is_relative_to(x) and out!=x for x in allowed):raise ValueError('task output subtree required')
out.mkdir(parents=True,exist_ok=False);src=out/'source';src.mkdir()
fs=[H/'candidate'/x for x in ('source_route.c','neighbors_engineering.c','neighbor_sync.c','neighbor_sync.h','peer_cache_mac.c','peer_cache_mac.h','sdk_peer_adapter.inc','test_dedup.c','test_neighbor_churn.c','test_sdk_peer.c','test_chain.c')]
if (H/'firmware_core').is_dir():fs += [H/'firmware_core'/x for x in ('mid.c','mid.h','source_route.h','neighbors.h')]
else:fs += [R/'firmware/mid_baseline'/x for x in ('mid.c','mid.h','field_agent/source_route.h','field_agent/neighbors.h')]
for f in fs:shutil.copy2(f,src/f.name)
r={'status':'running','source_hashes':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in fs},'checks':[],'limitations':['host fixture only; no target runtime or RF evidence']}
def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
save();start=time.monotonic()
try:
 for mode in (0,1):
  for test,sources,macro in [('chain',['test_chain.c','source_route.c','mid.c'],'ENGINEERING_RREQ_DEDUP'),('churn',['test_neighbor_churn.c','neighbors_engineering.c','neighbor_sync.c','source_route.c','mid.c'],'ENGINEERING_RECLAIM_LOST'),('dedup',['test_dedup.c','source_route.c','peer_cache_mac.c','mid.c'],'ENGINEERING_RREQ_DEDUP')]:
   name=f'{test}-{mode}';exe=out/(name+'.exe');cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-D'+macro+'='+str(mode),'-I'+str(src),*[str(src/x) for x in sources],'-o',str(exe)]
   x=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/(name+'-compile.log')).write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
   x=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);(out/(name+'.log')).write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode();r['checks'].append(name);save()
 cmd=['gcc','-std=c99','-O2','-Wall','-Wextra','-Werror','-I'+str(src),str(src/'test_sdk_peer.c'),str(src/'peer_cache_mac.c'),'-o',str(out/'sdk.exe')]
 x=subprocess.run(cmd,capture_output=True,text=True,timeout=30);(out/'sdk-compile.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
 x=subprocess.run([str(out/'sdk.exe')],capture_output=True,text=True,timeout=30);(out/'sdk.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode();r['checks'].append('sdk')
 r['status']='passed'
except Exception as e:r.update(status='failed',error=repr(e));raise
finally:r['elapsed_seconds']=time.monotonic()-start;save();print(json.dumps({'status':r['status'],'checks':r['checks']}),flush=True)
