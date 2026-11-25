import subprocess,sys,json
from pathlib import Path
r=Path(__file__).resolve().parents[3]
for i,case in enumerate(['AB','AC','AD','AE','BC','BD','BE','CD','CE','DE'],1):
 out=r/'simulation/outputs/H-006'/f'20261107-L{i:02d}-link-{case}'
 code=subprocess.run([sys.executable,str(r/'tools/mid_hardware/replacement/run_bounded.py'),'--script',str(r/'tools/mid_hardware/replacement/measure_links.py'),'--logs',str(out)+'-supervisor','--seconds','60','--','--case',case,'--output',str(out)]).returncode
 print(json.dumps(dict(case=case,exit_code=code)),flush=True)
 if code:break
