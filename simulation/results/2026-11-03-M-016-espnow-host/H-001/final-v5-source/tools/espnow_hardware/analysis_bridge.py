"""Append derived measurements only from a closed, provenance-checked capture."""
import importlib.util
import math
from pathlib import Path

from . import hardware_tool as h

ANALYZER_KEY = "E2_analyzer_v2"
ANALYZER_ANCHOR = "919ee80516e48548e086813badaf18dcd7a5f2d1d8311dad1290df1d92d6b3f9"
# Explicit M replacement approval; v1 is not a fallback.
ANALYZER_ENABLED = True


def load_analyzer(root):
    if not ANALYZER_ENABLED:
        raise ValueError("analyzer integration paused pending M-approved replacement freeze")
    root = Path(root)
    prefix = "tests/espnow/"
    anchor = prefix + "ANALYZER_FREEZE.json"
    registry = h.read_json(root / "coordination/reviews/M-016-verification.json")
    if registry.get("active_freezes", {}).get("E2_analyzer") != ANALYZER_KEY:
        raise ValueError("unknown or unapproved active E2 analyzer")
    frozen = registry.get("frozen", {}).get(ANALYZER_KEY)
    if not isinstance(frozen, dict) or frozen.get(anchor) != ANALYZER_ANCHOR or h.sha(root / anchor) != ANALYZER_ANCHOR:
        raise ValueError("unapproved E2 analyzer freeze")
    declaration = h.read_json(root / anchor)
    expected = {prefix + k: v for k, v in declaration["source_hashes"].items()}
    expected[anchor] = ANALYZER_ANCHOR
    if frozen != expected:
        raise ValueError("E2 analyzer source set mismatch")
    for name, digest in frozen.items():
        path = (root / name).resolve()
        if not path.is_relative_to((root / prefix).resolve()) or ".." in Path(name).parts or h.sha(path) != digest:
            raise ValueError("E2 analyzer source drift or path escape")
    spec = importlib.util.spec_from_file_location("ann_frozen_analyzer", root / prefix / "analyze_logs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, frozen


def capture_context(plan, result, capture, by_id, runtime):
    sender, receiver = plan["sender_id"], plan["receiver_id"]
    source = by_id[sender]["node_id"].lower()
    destination = by_id[receiver]["node_id"].lower()
    infos = {p["id"]: p["info"] for p in result["probes"]}
    reasons = []
    if result["status"] != "hardware_capture_unanalyzed" or result.get("cleanup_errors"):
        reasons.append("capture_or_cleanup_failed")
    if len(result.get("stop_attempts", [])) != len(plan["device_ids"]) or not all(p["acknowledged"] for p in result.get("stop_attempts", [])):
        reasons.append("stop_not_confirmed_for_all_devices")
    for device in plan["device_ids"]:
        baseline = runtime.get("baseline_stats", {}).get(device)
        final = runtime.get("final_stats", {}).get(device)
        if not baseline or not final:
            reasons.append("missing_stats:" + device)
            continue
        boot = infos.get(device, {}).get("boot_id")
        if baseline.get("boot_id") != boot or final.get("boot_id") != boot or capture.observed_boots.get(device, set()) != {boot}:
            reasons.append("logger_boot_changed_or_missing:" + device)
        for counter in ("event_overflow", "queue_overflow", "delivered"):
            if type(baseline.get(counter)) is not int or type(final.get(counter)) is not int or final[counter] < baseline[counter]:
                reasons.append("unknown_or_regressed_counter:" + device + ":" + counter)
        if any(final.get(k) != 0 for k in ("event_overflow", "queue_overflow")):
            reasons.append("event_or_queue_overflow:" + device)
        if device in capture.malformed_devices or capture.pending.get(device) or capture.pending.get(device + "_discard"):
            reasons.append("malformed_or_partial_serial:" + device)
    baseline = runtime.get("baseline_stats", {}).get(receiver, {})
    final = runtime.get("final_stats", {}).get(receiver, {})
    observed = {key for key in capture.unique_rx.get(receiver, set())
                if key[0] == source and key[1] == infos.get(sender, {}).get("boot_id")}
    if type(baseline.get("delivered")) is int and type(final.get("delivered")) is int:
        if final["delivered"] - baseline["delivered"] != len(observed):
            reasons.append("receiver_counter_log_mismatch")
    start, end = runtime.get("window_start_ns"), runtime.get("window_end_ns")
    duration = (end - start) // 1000 if type(start) is int and type(end) is int and end > start else None
    synthetic = capture.evidence_kind == "synthetic"
    if capture.evidence_kind not in ("synthetic", "hardware_serial"):
        reasons.append("unknown_capture_evidence_kind")
    log_path = str(capture.path.resolve())
    log_digest = h.sha(capture.path)
    return {"schema": "ann.hardware.capture_context.v1", "task_id": "H-001", "run_id": plan["run_id"],
            "status": result["status"], "evidence_kind": "synthetic" if synthetic else "hardware_measured",
            "source_node_id": source, "destination_id": destination, "expected_generated": plan["count"],
            "receiver_log_complete": not reasons, "coverage_reasons": reasons,
            "duration_clock": "host_monotonic_controlled_window" if duration else None,
            "measurement_duration_us": duration, "window_start_ns": start, "window_end_ns": end,
            "window_reason": None if duration else "measured_host_window_missing",
            "baseline_stats": runtime.get("baseline_stats", {}), "final_stats": runtime.get("final_stats", {}),
            "bindings": {key: by_id[key] for key in plan["device_ids"]}, "verified_infos": infos,
            "stop_attempts": result.get("stop_attempts", []), "cleanup_errors": result.get("cleanup_errors", []),
            "serial_sha256": log_digest,
            "raw_logs": [{"path": log_path, "sha256": log_digest}],
            "log_sha256": {log_path: log_digest},
            "stats_errors": runtime.get("stats_errors", []),
            "notes": ["Host window includes serial command/stop/drain latency", "Counter reconciliation supports log coverage; no RF retry or PHY airtime measurement"]}


def append_measurements(output, analysis, analysis_path, context):
    """Never overwrite baseline measurements.json; one new sourced update per run."""
    if analysis.get("evidence_kind") != "hardware_measured" or context.get("evidence_kind") != "hardware_measured":
        return {"status": "synthetic_or_unknown_not_imported"}
    if analysis.get("schema") != "ann.analysis.v1" or analysis.get("run_id") != context["run_id"] or analysis.get("mode") != "reliable":
        return {"status": "analysis_schema_run_or_mode_mismatch"}
    if not context["receiver_log_complete"] or analysis.get("issues") or analysis.get("generated_unique") != context["expected_generated"]:
        return {"status": "insufficient_capture_evidence"}
    metrics = {}
    for key in h.METRICS:
        status = analysis.get("metric_status", {}).get(key, {})
        value = analysis.get(key)
        valid = (key in ("pdr", "goodput_bps", "rtt_p95_ms") and status.get("status") in
                 ("calculated", "calculated_successful_echo_subset") and type(value) in (int, float) and math.isfinite(value) and value >= 0)
        if key == "pdr" and valid and value > 1:
            valid = False
        metrics[key] = {"value": value if valid else None, "status": "measured" if valid else "not_measured",
                        "reason": None if valid else status.get("reason", "not_observed"),
                        "source": {"analysis": str(analysis_path), "sha256": h.sha(analysis_path)} if valid else None}
    if not any(metric["value"] is not None for metric in metrics.values()):
        return {"status": "no_admissible_metrics"}
    update = {"schema": "ann.hardware.measurement_update.v1", "run_id": context["run_id"],
              "evidence_kind": "hardware_measured", "status": "measured", "metrics": metrics,
              "source": {"analysis": str(analysis_path), "sha256": h.sha(analysis_path),
                         "logs": analysis["source_logs"], "manifests": analysis["source_manifests"],
                         "config": analysis["source_config"], "analyzer_sha256": analysis["analyzer_sha256"]},
              "goodput_definition": analysis.get("goodput_definition"),
              "rtt_scope": "nearest-rank P95 of successful same-source-boot echoes only",
              "generated_unique": analysis.get("generated_unique"), "generated_without_echo": analysis.get("generated_without_echo")}
    import json
    path = Path(output) / "measurement_updates.jsonl"
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(update, ensure_ascii=False, allow_nan=False) + "\n")
    return {"status": "appended", "path": str(path), "sha256": h.sha(path)}


