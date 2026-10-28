"""E1-012: bounded A0 with read-only E1-010 assets and a new task ledger."""
from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
import re
import subprocess
import time
import traceback

from .a0 import verify_model_file
from .common import ROOT, available_ram, complete_run, file_sha, inventory, new_run, utc_now
from .runtime import encode, parse_action, sha, synthetic_png, write_json

TASK = "E1-012"
TASK_DATA = ROOT / "data/agent_native" / TASK
ASSETS = ROOT / "data/agent_native/E1-010"
SOURCE_LOCK = ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json"
LOCK_SHA = "139330b3c5ba0468b06999e0b238a999c21cd6d10f1f106fe03b21d2601503c1"
CAPS = dict(worker_starts=4, max_new_tokens=256, per_worker_s=180, total_worker_s=720,
            images_per_call=1, image_width=64, image_height=64)
PROMPTS = [
    'Look at the supplied image and name its dominant visible color. Return only one JSON object with exactly these fields: '
    '{"tool":"finish","answer":"the dominant color","evidence_refs":["local-image"]}.',
    'Identify the dominant color shown in the image. Answer only JSON in this exact structure, replacing COLOR with your observation: '
    '{"tool":"finish","answer":"COLOR","evidence_refs":["local-image"]}'
]


class TaskLedger:
    """Append-only reservations; interrupted starts are charged their full limit."""
    def __init__(self, path):
        self.path = Path(path)
        self.rows = [json.loads(s) for s in self.path.read_text(encoding="utf-8").splitlines()] if self.path.exists() else []

    def append(self, event, **fields):
        row = dict(task_id=TASK, event=event, at=utc_now(), **fields)
        with self.path.open("ab") as stream:
            stream.write(encode(row) + b"\n")
            stream.flush()
        self.rows.append(row)
        return row

    def state(self):
        starts = [r for r in self.rows if r["event"] == "worker_reserved"]
        ended = {r["worker_id"]: r for r in self.rows if r["event"] == "worker_finished"}
        charged = sum(ended[r["worker_id"]]["wall_seconds"] if r["worker_id"] in ended else r["timeout_s"] for r in starts)
        return dict(worker_starts=len(starts), charged_worker_seconds=charged,
                    generated_calls=sum(bool(r.get("actual_forward_started")) for r in ended.values()))

    def reserve(self, run_id, max_tokens=256):
        state = self.state()
        if type(max_tokens) is not int or not 1 <= max_tokens <= CAPS["max_new_tokens"]:
            raise ValueError("token budget outside task cap")
        if state["worker_starts"] >= CAPS["worker_starts"] or state["charged_worker_seconds"] >= CAPS["total_worker_s"]:
            raise RuntimeError("task-wide worker budget exhausted")
        timeout = min(CAPS["per_worker_s"], CAPS["total_worker_s"] - state["charged_worker_seconds"])
        return self.append("worker_reserved", worker_id=state["worker_starts"] + 1,
                           run_id=run_id, timeout_s=timeout, max_new_tokens=max_tokens)


def resource_ok(record):
    lines = record.get("gpu_query", {}).get("stdout", "").strip().splitlines()
    free_gpu = int(lines[0].split(",")[2].strip().split()[0]) * 1024 ** 2 if lines and len(lines[0].split(",")) == 4 else 0
    return record.get("free_ram_bytes", 0) >= 2 * 1024 ** 3 and free_gpu >= 2684354560


def prompt_context(node, image, prompt_version):
    # Expected colors, filenames, hashes and other-node inputs never enter text.
    context = dict(node_id=node, visible_evidence_ids=["local-image"], image_count=1,
                   inbox=[], private_context=True)
    return dict(context=context, images=[copy.deepcopy(image)], prompt=PROMPTS[prompt_version])


def evaluate(raw):
    result = dict(format_valid=False, legal_reference=False, visual_color=None)
    try:
        action = parse_action(raw)
        result["format_valid"] = action["tool"] == "finish"
        result["legal_reference"] = action.get("evidence_refs") == ["local-image"]
        text = action.get("answer", "")
        result["parsed_action"] = action
    except (ValueError, TypeError) as exc:
        result["format_error"] = str(exc)
        text = raw
    words = set(re.findall(r"[a-z]+", text.lower()))
    colors = words & {"red", "blue"}
    result["visual_color"] = next(iter(colors)) if len(colors) == 1 else None
    result["visual_scoring_basis"] = "parsed_answer" if result["format_valid"] else "raw_unstructured_output"
    return result


