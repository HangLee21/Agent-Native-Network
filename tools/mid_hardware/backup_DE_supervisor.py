import subprocess,time,json,sys
from pathlib import Path
r=Path(__file__).resolve().parents[2];all_results=[]
for run in ['20261107-02-D-segmented','20261107-03-E-segmented']:
 g=r/'simulation/outputs/H-005'/run
 for part in range(4):
  t=time.monotonic()
  with (g/f'stdout-{part}.txt').open('xb') as o,(g/f'stderr-{part}.txt').open('xb') as e:
   try:p=subprocess.run([sys.executable,str(g/'run_segment.py'),'--part',str(part)],stdout=o,stderr=e,timeout=180);code=p.returncode
   except subprocess.TimeoutExpired:code=124
  item=dict(run=run,part=part,exit_code=code,elapsed_s=time.monotonic()-t)
  (g/f'supervisor-{part}.json').write_text(json.dumps(item));all_results.append(item)
  print(json.dumps(item),flush=True)
  if code:break
(r/'simulation/outputs/H-005/20261107-01-five-identify/DE-backup-supervisor.json').write_text(json.dumps(all_results,indent=2))
