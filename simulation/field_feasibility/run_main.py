"""Run all preregistered N/seed combinations serially, preserving partial runs."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def write(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',required=True); ap.add_argument('--config',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); config_path=Path(args.config).resolve(); cfg=json.loads(config_path.read_text(encoding='utf8'))
    if cfg['phase']!=4 or cfg['node_counts']!=[5,10,20,30] or len(set(cfg['seeds']))<20:
        raise ValueError('Phase 4 requires all four scales and at least 20 distinct seeds')
    if cfg['policies']!=['A','B','C','D','D_degraded','E']: raise ValueError('missing primary or degraded control')
    out=Path(args.out).resolve(); out.mkdir(parents=True,exist_ok=False)
    (out/'config_main.json').write_bytes(config_path.read_bytes())
    manifest={'task_id':'E1-035','phase':4,'status':'running','started_at':datetime.now().astimezone().isoformat(),
              'timezone':'Asia/Shanghai','config_sha256':sha(config_path),'node_counts':cfg['node_counts'],
              'seeds':cfg['seeds'],'policies':cfg['policies'],'expected_main_runs':400,'expected_degraded_runs':80,
              'completed_node_counts':[],'process_id':os.getpid(),'python_executable':sys.executable,'command':sys.argv,
              'runner_sha256':sha(__file__)}
    write(out/'RUN_MANIFEST.json',manifest)
    env=dict(os.environ); env['OPENBLAS_NUM_THREADS']='1'; env['OMP_NUM_THREADS']='1'
    with (out/'run.log').open('w',encoding='utf8',buffering=1) as log:
        for count in cfg['node_counts']:
            sub=dict(cfg); sub['nodes']=count; sub.pop('node_counts')
            frozen=out/f'config-n{count:02d}.json'; write(frozen,sub)
            cmd=[sys.executable,'-u','simulation/field_feasibility/run_pilot.py','--data',str(Path(args.data).resolve()),
                 '--config',str(frozen),'--out',str(out/f'n{count:02d}')]
            print('Launching N=',count,flush=True); log.write('Launching '+repr(cmd)+'\n')
            child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace',env=env)
            for line in child.stdout:
                print(f'N={count} {line}',end='',flush=True); log.write(line)
            code=child.wait()
            if code:
                manifest.update(status='failed',exit_code=code,failed_n=count,finished_at=datetime.now().astimezone().isoformat())
                write(out/'RUN_MANIFEST.json',manifest); raise SystemExit(code)
            manifest['completed_node_counts'].append(count); write(out/'RUN_MANIFEST.json',manifest)
    manifest.update(status='completed',exit_code=0,finished_at=datetime.now().astimezone().isoformat())
    write(out/'RUN_MANIFEST.json',manifest)

if __name__=='__main__': main()
