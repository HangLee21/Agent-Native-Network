"""Bounded non-overwriting run using frozen E1-030 event-radio environment."""
import argparse,datetime,hashlib,json,os,pathlib,platform,shutil,subprocess,sys,time
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[2]
FROZEN=ROOT/'simulation/outputs/E1-030/20261114-62-engineering-frozen/src'
sys.path.insert(0,str(FROZEN))
sys.path.insert(0,str(HERE))
from engine_diagnostic import simulate_v2

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--ring-cap',type=int,choices=[8,16,32],default=16);p.add_argument('--hop-limit',type=int,choices=[8,16,32],default=32);p.add_argument('--pending-ms',type=int,default=3000);p.add_argument('--seconds',type=int,default=60);p.add_argument('--seed',type=int,default=0);p.add_argument('--mode',choices=['formation','crossing','reorganize'],default='crossing');p.add_argument('--speed',type=int,default=25);p.add_argument('--density',choices=['compact','sparse'],default='compact');p.add_argument('--rate',type=float,default=1.0);p.add_argument('--payload',type=int,default=32);p.add_argument('--policy',type=int,choices=[0,1,2,3],default=1);a=p.parse_args()
 if not(1<=a.seconds<=21600 and 0<a.rate<=5 and 1<=a.payload<=160):p.error('invalid bounded input')
 out=pathlib.Path(a.output).resolve();base=(ROOT/'simulation/outputs/E1-031').resolve()
 if not out.is_relative_to(base) or out==base:p.error('new output under E1-031 required')
 out.mkdir(parents=True,exist_ok=False);source=out/'src';source.mkdir()
 sources=[HERE/'aodv.c',HERE/'aodv.h',HERE/'host_bridge.c',HERE/'run.py',HERE/'CONTRACT.md',HERE/'engine_diagnostic.py']+[FROZEN/f for f in ('engine.py','engine_v2.py','motion.py','radio_model.py')]
 for f in sources:shutil.copy2(f,source/f.name)
 dll=out/'core.dll';cmd=['gcc','-O2','-std=c99','-shared',str(source/'aodv.c'),str(source/'host_bridge.c'),'-o',str(dll)]
 manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));start=time.monotonic()
 manifest.update(template_only=False,task_id='E1-031',run_id=out.name,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),timezone='UTC',worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,dependency_snapshot={'python':platform.python_version(),'compiler':subprocess.check_output(['gcc','--version'],text=True).splitlines()[0]},source_sha256={str(f.relative_to(ROOT)):digest(f) for f in sources},seeds=[a.seed],budget={'workers':1,'max_wall_s':1200},output_directory=str(out),process_id=os.getpid(),status='running',limitations=['Synthetic uncalibrated RF','AODV subset, not RFC wire compatible','No periodic HELLO or end-to-end ACK','SDK peer operations idealized'])
 (out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 try:
  subprocess.run(cmd,check=True,capture_output=True,text=True)
  with (out/'events.jsonl').open('w',encoding='utf8',buffering=1024*1024) as f:
   res=simulate_v2(dll,a.mode,a.speed,a.seed,a.seconds,f,density=a.density,policy=a.policy,rate=a.rate,payload_bytes=a.payload,sync_mode='cached',deadline=start+1200,ring_cap=a.ring_cap,hop_limit=a.hop_limit,pending_ms=a.pending_ms)
  (out/'summary.json').write_text(json.dumps(res,indent=2),encoding='utf8')
  manifest.update(status='completed',exit_code=0,binary_sha256=digest(dll));print(json.dumps({k:res[k] for k in ('offered','delivered','eligible_1s','eligible_within_1s','control_airtime_us','data_airtime_us','core_event_overflows')}))
 except BaseException as e:manifest.update(status='failed',exit_code=1,error=repr(e));raise
 finally:
  manifest.update(elapsed_seconds=time.monotonic()-start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
if __name__=='__main__':main()
