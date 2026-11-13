"""Final staging CLI exercise, without activating any system services."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True);root=out/'staged-root'
config=out/'config.json';config.write_bytes((ROOT/'deploy/ubuntu/config.example.json').read_bytes());logs=[]
for action in ['install','uninstall']:
    command=[sys.executable,str(ROOT/'deploy/ubuntu/install.py'),action,'--root',str(root)]
    if action=='install':command+=['--config',str(config)]
    result=subprocess.run(command,capture_output=True,text=True,timeout=20);assert result.returncode==0,result.stderr
    logs.append(dict(command=command,returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
    if action=='install':
        shutil.copytree(root/'opt/mid-edge',out/'installed-runtime')
        (root/'var/lib/mid-edge').mkdir(parents=True);(root/'var/lib/mid-edge/user-state').write_text('preserve')
assert not (root/'opt/mid-edge').exists() and (root/'var/lib/mid-edge/user-state').read_text()=='preserve'
guard=subprocess.run([sys.executable,str(ROOT/'deploy/ubuntu/install.py'),'uninstall'],capture_output=True,text=True,timeout=5)
(out/'live-guard.json').write_text(json.dumps(dict(returncode=guard.returncode,stdout=guard.stdout,stderr=guard.stderr),indent=2))
assert guard.returncode==2 and ('requires --activate' in guard.stderr or 'live installation requires Ubuntu root' in guard.stderr)
(out/'checks.json').write_text(json.dumps(dict(status='passed',commands=logs,live_uninstall_without_stop_rejected=True,live_guard_reason=guard.stderr,retained_state=True,live_activation_tested=False),indent=2));print('Final staging CLI and live-removal guard passed')
