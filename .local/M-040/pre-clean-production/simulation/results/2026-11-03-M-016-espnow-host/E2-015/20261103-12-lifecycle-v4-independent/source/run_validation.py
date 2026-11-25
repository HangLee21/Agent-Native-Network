"""Bounded host-only test runner; source snapshots and persistent 600s ledger."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest

OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[1]
OUT=ROOT/"simulation/outputs/E2-015"
LEDGER=OWN/"execution_budget.jsonl"


def now(): return datetime.now(timezone.utc).isoformat()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")


def child(result_path,pattern):
    os.environ["E2_TEST_OUTPUT"] = str(Path(result_path).resolve().parent)
    suite=unittest.defaultTestLoader.discover(str(OWN),pattern=pattern,top_level_dir=str(OWN))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    core_build=Path(result_path).parent/"core_build.json"
    write(Path(result_path),dict(evidence_kind="synthetic_host_tests",tests_run=result.testsRun,
                               failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
                               successful=result.wasSuccessful(),real_radio_calls=0,real_model_calls=0,
                               actual_E1_core_compiled=core_build.exists(),hardware_measurements=False))
    return 0 if result.wasSuccessful() else 1


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--output");p.add_argument("--child");p.add_argument("--pattern",default="test_*.py")
    args=p.parse_args()
    if "/" in args.pattern or "\\" in args.pattern or not args.pattern.startswith("test_") or not args.pattern.endswith(".py"):
        raise ValueError("local test filename pattern required")
    if args.child: return child(args.child,args.pattern)
    if not args.output: p.error("--output required")
    output=(ROOT/args.output).resolve()
    if not output.is_relative_to(OUT.resolve()) or output==OUT.resolve() or output.exists():
        raise ValueError("new non-existing E2-015 run directory required")
    rows=[json.loads(s) for s in LEDGER.read_text(encoding="utf-8").splitlines()] if LEDGER.exists() else []
    reservations={r["run_id"]:r for r in rows if r["event"]=="reserved"}
    ended={r["run_id"]:r for r in rows if r["event"]=="finished"}
    if any(r.get("protection_stopped") for r in ended.values()):
        raise RuntimeError("prior protection stop; no automatic restart")
    consumed=sum(ended[k]["elapsed_s"] if k in ended else row["timeout_s"] for k,row in reservations.items())
    timeout=min(120,600-consumed)
    if timeout<=0: raise RuntimeError("600s task execution budget exhausted")
    output.mkdir(parents=True,exist_ok=False)
    source=output/"source";source.mkdir()
    source_hashes={}
    for path in OWN.rglob("*"):
        if path.is_file() and path.suffix in {".py",".json",".md",".c",".h"} and "__pycache__" not in path.parts:
            rel=path.relative_to(OWN); target=source/rel;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,target);source_hashes[str(path.relative_to(ROOT))]=sha(path)
    for name,path in [("M-016-contract.md",ROOT/"coordination/handoffs/M-016-contract.md"),("E2-015.md",ROOT/"coordination/tasks/E2-015.md")]:
        shutil.copyfile(path,output/name)
    template=ROOT/"coordination/templates/RUN_MANIFEST.json";shutil.copyfile(template,output/"RUN_MANIFEST.template.json")
    manifest=json.loads(template.read_text(encoding="utf-8-sig"))
    command=[sys.executable,"-B",str(Path(__file__).resolve()),"--child",str(output/"result.json"),"--pattern",args.pattern]
    manifest.update(template_only=False,task_id="E2-015",run_id=output.name,started_at=now(),worktree=str(ROOT),
                    git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
                    dirty_files_sha256=source_hashes,command=command,python_executable=sys.executable,
                    dependency_snapshot={"python":sys.version,"libraries":"stdlib only"},config_file=str(OWN/"CASES.json"),
                    seeds=[],budget={"command_timeout_s":timeout,"task_cap_s":600,"prior_charged_s":consumed,"output_cap_bytes":104857600},
                    output_directory=str(output),process_id=os.getpid(),status="running",
                    contract_sha256=sha(output/"M-016-contract.md"),task_card_sha256=sha(output/"E2-015.md"),
                    limitations=["preparation tests, no E1 C implementation or target compilation", "all fixtures synthetic; no serial opened or hardware measurements"])
    write(output/"manifest.json",manifest)
    with LEDGER.open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(dict(event="reserved",run_id=output.name,at=now(),timeout_s=timeout))+"\n")
    start=time.monotonic();protection=False
    with (output/"test-output.txt").open("w",encoding="utf-8") as stream:
        try:
            result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,timeout=timeout)
            code=result.returncode
        except subprocess.TimeoutExpired:
            protection=True;code=124
    elapsed=time.monotonic()-start
    output_bytes=sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    if output_bytes>104857600:protection=True;code=125
    manifest.update(finished_at=now(),exit_code=code,status="host_checks_passed" if code==0 else "host_checks_failed",
                    execution_elapsed_s=elapsed,protection_stopped=protection,task_output_bytes=output_bytes)
    write(output/"manifest.json",manifest)
    with LEDGER.open("a",encoding="utf-8") as stream:
        stream.write(json.dumps(dict(event="finished",run_id=output.name,at=now(),elapsed_s=elapsed,exit_code=code,protection_stopped=protection))+"\n")
    return code


if __name__=="__main__": raise SystemExit(main())
