"""M release selection guards and frozen E1 serial golden preservation."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.espnow_hardware import hardware_tool as h
from tools.espnow_hardware import verify_host as verify


class ReleaseTests(unittest.TestCase):
    @contextlib.contextmanager
    def release_fixture(self, source_name="INTERFACE.md"):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            firmware = root / "firmware/agent_native"
            firmware.mkdir(parents=True)
            (firmware / "INTERFACE.md").write_text("synthetic interface", encoding="utf-8")
            source = firmware / "INTERFACE.md"
            anchor = firmware / "FREEZE.json"
            h.write_json(anchor, {"source_hashes": {source_name: h.sha(source)}})
            version = "E1_full_v3"
            hashes = {"firmware/agent_native/" + source_name: h.sha(source), "firmware/agent_native/FREEZE.json": h.sha(anchor)}
            registry = {"active_freezes": {"E1": version}, "frozen": {version: hashes}}
            (root / "coordination/reviews").mkdir(parents=True)
            (root / "coordination/templates").mkdir(parents=True)
            (root / "coordination/templates/RUN_MANIFEST.json").write_text("{}", encoding="utf-8")
            h.write_json(root / "coordination/reviews/M-016-verification.json", registry)
            with patch.object(verify, "AUTHORIZED_RELEASES", {version: h.sha(anchor)}):
                yield root, registry

    def test_known_active_release_selected_and_every_source_checked(self):
        with self.release_fixture() as (root, _):
            checked = verify.check_active_release(root)
            self.assertEqual(checked["active_key"], "E1_full_v3")
            self.assertEqual(len(checked["checked"]), 2)
            self.assertTrue(all(v["expected"] == v["actual"] for v in checked["checked"].values()))

    def test_unknown_version_missing_selection_and_no_fallback(self):
        for active in (None, "E1_public_interface_v1", "E1_full_v999"):
            with self.subTest(active=active), self.release_fixture() as (root, registry):
                registry["active_freezes"]["E1"] = active
                path = root / "coordination/reviews/M-016-verification.json"
                path.write_text(json.dumps(registry), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "unknown or unapproved"):
                    verify.check_active_release(root)

    def test_source_drift_anchor_drift_and_registry_omission_rejected(self):
        for fault in ("source", "anchor", "registry"):
            with self.subTest(fault=fault), self.release_fixture() as (root, registry):
                if fault == "source":
                    (root / "firmware/agent_native/INTERFACE.md").write_text("changed", encoding="utf-8")
                elif fault == "anchor":
                    (root / "firmware/agent_native/FREEZE.json").write_text("{}", encoding="utf-8")
                else:
                    del registry["frozen"]["E1_full_v3"]["firmware/agent_native/INTERFACE.md"]
                    (root / "coordination/reviews/M-016-verification.json").write_text(json.dumps(registry), encoding="utf-8")
                with self.assertRaises(ValueError):
                    verify.check_active_release(root)

    def test_release_cannot_escape_firmware_root(self):
        with self.release_fixture("../outside.txt") as (root, _):
            with self.assertRaisesRegex(ValueError, "escapes"):
                verify.check_active_release(root)

    def test_guard_failure_persists_manifest_without_running_tests(self):
        with self.release_fixture() as (root, registry):
            registry["active_freezes"]["E1"] = "unapproved"
            (root / "coordination/reviews/M-016-verification.json").write_text(json.dumps(registry), encoding="utf-8")
            out = root / "simulation/outputs/H-001/fixture-guard"
            with patch.object(h, "ROOT", root), patch.object(verify.sys, "argv", ["verify", "--output", str(out)]), \
                 patch.object(verify.subprocess, "run", side_effect=AssertionError("must stop before subprocess")) as run, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(verify.main(), 1)
            run.assert_not_called()
            manifest = h.read_json(out / "RUN_MANIFEST.json")
            self.assertEqual(manifest["status"], "verification_failed")
            self.assertEqual(manifest["exit_code"], 1)
            self.assertIn("unknown or unapproved", manifest["error"])


class GoldenTests(unittest.TestCase):
    def test_frozen_golden_roundtrip_preserves_origin_and_clock_fields(self):
        verify.check_active_release(h.ROOT)
        lines = (h.ROOT / "firmware/agent_native/golden/serial-v1.jsonl").read_bytes().splitlines()
        rows = [h.parse_event(line) for line in lines]
        self.assertTrue(all(rows))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            capture = h.Capture(temp, evidence_kind="synthetic")
            for line, row in zip(lines, rows):
                self.assertEqual(capture.record("fixture", "device_rx", line), row)
            capture.close()
            saved = [json.loads(line)["event"] for line in capture.path.read_text().splitlines()]
            self.assertEqual(saved, rows)
        for row in rows:
            if row["event"] in ("generated", "tx_submit", "tx_result", "frame_rx", "rx", "echo"):
                self.assertIn("origin_boot_id", row)
                self.assertIn("boot_id", row)
            if row["event"] in ("tx_submit", "tx_result"):
                self.assertGreater(row["tx_attempt"], 0)
            if row["event"] == "frame_rx":
                self.assertFalse(row["unique_receive"])
            if row["event"] in ("rx", "echo"):
                self.assertTrue(row["unique_receive"])
        correlation = next(row for row in rows if row["event"] == "echo_correlation")
        for key in ("request_origin_id", "request_boot_id", "request_seq", "same_source_boot"):
            self.assertIn(key, correlation)
        self.assertIsNone(correlation["rtt_ms"])
        self.assertEqual(correlation["evidence_kind"], "synthetic")
        self.assertTrue(all(metric["value"] is None for metric in h.measurement_ledger()["metrics"].values()))

    def test_real_golden_host_identity_never_registers_as_physical_board(self):
        row = h.parse_event((h.ROOT / "firmware/agent_native/golden/serial-v1.jsonl").read_bytes().splitlines()[0])
        self.assertEqual(row["chip"], "host-synthetic")
        with self.assertRaisesRegex(ValueError, "chip"):
            h.validate_info(row, row["nonce"], {"node_id": row["node_id"]})


if __name__ == "__main__":
    unittest.main()
