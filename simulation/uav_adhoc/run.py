"""Bounded E1-030 Wi-Fi runs; output is exclusively a new task run directory."""
import argparse
import csv
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from engine import simulate

ROOT=Path(__file__).resolve().parents[2]
CODE=Path(__file__).resolve().parent


def main():
    raise RuntimeError('Legacy 25 ms diagnostic is frozen; use engineering_run.py')
    ap=argparse.ArgumentParser();ap.add_argument('--run-id',required=True);ap.add_argument('--suite',choices=['diagnostic','matrix'],required=True);a=ap.parse_args()
    if not a.run_id or any(not(c.isalnum() or c in '-_') for c in a.run_id):raise ValueError('simple run ID required')
    out=ROOT/'simulation/outputs/E1-030'/a.run_id;out.mkdir(parents=True,exist_ok=False)
    source=out/'source';source.mkdir()
    files=[CODE/'engine.py',CODE/'motion.py',CODE/'core_bridge.c',CODE/'run.py',CODE/'semantic_check.py',CODE/'candidate/peer_cache_mac.c',CODE/'candidate/peer_cache_mac.h',
           ROOT/'firmware/mid_baseline/mid.c',ROOT/'firmware/mid_baseline/mid.h',
           ROOT/'firmware/mid_baseline/field_agent/source_route.c',ROOT/'firmware/mid_baseline/field_agent/source_route.h',
           ROOT/'firmware/mid_baseline/field_agent/neighbors.c',ROOT/'firmware/mid_baseline/field_agent/neighbors.h']
    for p in files:shutil.copy2(p,source/p.name)
    dll=out/'firmware_core.dll';cmd=['gcc','-O2','-std=c99','-shared','-I'+str(source),str(source/'core_bridge.c'),str(source/'source_route.c'),str(source/'peer_cache_mac.c'),str(source/'neighbors.c'),str(source/'mid.c'),'-o',str(dll)]
    config=dict(suite=a.suite,nodes=30,seconds=15 if a.suite=='diagnostic' else 300,slot_ms=25,geometry_sample_ms=250,
       radius_m=150,phy='directed prr=clamp(1-0.35*(distance/radius)^2,0.10,0.99)',backoff_probability_per_slot=.18,
       carrier_sense='previous slot plus randomized greedy sensing within slot; hidden senders collide',retries=3,retry_backoff_slots=[1,8],nd_queue=16,peer_cap=20,
       seeds=[0] if a.suite=='diagnostic' else [0,1,2],speeds=[25] if a.suite=='diagnostic' else [5,25,50],
       modes=['crossing'] if a.suite=='diagnostic' else ['formation','crossing','reorganize'],policies=['baseline','local_cache_2s'],
       traffic='each node U(2,3) seconds; uniform nonself destination',density='30 nodes; fixed specified geometry',
       fairness='fixed motion and independent per-node traffic seeds; keyed backoff/PHY draws',
       candidate='locally clamp cached route lifetime to 2s; no future/global state; additional route discoveries are charged',
       limits='single batch 1200s, total task 3600s')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    manifest.update(template_only=False,task_id='E1-030',run_id=a.run_id,worktree=str(ROOT),started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
      command=[sys.executable,*sys.argv],compile_command=cmd,python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),status='running',
      seeds=config['seeds'],budget=dict(single_batch_seconds=1200,total_task_seconds=3600,processes=1),
      source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
      limitations=['Simplified slotted shared channel and ideal distance threshold; not an ESP-NOW RF emulator','No LoRa or physical devices'])
    def save(): (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    save();(out/'config.json').write_text(json.dumps(config,indent=2)+'\n',encoding='utf-8');start=time.monotonic();results=[]
    try:
      p=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(p.stdout+p.stderr,encoding='utf-8');p.check_returncode()
      manifest['binary_sha256']=hashlib.sha256(dll.read_bytes()).hexdigest();save()
      check=subprocess.run([sys.executable,'-B',str(source/'semantic_check.py'),str(dll)],capture_output=True,text=True,timeout=30)
      (out/'semantic_check.log').write_text(check.stdout+check.stderr,encoding='utf-8');check.check_returncode()
      for mode in config['modes']:
       for speed in config['speeds']:
        for seed in config['seeds']:
         for policy in range(2):
          if time.monotonic()-start>=1200:raise TimeoutError('batch wall budget before next run')
          name=f'{mode}-{speed}-seed{seed}-{config["policies"][policy]}';t0=time.monotonic()
          with (out/(name+'.jsonl')).open('w',encoding='utf-8') as f: result=simulate(dll,mode,speed,seed,policy,config['seconds'],f,deadline=start+1200)
          result.update(mode=mode,speed_m_s=speed,seed=seed,policy=config['policies'][policy],wall_seconds=time.monotonic()-t0)
          results.append(result);(out/'summary.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
          print(json.dumps(dict(run=name,offered=result['offered'],delivered=result['delivered'],wall_seconds=result['wall_seconds'])),flush=True)
      flat=[{k:v for k,v in row.items() if k!='node_stats'} for row in results]
      with (out/'summary.csv').open('w',encoding='utf-8',newline='') as f:
       w=csv.DictWriter(f,fieldnames=list(flat[0]));w.writeheader();w.writerows(flat)
      manifest.update(status='passed',exit_code=0,completed_runs=len(results))
    except Exception as exc:
      manifest.update(status='failed',exit_code=1,completed_runs=len(results),error=repr(exc));raise
    finally:
      manifest.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),elapsed_seconds=time.monotonic()-start);save()


if __name__=='__main__':main()
