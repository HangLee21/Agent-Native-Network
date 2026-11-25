"""Bounded host validation of the same offline installer and headless display model."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from make_profile import make
from build import ROOT, sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--run",required=True);a=p.parse_args()
    if any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in a.run):raise ValueError("simple run name required")
    out=ROOT/"simulation/outputs/E1-023"/a.run;out.mkdir(parents=True,exist_ok=False)
    files=["firmware/mid_baseline/mid.c","firmware/mid_baseline/mid.h","firmware/mid_baseline/edge/deployment.c","firmware/mid_baseline/edge/deployment.h","firmware/mid_baseline/edge/test_deployment.c","firmware/mid_baseline/edge/headless_components/mid_display/headless.c","firmware/mid_display/src/mid_display_model.c","firmware/mid_display/include/mid_display.h","tools/mid_baseline/edge_profiles/make_profile.py"]
    m=json.loads((ROOT/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"));start=time.monotonic()
    m.update(template_only=False,task_id="E1-023",run_id=a.run,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),worktree=str(ROOT),git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),status="running",budget=dict(per_command_s=120,cpu_jobs=1),seeds=[],limitations=["Synthetic host forwarding/reset and serialized profile; no ESP NVS, radio, physical display or three-host evidence."],source_sha256={f:sha(ROOT/f) for f in files})
    for f in files:
        dest=out/"source"/f;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f,dest)
    src=out/"source";exe=out/"test_deployment.exe"
    cmd=["gcc","-std=c99","-Wall","-Wextra","-Werror","-pedantic","-I"+str(src/"firmware/mid_baseline"),"-I"+str(src/"firmware/mid_baseline/edge"),"-I"+str(src/"firmware/mid_display/include")]+[str(src/f) for f in files if f.endswith(".c")]+["-o",str(exe)]
    m["command"]=cmd
    try:
        with (out/"host.log").open("w",encoding="utf-8") as log:
            subprocess.run(["gcc","--version"],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10)
            subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
            for path in (["A","B","C"],["A","B","C","D","E"]):
                profile=make(path,True,"host-"+"".join(path));table=out/("table-"+str(len(path))+".bin");table.write_bytes(bytes.fromhex(profile["table_hex"]))
                (out/(table.stem+".json")).write_text(json.dumps(profile,indent=2)+"\n",encoding="utf-8")
                subprocess.run([str(exe),str(table)],stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        m.update(status="passed",exit_code=0)
    except Exception as exc:m.update(status="failed",exit_code=1,error=repr(exc))
    m.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),elapsed_s=time.monotonic()-start,child_reaped=True)
    (out/"RUN_MANIFEST.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8");print(json.dumps(dict(status=m["status"],output=str(out))))
    return m["exit_code"]
if __name__=="__main__":raise SystemExit(main())
