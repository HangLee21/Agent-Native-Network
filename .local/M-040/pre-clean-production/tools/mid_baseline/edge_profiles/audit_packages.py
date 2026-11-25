"""Compare the two released variants and their common network/serial/deployment sources."""
import argparse
import datetime as dt
import json
from pathlib import Path
from build import ROOT, sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("oled","headless","run"):p.add_argument("--"+name,required=True)
    a=p.parse_args()
    out=ROOT/"simulation/outputs/E1-023"/a.run;out.mkdir(parents=True,exist_ok=False)
    results={};manifests={}
    for label,arg in (("oled",a.oled),("headless",a.headless)):
        root=Path(arg).resolve()
        if not root.is_relative_to((ROOT/".local/mid/E1-023").resolve()):raise ValueError("package outside own scope")
        m=json.loads((root/"PACKAGE_MANIFEST.json").read_text(encoding="utf-8"));manifests[label]=m
        for row in m["files"]:
            f=root/row["path"]
            if f.stat().st_size!=row["bytes"] or sha(f)!=row["sha256"]:raise ValueError("sealed payload mismatch: "+str(f))
        results[label]=dict(package=str(root),file_count=len(m["files"]),build_id=m["build_id"],manifest_sha256=sha(root/"PACKAGE_MANIFEST.json"))
    shared=["mid_baseline/mid.c","mid_baseline/mid.h","mid_baseline/edge/deployment.c","mid_baseline/edge/deployment.h","mid_baseline/edge/idf/main/app_main.c","mid_display/include/mid_display.h","mid_display/src/mid_display_model.c"]
    common={}
    for name in shared:
        lhs=Path(a.oled)/"source/firmware"/name;rhs=Path(a.headless)/"source/firmware"/name
        if sha(lhs)!=sha(rhs):raise ValueError("variant business implementation diverged: "+name)
        common[name]=sha(lhs)
    if manifests["oled"]["build_id"]==manifests["headless"]["build_id"]:raise ValueError("variant IDs were not distinguished")
    original=ROOT/".local/mid/E1-017/uart-package-02/source/firmware/mid_baseline"
    for name in ("mid.c","mid.h"):
        if sha(original/name)!=common["mid_baseline/"+name]:raise ValueError("original MID core changed")
    host=ROOT/"simulation/outputs/E1-023/20261108-01-host-offline/source"
    for name in shared:
        file=host/"firmware"/name
        # app_main was target-compiled; host test covers core/installer/model only.
        if file.exists() and sha(file)!=common[name]:raise ValueError("host-tested source changed: "+name)
    headless=json.loads((Path(a.headless)/"DISPLAY_BUILD.json").read_text(encoding="utf-8"))
    assert not headless["display_enabled"] and "esp_driver_i2c" not in headless["components"]
    result=dict(status="passed",packages=results,identical_common_source_sha256=common,original_mid_core_unchanged=True,host_tested_core_installer_model_unchanged=True,headless_i2c_absent=True,limitations=["Static sealed-package/source/ELF comparison and earlier synthetic host evidence only; H must verify actual boards, NVS reboot and application delivery."])
    (out/"result.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    m=json.loads((ROOT/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"));m.update(template_only=False,task_id="E1-023",run_id=a.run,started_at=dt.datetime.now(dt.timezone.utc).isoformat(),finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),worktree=str(ROOT),output_directory=str(out),status="passed",exit_code=0,budget=dict(model_calls=0,device_access=0),command=["audit_packages.py",*__import__("sys").argv[1:]],limitations=result["limitations"])
    (out/"RUN_MANIFEST.json").write_text(json.dumps(m,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))

if __name__=="__main__":main()
