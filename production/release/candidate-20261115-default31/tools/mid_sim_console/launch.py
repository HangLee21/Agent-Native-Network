import json,subprocess,sys,urllib.request,urllib.error,webbrowser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];URL='http://127.0.0.1:8767/'
try:
    with urllib.request.urlopen(URL+'api/status',timeout=2) as r:status=json.load(r)
except (urllib.error.URLError,TimeoutError):status=None
if status is not None:
    if status.get('mode')!='software_simulation':raise SystemExit('8767被其他服务占用，未修改已有服务。')
    webbrowser.open(URL)
else:
    raise SystemExit(subprocess.call([sys.executable,str(ROOT/'tools/mid_sim_console/server.py'),'--open'],cwd=ROOT))
