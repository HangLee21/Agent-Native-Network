import json,subprocess,sys
from pathlib import Path
r=Path(__file__).resolve().parents[3];base=r/'simulation/outputs/H-006';source=r/'tools/mid_hardware/replacement/paired_run.py';common=base/'20261107-model-scenario'
order=json.loads((r/'tools/mid_baseline/validation/replacement/RUN_ORDER.json').read_text())
(base/'formal-run-order.json').write_text(json.dumps(order,indent=2))
for pair in range(2,6):
 arms=['replan','fixed'] if pair%2==0 else ['fixed','replan']
 for arm in arms:
  used=120+14.266+254.091995+sum(json.loads(p.read_text()).get('RF_host_window_seconds',0) for p in base.glob('20261107-pair??-*/result.json'))
  if used+80>1200:raise SystemExit('RF remaining budget cannot reserve80s; no additional run')
  out=base/f'20261107-pair{pair:02d}-{arm}'
  cmd=[sys.executable,str(r/'tools/mid_hardware/replacement/run_bounded.py'),'--script',str(source),'--logs',str(out)+'-supervisor','--seconds','100','--','--pair',str(pair),'--arm',arm,'--initial',str(common/'initial-solve'),'--scenario',str(common/'scenario.json'),'--model',str(common/'model.json'),'--output',str(out)]
  code=subprocess.run(cmd).returncode;print(json.dumps(dict(pair=pair,arm=arm,exit_code=code,RF_budget_before=used)),flush=True)
  if code:raise SystemExit(code)
