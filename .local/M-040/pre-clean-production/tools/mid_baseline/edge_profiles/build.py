"""Build isolated OLED/headless ESP32-S3 candidates using the already installed toolchain."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SDK_ROOT = ROOT / ".local/espnow/E1-015"

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--candidate", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--variant", choices=["oled", "headless"], required=True)
    a=p.parse_args()
    for name in (a.candidate,a.run):
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):
            raise ValueError("candidate/run must be simple names")
    local=ROOT/".local/mid/E1-023";local.mkdir(parents=True,exist_ok=True)
    work=local/a.candidate;work.mkdir(exist_ok=True)
    fw=work/"firmware"
    if not fw.exists():
        (fw/"mid_baseline").mkdir(parents=True)
        for name in ("mid.c","mid.h"):shutil.copy2(ROOT/"firmware/mid_baseline"/name,fw/"mid_baseline"/name)
        shutil.copytree(ROOT/"firmware/mid_baseline/edge",fw/"mid_baseline/edge")
        shutil.copytree(ROOT/"firmware/mid_display",fw/"mid_display")
    out=ROOT/"simulation/outputs/E1-023"/a.run;out.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    mapping=subprocess.check_output(["subst"],text=True)
    current=[s for s in mapping.splitlines() if s.upper().startswith("R:")]
    if current:
        if str(SDK_ROOT).casefold() not in current[0].casefold():raise RuntimeError("R: belongs to a different workspace")
    else:subprocess.run(["subst","R:",str(SDK_ROOT)],check=True)
    env=os.environ.copy();env.update(json.loads((SDK_ROOT/"environment.json").read_text()))
    for key in ("PYTHONHOME","PYTHONPATH","VIRTUAL_ENV"):env.pop(key,None)
    tmp=work/"tmp";tmp.mkdir(exist_ok=True)
    env.update(TEMP=str(tmp),TMP=str(tmp),PYTHONDONTWRITEBYTECODE="1",CMAKE_BUILD_PARALLEL_LEVEL="2",CCACHE_DISABLE="1",IDF_COMPONENT_CACHE_PATH=str(work/"component-cache"))
    project=fw/"mid_baseline/edge/idf";build=work/("build-"+a.variant);config=work/("sdkconfig-"+a.variant)
    command=["R:/tools/python_env/idf5.5_py3.11_env/Scripts/python.exe","R:/sdk/esp-idf-v5.5.1/tools/idf.py","-B",str(build),"-D","SDKCONFIG="+str(config),"-D","SDKCONFIG_DEFAULTS="+str(project/"sdkconfig.defaults"),"-D","MID_HEADLESS="+("ON" if a.variant=="headless" else "OFF"),"reconfigure"]
    m=json.loads((ROOT/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
    m.update(template_only=False,task_id="E1-023",run_id=a.run,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),worktree=str(ROOT),git_commit=subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip(),command=command,python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),status="running",budget=dict(cpu_jobs=2,per_command_s=1200),upstream_commit="fcae32885b0296b32044cb99ecbdc50d98dddb83",config_file=str(config),dependency_snapshot=str(SDK_ROOT/"environment.json"),limitations=["Target build only: no serial port opened, flash or RF test.","Existing SDK has recorded Windows archive mode changes."],variant=a.variant,source_sha256={str(f.relative_to(fw)):sha(f) for f in sorted(fw.rglob("*")) if f.is_file()})
    def save(): (out/"RUN_MANIFEST.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8")
    save();shutil.copy2(ROOT/"coordination/tasks/E1-023.md",out/"TASK_AT_RUN.md");shutil.copy2(__file__,out/"build.py")
    try:
        for name,cmd in [("configure",command),("build",["R:/tools/tools/cmake/3.30.2/bin/cmake.exe","--build",str(build),"--parallel","2"])]:
            with (out/(name+".log")).open("w",encoding="utf-8") as log:
                proc=subprocess.Popen(cmd,cwd=project,env=env,stdout=log,stderr=subprocess.STDOUT);m["child_pid"]=proc.pid;save()
                try:code=proc.wait(timeout=1200)
                except subprocess.TimeoutExpired:
                    subprocess.run(["taskkill","/PID",str(proc.pid),"/T","/F"],check=False);proc.wait();raise
                if code:raise RuntimeError((name,code))
        m.update(status="passed",exit_code=0,artifacts={str(f.relative_to(build)):dict(bytes=f.stat().st_size,sha256=sha(f)) for f in [build/"mid_edge.bin",build/"mid_edge.elf",build/"bootloader/bootloader.bin",build/"partition_table/partition-table.bin"]})
    except Exception as exc:m.update(status="failed",exit_code=1,error=repr(exc))
    finally:
        m.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),elapsed_s=time.monotonic()-start,child_reaped=True);save();print(json.dumps(dict(status=m["status"],elapsed_s=m["elapsed_s"],output=str(out))))
    return m["exit_code"]

if __name__=="__main__":raise SystemExit(main())
