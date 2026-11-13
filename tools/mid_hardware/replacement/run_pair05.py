import subprocess,sys,json
from pathlib import Path
r=Path(__file__).resolve().parents[3];base=r/'simulation/outputs/H-006';common=base/'20261107-model-scenario';budget=json.loads((base/'20261107-fault04-cleanup/budget.json').read_text());used=budget['RF_budget_upper_bound_used']
for arm in ['fixed','replan']:
 if used+80>1320:raise SystemExit('New1320s budget insufficient')
 out=base/('20261107-pair05-'+arm)
 cmd=[sys.executable,str(r/'tools/mid_hardware/replacement/run_bounded.py'),'--script',str(r/'tools/mid_hardware/replacement/paired_run.py'),'--logs',str(out)+'-supervisor','--seconds','100','--','--pair','5','--arm',arm,'--initial',str(base/'20261107-pair05-initial/solve'),'--scenario',str(common/'scenario.json'),'--model',str(common/'model.json'),'--output',str(out)]
 code=subprocess.run(cmd).returncode;print(json.dumps(dict(pair=5,arm=arm,exit_code=code)),flush=True)
 if code:raise SystemExit(code)
 used+=json.loads((out/'result.json').read_text())['RF_host_window_seconds']