def run(output, preflight_only=False, resource_change_note=None, resume=False):
    card = ROOT / "coordination/tasks/E1-012.md"
    card_text = card.read_text(encoding="utf-8")
    if "M授权E1-012在本卡新预算内执行有限A0真实模型兼容验证。" not in card_text or "- 状态：running" not in card_text:
        raise ValueError("live task checkpoint/running state required")
    if file_sha(SOURCE_LOCK) != LOCK_SHA:
        raise ValueError("D source lock changed")
    TASK_DATA.mkdir(parents=True, exist_ok=True)
    ledger = TaskLedger(TASK_DATA / "worker_ledger.jsonl")
    checks = [r for r in ledger.rows if r["event"] == "formal_preflight"]
    if resume and (not checks or not checks[-1]["passed"]):
        raise RuntimeError("resume requires the prior passing formal preflight")
    if not resume and (len(checks) >= 2 or (checks and (checks[0]["passed"] or not resource_change_note))):
        raise RuntimeError("no further formal preflight authorized without first-failure resource change")
    out, manifest = new_run(output, "E1-012_real_A0", CAPS, task_id=TASK)
    manifest.update(upstream_commit="7b375e1b73b11138ff12fe22c8f2822d8fe03467",
                    backend="smolvlm_local_model", deployment="P2_serial_private_contexts", downloads_bytes=0,
                    task_card_sha256=file_sha(card), source_lock_sha256=LOCK_SHA)
    (out / "task-card-snapshot.md").write_bytes(card.read_bytes())
    (out / "SOURCE_LOCK.json").write_bytes(SOURCE_LOCK.read_bytes())
    write_json(out / "config.json", dict(task_id=TASK, caps=CAPS, model_dir=str(ASSETS / "model"),
                                         python=str(ASSETS / "env/Scripts/python.exe"), prompt_versions=PROMPTS,
                                         task_card_sha256=manifest["task_card_sha256"], source_lock_sha256=LOCK_SHA))
    manifest["config_sha256"] = file_sha(out / "config.json")
    if resume:
        observations, passed = dict(reused_formal_preflight=checks[-1]), True
        write_json(out / "formal_preflight_reference.json", checks[-1])
    else:
        observations = inventory()
        write_json(out / "inventory.json", observations)
        passed = resource_ok(observations)
        ledger.append("formal_preflight", run_id=out.name, passed=passed,
                      free_ram_bytes=observations.get("free_ram_bytes"), gpu_query=observations["gpu_query"],
                      resource_change_note=resource_change_note)
    write_json(out / "manifest.json", manifest)
    if not passed or preflight_only:
        write_json(out / "result.json", dict(status="resource_pass" if passed else "resource_blocked", worker_starts=0,
                                             actual_model_forwards=0, resource=observations))
        complete_run(out, manifest, "resource_pass" if passed else "resource_blocked", 0 if passed else 2,
                     actual_model_forwards=0, worker_starts=0, task_ledger=ledger.state())
        return 0 if passed else 2
    results = []
    try:
        source = json.loads(SOURCE_LOCK.read_text(encoding="utf-8"))["model"]
        verified = {}
        for row in source["files"]:
            if row["path"] in source["download_plan"]["conservative_root_allowlist"]:
                p = ASSETS / "model" / row["path"]
                verified[row["path"]] = verify_model_file(p, row, file_sha(p))
        write_json(out / "asset_verification.json", verified)
        manifest["data_and_weights_sha256"] = {name: record["sha256"] for name, record in verified.items()}
        inputs = out / "inputs"; inputs.mkdir()
        images, expected = [], ["red", "blue"]
        for index, rgb in enumerate(((255, 0, 0), (0, 0, 255))):
            path = inputs / f"input-{index}.png"
            raw = synthetic_png(rgb); path.write_bytes(raw)
            images.append(dict(path=str(path), sha256=sha(raw), encoded_bytes=len(raw), width=64, height=64))
        write_json(out / "input_manifest.json", images)
        # Evaluator labels live outside worker specs and are not included in text.
        write_json(out / "evaluator_labels.json", dict(input_expected_colors=expected, rule="one expected color word, no opposite color word"))
        env = dict(os.environ, HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", USE_TF="0", USE_FLAX="0",
                   HF_HOME=str(TASK_DATA / "hf-cache"), PYTHONDONTWRITEBYTECODE="1", TOKENIZERS_PARALLELISM="false",
                   OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        version = int(any(row["event"] == "prompt_revision" for row in ledger.rows))
        completed_inputs = {row["input_index"] for row in ledger.rows
                            if row["event"] == "worker_finished" and row.get("input_passed")}
        case_index = next((i for i in range(2) if i not in completed_inputs), 2)
        # At most one wording revision; reattempting is always charged as a new worker.
        while len(results) < 4 and case_index < 2:
            launch_ram = available_ram()
            ledger.append("launch_ram_guard", run_id=out.name, free_ram_bytes=launch_ram,
                          passed=launch_ram >= 2 * 1024 ** 3)
            if launch_ram < 2 * 1024 ** 3:
                raise RuntimeError("less than 2GiB free RAM immediately before worker start")
            reservation = ledger.reserve(out.name)
            call_dir = out / f"worker-{reservation['worker_id']:02d}"
            call_dir.mkdir()
            prompt = prompt_context(f"participant-{case_index}", images[case_index], version)
            spec = dict(node_id=prompt["context"]["node_id"], context_sha256=sha(encode(prompt["context"])),
                        source_revision=source["revision"], model_dir=str(ASSETS / "model"), images=prompt["images"],
                        prompt=prompt["prompt"], max_new_tokens=256, max_generation_s=min(170, reservation["timeout_s"]),
                        direct_cuda_load=True, free_ram_before_start_bytes=launch_ram)
            write_json(call_dir / "spec.json", spec)
            command = [str(ASSETS / "env/Scripts/python.exe"), "-B", str(out / "source/model_worker.py"),
                       "--spec", str(call_dir / "spec.json"), "--result", str(call_dir / "result.json")]
            start = time.monotonic(); timed_out = False; error = None
            try:
                with (call_dir / "stdout.txt").open("w", encoding="utf-8") as log:
                    proc = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=reservation["timeout_s"])
                code = proc.returncode
            except subprocess.TimeoutExpired:
                timed_out, code = True, -999
            except OSError as exc:
                code, error = -998, str(exc)
            wall = time.monotonic() - start
            result_path = call_dir / "result.json"
            worker = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
            grading = evaluate(worker.get("raw_output", ""))
            grading["visual_correct"] = grading["visual_color"] == expected[case_index]
            input_passed = code == 0 and worker.get("status") == "generated" and all(grading.get(k) for k in ("format_valid", "legal_reference", "visual_correct"))
            ledger.append("worker_finished", worker_id=reservation["worker_id"], wall_seconds=wall,
                          actual_forward_started=worker.get("actual_forward_started", False), exit_code=code,
                          input_index=case_index, input_passed=input_passed)
            record = dict(worker_id=reservation["worker_id"], input_index=case_index, prompt_version=version,
                          exit_code=code, timed_out=timed_out, start_error=error, wall_seconds=wall,
                          actual_forward_started=worker.get("actual_forward_started", False), **grading)
            write_json(call_dir / "process.json", dict(command=command, **record))
            results.append(record)
            write_json(out / "summary.json", dict(calls=results, task_ledger=ledger.state()))
            print(json.dumps(record, ensure_ascii=False), flush=True)
            if code != 0 or worker.get("status") != "generated":
                break  # Runtime diagnostics may authorize a bounded corrected re-entry.
            if grading["format_valid"] and grading["legal_reference"] and grading["visual_correct"]:
                case_index += 1
            elif version == 0:
                ledger.append("prompt_revision", version=1, reason="generated output did not pass visual/format check")
                version = 1
            else:
                break
        success = case_index == 2
        complete_run(out, manifest, "A0_passed_two_inputs" if success else "A0_incomplete", 0 if success else 1,
                     worker_starts=len(results), actual_model_forwards=sum(r["actual_forward_started"] for r in results),
                     task_ledger=ledger.state(), limitations=["Synthetic visual/format compatibility only; no autonomous collaboration",
                                                           "Two private contexts execute serially with shared read-only weights"])
        return 0 if success else 1
    except Exception as exc:
        write_json(out / "failure.json", dict(error=str(exc), error_type=type(exc).__name__, traceback=traceback.format_exc()))
        complete_run(out, manifest, "A0_failed", 1, task_ledger=ledger.state(), worker_starts=len(results),
                     actual_model_forwards=sum(r["actual_forward_started"] for r in results))
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--preflight-only", action="store_true")
    p.add_argument("--resource-change-note")
    p.add_argument("--resume", action="store_true", help="bounded runtime repair, no extra formal preflight")
    a = p.parse_args()
    return run(a.output, a.preflight_only, a.resource_change_note, a.resume)


if __name__ == "__main__":
    raise SystemExit(main())
