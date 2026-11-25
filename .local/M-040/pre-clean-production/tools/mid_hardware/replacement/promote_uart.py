import subprocess,sys,json
from pathlib import Path
r=Path(__file__).resolve().parents[3]
for board in 'ACDE':
 out=r/'simulation/outputs/H-006'/('20261107-U05-'+board+'-flash')
 cmd=[sys.executable,str(r/'tools/mid_hardware/replacement/run_bounded.py'),'--script',str(r/'tools/mid_hardware/replacement/flash_uart.py'),'--logs',str(out)+'-supervisor','--seconds','180','--','--board',board,'--package',str(r/'.local/mid/E1-017/uart-package-02'),'--runtime-baud','460800','--gate',str(r/'simulation/outputs/H-006/20261107-U00-UART-gate/gate.json'),'--output',str(out)]
 code=subprocess.run(cmd).returncode;print(json.dumps(dict(board=board,exit_code=code)),flush=True)
 if code:break
