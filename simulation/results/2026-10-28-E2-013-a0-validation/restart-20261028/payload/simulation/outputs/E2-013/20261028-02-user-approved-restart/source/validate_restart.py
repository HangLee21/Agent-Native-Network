"""Second/final stdlib evidence check for M-frozen human-approved continuation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from validate_a0 import ROOT, OWN, OUT, Evidence, local, strict_json, encode, write, digest, now, png_rgb, tool_check


def ledger_state(rows):
    starts = [r for r in rows if r["event"] == "worker_reserved"]
    finishes = {r["worker_id"]:r for r in rows if r["event"] == "worker_finished"}
    protected = False
    for row in rows:
        if row["event"] == "user_restart_authorized":
            protected = False
        if row["event"] == "worker_finished" and row.get("monitor_stop_reason") in {"low_system_ram","monitor_unavailable"}:
            protected = True
    return dict(worker_starts=len(starts),charged_worker_seconds=sum(finishes[r["worker_id"]]["wall_seconds"] if r["worker_id"] in finishes else r["timeout_s"] for r in starts),generated_calls=sum(bool(r["actual_forward_started"]) for r in finishes.values()),monitor_protection_stopped=protected)


def evaluate(e,freeze,criteria):
    checks, cases, run_statuses = [], [], []
    def ck(name,ok,details=None):
        checks.append(dict(name=name,passed=bool(ok),details=details))
    base = ROOT/"simulation/outputs/E1-012"
    arch = ROOT/"simulation/results/2026-10-28-E1-012-a0"
    inc = arch/"user-approved-restart-20261028"
    old_freeze_bytes = (ROOT/"simulation/outputs/E2-013/20261028-01-frozen-a0/freeze.json").read_bytes()
    ck("old_freeze",digest(old_freeze_bytes)==criteria["old_freeze_sha256"])
    old_freeze = strict_json(old_freeze_bytes)
    old_e2 = ROOT/"simulation/results/2026-10-28-E2-013-a0-validation"
    old_mapping_bytes=(old_e2/"ARCHIVE_MANIFEST.json").read_bytes()
    ck("old_E2_archive_manifest",digest(old_mapping_bytes)=="70327fecbd2e1f1bfb7f61555d1d06a74fb755babeaf02ea1bf82ee7474c2b07")
    for record in strict_json(old_mapping_bytes)["files"]:
        ck("old_E2_payload:"+record["archive"],digest((old_e2/record["archive"]).read_bytes())==record["sha256"])
    ck("old_E2_validation",digest((ROOT/"simulation/outputs/E2-013/20261028-01-frozen-a0/validation.json").read_bytes())=="8230e2a2374631de4d3130c79c52cd19b258751a5f7b3878bd7b46b88316acf4")
    for name,sha in old_freeze["files"].items():
        if name.startswith("simulation/outputs/E1-012/") or name.startswith("simulation/results/2026-10-28-E1-012-a0/"):
            ck("historical_immutable:"+name,digest(e.read(name))==sha)
    old_ledger = e.read(arch/"payload/data/agent_native/E1-012/worker_ledger.jsonl")
    ledger_bytes = e.read(ROOT/"data/agent_native/E1-012/worker_ledger.jsonl")
    ck("ledger_prefix",ledger_bytes.startswith(old_ledger))
    rows = [strict_json(line) for line in ledger_bytes.decode("utf-8").splitlines() if line]
    starts = [r for r in rows if r["event"]=="worker_reserved"]
    ends = [r for r in rows if r["event"]=="worker_finished"]
    preflights = [r for r in rows if r["event"]=="formal_preflight"]
    restarts = [r for r in rows if r["event"]=="user_restart_authorized"]
    revisions = [r for r in rows if r["event"]=="prompt_revision"]
    ck("ledger_task",all(r["task_id"]=="E1-012" for r in rows))
    ck("authorization",freeze["authorization"]["text"]=="批准启动" and freeze["authorization"]["verified_via"]=="read_thread" and bool(freeze["authorization"].get("user_message_id")))
    ck("single_restart",len(restarts)==1 and restarts[0]["extra_preflights"]==1 and restarts[0]["prior_worker_starts"]==1 and restarts[0]["prior_charged_worker_seconds"]==ledger_state([r for r in rows if r["at"]<restarts[0]["at"]])["charged_worker_seconds"])
    ck("budgets",len(starts)==len(ends)==4 and len(preflights)==3 and len(revisions)==1 and [r["worker_id"] for r in starts]==[1,2,3,4] and len({r["worker_id"] for r in ends})==4 and all(r["max_new_tokens"]<=256 and r["timeout_s"]<=180 for r in starts) and all(0<r["wall_seconds"]<=180 for r in ends) and sum(r["wall_seconds"] for r in ends)<=720)
    protected=False
    for row in rows:
        if row["event"]=="user_restart_authorized":
            ck("restart_after_protection",protected)
            protected=False
        if row["event"] in {"worker_reserved","formal_preflight"}:
            ck("no_unauthorized_retry:"+row["at"],not protected)
        if row["event"]=="worker_finished" and row.get("monitor_stop_reason") in {"low_system_ram","monitor_unavailable"}:
            protected=True
    for run_name in freeze["runs"]:
        run=base/run_name
        m=e.json(run/"manifest.json")
        run_statuses.append(dict(run=run_name,status=m["status"],actual_model_forwards=m.get("actual_model_forwards",0)))
        ck(run_name+":task",m["task_id"]=="E1-012" and m["status"] not in {"running","not_started"})
        ck(run_name+":complete_freeze",all(p.resolve() in e.expected for p in run.rglob("*") if p.is_file()))
        for name,sha in m.get("source_hashes",{}).items():
            ck(run_name+":snapshot:"+name,digest(e.read(run/"source"/name.replace("\\","/").split("/")[-1]))==sha)
        if m.get("entry_kind")!="E1-012_real_A0":
            ck(run_name+":not_model",m.get("actual_model_forwards",0)==0)
            continue
        cfg_bytes=e.read(run/"config.json"); cfg=strict_json(cfg_bytes)
        card=e.read(run/"task-card-snapshot.md")
        ck(run_name+":card",digest(card)==cfg["task_card_sha256"]==m["task_card_sha256"])
        if "config_sha256" in m:
            ck(run_name+":config",digest(cfg_bytes)==m["config_sha256"])
        lock_bytes=e.read(run/"SOURCE_LOCK.json"); lock=strict_json(lock_bytes)["model"]
        ck(run_name+":lock",digest(lock_bytes)==cfg["source_lock_sha256"]==m["source_lock_sha256"]=="139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1")
        ck(run_name+":model",local(cfg["model_dir"])==ROOT/"data/agent_native/E1-010/model" and local(cfg["python"])==ROOT/"data/agent_native/E1-010/env/Scripts/python.exe" and m["upstream_commit"]==lock["revision"]=="7b375e1b73b11138ff12fe22c8f2822d8fe03467")
        ck(run_name+":caps",cfg["caps"]==m["budget"]==dict(worker_starts=4,max_new_tokens=256,per_worker_s=180,total_worker_s=720,images_per_call=1,image_width=64,image_height=64))
        minimum=1610612736 if cfg.get("monitored_direct_cuda") else 2147483648
        pf=next((r for r in preflights if r["run_id"]==run_name),None)
        if pf:
            inv=e.json(run/"inventory.json")
            gpu=int(inv["gpu_query"]["stdout"].split(",")[2].strip().split()[0])*1024**2
            passed=inv["free_ram_bytes"]>=minimum and gpu>=2684354560
            ck(run_name+":preflight",passed==pf["passed"] and inv["free_ram_bytes"]==pf["free_ram_bytes"])
        else:
            ref=e.json(run/"formal_preflight_reference.json")
            ck(run_name+":reuse_preflight",ref==preflights[-1] and ref["passed"] and ref["monitored_direct_cuda"]==cfg["monitored_direct_cuda"])
            passed=ref["passed"]
        workers=sorted(p for p in run.iterdir() if p.is_dir() and p.name.startswith("worker-"))
        if not passed:
            ck(run_name+":blocked_preserved",not workers and m["status"]=="resource_blocked" and m["worker_starts"]==m["actual_model_forwards"]==0)
            continue
        if cfg.get("monitored_direct_cuda"):
            ck(run_name+":monitor_authority","## M有监测低RAM加载修订" in card.decode("utf-8") and cfg["monitor_stop_free_ram_bytes"]==536870912 and cfg["monitor_interval_seconds"]<=.5)
        if cfg.get("user_approved_restart"):
            ck(run_name+":user_checkpoint","用户已关闭游戏等释放资源，检查后明确回复“批准启动”。" in card.decode("utf-8") and restarts[0]["task_card_sha256"]==m["task_card_sha256"] and restarts[0]["run_id"]==run_name)
        assets=e.json(run/"asset_verification.json")
        ck(run_name+":assets",set(assets)==set(lock["download_plan"]["conservative_root_allowlist"]) and {n:v["sha256"] for n,v in assets.items()}==m["data_and_weights_sha256"])
        for source in lock["files"]:
            if source["path"] in assets:
                v=assets[source["path"]]
                ck(run_name+":asset_record:"+source["path"],v["sha256"]==source["sha256"] if source["sha256"] else v["git_blob_sha1"]==source["git_blob_sha1"])
        images=e.json(run/"input_manifest.json")
        ck(run_name+":two_inputs",len(images)==2)
        for i,image in enumerate(images):
            raw=e.read(image["path"]); px=png_rgb(raw)
            ck(run_name+":pixel:"+str(i),digest(raw)==image["sha256"] and len(raw)==image["encoded_bytes"] and px["rgb"]==[[255,0,0],[0,0,255]][i])
        summary=e.json(run/"summary.json")
        ck(run_name+":count",len(workers)==len(summary["calls"])==m["worker_starts"])
        cut=[r for r in rows if r["at"]<=m["finished_at"]]
        ck(run_name+":state_at_completion",ledger_state(cut)==summary["task_ledger"]==m["task_ledger"])
        started_count=0
        for w in workers:
            spec=e.json(w/"spec.json"); result=e.json(w/"result.json"); proc=e.json(w/"process.json")
            index=proc["input_index"]; wid=proc["worker_id"]
            reservation=next(r for r in starts if r["worker_id"]==wid); end=next(r for r in ends if r["worker_id"]==wid)
            ctx=dict(node_id="participant-"+str(index),visible_evidence_ids=["local-image"],image_count=1,inbox=[],private_context=True)
            ck(w.name+":context",spec["node_id"]==result["node_id"]==ctx["node_id"] and spec["context_sha256"]==result["context_sha256"]==digest(encode(ctx)) and spec["images"]==[images[index]])
            ck(w.name+":prompt",spec["prompt"]==cfg["prompt_versions"][proc["prompt_version"]] and not re.search(r"\b(red|blue)\b",spec["prompt"],re.I))
            ck(w.name+":process_binding",local(proc["command"][0])==local(cfg["python"]) and local(result["python"])==local(cfg["python"]) and proc["command"][1]=="-B" and local(proc["command"][2])==run/"source/model_worker.py" and proc["command"][3:]==["--spec",str(w/"spec.json"),"--result",str(w/"result.json")])
            ck(w.name+":ledger",end["wall_seconds"]==proc["wall_seconds"] and end["exit_code"]==proc["exit_code"] and end["input_index"]==index and end["actual_forward_started"]==proc["actual_forward_started"]==result["actual_forward_started"] and reservation["run_id"]==run_name)
            ck(w.name+":summary",{k:v for k,v in proc.items() if k!="command"} in summary["calls"])
            ck(w.name+":limits",spec["free_ram_before_start_bytes"]>=minimum and 0<spec["max_generation_s"]<=180 and spec["max_new_tokens"]==result["max_new_tokens"]==reservation["max_new_tokens"]==256 and spec["source_revision"]==result["source_revision"]==lock["revision"] and spec["direct_cuda_load"] is True)
            started_count+=int(result["actual_forward_started"])
            curve=[strict_json(s) for s in e.read(w/"ram_curve.jsonl").decode("utf-8").splitlines() if s]
            times=[r["elapsed_seconds"] for r in curve]; gaps=[b-a for a,b in zip(times,times[1:])]; mon=proc["monitor"]
            ck(w.name+":curve",len(curve)==mon["ram_samples"] and times[0]<=.5 and all(0<=g<=.5 for g in gaps) and 0<=proc["wall_seconds"]-times[-1]<=.5 and min(r["free_ram_bytes"] for r in curve)==mon["minimum_observed_free_ram_bytes"] and all(r["worker_pid"]==mon["worker_pid"] for r in curve) and mon["worker_reaped"] is True)
            if wid==1:
                ck(w.name+":old_guard",curve[-1]["stop_reason"]==mon["monitor_stop_reason"]=="low_system_ram" and curve[-1]["free_ram_bytes"]<536870912 and result["status"]=="loading" and not result["actual_forward_started"])
            else:
                ck(w.name+":no_new_guard",mon["monitor_stop_reason"] is None and all(r["stop_reason"] is None and r["free_ram_bytes"]>=536870912 for r in curve) and proc["exit_code"]==mon["exit_code"]==0)
            row=dict(worker_id=wid,input_index=index,prompt_version=proc["prompt_version"],run=run_name,status=result["status"],wall_seconds=proc["wall_seconds"],worker_pid=mon["worker_pid"],ram_min_bytes=mon["minimum_observed_free_ram_bytes"],max_sampling_gap_seconds=max(gaps,default=0),generation_started=result["actual_forward_started"],generation_completed=result["status"]=="generated",format_status="not_tested",reference_status="not_tested",semantic_word_rule="not_tested")
            if result["status"]=="generated":
                raw=result["raw_output"]; word_set=set(re.findall(r"[a-z]+",raw.lower())) & {"red","blue"}
                word_correct=word_set=={["red","blue"][index]}
                try:
                    action=tool_check(raw,dict(private_and_arrived_evidence={"local-image":images[index]},peers=[]))
                    valid=action["tool"]=="finish"; legal=action.get("evidence_refs")==["local-image"]
                except (ValueError,TypeError,KeyError):
                    valid=legal=False
                ck(w.name+":independent_scores",valid==proc["format_valid"] and legal==proc["legal_reference"] and word_correct==proc["visual_correct"] and end["input_passed"]==False)
                ck(w.name+":generated",result["actual_forward_started"] and 0<result["output_tokens"]<=256 and len(raw.encode("utf-8"))==result["output_utf8_bytes"])
                ck(w.name+":tensor",result["input_tensor_shapes"]["pixel_values"]==[1,1,3,512,512] and result["input_tensor_shapes"]["pixel_attention_mask"]==[1,1,512,512] and result["input_tensor_shapes"]["input_ids"]==[1,118])
                ck(w.name+":placement",result["loading_strategy"]=="direct_cuda" and result["hf_device_map"]=={"":"cuda:0"} and result["parameter_devices"]==["cuda:0"] and result["parameter_dtypes"]==["torch.float16"] and result["parameter_bytes"]==1014964608)
                ck(w.name+":versions",result["versions"]=={"torch":"2.3.1+cu121","transformers":"4.51.3","Pillow":"10.4.0","tokenizers":"0.21.1","huggingface-hub":"0.30.2","safetensors":"0.5.3"})
                ck(w.name+":timing",0<result["model_load_seconds"]<result["load_and_preprocess_seconds"]<result["wall_seconds"]<=proc["wall_seconds"] and 0<result["generation_seconds"]<result["wall_seconds"])
                ck(w.name+":GPU_scope",result["free_gpu_before_load_bytes"]>=2684354560 and 0<result["peak_allocated_gpu_bytes_through_load"]<=result["peak_reserved_gpu_bytes"] and 0<result["peak_allocated_gpu_bytes"]<=result["peak_reserved_gpu_bytes"] and "excludes transient load peak" in result["gpu_generation_peak_scope"])
                row.update(raw_output=raw,format_status="pass" if valid else "fail",reference_status="pass" if legal else "fail",semantic_word_rule="pass" if word_correct else "fail",semantic_auxiliary="hex #FF0000 denotes red; not rescored" if raw.strip()=="#FF0000" else "unambiguous observed color word",tensor_shapes=result["input_tensor_shapes"],model_load_seconds=result["model_load_seconds"],generation_seconds=result["generation_seconds"],gpu_load_peak_bytes=result["peak_allocated_gpu_bytes_through_load"],gpu_generation_peak_bytes=result["peak_allocated_gpu_bytes"],gpu_reserved_peak_bytes=result["peak_reserved_gpu_bytes"])
            cases.append(row)
        ck(run_name+":forward_count",m["actual_model_forwards"]==started_count)
    for archive,mutable_sources in [(arch,False),(inc,True)]:
        mapping=e.json(archive/"ARCHIVE_MANIFEST.json")
        for row in mapping["files"]:
            data=e.read(archive/row["archive"])
            ok=len(data)==row["bytes"] and digest(data)==row["sha256"]
            if mutable_sources:
                ok=ok and data==e.read(row["source"])
            ck("archive:"+str(archive.relative_to(ROOT))+":"+row["source"],ok)
    for run_name,test in [("20261028-12-A0-user-approved","20261028-11-user-restart-checks"),("20261028-14-A0-blue-diagnostic","20261028-13-two-input-checks")]:
        for n in e.json(base/run_name/"manifest.json")["source_hashes"]:
            name=n.replace("\\","/").split("/")[-1]
            ck(run_name+":matched_tests:"+name,e.read(base/run_name/"source"/name)==e.read(base/test/"source"/name))
    test=e.json(base/"20261028-13-two-input-checks/result.json")
    ck("saved37_checks",test["tests_run"]==37 and test["successful"] and test["failures"]==test["errors"]==test["actual_model_forwards"]==0)
    cleanup=e.json(base/"20261028-15-restart-audit/process-check.json")
    ck("recorded_cleanup",cleanup["present_pids"]==[] and all(c["worker_pid"] in cleanup["checked_pids"] for c in cases if c["worker_id"]>1))
    ck("worker_accounting",len(cases)==4 and sum(c["generation_started"] for c in cases)==3 and sum(c["generation_completed"] for c in cases)==3)
    return dict(evidence_consistency="pass" if all(c["passed"] for c in checks) else "fail",checks=checks,cases=cases,runs=run_statuses,task_ledger=ledger_state(rows),formal_preflights=len(preflights),user_restart_authorizations=len(restarts),prompt_revisions=len(revisions),actual_worker_starts=len(starts),actual_generation_completed=sum(c["generation_completed"] for c in cases),A0_joint_pass=False,capability="load_and_visual_generation_demonstrated_strict_JSON_failed",limitations=["raw color semantics and strict JSON scored separately; no post-hoc hex-word promotion","64px source becomes 512px tensor","GPU allocator peaks are not whole-card utilization; system free RAM is not process peak","historical payloads immutable, current mutable sources compared only to continuation archive","37 saved regression checks reviewed, not rerun; no model/network/collaboration/general-accuracy experiment"])


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--freeze",required=True); parser.add_argument("--output",required=True); args=parser.parse_args()
    criteria_bytes=(OWN/"criteria_restart.json").read_bytes(); criteria=strict_json(criteria_bytes)
    fbytes=local(args.freeze).read_bytes(); freeze=strict_json(fbytes)
    if digest(fbytes)!=criteria["freeze_sha256"] or freeze["schema"]!="M-014-restart-freeze/1":
        raise ValueError("M restart freeze hash required")
    previous=list(OUT.glob("*/manifest.json")); output=local(args.output)
    if len(previous)!=1 or output.exists() or not output.is_relative_to(OUT.resolve()) or output==OUT.resolve():
        raise ValueError("exactly one prior run and a new E2-013 output are required; total cap two")
    output.mkdir(parents=True,exist_ok=False); source=output/"source"; source.mkdir()
    for p in OWN.iterdir():
        if p.is_file(): shutil.copyfile(p,source/p.name)
    (output/"freeze.json").write_bytes(fbytes); shutil.copyfile(ROOT/"coordination/tasks/E2-013.md",output/"E2-013.md")
    template=(ROOT/"coordination/templates/RUN_MANIFEST.json").read_bytes(); (output/"RUN_MANIFEST.template.json").write_bytes(template); m=strict_json(template)
    m.update(template_only=False,task_id="E2-013",run_id=output.name,started_at=now(),worktree=str(ROOT),git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),command=[sys.executable,*sys.argv],python_executable=sys.executable,dependency_snapshot={"python":sys.version,"external_dependencies":[]},config_file=str(local(args.freeze)),config_sha256=digest(fbytes),dirty_files_sha256={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in OWN.iterdir() if p.is_file()},seeds=[],budget={"formal_validation_run":2,"max_runs":2,"models_download_training_simulation":0},output_directory=str(output),process_id=os.getpid(),status="running",limitations=["independent frozen evidence check only; no E1 execution"],validator_signature=digest(Path(__file__).read_bytes()+criteria_bytes))
    write(output/"manifest.json",m); e=None
    try:
        e=Evidence(freeze); result=evaluate(e,freeze,criteria)
        for p in e.expected: e.read(p)
        write(output/"validation.json",result); code=0 if result["evidence_consistency"]=="pass" else 1
        m["status"]="evidence_consistent_A0_format_failed" if code==0 else "evidence_inconsistent"
    except Exception as exc:
        write(output/"failure.json",dict(error_type=type(exc).__name__,error=str(exc))); code=1; m["status"]="validation_failed"
    m.update(finished_at=now(),exit_code=code,input_files_sha256=e.observed if e else {}); write(output/"manifest.json",m); return code


if __name__=="__main__":
    raise SystemExit(main())
