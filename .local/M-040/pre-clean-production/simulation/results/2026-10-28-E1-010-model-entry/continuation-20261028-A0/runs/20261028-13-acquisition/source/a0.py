"""Bounded local A0 compatibility; requires M's task checkpoint and D's lock.

This does not acquire dependencies or weights. No model invocation is allowed
before the human M checkpoint; file hashes check provenance, not authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import traceback

from .common import DATA_ROOT, ROOT, complete_run, file_sha, inventory, new_run, utc_now
from .model_backend import SmolVLMBackend
from .runtime import Runtime, encode, parse_action, sha, synthetic_png, write_json


def verify_model_file(path, source_file, expected_local_sha256):
    """Bind ordinary Git files to D's frozen blob, not a caller's own SHA.

    LFS weights use their published content SHA-256. Their Git blob identifies
    the small pointer file, so it must not be compared to the weight content.
    """
    path = Path(path)
    size = path.stat().st_size
    if size != source_file["size_bytes"]:
        raise ValueError(f"model file size differs: {source_file['path']}")
    actual_sha256 = file_sha(path)
    published_sha256 = source_file["sha256"]
    if actual_sha256 != expected_local_sha256 or (published_sha256 is not None and actual_sha256 != published_sha256):
        raise ValueError(f"model file SHA-256 differs: {source_file['path']}")
    actual_blob = None
    if published_sha256 is None:
        frozen_blob = source_file.get("git_blob_sha1")
        if not frozen_blob:
            raise ValueError("file has no frozen content identity")
        digest = hashlib.sha1(f"blob {size}\0".encode("ascii"))
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual_blob = digest.hexdigest()
        if actual_blob != frozen_blob:
            raise ValueError(f"model file Git blob differs: {source_file['path']}")
    return dict(sha256=actual_sha256, git_blob_sha1=actual_blob)


def validate_config(config):
    lock = (ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json").resolve()
    card = (ROOT / "coordination/tasks/E1-010.md").resolve()
    if not config.get("m_checkpoint_excerpt") or config["m_checkpoint_excerpt"] not in card.read_text(encoding="utf-8-sig"):
        raise ValueError("M checkpoint excerpt absent from live task card")
    if sha(card.read_bytes()) != config["task_card_sha256"] or sha(lock.read_bytes()) != config["source_lock_sha256"]:
        raise ValueError("task checkpoint or frozen source lock changed")
    if config["repo_id"] != "HuggingFaceTB/SmolVLM2-500M-Video-Instruct":
        raise ValueError("A0 only supports the assigned SmolVLM2 model")
    source = json.loads(lock.read_text(encoding="utf-8-sig"))["model"]
    if config["repo_id"] != source["repo_id"] or config["source_revision"] != source["revision"]:
        raise ValueError("A0 model identity/revision differs from D's frozen lock")
    if set(config["model_file_sha256"]) != set(source["download_plan"]["conservative_root_allowlist"]):
        raise ValueError("A0 requires exactly D's 13-file conservative allowlist")
    revision = config["source_revision"]
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("immutable model revision required")
    for key in ("python", "model_dir"):
        path = Path(config[key]).resolve()
        if not path.is_relative_to(DATA_ROOT.resolve()) or not path.exists():
            raise ValueError(f"{key} must exist inside E1-010 data directory")
    for rel, expected in config["model_file_sha256"].items():
        source_file = next((row for row in source["files"] if row["path"] == rel), None)
        if source_file is None or (source_file["sha256"] is not None and source_file["sha256"] != expected):
            raise ValueError(f"file absent from D lock or published hash differs: {rel}")
        path = (Path(config["model_dir"]) / rel).resolve()
        if not path.is_relative_to(Path(config["model_dir"]).resolve()):
            raise ValueError(f"model file outside assigned model directory: {rel}")
        verify_model_file(path, source_file, expected)
    if not config["model_file_sha256"] or not any(name.endswith(".safetensors") for name in config["model_file_sha256"]):
        raise ValueError("no verified safe tensor weights")
    budget = config["budget"]
    if type(budget["calls"]) is not int or not 1 <= budget["calls"] <= 4:
        raise ValueError("A0 allows 1..4 invocations")
    if not 1 <= budget["max_new_tokens"] <= 128 or not 0 < budget["per_call_s"] <= 180 or not 0 < budget["total_s"] <= 720:
        raise ValueError("A0 exceeds approved task-card limits")
    if config["minimum_free_ram_bytes"] < 2147483648:
        raise ValueError("safe-load floor is at least 2GiB free RAM; not a measured model requirement")
    return lock, card


def run(config_path, output):
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    lock, card = validate_config(config)
    budget = config["budget"]
    out, manifest = new_run(output, "A0_local_model_compatibility", budget, config_path)
    manifest.update(backend="smolvlm_local_model", deployment="P2_serial_independent_contexts",
                    source_lock_sha256=sha(lock.read_bytes()), task_card_sha256=sha(card.read_bytes()),
                    upstream_commit=config["source_revision"], actual_model_forwards=0,
                    data_and_weights_sha256=config["model_file_sha256"],
                    m_checkpoint_excerpt=config["m_checkpoint_excerpt"],
                    limitations=["Synthetic image compatibility only; no autonomous collaboration, no wireless",
                                 "Shared read-only weights, separate prompts/contexts, serial GPU use",
                                 "Per-call wall timeout includes model load and preprocessing"])
    write_json(out / "manifest.json", manifest)
    (out / "SOURCE_LOCK.json").write_bytes(lock.read_bytes())
    (out / "E1-010-checkpoint.md").write_bytes(card.read_bytes())
    inventory_data = inventory()
    write_json(out / "inventory.json", inventory_data)
    manifest["dependency_snapshot"] = "worker result version dictionaries + inventory.json"
    backend = None
    try:
        if inventory_data.get("free_ram_bytes", 0) < config["minimum_free_ram_bytes"]:
            raise RuntimeError("insufficient free RAM for declared safe-load threshold")
        # The sole E1 writer retains attempts across failed runs; no reset on retry.
        ledger = DATA_ROOT / "a0_attempt_ledger.jsonl"
        attempts = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()] if ledger.exists() else []
        if len(attempts) + budget["calls"] > 4:
            raise RuntimeError("task-wide A0 attempt cap would be exceeded")
        consumed_worker_s = sum(row.get("worker_wall_seconds", 0) for row in attempts)
        if consumed_worker_s >= 720:
            raise RuntimeError("task-wide A0 wall budget exhausted")
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
                   HF_HUB_DISABLE_TELEMETRY="1", HF_HOME=str(DATA_ROOT / "hf-cache"),
                   OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", TOKENIZERS_PARALLELISM="false")
        backend = SmolVLMBackend(config["python"], config["model_dir"], config["source_revision"], out,
                                out / "source/model_worker.py", max_new_tokens=budget["max_new_tokens"],
                                per_call_s=budget["per_call_s"], total_s=min(budget["total_s"], 720 - consumed_worker_s), environment=env)
        inputs = out / "inputs"
        inputs.mkdir()
        nodes = {}
        for node, color in (("n0", (255, 0, 0)), ("n1", (0, 0, 255))):
            data = synthetic_png(color)
            path = inputs / (node + ".png")
            path.write_bytes(data)
            nodes[node] = {node + ":image": dict(kind="private_image", path=str(path), sha256=sha(data),
                                                encoded_bytes=len(data), width=64, height=64,
                                                provenance="generated_solid_color_compatibility_fixture")}
        write_json(out / "input_manifest.json", nodes)
        contexts = Runtime(nodes, backend, run_id=out.name).context
        calls = []
        for index in range(budget["calls"]):
            node = ("n0", "n1")[index % 2]
            # Each A0 call is independent; generated tools are parsed but not
            # executed as an autonomous conversation or fixture round-robin.
            record = dict(task_attempt=len(attempts) + len(calls) + 1, run_id=out.name,
                          call_index=index + 1, node_id=node, started_at=utc_now(), status="started")
            with ledger.open("a", encoding="utf-8") as stream:
                stream.write(encode(record).decode("utf-8") + "\n")
            started = time.monotonic()
            try:
                raw = backend.decide(node, contexts(node))
                action = parse_action(raw)
                # Validate local references/tool legality against the same boundary;
                # this does not deliver generated requests to another model.
                sandbox = Runtime(nodes, backend, run_id=out.name)
                sandbox.apply(node, action, "a0_external_tool_check")
                record.update(status="generated_valid_tool", raw_output=raw, parsed_action=action)
            except Exception as exc:
                record.update(status="model_or_format_failed", error=str(exc), traceback=traceback.format_exc())
            record["worker_wall_seconds"] = time.monotonic() - started
            calls.append(record)
            # Rewrite our own task-local ledger to fill completion, preserving all
            # previous attempts and their failure records. No other writer exists.
            complete = attempts + calls
            ledger.write_bytes(b"".join(encode(row) + b"\n" for row in complete))
            write_json(out / "summary.json", dict(calls=calls, attempted=backend.attempts,
                                                  actual_model_forwards_started=backend.forward_started))
            # A0 stops after the first load, OOM, generation or format failure.
            if record["status"] != "generated_valid_tool":
                break
        success = len(calls) == budget["calls"] and all(row["status"] == "generated_valid_tool" for row in calls)
        complete_run(out, manifest, "A0_compatible" if success else "A0_failed", 0 if success else 1,
                     actual_model_forwards=backend.forward_started, attempted=backend.attempts,
                     worker_wall_seconds=backend.accumulated_worker_s)
        return 0 if success else 1
    except Exception as exc:
        write_json(out / "failure.json", dict(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc()))
        complete_run(out, manifest, "blocked_before_forward" if backend is None else "failed", 1,
                     actual_model_forwards=backend.forward_started if backend else 0)
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    return run(args.config, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
