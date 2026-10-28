"""Read only M-frozen E1 evidence with stdlib; never import or run E1 code."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[2]
OWN = Path(__file__).resolve().parent
OUT = ROOT / "simulation/outputs/E2-013"


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def write(path, value):
    path.write_bytes(encode(value) + b"\n")


def local(path):
    path = Path(path)
    full = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not full.is_relative_to(ROOT.resolve()):
        raise ValueError("input outside workspace")
    return full


class Evidence:
    def __init__(self, freeze):
        self.expected = {local(name): sha for name, sha in freeze["files"].items()}
        self.observed = {}
        total = 0
        allowed = [ROOT / name for name in (
            "simulation/outputs/E1-012", "simulation/results/2026-10-28-E1-012-a0",
            "data/agent_native/E1-012", "simulation/edge_agent_entry")]
        exact = {ROOT / "coordination/tasks/E1-012.md",
                 ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json",
                 ROOT / "research/agent_native_network/a0_20261028/MODEL_RUN.md"}
        for path, sha in self.expected.items():
            if not (path in exact or any(path.is_relative_to(base.resolve()) for base in allowed)):
                raise ValueError("unassigned frozen input: " + str(path))
            if not re.fullmatch(r"[a-f0-9]{64}", sha):
                raise ValueError("invalid SHA-256")
            size = path.stat().st_size
            total += size
            if size > 20 * 1024**2 or total > 100 * 1024**2:
                raise ValueError("evidence size limit; no model/weights permitted")
            self.read(path)

    def read(self, path):
        path = local(path)
        if path not in self.expected:
            raise ValueError("file absent from M freeze: " + str(path))
        data = path.read_bytes()
        sha = digest(data)
        if sha != self.expected[path]:
            raise ValueError("M frozen SHA differs: " + str(path))
        self.observed[str(path.relative_to(ROOT))] = sha
        return data

    def json(self, path):
        return strict_json(self.read(path).decode("utf-8-sig"))


def png_rgb(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not PNG")
    offset, compressed, header, ended = 8, b"", None, False
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset+4])[0]
        kind = data[offset+4:offset+8]
        body = data[offset+8:offset+8+length]
        crc = struct.unpack(">I", data[offset+8+length:offset+12+length])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("PNG CRC differs")
        offset += 12 + length
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            compressed += body
        elif kind == b"IEND":
            ended = True
            break
    if not header or not ended or offset != len(data):
        raise ValueError("incomplete PNG")
    width, height, bits, color, compression, filtering, interlace = header
    if (width, height, bits, color, compression, filtering, interlace) != (64,64,8,2,0,0,0):
        raise ValueError("expected 64px RGB8 noninterlaced PNG")
    raw = zlib.decompress(compressed)
    stride = width * 3
    if len(raw) != height * (stride + 1):
        raise ValueError("PNG decompressed length differs")
    pixels, previous = [], [0] * stride
    for y in range(height):
        start = y * (stride + 1)
        mode, row = raw[start], list(raw[start+1:start+1+stride])
        if mode not in range(5):
            raise ValueError("invalid PNG filter")
        for i in range(stride):
            a = row[i-3] if i >= 3 else 0
            b = previous[i]
            c = previous[i-3] if i >= 3 else 0
            p = a+b-c
            distances = [abs(p-a), abs(p-b), abs(p-c)]
            paeth = (a,b,c)[distances.index(min(distances))]
            predictor = (0,a,b,(a+b)//2,paeth)[mode]
            row[i] = (row[i] + predictor) & 255
        pixels.extend(tuple(row[i:i+3]) for i in range(0,stride,3))
        previous = row
    colors = set(pixels)
    if len(colors) != 1:
        raise ValueError("input is not a uniform compatibility image")
    return dict(width=width, height=height, rgb=list(next(iter(colors))))


def tool_check(raw, context):
    action = strict_json(raw)
    fields = {"request":{"tool","peer","query","deadline_s"},
              "respond":{"tool","request_id","body","evidence_refs"},
              "consume":{"tool","message_id"},
              "finish":{"tool","answer","evidence_refs"}}
    if not isinstance(action, dict) or action.get("tool") not in fields:
        raise ValueError("unknown tool/non-object")
    tool = action["tool"]
    if set(action) != fields[tool]:
        raise ValueError("tool fields differ")
    for key in fields[tool] - {"tool","evidence_refs","deadline_s"}:
        if not isinstance(action[key],str) or not action[key]:
            raise ValueError("nonempty string required")
    visible = context["private_and_arrived_evidence"]
    refs = action.get("evidence_refs", [])
    if (not isinstance(refs,list) or any(not isinstance(ref,str) for ref in refs)
            or len(set(refs)) != len(refs) or any(ref not in visible for ref in refs)):
        raise ValueError("invalid/unavailable local reference")
    if tool == "request":
        duration = action["deadline_s"]
        if (action["peer"] not in context["peers"] or isinstance(duration,bool)
                or not isinstance(duration,(int,float)) or not math.isfinite(duration) or duration <= 0):
            raise ValueError("invalid request peer/deadline")
    if tool in {"consume","respond"}:
        raise ValueError("independent A0 context has no arrived request/evidence")
    if tool == "finish" and not refs:
        raise ValueError("visual finish must cite its local image")
    return action


def semantics(raw, expected):
    try:
        action = strict_json(raw)
    except (ValueError,TypeError):
        return dict(status="needs_review", reason="malformed JSON; inspect raw semantics separately")
    answer = action.get("answer") if isinstance(action,dict) and action.get("tool") == "finish" else None
    if not isinstance(answer,str):
        return dict(status="needs_review", reason="no finish answer")
    colors = set(re.findall(r"\b(red|blue|green|yellow|black|white|purple|orange|pink|brown|gray|grey)\b",answer.lower()))
    if re.search(r"\b(no|not|isnt|isn't|without|neither)\b",answer.lower()) or len(colors) > 1:
        return dict(status="needs_review", answer=answer, reason="negation/multiple colors")
    return dict(status="pass" if colors == {expected} else "fail", answer=answer,
                mentioned_colors=sorted(colors), expected=expected)


def evaluate(evidence, freeze, criteria):
    checks, cases, runs, caveats = [], [], [], []
    def check(name, ok, details=None):
        checks.append(dict(name=name, passed=bool(ok), details=details))
    template_keys = set(strict_json((ROOT/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig")))
    ledger = [strict_json(line) for line in evidence.read(freeze["ledger"]).decode("utf-8-sig").splitlines() if line.strip()]
    preflights = [r for r in ledger if r["event"] == "formal_preflight"]
    reservations = [r for r in ledger if r["event"] == "worker_reserved"]
    finishes = [r for r in ledger if r["event"] == "worker_finished"]
    revisions = [r for r in ledger if r["event"] == "prompt_revision"]
    preflight_by_run = {r["run_id"]:r for r in preflights}
    process_records, manifest_workers = [], 0
    for run_name in freeze["runs"]:
        run = local(run_name)
        manifest = evidence.json(run/"manifest.json")
        kind = manifest.get("entry_kind")
        auxiliary = kind == "read_only_evidence_audit"
        check(run.name+":manifest_fields", template_keys <= set(manifest))
        check(run.name+":task_status", manifest.get("task_id") == "E1-012" and manifest.get("status") not in {None,"running","not_started"})
        check(run.name+":completion_record", auxiliary or bool(manifest.get("finished_at")))
        if auxiliary:
            caveats.append(dict(run=run.name, note="post-hoc auxiliary manifest; unknown times/command remain null"))
        actual_files = {p.resolve() for p in run.rglob("*") if p.is_file()}
        check(run.name+":complete_inventory", actual_files <= set(evidence.expected))
        for source_name, expected_sha in manifest.get("source_hashes",{}).items():
            source = run/"source"/source_name.replace("\\","/").split("/")[-1]
            check(run.name+":source:"+source.name, digest(evidence.read(source)) == expected_sha)
        run_workers = sorted(p for p in run.iterdir() if p.is_dir() and p.name.startswith("worker-"))
        runs.append(dict(run=run.name,kind=kind,status=manifest["status"],exit_code=manifest.get("exit_code"),
                         real_worker_directories=len(run_workers)))
        if kind != "E1-012_real_A0":
            check(run.name+":no_model", manifest.get("actual_model_forwards") == 0 and not run_workers)
            continue  # Nested mock call-/worker- fixtures are not actual starts.
        manifest_workers += manifest["worker_starts"]
        config_bytes = evidence.read(run/"config.json")
        config = strict_json(config_bytes.decode("utf-8"))
        if "config_sha256" in manifest:
            check(run.name+":config_hash", digest(config_bytes) == manifest["config_sha256"])
        else:
            caveats.append(dict(run=run.name,note="legacy 03 manifest lacks config_sha256; config bound by M freeze and archive, not retrofilled"))
        task_bytes = evidence.read(run/"task-card-snapshot.md")
        check(run.name+":task_snapshot", digest(task_bytes) == manifest["task_card_sha256"] == config["task_card_sha256"])
        lock_bytes = evidence.read(run/"SOURCE_LOCK.json")
        lock = strict_json(lock_bytes.decode("utf-8"))["model"]
        check(run.name+":lock", digest(lock_bytes) == manifest["source_lock_sha256"] == config["source_lock_sha256"] == criteria["source_lock_sha256"])
        check(run.name+":revision", manifest["upstream_commit"] == lock["revision"] == criteria["model_revision"])
        check(run.name+":caps", config["caps"] == manifest["budget"] == dict(worker_starts=4,max_new_tokens=256,per_worker_s=180,total_worker_s=720,images_per_call=1,image_width=64,image_height=64))
        check(run.name+":readonly_assets", local(config["model_dir"]) == ROOT/"data/agent_native/E1-010/model" and local(config["python"]) == ROOT/"data/agent_native/E1-010/env/Scripts/python.exe")
        observed = evidence.json(run/"inventory.json")
        pf = preflight_by_run[run.name]
        monitored = config.get("monitored_direct_cuda",False)
        minimum = criteria["monitored_minimum_free_ram_bytes"] if monitored else criteria["minimum_free_ram_bytes"]
        free_gpu = int(observed["gpu_query"]["stdout"].strip().splitlines()[0].split(",")[2].strip().split()[0])*1024**2
        passed = observed["free_ram_bytes"] >= minimum and free_gpu >= criteria["minimum_free_vram_bytes"]
        check(run.name+":preflight", passed == pf["passed"] and pf["free_ram_bytes"] == observed["free_ram_bytes"] and pf["gpu_query"] == observed["gpu_query"])
        if monitored:
            check(run.name+":M_mode_revision", "## M有监测低RAM加载修订（03预检失败后）" in task_bytes.decode("utf-8") and config["minimum_free_ram_bytes"] == minimum and config["monitor_interval_seconds"] <= .5 and config["monitor_stop_free_ram_bytes"] == criteria["monitor_stop_free_ram_bytes"] and bool(pf.get("resource_change_note")))
        if not passed:
            result = evidence.json(run/"result.json")
            check(run.name+":resource_block_retained", manifest["status"] == result["status"] == "resource_blocked" and not run_workers and manifest["worker_starts"] == result["worker_starts"] == 0 and result["actual_model_forwards"] == 0)
            continue
        assets = evidence.json(run/"asset_verification.json")
        allowed = lock["download_plan"]["conservative_root_allowlist"]
        check(run.name+":asset_manifest", set(assets) == set(allowed) and {n:r["sha256"] for n,r in assets.items()} == manifest["data_and_weights_sha256"])
        for source in lock["files"]:
            name = source["path"]
            if name not in assets:
                continue
            identity = (assets[name]["sha256"] == source["sha256"]) if source["sha256"] else (assets[name]["git_blob_sha1"] == source["git_blob_sha1"])
            check(run.name+":asset_identity_record:"+name, identity)
        images = evidence.json(run/"input_manifest.json")
        labels = evidence.json(run/"evaluator_labels.json")
        pixels = []
        for index,image in enumerate(images):
            raw = evidence.read(image["path"])
            pixel = png_rgb(raw); pixels.append(pixel)
            check(run.name+":image:"+str(index), digest(raw) == image["sha256"] and len(raw) == image["encoded_bytes"] and pixel["rgb"] == criteria["expected_input_colors"][str(index)])
        check(run.name+":two_inputs",len(images) == 2 and labels["input_expected_colors"] == ["red","blue"])
        summary = evidence.json(run/"summary.json")
        check(run.name+":worker_count",manifest["worker_starts"] == len(run_workers) == len(summary["calls"]))
        forward_count = 0
        for worker_dir in run_workers:
            spec = evidence.json(worker_dir/"spec.json")
            result = evidence.json(worker_dir/"result.json")
            process = evidence.json(worker_dir/"process.json")
            process_records.append(process)
            index = process["input_index"]
            node = "participant-"+str(index)
            context = dict(node_id=node,visible_evidence_ids=["local-image"],image_count=1,inbox=[],private_context=True)
            check(worker_dir.name+":private_context",spec["node_id"] == result["node_id"] == node and digest(encode(context)) == spec["context_sha256"] == result["context_sha256"] and spec["images"] == [images[index]])
            check(worker_dir.name+":prompt",spec["prompt"] == config["prompt_versions"][process["prompt_version"]] and not re.search(r"\b(red|blue)\b",spec["prompt"],re.I) and str(index) not in spec["prompt"])
            check(worker_dir.name+":spec_limits",spec["max_new_tokens"] == result["max_new_tokens"] == 256 and 0 < spec["max_generation_s"] <= 180 and spec["source_revision"] == result["source_revision"] == lock["revision"])
            check(worker_dir.name+":launch_gate",spec["free_ram_before_start_bytes"] >= minimum and (not monitored or spec["direct_cuda_load"] is True))
            command = process["command"]
            check(worker_dir.name+":actual_worker_command",local(command[0]) == local(config["python"]) and command[1] == "-B" and local(command[2]) == run/"source/model_worker.py" and command[3:] == ["--spec",str(worker_dir/"spec.json"),"--result",str(worker_dir/"result.json")] and local(result["python"]) == local(config["python"]))
            started = result["actual_forward_started"] is True
            generated = result["status"] == "generated"
            forward_count += int(started)
            check(worker_dir.name+":forward_consistency",process["actual_forward_started"] == started and (not generated or started))
            check(worker_dir.name+":summary",{k:v for k,v in process.items() if k != "command"} in summary["calls"])
            reservation = next(r for r in reservations if r["worker_id"] == process["worker_id"])
            finish = next(r for r in finishes if r["worker_id"] == process["worker_id"])
            check(worker_dir.name+":ledger",reservation["run_id"] == run.name and finish["wall_seconds"] == process["wall_seconds"] and finish["actual_forward_started"] == started and finish["exit_code"] == process["exit_code"] and finish["input_index"] == index and finish["monitor_stop_reason"] == process["monitor"].get("monitor_stop_reason"))
            row = dict(worker_id=process["worker_id"],run=run.name,input_index=index,status=result["status"],
                       actual_forward_started=started,generated_completed=generated,wall_seconds=process["wall_seconds"],
                       worker_pid=process["monitor"].get("worker_pid"),
                       format_status="not_tested_no_generation",reference_status="not_tested_no_generation",
                       semantic_status="not_tested_no_generation",pixels=pixels[index])
            if generated:
                raw = result["raw_output"]
                row["raw_output"] = raw
                check(worker_dir.name+":tokens",type(result["output_tokens"]) is int and 0 < result["output_tokens"] <= spec["max_new_tokens"])
                check(worker_dir.name+":tensor_record",bool(result.get("input_tensor_shapes")))
                try:
                    action = tool_check(raw,dict(private_and_arrived_evidence={"local-image":images[index]},peers=[]))
                    row["format_status"] = "pass"
                    row["reference_status"] = "pass" if action.get("evidence_refs") == ["local-image"] else "fail"
                except (ValueError,TypeError,KeyError) as exc:
                    row.update(format_status="fail",reference_status="fail",tool_error=str(exc))
                row["semantic"] = semantics(raw,["red","blue"][index])
                row["semantic_status"] = row["semantic"]["status"]
            else:
                check(worker_dir.name+":no_invented_output",not result.get("raw_output") and not result.get("input_tensor_shapes") and not process.get("visual_correct"))
            monitor = process.get("monitor",{})
            if monitored:
                curve = [strict_json(line) for line in evidence.read(worker_dir/"ram_curve.jsonl").decode("utf-8").splitlines() if line.strip()]
                times = [r["elapsed_seconds"] for r in curve]
                gaps = [b-a for a,b in zip(times,times[1:])]
                check(worker_dir.name+":monitor_samples",len(curve) == monitor["ram_samples"] and all(r["worker_pid"] == monitor["worker_pid"] for r in curve) and times[0] <= .5 and all(0<=g<=.5 for g in gaps) and 0<=process["wall_seconds"]-times[-1]<=.5)
                last = curve[-1]
                check(worker_dir.name+":monitor_minimum",min(r["free_ram_bytes"] for r in curve) == monitor["minimum_observed_free_ram_bytes"])
                check(worker_dir.name+":guard_stop",monitor["monitor_stop_reason"] == last["stop_reason"] == finish["monitor_stop_reason"] == "low_system_ram" and last["free_ram_bytes"] < criteria["monitor_stop_free_ram_bytes"] and all(r["free_ram_bytes"]>=criteria["monitor_stop_free_ram_bytes"] and r["stop_reason"] is None for r in curve[:-1]) and monitor["worker_reaped"] is True and monitor["exit_code"] == process["exit_code"] != 0)
                row["monitor"] = dict(samples=len(curve),maximum_gap_seconds=max(gaps,default=0),minimum_free_ram_bytes=monitor["minimum_observed_free_ram_bytes"],last=last,worker_reaped=monitor["worker_reaped"])
            cases.append(row)
        check(run.name+":forward_count",manifest["actual_model_forwards"] == forward_count)
        state = dict(worker_starts=len(reservations),charged_worker_seconds=sum(r["wall_seconds"] for r in finishes),generated_calls=sum(bool(r["actual_forward_started"]) for r in finishes),monitor_protection_stopped=any(r.get("monitor_stop_reason") in {"low_system_ram","monitor_unavailable"} for r in finishes))
        check(run.name+":ledger_state",state == summary["task_ledger"] == manifest["task_ledger"])
    ids = [r["worker_id"] for r in reservations]
    check("ledger_task",all(r["task_id"] == "E1-012" for r in ledger))
    check("ledger_attempt_identity",ids == list(range(1,len(ids)+1)) and {r["worker_id"] for r in finishes} == set(ids) and len(finishes) == len(ids) == manifest_workers == len(cases))
    check("budget",len(reservations)<=4 and len(preflights)<=2 and len(revisions)<=1 and sum(r["wall_seconds"] for r in finishes)<=720 and all(0<r["wall_seconds"]<=180 for r in finishes) and all(r["max_new_tokens"]<=256 and r["timeout_s"]<=180 for r in reservations))
    guarded_positions = [i for i,r in enumerate(ledger) if r["event"] == "worker_finished" and r.get("monitor_stop_reason") in {"low_system_ram","monitor_unavailable"}]
    check("no_retry_after_guard",all(not any(r["event"] in {"worker_reserved","formal_preflight","prompt_revision"} for r in ledger[i+1:]) for i in guarded_positions))
    # Explicitly verify original-to-archive bytes without modifying either side.
    archive_root = ROOT/"simulation/results/2026-10-28-E1-012-a0"
    archive = evidence.json(archive_root/"ARCHIVE_MANIFEST.json")
    for record in archive["files"]:
        a,b = evidence.read(record["source"]),evidence.read(archive_root/record["archive"])
        check("archive:"+record["source"],a == b and len(a) == record["bytes"] and digest(a) == record["sha256"])
    check("final_test_matches_execution",all(evidence.read(ROOT/"simulation/outputs/E1-012/20261028-07-monitor-final-checks/source"/name) == evidence.read(ROOT/"simulation/outputs/E1-012/20261028-08-A0-monitored/source"/name) == evidence.read(ROOT/"simulation/edge_agent_entry"/name) for name in ["a0_task.py","common.py","model_worker.py","runtime.py","a0.py"]))
    process_check = evidence.json(ROOT/"simulation/outputs/E1-012/20261028-10-final-audit/process-check.json")
    check("recorded_process_cleanup",process_check["present_pids"] == [] and process_check["worker_reaped_from_parent_record"] is True and all(row["worker_pid"] in process_check["checked_pids"] for row in cases))
    final_tests = evidence.json(ROOT/"simulation/outputs/E1-012/20261028-07-monitor-final-checks/result.json")
    check("saved_final_regression",final_tests["tests_run"] == 35 and final_tests["failures"] == final_tests["errors"] == 0 and final_tests["successful"] is True and final_tests["actual_model_forwards"] == 0)
    evidence_ok = all(c["passed"] for c in checks)
    passed_inputs = {r["input_index"] for r in cases if r["generated_completed"] and r["format_status"] == r["reference_status"] == r["semantic_status"] == "pass"}
    return dict(checks=checks, runs=runs, cases=cases, caveats=caveats,
                all_automatic_checks_passed=evidence_ok,evidence_consistency="pass" if evidence_ok else "fail",
                compatibility_conclusion="candidate_pass_manual_source_review_required" if evidence_ok and passed_inputs == {0,1} else "not_established",
                actual_worker_starts=len(reservations),actual_generation_started=sum(r["actual_forward_started"] for r in cases),
                actual_generation_completed=sum(r["generated_completed"] for r in cases),formal_preflights=len(preflights),
                prompt_revisions=len(revisions),worker_wall_seconds=sum(r["wall_seconds"] for r in finishes),
                archive_file_count=len(archive["files"]),manual_source_review_required=True,
                limitations=["resource guard failure is retained valid evidence, not a visual misclassification",
                             "model load/image tensors/format/color ability unestablished without generation",
                             "two synthetic inputs only; no collaboration/general accuracy/network result",
                             "RAM curve is system available memory, not worker peak or causal attribution",
                             "saved process cleanup and regression evidence reviewed, not rerun",
                             "weights/environment remain read-only and were not rehashed/imported by E2"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze",required=True)
    parser.add_argument("--output",required=True)
    args = parser.parse_args()
    freeze_path = local(args.freeze)
    freeze_bytes = freeze_path.read_bytes()
    if digest(freeze_bytes) != "ebd13fd8df0b5dddb0236211a87154d286860054d3c4a208ee75a51eed13cc06":
        raise ValueError("freeze differs from M checkpoint hash; request new explicit freeze")
    freeze = strict_json(freeze_bytes.decode("utf-8-sig"))
    if (freeze.get("schema") != "E2-013-M-freeze/1" or freeze.get("frozen_by_role") != "M"
            or freeze.get("target_task") != "E1-012" or freeze.get("all_attempts_included") is not True
            or not freeze.get("frozen_at") or not freeze.get("version_reference")):
        raise ValueError("M complete freeze required")
    output = local(args.output)
    if not output.is_relative_to(OUT.resolve()) or output == OUT.resolve():
        raise ValueError("new directory under E2-013 outputs required")
    previous = [p for p in OUT.glob("*/manifest.json")] if OUT.exists() else []
    if len(previous) >= 2:
        raise ValueError("E2-013 validation run cap exhausted")
    criteria_bytes = (OWN/"criteria.json").read_bytes()
    signature = digest(Path(__file__).read_bytes()+criteria_bytes)
    if previous and strict_json(previous[0].read_text(encoding="utf-8"))["validator_signature"] == signature:
        raise ValueError("second validation requires a recorded validator/criteria revision")
    output.mkdir(parents=True,exist_ok=False)
    snapshot = output / "source"
    snapshot.mkdir()
    for path in OWN.iterdir():
        if path.is_file() and path.suffix in {".py",".json",".md"}:
            shutil.copyfile(path,snapshot/path.name)
    card = ROOT / "coordination/tasks/E2-013.md"
    shutil.copyfile(card,output/card.name)
    (output/"freeze.json").write_bytes(freeze_bytes)
    template_bytes = (ROOT/"coordination/templates/RUN_MANIFEST.json").read_bytes()
    (output/"RUN_MANIFEST.template.json").write_bytes(template_bytes)
    manifest = strict_json(template_bytes.decode("utf-8-sig"))
    manifest.update(template_only=False,task_id="E2-013",run_id=output.name,started_at=now(),
                    worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,
                    dependency_snapshot={"python":sys.version,"external_dependencies":[]},
                    config_file=str(freeze_path),config_sha256=digest(freeze_bytes),seeds=[],
                    budget={"validation_runs_max":2,"model_calls":0,"downloads":0,"simulations":0},
                    output_directory=str(output),process_id=os.getpid(),status="running",
                    validator_signature=signature,task_card_sha256=digest(card.read_bytes()),
                    dirty_files_sha256={str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in OWN.iterdir() if p.is_file()},
                    limitations=["frozen evidence only; no model/env execution"])
    manifest["git_commit"] = subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    write(output/"manifest.json",manifest)
    evidence = None
    try:
        evidence = Evidence(freeze)
        report = evaluate(evidence,freeze,strict_json(criteria_bytes.decode("utf-8")))
        # Repeat hash reads so concurrent mutation is not silently accepted.
        for path in evidence.expected:
            evidence.read(path)
        write(output/"validation.json",report)
        code = 0 if report["all_automatic_checks_passed"] else 1
        manifest["status"] = "automatic_checks_passed_manual_pending" if code == 0 else "evidence_checks_failed"
    except Exception as exc:
        write(output/"failure.json",dict(error_type=type(exc).__name__,error=str(exc)))
        manifest["status"], code = "validation_failed",1
    manifest.update(finished_at=now(),exit_code=code,input_files_sha256=evidence.observed if evidence else {})
    write(output/"manifest.json",manifest)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