def finalize_capture(root, output, plan, result, capture, by_id, runtime):
    """Closed raw data + immutable context/config -> frozen analyzer -> append-only update."""
    output = Path(output)
    context = capture_context(plan, result, capture, by_id, runtime)
    context_path = output / "capture_context.json"
    h.write_json(context_path, context)
    if result["status"] != "hardware_capture_unanalyzed":
        return {"status": "capture_failed_not_analyzed", "context": str(context_path)}
    destination = output / "synthetic" if context["evidence_kind"] == "synthetic" else output
    if destination != output:
        destination.mkdir(exist_ok=False)
    config_path = destination / "analysis_config.json"
    config = {key: context[key] for key in ("run_id", "source_node_id", "destination_id", "evidence_kind", "expected_generated", "receiver_log_complete", "measurement_duration_us", "duration_clock")}
    config["mode"] = "reliable"
    h.write_json(config_path, config)
    analyzer, frozen = load_analyzer(root)
    # Hash the inputs before and after; never pass the mutable final RUN_MANIFEST.
    original = {str(path): h.sha(path) for path in (capture.path, context_path, config_path)}
    analysis = analyzer.analyze_files(config_path, [capture.path], manifest_paths=[context_path])
    if any(h.sha(path) != digest for path, digest in original.items()):
        raise ValueError("analysis input changed during calculation")
    _, after = load_analyzer(root)
    if after != frozen:
        raise ValueError("analyzer freeze changed during calculation")
    analysis_path = destination / "analysis.json"
    h.write_json(analysis_path, analysis)
    update = append_measurements(output, analysis, analysis_path, context)
    return {"status": "analyzed", "analysis": str(analysis_path), "sha256": h.sha(analysis_path),
            "context": str(context_path), "measurement_update": update}
