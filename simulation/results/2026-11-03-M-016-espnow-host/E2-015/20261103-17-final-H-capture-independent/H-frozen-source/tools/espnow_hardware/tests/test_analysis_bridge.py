"""Real frozen golden -> real H Capture -> frozen E2 API. All file fixtures synthetic."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tools.espnow_hardware import hardware_tool as h
from tools.espnow_hardware import analysis_bridge as bridge


class AnalysisIntegrationTests(unittest.TestCase):
    def test_own_capture_context_binds_run_log_hash_and_coverage(self):
        # This test uses only H code and the already frozen E1 golden, not E2.
        with self.fixture() as (output, plan, result, capture, by_id, runtime):
            context = bridge.capture_context(plan, result, capture, by_id, runtime)
            self.assertEqual(context["run_id"], plan["run_id"])
            self.assertEqual(context["task_id"], "H-001")
            self.assertEqual(context["status"], "hardware_capture_unanalyzed")
            self.assertEqual(context["raw_logs"][0]["sha256"], h.sha(capture.path))
            self.assertEqual(context["log_sha256"], {str(capture.path.resolve()): h.sha(capture.path)})
            self.assertTrue(context["receiver_log_complete"])
            self.assertEqual(context["measurement_duration_us"], 1_000_000)
        with self.fixture(malformed=True) as (_, plan, result, capture, by_id, runtime):
            self.assertFalse(bridge.capture_context(plan, result, capture, by_id, runtime)["receiver_log_complete"])

    @contextlib.contextmanager
    def fixture(self, *, omit_source=False, malformed=False, count=1, receiver_delta=1, fail_stop=False, window=True, hardware_outer=False):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            output = Path(temp) / "synthetic-fixture"
            output.mkdir()
            source, destination = "00:00:00:00:00:01", "00:00:00:00:00:05"
            boots = {"board1": "00000064", "board2": "00000068"}
            by_id = {"board1": {"node_id": source}, "board2": {"node_id": destination}}
            plan = {"run_id": "chain", "device_ids": ["board1", "board2"], "sender_id": "board1", "receiver_id": "board2", "count": count}
            capture = h.Capture(output, evidence_kind="hardware_serial" if hardware_outer else "synthetic")
            lines = (h.ROOT / "firmware/agent_native/golden/serial-v1.jsonl").read_bytes().splitlines()
            for raw in lines:
                row = h.parse_event(raw)
                if row.get("run_id") != "chain":
                    continue
                if omit_source and row["node_id"] == source:
                    continue
                capture.record("board1" if row["node_id"] == source else "board2", "device_rx", raw)
            if malformed:
                capture.record("board2", "device_rx", b'{"schema":"ann.serial.v1","schema":"ann.serial.v1",bad}')
            capture.close()
            infos = [{"id": key, "info": {"boot_id": boot, "chip": "host-synthetic"}} for key, boot in boots.items()]
            result = {"status": "stop_unconfirmed" if fail_stop else "hardware_capture_unanalyzed", "probes": infos,
                      "cleanup_errors": [], "stop_attempts": [{"id": key, "acknowledged": not fail_stop} for key in boots]}
            baseline = {key: {"boot_id": boot, "event_overflow": 0, "queue_overflow": 0, "delivered": 0} for key, boot in boots.items()}
            final = {key: {**stats, "delivered": receiver_delta if key == "board2" else 0} for key, stats in baseline.items()}
            runtime = {"baseline_stats": baseline, "final_stats": final,
                       "window_start_ns": 1_000_000_000 if window else None, "window_end_ns": 2_000_000_000 if window else None}
            h.write_json(output / "measurements.json", h.measurement_ledger())
            yield output, plan, result, capture, by_id, runtime

    def test_actual_C_golden_H_envelope_E2_API_interop_stays_synthetic(self):
        with self.fixture() as (output, plan, result, capture, by_id, runtime):
            baseline_hash = h.sha(output / "measurements.json")
            imported = bridge.finalize_capture(h.ROOT, output, plan, result, capture, by_id, runtime)
            analysis = h.read_json(output / "synthetic/analysis.json")
            self.assertEqual(analysis["evidence_kind"], "synthetic")
            self.assertEqual(analysis["pdr"], 1)
            self.assertEqual(analysis["goodput_bps"], 88)
            self.assertIsNone(analysis["rtt_p95_ms"])
            self.assertEqual(imported["measurement_update"]["status"], "synthetic_or_unknown_not_imported")
            self.assertFalse((output / "measurement_updates.jsonl").exists())
            self.assertEqual(h.sha(output / "measurements.json"), baseline_hash)
            context = output / "capture_context.json"
            self.assertEqual(analysis["source_manifests"][0]["sha256"], h.sha(context))
            self.assertEqual(analysis["source_logs"][0]["sha256"], h.sha(capture.path))

    def test_synthetic_C_events_cannot_be_promoted_by_hardware_envelope(self):
        with self.fixture(hardware_outer=True) as args:
            with self.assertRaisesRegex(ValueError, "synthetic"):
                bridge.finalize_capture(h.ROOT, *args)
            self.assertFalse((args[0] / "measurement_updates.jsonl").exists())

    def test_v2_rejects_wrong_run_missing_mapping_and_changed_log_before_metrics(self):
        for fault in ("missing_run", "wrong_run", "missing_map", "wrong_hash", "changed_log"):
            with self.subTest(fault=fault), self.fixture(hardware_outer=True) as (output, plan, result, capture, by_id, runtime):
                context = bridge.capture_context(plan, result, capture, by_id, runtime)
                if fault == "missing_run":
                    del context["run_id"]
                elif fault == "wrong_run":
                    context["run_id"] = "other-run"
                elif fault == "missing_map":
                    del context["log_sha256"]
                elif fault == "wrong_hash":
                    context["log_sha256"][str(capture.path.resolve())] = "0" * 64
                elif fault == "changed_log":
                    with capture.path.open("a", encoding="utf-8") as stream:
                        stream.write("mutated after capture hash\n")
                context_path = output / "counterfeit-context.json"
                config_path = output / "counterfeit-config.json"
                h.write_json(context_path, context)
                h.write_json(config_path, {"run_id": "chain", "source_node_id": by_id["board1"]["node_id"],
                             "destination_id": by_id["board2"]["node_id"], "mode": "reliable", "evidence_kind": "hardware_measured",
                             "expected_generated": 1, "receiver_log_complete": True, "measurement_duration_us": 1_000_000,
                             "duration_clock": "host_monotonic_controlled_window"})
                analyzer, _ = bridge.load_analyzer(h.ROOT)
                with self.assertRaisesRegex(ValueError, "same-run|log_sha256"):
                    analyzer.analyze_files(config_path, [capture.path], [context_path])
                self.assertFalse((output / "measurement_updates.jsonl").exists())

    def test_missing_source_malformed_log_count_and_counter_mismatch_keep_pdr_null(self):
        for change in ({"omit_source": True}, {"malformed": True}, {"count": 2}, {"receiver_delta": 2}):
            with self.subTest(change=change), self.fixture(**change) as args:
                bridge.finalize_capture(h.ROOT, *args)
                analysis = h.read_json(args[0] / "synthetic/analysis.json")
                self.assertIsNone(analysis["pdr"])
                self.assertIsNone(analysis["goodput_bps"])
                self.assertFalse((args[0] / "measurement_updates.jsonl").exists())

    def test_missing_real_window_does_not_invent_goodput(self):
        with self.fixture(window=False) as args:
            bridge.finalize_capture(h.ROOT, *args)
            analysis = h.read_json(args[0] / "synthetic/analysis.json")
            self.assertEqual(analysis["pdr"], 1)
            self.assertIsNone(analysis["goodput_bps"])
            self.assertEqual(analysis["metric_status"]["goodput_bps"]["reason"], "measured_window_missing_or_wrong_clock")

    def test_failed_stop_saves_context_and_never_analyzes_or_imports(self):
        with self.fixture(fail_stop=True) as args:
            status = bridge.finalize_capture(h.ROOT, *args)
            self.assertEqual(status["status"], "capture_failed_not_analyzed")
            self.assertFalse(h.read_json(args[0] / "capture_context.json")["receiver_log_complete"])
            self.assertFalse((args[0] / "synthetic").exists())
            self.assertFalse((args[0] / "measurement_updates.jsonl").exists())

    def test_missing_log_and_analyzer_drift_fail_without_measurement(self):
        with self.fixture() as args:
            args[3].path.unlink()
            with self.assertRaises(FileNotFoundError):
                bridge.finalize_capture(h.ROOT, *args)
            self.assertFalse((args[0] / "measurement_updates.jsonl").exists())
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            frozen = h.read_json(h.ROOT / "coordination/reviews/M-016-verification.json")["frozen"]["E2_analyzer_v2"]
            for name in frozen:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(h.ROOT / name, target)
            (root / "coordination/reviews").mkdir(parents=True)
            h.write_json(root / "coordination/reviews/M-016-verification.json", {"active_freezes": {"E2_analyzer": "E2_analyzer_v2"}, "frozen": {"E2_analyzer_v2": frozen}})
            (root / "tests/espnow/analyze_logs.py").write_text("raise AssertionError('must never execute')", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "drift"):
                bridge.load_analyzer(root)

    def test_hardware_append_branch_only_in_memory_and_unknowns_stay_null(self):
        # No fake measured file is exported. Exercise the positive branch in memory.
        analysis = {"schema": "ann.analysis.v1", "run_id": "memory-only", "mode": "reliable", "evidence_kind": "hardware_measured", "issues": [], "generated_unique": 1,
                    "pdr": 0, "goodput_bps": 0, "rtt_p95_ms": None,
                    "metric_status": {"pdr": {"status": "calculated"}, "goodput_bps": {"status": "calculated"}},
                    "source_logs": [], "source_manifests": [], "source_config": {}, "analyzer_sha256": "counterfactual-branch-test"}
        context = {"evidence_kind": "hardware_measured", "receiver_log_complete": True, "expected_generated": 1, "run_id": "memory-only"}
        class MemoryFile(io.StringIO):
            def __exit__(self, *args):
                return False
        memory = MemoryFile()
        with patch.object(Path, "open", return_value=memory), patch.object(h, "sha", return_value="in-memory-fixture"):
            status = bridge.append_measurements(Path("memory-only"), analysis, Path("analysis.json"), context)
        self.assertEqual(status["status"], "appended")
        update = json.loads(memory.getvalue())
        self.assertEqual(update["metrics"]["pdr"]["value"], 0)
        self.assertIsNone(update["metrics"]["range_m"]["value"])
        self.assertIsNone(update["metrics"]["rf_retries"]["value"])
        self.assertIsNone(update["metrics"]["airtime_s"]["value"])
        memory.close()


if __name__ == "__main__":
    unittest.main()
