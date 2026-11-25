"""Compile/run same bounded telemetry C core; never opens a serial port."""
from pathlib import Path
import argparse,datetime,json,subprocess,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[3]
def main():
    p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
    if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
    out=ROOT/'simulation/outputs/E1-026'/a.run;out.mkdir(parents=True,exist_ok=False)
    files=['firmware/mid_baseline/mid.c','firmware/mid_baseline/mid.h','firmware/mid_baseline/mobile_telemetry/telemetry.c','firmware/mid_baseline/mobile_telemetry/telemetry.h','firmware/mid_baseline/mobile_telemetry/test_telemetry.c']
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-026',run_id=a.run,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),output_directory=str(out),python_executable=sys.executable,budget=dict(per_command_s=120,device_access=0,downloads=0),status='running',source_sha256={f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},limitations=['Host C telemetry only: no RF, rx_ctrl runtime, GPS hardware or physical board/NVS evidence.'])
    def save():(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8')
    save()
    for f in files:
        dest=out/'source'/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f,dest)
    src=out/'source';cmd=['gcc','-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(src/'firmware/mid_baseline'),'-I'+str(src/'firmware/mid_baseline/mobile_telemetry')]+[str(src/f) for f in files if f.endswith('.c')]+['-o',str(out/'test.exe')];m['command']=cmd;save()
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=120);(out/'compile.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode()
        r=subprocess.run([str(out/'test.exe')],capture_output=True,text=True,timeout=120);(out/'host.log').write_text(r.stdout+r.stderr,encoding='utf-8');r.check_returncode();m.update(status='passed',exit_code=0);print(r.stdout)
    except Exception as e:m.update(status='failed',exit_code=1,error=repr(e))
    m['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();save();print(json.dumps(dict(status=m['status'],output=str(out))));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
