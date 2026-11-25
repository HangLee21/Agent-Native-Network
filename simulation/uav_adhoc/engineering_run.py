"""Finite, non-overwriting E1/E2 runner for the corrected radio model."""
import argparse, csv, datetime, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path
from engine_v2 import simulate_v2
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent

def main():
    global ROOT
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--repo-root',default=None)
    p.add_argument('--seconds',type=int,default=60);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--mode',choices=['formation','crossing','reorganize'],default='crossing')
    p.add_argument('--speed',type=int,default=25);p.add_argument('--density',choices=['compact','sparse'],default='compact')
    p.add_argument('--rate',type=float,default=1);p.add_argument('--payload',type=int,default=32)
    p.add_argument('--phy-rate',type=float,default=1);p.add_argument('--preamble-us',type=int,default=192)
    p.add_argument('--service-ms',type=int,default=10);p.add_argument('--geometry-ms',type=int,default=250)
    p.add_argument('--peer-eviction-us',type=int,default=0)
    p.add_argument('--sync-mode',choices=['event','periodic','cached'],default='periodic')
    p.add_argument('--policy',type=int,choices=range(8),default=0)
    p.add_argument('--prepare-only',action='store_true');p.add_argument('--reuse-build');a=p.parse_args()
    if a.prepare_only and a.reuse_build:p.error('prepare-only cannot reuse a build')
    if a.repo_root:
        ROOT=Path(a.repo_root).resolve()
        if not (ROOT/'coordination/templates/RUN_MANIFEST.json').is_file():p.error('repo root missing manifest template')
    if not (1<=a.seconds<=21600 and 0<a.rate<=5 and 16<=a.payload<=160 and a.phy_rate>0 and a.service_ms>=1 and a.geometry_ms>=1 and 0<=a.peer_eviction_us<=100000):p.error('invalid bounded parameters')
    out=Path(a.output).resolve();allowed=[(ROOT/'simulation/outputs/E1-030').resolve(),(ROOT/'simulation/outputs/E2-033').resolve()]
    if not any(out.is_relative_to(x) and out!=x for x in allowed):p.error('output must be a new directory under E1-030 or E2-033 outputs')
    out.mkdir(parents=True,exist_ok=False);source=out/'source';source.mkdir()
    files=[HERE/x for x in ['engine.py','engine_v2.py','radio_model.py','motion.py','core_bridge.c','semantic_check.py','churn_sync_check.py','engineering_run.py','candidate/source_route.c','candidate/neighbors_engineering.c','candidate/neighbor_sync.c','candidate/neighbor_sync.h','candidate/peer_cache_mac.c','candidate/peer_cache_mac.h','candidate/test_dedup.c','candidate/test_sdk_peer.c','candidate/sdk_peer_adapter.inc']]
    frozen_core=HERE/'firmware_core'
    if frozen_core.is_dir():
        files += [frozen_core/x for x in ['mid.c','mid.h','source_route.h','neighbors.h']]
    else:
        files += [ROOT/'firmware/mid_baseline'/x for x in ['mid.c','mid.h','field_agent/source_route.h','field_agent/neighbors.h']]
    for f in files:shutil.copy2(f,source/f.name)
    dll=out/'firmware_core.dll';cmd=['gcc','-O2','-std=c99','-shared','-DENGINEERING_RREQ_DEDUP='+str(a.policy&1),'-DENGINEERING_RECLAIM_LOST='+str(int(bool(a.policy&4))),'-I'+str(source),str(source/'core_bridge.c'),str(source/'source_route.c'),str(source/'peer_cache_mac.c'),str(source/'neighbors_engineering.c'),str(source/'neighbor_sync.c'),str(source/'mid.c'),'-o',str(dll)]
    config=dict(vars(a));config.update(nodes=30,geometry_radius_m=150,slot_us=20,difs_us=50,retry_limit=3,
      mac_overhead_bytes=43,mac_ack_us=314,phy='synthetic directed distance PRR; uncalibrated',
      algorithm={'rreq_dedup':bool(a.policy&1),'peer_lru':bool(a.policy&2),'reclaim_lost_neighbors':bool(a.policy&4)},
      queue='ND/ACK 16 items, expire >1000ms; SR actual core checks 250ms on dequeue',
      neighbor_sync={'event':'event-triggered plus expiry events','periodic':'all nodes each service tick','cached':'each service tick, update SR only on ND state change'}[a.sync_mode],
      limitations=['ACK is approximated in sender airtime and not a separate interfering transmission',
        'SDK peer add/delete is idealized; API failures are not modeled; eviction delay is a configurable unmeasured assumption',
        'endpoints not reached at finish may be failed or right-censored',
        'service tick 10ms approximates a variable callback-driven loop',
        'synthetic PHY is not real ESP-NOW airtime or measured packet error'])
    (out/'config.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    manifest.update(template_only=False,task_id=next(x.name for x in allowed if out.is_relative_to(x)),run_id=out.name,status='running',
      started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=[sys.executable,*sys.argv],
      source_hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
      source_snapshot=True,compile_command=cmd,output_directory=str(out),seed=a.seed,
      limitations=config['limitations'],budget={'wall_seconds':1200,'worker_count':1})
    def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    save();start=time.monotonic()
    try:
        if a.reuse_build:
            reference=Path(a.reuse_build).resolve()
            if not any(reference.is_relative_to(x) for x in allowed):raise ValueError('build reference outside task outputs')
            ref=json.loads((reference/'RUN_MANIFEST.json').read_text(encoding='utf-8'))
            ref_config=json.loads((reference/'config.json').read_text(encoding='utf-8'))
            if ref['status']!='prepared' or ref_config['policy']!=a.policy:raise ValueError('build policy or state mismatch')
            if ref['source_hashes']!=manifest['source_hashes']:raise ValueError('build source hashes differ')
            if hashlib.sha256((reference/'firmware_core.dll').read_bytes()).hexdigest()!=ref['binary_sha256']:raise ValueError('build binary hash differs')
            shutil.copy2(reference/'firmware_core.dll',dll)
            manifest.update(reused_build=str(reference),reused_build_manifest_sha256=hashlib.sha256((reference/'RUN_MANIFEST.json').read_bytes()).hexdigest(),compile_command=None)
        else:
            x=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            x=subprocess.run([sys.executable,'-B',str(source/'semantic_check.py'),str(dll)],capture_output=True,text=True,timeout=30)
            (out/'semantic_check.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            if a.policy&4:
                x=subprocess.run([sys.executable,'-B',str(source/'churn_sync_check.py'),str(dll)],capture_output=True,text=True,timeout=30)
                (out/'churn_sync_check.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            x=subprocess.run([sys.executable,'-B',str(source/'radio_model.py')],capture_output=True,text=True,timeout=30)
            (out/'radio_check.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            testbin=out/'dedup_check.exe'
            testcmd=['gcc','-O2','-std=c99','-DENGINEERING_RREQ_DEDUP='+str(a.policy&1),'-I'+str(source),str(source/'test_dedup.c'),str(source/'source_route.c'),str(source/'peer_cache_mac.c'),str(source/'mid.c'),'-o',str(testbin)]
            x=subprocess.run(testcmd,capture_output=True,text=True,timeout=30);(out/'dedup_compile.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            x=subprocess.run([str(testbin)],capture_output=True,text=True,timeout=30)
            (out/'dedup_check.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            sdkbin=out/'sdk_peer_check.exe'
            x=subprocess.run(['gcc','-O2','-std=c99','-Wall','-Wextra','-Werror','-I'+str(source),str(source/'test_sdk_peer.c'),str(source/'peer_cache_mac.c'),'-o',str(sdkbin)],capture_output=True,text=True,timeout=30)
            (out/'sdk_peer_compile.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
            x=subprocess.run([str(sdkbin)],capture_output=True,text=True,timeout=30)
            (out/'sdk_peer_check.log').write_text(x.stdout+x.stderr,encoding='utf-8');x.check_returncode()
        if a.prepare_only:
            manifest.update(status='prepared',exit_code=0,binary_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
            print(json.dumps({'status':'prepared','policy':a.policy}),flush=True)
            return
        with (out/'events.jsonl').open('w',encoding='utf-8') as f:
            result=simulate_v2(dll,a.mode,a.speed,a.seed,a.seconds,f,density=a.density,policy=a.policy,rate=a.rate,
                 payload_bytes=a.payload,service_ms=a.service_ms,geometry_ms=a.geometry_ms,
                 phy_rate_mbps=a.phy_rate,preamble_us=a.preamble_us,peer_eviction_us=a.peer_eviction_us,sync_mode=a.sync_mode,deadline=start+1200)
        (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        manifest.update(status='completed',exit_code=0,binary_sha256=hashlib.sha256(dll.read_bytes()).hexdigest())
        print(json.dumps(result),flush=True)
    except Exception as e:
        manifest.update(status='failed',exit_code=1,error=repr(e));raise
    finally:
        manifest['elapsed_seconds']=time.monotonic()-start;manifest['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
if __name__=='__main__':main()
