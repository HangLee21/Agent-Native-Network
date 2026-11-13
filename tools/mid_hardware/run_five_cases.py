import subprocess,sys,json
from pathlib import Path
r=Path(__file__).resolve().parents[2]
cases=['AB','AC','AD','AE','BC','BD','BE','CD','CE','DE','chain_ABCDE','chain_BADEC']
for case in sys.argv[1:]:
 assert case in cases
 run='20261107-'+str(6+cases.index(case)).zfill(2)+'-'+case+'-RF'
 out=r/'simulation/outputs/H-005'/run
 cmd=[sys.executable,str(r/'tools/mid_hardware/run_bounded.py'),'--script',str(r/'tools/mid_hardware/execute_five.py'),'--logs',str(out)+'-supervisor','--seconds','80','--','--case',case,'--output',str(out)]
 code=subprocess.run(cmd).returncode
 print(json.dumps(dict(case=case,exit_code=code)),flush=True)
 if code:break
