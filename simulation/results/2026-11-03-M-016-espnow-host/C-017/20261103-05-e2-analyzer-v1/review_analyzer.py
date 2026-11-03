"""C-017 E2 API tests. All inputs/results are synthetic; no physical measurement."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
assert OUT.parent == ROOT / "simulation/outputs/C-017"
SOURCE, DEST, BOOT = "00:00:00:00:00:01", "00:00:00:00:00:02", "00000064"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def config(**changes):
    return dict(run_id="fixture-run", source_node_id=SOURCE, destination_id=DEST,
                mode="reliable", evidence_kind="synthetic", expected_generated=1,
                receiver_log_complete=True, measurement_duration_us=1_000_000,
                duration_clock="receiver_local_window", **changes)


def rows():
    generated = dict(schema="ann.serial.v1", event="generated", nonce=None, run_id="fixture-run",
                     node_id=SOURCE, boot_id=BOOT, origin_id=SOURCE, origin_boot_id=BOOT,
                     seq=1, t_us=1000, frame_bytes=120, payload_bytes=8, status=0,
                     tx_attempt=None, unique_receive=False, evidence_kind="synthetic")
    received = dict(generated, event="rx", node_id=DEST, boot_id="000000c8", t_us=500,
                    unique_receive=True)
    echo = dict(generated, event="echo_correlation", t_us=4000,
                request_origin_id=SOURCE, request_boot_id=BOOT, request_seq=1, same_source_boot=True)
    return generated, received, echo


def main():
    began = time.monotonic()
    expected = json.loads((ROOT / "coordination/reviews/M-016-verification.json").read_text("utf-8-sig"))["frozen"]["E2_analyzer_v1"]
    if any(sha(ROOT / path) != value for path, value in expected.items()):
        raise RuntimeError("E2 analyzer freeze mismatch; stop")
    manifest = json.loads((ROOT / "coordination/templates/RUN_MANIFEST.json").read_text("utf-8-sig"))
    manifest.update(template_only=False, task_id="C-017", run_id=OUT.name,
                    started_at=datetime.now(timezone.utc).isoformat(), worktree=str(ROOT),
                    git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=2, text=True).strip(),
                    command=[sys.executable, "-B", str(Path(__file__).resolve())],
                    python_executable=sys.executable, output_directory=str(OUT),
                    dirty_files_sha256=expected | {str(Path(__file__).resolve().relative_to(ROOT)): sha(__file__)},
                    dependency_snapshot={"python": sys.version, "dependencies": "stdlib only"},
                    budget={"run_seconds": 60, "task_seconds": 600, "bytes": 104857600},
                    evidence_kind="synthetic", status="running", review_reference="coordination/reviews/C-017.md",
                    limitations=["Negative hardware-label inputs are synthetic fixtures, never actual measurement records",
                                 "No E2 active tests, H active integration, serial, RF, target build or model execution"])
    save("RUN_MANIFEST.started.json", manifest)
    spec = importlib.util.spec_from_file_location("c017_frozen_analysis", ROOT / "tests/espnow/analyze_logs.py")
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    observations = {}

    class AnalysisTests(unittest.TestCase):
        def test_valid_synthetic_control(self):
            result = analyzer.analyze(list(rows()), config())
            self.assertEqual(result["pdr"], 1)
            self.assertEqual(result["goodput_bps"], 64)
            self.assertEqual(result["rtt_p95_ms"], 3)
            self.assertIsNone(result["one_way_delay_ms"])
            self.assertIsNone(result["airtime_us"])
            observations["valid_control"] = {key: result[key] for key in ("pdr", "goodput_bps", "rtt_p95_ms", "issues")}

        def test_invalid_unique_receive_type_never_counts_delivery(self):
            for value in ("false", 0):
                with self.subTest(value=value):
                    generated, received, _ = rows()
                    received["unique_receive"] = value
                    result = analyzer.analyze([generated, received], config())
                    observations["non_boolean_unique_receive_" + str(value)] = {
                        key: result[key] for key in ("pdr", "destination_unique_rx_observed", "issues")}
                    self.assertNotEqual(result["pdr"], 1, "a non-boolean false-like flag cannot prove unique delivery")

        def test_conflicting_generation_identity_cannot_give_rtt(self):
            generated, received, echo = rows()
            conflicting = dict(generated, t_us=2000)
            result = analyzer.analyze([generated, conflicting, received, echo], config())
            observations["conflicting_generation"] = {
                key: result[key] for key in ("pdr", "rtt_p95_ms", "successful_same_boot_rtt_count", "issues", "metric_status")}
            self.assertIsNone(result["rtt_p95_ms"], "conflicting source generation times make this identity's RTT ambiguous")

        def test_hardware_manifest_must_match_selected_run(self):
            generated, received, _ = rows()
            for item in (generated, received):
                item["evidence_kind"] = "firmware_event"
            log = OUT / "hypothetical-hardware-envelope.jsonl"
            with log.open("x", encoding="utf-8") as stream:
                for item in (generated, received):
                    stream.write(json.dumps(dict(direction="device_rx", event=item, evidence_kind="hardware_serial")) + "\n")
            cfg = config()
            cfg["evidence_kind"] = "hardware_measured"
            save("hypothetical-hardware-config.json", cfg)
            save("unrelated-capture-manifest.json", dict(task_id="H-001", run_id="OTHER-RUN",
                    status="hardware_capture_unanalyzed", fixture_notice="Synthetic negative test, no hardware capture exists"))
            result = None
            rejected = None
            try:
                result = analyzer.analyze_files(OUT / "hypothetical-hardware-config.json", [log],
                                               [OUT / "unrelated-capture-manifest.json"])
            except ValueError as exc:
                rejected = str(exc)
            observations["unrelated_manifest"] = dict(rejected=rejected,
                    returned_label=result["evidence_kind"] if result else None,
                    pdr=result["pdr"] if result else None,
                    goodput_bps=result["goodput_bps"] if result else None,
                    manifest_run_id=result["source_manifests"][0]["run_id"] if result else None,
                    fixture_only=True)
            self.assertTrue(rejected is not None or (result["pdr"] is None and result["goodput_bps"] is None),
                            "a capture manifest for another run cannot establish hardware provenance")

        def test_unconfirmed_receiver_coverage_is_unknown(self):
            cfg = config()
            cfg["receiver_log_complete"] = False
            result = analyzer.analyze(list(rows()), cfg)
            self.assertIsNone(result["pdr"])
            self.assertIsNone(result["goodput_bps"])

    with (OUT / "unittest.txt").open("x", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AnalysisTests))
    summary = dict(schema="C-017.E2-analysis-audit/1", evidence_kind="synthetic", tests_run=result.testsRun,
                   failures=len(result.failures), errors=len(result.errors), observations=observations,
                   actual_hardware_operations=0, elapsed_seconds=time.monotonic() - began,
                   frozen_sources_unchanged=all(sha(ROOT / path) == value for path, value in expected.items()))
    save("summary.json", summary)
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), elapsed_seconds=summary["elapsed_seconds"],
                    exit_code=0 if result.wasSuccessful() else 1,
                    status="passed" if result.wasSuccessful() else "findings_reproduced")
    save("RUN_MANIFEST.json", manifest)
    output_bytes = sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file())
    if output_bytes > 104857600 or summary["elapsed_seconds"] > 60:
        raise RuntimeError("C budget exceeded; stop")
    print(json.dumps({"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
                      "elapsed_seconds": summary["elapsed_seconds"], "output_bytes": output_bytes,
                      "sources_unchanged": summary["frozen_sources_unchanged"]}))
    return manifest["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
