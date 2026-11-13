"""Seal one successfully built candidate with image checks and H-only flash instructions."""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from build import ROOT, SDK_ROOT, sha
OUT = None

def write(path, value):
    path.write_text(json.dumps(value, indent=2)+"\n",encoding="utf-8")

def main():
    global OUT
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ("candidate","variant","build-run","run","package"):p.add_argument("--"+arg,required=True)
    a=p.parse_args()
    if a.variant not in ("oled","headless"):raise ValueError("variant")
    for name in (a.candidate,a.build_run,a.run,a.package):
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name):raise ValueError("simple path names required")
    work=ROOT/".local/mid/E1-023"/a.candidate;build=work/("build-"+a.variant);fw=work/"firmware"
    prior=ROOT/"simulation/outputs/E1-023"/a.build_run/"RUN_MANIFEST.json"
    bm=json.loads(prior.read_text(encoding="utf-8"))
    if bm["status"]!="passed" or bm["variant"]!=a.variant:raise ValueError("no successful corresponding target build")
    for file,h in bm["source_sha256"].items():
        if sha(fw/file)!=h:raise ValueError("candidate source changed after build: "+file)
    package=ROOT/".local/mid/E1-023"/a.package;package.mkdir(exist_ok=False)
    out=ROOT/"simulation/outputs/E1-023"/a.run;out.mkdir(parents=True,exist_ok=False);OUT=out
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    initial=json.loads((ROOT/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
    initial.update(template_only=False,task_id="E1-023",run_id=a.run,started_at=started,worktree=str(ROOT),command=sys.argv,python_executable=sys.executable,output_directory=str(out),status="running",budget=dict(per_command_s=60),source_manifest_sha256=sha(prior),limitations=["Packaging/image checks only, no serial/flash/RF."])
    write(out/"RUN_MANIFEST.json",initial)
    for name in ("mid_edge.bin","mid_edge.elf","mid_edge.map","flasher_args.json","flash_args","project_description.json"):
        shutil.copy2(build/name,package/name)
    for name in ("bootloader/bootloader.bin","partition_table/partition-table.bin"):
        dest=package/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(build/name,dest)
    shutil.copy2(work/("sdkconfig-"+a.variant),package/"sdkconfig")
    shutil.copytree(fw,package/"source/firmware")
    shutil.copytree(ROOT/"tools/mid_baseline/edge_profiles",package/"source/tools/mid_baseline/edge_profiles",ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT/"simulation/outputs/E1-023/20261108-03-abc-profile",package/"abc-profile")
    shutil.copy2(ROOT/"tools/mid_baseline/edge_profiles/README.md",package/"DEPLOYMENT.md")
    shutil.copy2(prior,package/"TARGET_BUILD.json")
    shutil.copy2(ROOT/"coordination/tasks/E1-023.md",package/"TASK_AT_PACKAGE.md")
    enabled=0 if a.variant=="headless" else 1
    main=fw/"mid_baseline/edge/idf/main"
    sources=["app_main.c","CMakeLists.txt","../../../mid.c","../../../mid.h","../../deployment.c","../../deployment.h","../CMakeLists.txt","../sdkconfig.defaults","../../../../mid_display/include/mid_display.h","../../../../mid_display/src/mid_display_model.c"]
    sources += (["../../headless_components/mid_display/CMakeLists.txt","../../headless_components/mid_display/headless.c"] if not enabled else ["../../../../mid_display/CMakeLists.txt","../../../../mid_display/src/mid_display_render.c","../../../../mid_display/src/mid_display_idf.c","../../../../mid_display/src/mid_display_font.h"])
    import hashlib
    build_id="mid-edge-v1-"+hashlib.sha256(("MID_DISPLAY_ENABLED="+str(enabled)+"".join(sha(main/f) for f in sources)).encode()).hexdigest()
    if build_id.encode() not in (package/"mid_edge.bin").read_bytes():raise ValueError("computed build ID absent in app image")
    checks=[]
    py=str(SDK_ROOT/"tools/python_env/idf5.5_py3.11_env/Scripts/python.exe")
    for name,relative in (("app_image","mid_edge.bin"),("bootloader_image","bootloader/bootloader.bin")):
        cmd=[py,"-m","esptool","--chip","esp32s3","image_info","--version","2",str(package/relative)]
        r=subprocess.run(cmd,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
        (out/(name+".txt")).write_text(r.stdout+r.stderr,encoding="utf-8")
        if r.returncode or r.stdout.count("(valid)")<2:raise RuntimeError((name,r.returncode))
        shutil.copy2(out/(name+".txt"),package/(name+".txt"));checks.append(dict(name=name,command=cmd,exit_code=r.returncode))
    desc=json.loads((build/"project_description.json").read_text(encoding="utf-8"))
    files=[str(row["file"]).replace("\\","/") for row in json.loads((build/"compile_commands.json").read_text(encoding="utf-8"))]
    if not enabled:
        if "esp_driver_i2c" in desc["build_components"]:raise ValueError("headless unexpectedly depends on I2C")
        if any(n in f for f in files for n in ("mid_display_idf.c","mid_display_render.c","/esp_driver_i2c/")):raise ValueError("display backend compiled into headless")
        if not any("headless.c" in f for f in files):raise ValueError("headless shim absent")
    nm=SDK_ROOT/"tools/tools/xtensa-esp-elf/esp-14.2.0_20241119/xtensa-esp-elf/bin/xtensa-esp32s3-elf-nm.exe"
    symbols=subprocess.run([str(nm),"--defined-only",str(package/"mid_edge.elf")],capture_output=True,text=True,encoding="utf-8",errors="replace",check=True,timeout=60).stdout
    selected=[s for s in symbols.splitlines() if re.search(r"\b(mid_display_|i2c_(new_master_bus|master_|del_master_bus))",s)]
    (package/"DISPLAY_SYMBOLS.txt").write_text("\n".join(selected)+"\n",encoding="utf-8")
    if not enabled and any(re.search(r"\bi2c_(new_master_bus|master_|del_master_bus)",s) for s in selected):raise ValueError("I2C display symbols remain")
    write(package/"DISPLAY_BUILD.json",dict(variant=a.variant,display_enabled=bool(enabled),display_api=2,components=desc["build_components"],display_sources=[f for f in files if "mid_display" in f or "headless.c" in f],checks="Build components, compile inputs and defined ELF symbols; physical pixel behavior unverified."))
    old=ROOT/".local/mid/E1-017/uart-package-02"
    compatible={f:sha(package/f)==sha(old/f) for f in ("bootloader/bootloader.bin","partition_table/partition-table.bin")}
    def config_values(path):
        return dict(line.split("=",1) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("CONFIG_") and "=" in line)
    x,y=config_values(old/"sdkconfig"),config_values(package/"sdkconfig")
    prefixes=("CONFIG_BOOTLOADER_","CONFIG_SECURE_","CONFIG_ESPTOOLPY_","CONFIG_PARTITION_TABLE_","CONFIG_IDF_TARGET")
    keys={k for k in x.keys()|y.keys() if k.startswith(prefixes)}
    differences={k:[x.get(k),y.get(k)] for k in keys if x.get(k)!=y.get(k)}
    compatible["boot_flash_partition_target_config_equal"]=not differences
    if not compatible["partition_table/partition-table.bin"] or differences:
        raise ValueError("app-only handoff needs new bootloader/partition analysis: "+str(differences))
    flash=[py,"-m","esptool","--chip","esp32s3","--port","<H-bound-port>","--baud","460800","--before","default_reset","--after","hard_reset","write_flash","--flash_mode","dio","--flash_freq","40m","--flash_size","2MB","0x10000",str(package/"mid_edge.bin")]
    binaries=[dict(offset=offset,file=file,bytes=(package/file).stat().st_size,sha256=sha(package/file)) for offset,file in (("0x0","bootloader/bootloader.bin"),("0x8000","partition_table/partition-table.bin"),("0x10000","mid_edge.bin"))]
    handoff=dict(task_id="E1-023",package=str(package),variant=a.variant,build_id=build_id,binaries=binaries,application_uart=dict(baud=460800,format="8N1"),display_enabled=bool(enabled),display_api=2,app_only_compatible_with_c422=compatible,flash_command_not_executed=flash,cwd=str(package),rollback_app=str(old/"mid_espnow.bin"),rollback_sha256=sha(old/"mid_espnow.bin"),rollback_note="Before rollback stop/radio=false and deployment_clear on each configured board. Profile NVS bytes otherwise persist but c422 ignores this namespace. No erase_flash/NVS partition write/eFuse.",variant_swap_note="OLED and headless share the same NVS profile. A saved autostart=true profile will start radio after flash/reset, even if stop was issued before flashing. Explicitly stop again before another configuration or flash.",nvs_namespace="mid_deploy",profile=str(package/"abc-profile/deploy.json"),checks=checks,limitations=["E1 never opened a serial port or flashed hardware.","Synthetic host plus target compile/image evidence; actual cold-start, relay reboot, app delivery, pixels and physical multi-host deployment require H evidence."],build_source_sha256=bm["source_sha256"])
    write(package/"HANDOFF.json",handoff)
    write(package/"PACKAGE_MANIFEST.json",dict(schema="mid.package.manifest.v1",task_id="E1-023",build_id=build_id,variant=a.variant,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),files=[dict(path=str(f.relative_to(package)).replace("\\","/"),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(package.rglob("*")) if f.is_file() and f.name!="PACKAGE_MANIFEST.json"]))
    receipt=dict(status="passed",task_id="E1-023",variant=a.variant,package=str(package),build_id=build_id,manifest_sha256=sha(package/"PACKAGE_MANIFEST.json"),app_sha256=sha(package/"mid_edge.bin"),checks=checks,headless_backend_verified=not bool(enabled))
    write(out/"result.json",receipt)
    m=initial;m.update(finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),status="passed",exit_code=0,upstream_commit=bm["upstream_commit"],git_commit=bm["git_commit"],limitations=handoff["limitations"],package_manifest_sha256=receipt["manifest_sha256"]);write(out/"RUN_MANIFEST.json",m)
    print(json.dumps(receipt))

if __name__=="__main__":
    try:main()
    except Exception as exc:
        if OUT:
            import traceback
            m=json.loads((OUT/"RUN_MANIFEST.json").read_text(encoding="utf-8"));m.update(status="failed",exit_code=1,error=repr(exc),finished_at=dt.datetime.now(dt.timezone.utc).isoformat());write(OUT/"RUN_MANIFEST.json",m)
            (OUT/"failure.log").write_text(traceback.format_exc(),encoding="utf-8")
        raise
