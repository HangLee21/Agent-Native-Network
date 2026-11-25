"""Finite frozen C echo -> actual H Capture -> frozen E2 API interop; synthetic only."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from . import hardware_tool as h
from . import analysis_bridge as bridge
from .verify_host import check_active_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != (h.ROOT / "simulation/outputs/H-001").resolve():
        parser.error("new H-001 run directory required")
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest = h.read_json(h.ROOT / "coordination/templates/RUN_MANIFEST.json")
    manifest.update(template_only=False, task_id="H-001", run_id=out.name, started_at=h.now(),
                    worktree=str(h.ROOT), command=[sys.executable, *sys.argv], python_executable=sys.executable,
                    dirty_files_sha256=h.source_hashes(), evidence_kind="synthetic", output_directory=str(out),
                    budget={"whole_run_seconds": 120, "compile_parallel_jobs": 2, "task_seconds": 600})
    code = 1
    try:
        before = check_active_release(h.ROOT)
        _, analyzer = bridge.load_analyzer(h.ROOT)
        h.write_json(out / "input_freezes.json", {"E1": before, "E2": analyzer})
        build = out / "build"
        commands = [["cmake", "-S", str(h.ROOT / "firmware/agent_native"), "-B", str(build), "-G", "Ninja"],
                    ["cmake", "--build", str(build), "--target", "ann_host", "--parallel", "2"],
                    [str(build / ("ann_host.exe" if sys.platform == "win32" else "ann_host")), "--scenario", "echo"]]
        completed = []
        manifest["commands"] = commands
        for index, command in enumerate(commands):
            remaining = 115 - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("whole-run budget exhausted")
            run = subprocess.run(command, cwd=h.ROOT, capture_output=True, timeout=min(60, remaining))
            (out / f"command-{index}.stdout").write_bytes(run.stdout)
            (out / f"command-{index}.stderr").write_bytes(run.stderr)
            if run.returncode:
                raise RuntimeError(f"command {index} failed: {run.returncode}")
            completed.append(run)
        trace = completed[-1].stdout
        if len(trace) > h.MAX_BYTES:
            raise RuntimeError("C trace exceeds capture byte bound")
        synthetic = out / "synthetic"
        synthetic.mkdir()
        capture = h.Capture(synthetic, evidence_kind="synthetic")
        try:
            for raw in trace.splitlines():
                event = h.parse_event(raw)
                if event:
                    device = "board" + str(int(event["node_id"].split(":")[-1], 16))
                    capture.record(device, "device_rx", raw)
        finally:
            capture.close()
        by_id = {key: {"node_id": "00:00:00:00:00:" + f"{int(key[5:]):02x}"} for key in capture.observed_boots}
        infos = [{"id": key, "info": {"boot_id": next(iter(boots)), "chip": "host-synthetic"}}
                 for key, boots in capture.observed_boots.items()]
        plan = {"run_id": "echo", "sender_id": "board1", "receiver_id": "board5", "count": 1, "device_ids": sorted(by_id)}
        result = {"status": "hardware_capture_unanalyzed", "probes": infos, "cleanup_errors": [],
                  "stop_attempts": [{"id": key, "acknowledged": True} for key in by_id]}
        # Explicitly synthetic coverage fixture: trace is a finite successful C process.
        baseline = {p["id"]: {"boot_id": p["info"]["boot_id"], "delivered": 0, "event_overflow": 0, "queue_overflow": 0} for p in infos}
        final = {key: {**item, "delivered": len(capture.unique_rx.get(key, set()))} for key, item in baseline.items()}
        runtime = {"baseline_stats": baseline, "final_stats": final, "window_start_ns": 1_000_000_000, "window_end_ns": 2_000_000_000}
        h.write_json(synthetic / "measurements.json", h.measurement_ledger())
        analysis_result = bridge.finalize_capture(h.ROOT, synthetic, plan, result, capture, by_id, runtime)
        analysis = h.read_json(analysis_result["analysis"])
        if (analysis["evidence_kind"] != "synthetic" or analysis["generated_unique"] != 1 or
                analysis["destination_unique_rx_observed"] != 1 or analysis["successful_same_boot_rtt_count"] != 1):
            raise AssertionError("actual C echo and H capture identity interop failed")
        if (synthetic / "measurement_updates.jsonl").exists():
            raise AssertionError("synthetic capture must never append measured values")
        if check_active_release(h.ROOT) != before or bridge.load_analyzer(h.ROOT)[1] != analyzer:
            raise ValueError("input freeze changed during C interop")
        h.write_json(out / "result.json", {"status": "passed", "evidence_kind": "synthetic", "actual_frozen_C_compiled": True,
                     "C_trace_sha256": h.sha(out / "command-2.stdout"), "H_capture_sha256": h.sha(capture.path),
                     "analysis": analysis_result, "coverage_fixture": "synthetic counters and normalized one-second window; not UART/RF measurements",
                     "physical_ports_opened": 0, "wireless_runs": 0, "target_compilation": "not_verified"})
        manifest["status"] = "passed"
        code = 0
    except Exception as exc:
        manifest.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
    finally:
        manifest.update(finished_at=h.now(), exit_code=code, elapsed_seconds=time.monotonic() - started,
                        limitations=["Native host C build, not ESP target", "Synthetic C trace and coverage/window only", "No physical serial/radio/real measurements"])
        h.write_json(out / "RUN_MANIFEST.json", manifest)
    print(json.dumps({"status": manifest["status"], "output": str(out), "exit_code": code}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
