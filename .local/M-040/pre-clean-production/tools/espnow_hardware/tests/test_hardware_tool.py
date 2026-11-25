"""Synthetic safety and serial-contract tests. No physical ports are opened."""
import contextlib
import io
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.espnow_hardware import hardware_tool as h


def binding(index=1):
    return {"id": f"board{index}", "port": f"COM{index}", "vid": 1, "pid": 2,
            "serial_number": f"fixture-{index}", "node_id": f"02:00:00:00:00:{index:02x}",
            "allow_probe": True, "physically_confirmed": True, "binding_basis": "synthetic fixture"}


def info(b, nonce):
    return {"schema": h.SCHEMA, "event": "info", "nonce": nonce, "firmware": "ann-espnow",
            "protocol": 1, "node_id": b["node_id"], "chip": "esp32s3", "board": "unverified",
            "boot_id": "fixture-boot", "build_id": "fixture-build", "mode": "idle"}


class FakePort:
    def __init__(self, b):
        self.b, self.buffer, self.commands, self.closed = b, b"", [], False

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, size):
        data, self.buffer = self.buffer[:size], self.buffer[size:]
        return data

    def write(self, raw):
        command = json.loads(raw)
        self.commands.append(command)
        response = (info(self.b, command["nonce"]) if command["cmd"] == "info" else
                    {"schema": h.SCHEMA, "event": command["cmd"], "nonce": command["nonce"]})
        self.buffer += b"I IDF: synthetic startup\n" + json.dumps(response).encode() + b"\n"
        return len(raw)

    def close(self):
        self.closed = True


class HardwareTests(unittest.TestCase):
    def test_info_rejects_nonce_identity_protocol_and_busy(self):
        b = binding()
        valid = info(b, "nonce")
        self.assertEqual(h.validate_info(valid, "nonce", b), valid)
        for key, value in (("nonce", "stale"), ("node_id", binding(2)["node_id"]),
                           ("protocol", True), ("mode", "bench"), ("chip", "esp32"), ("build_id", "")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                h.validate_info({**valid, key: value}, "nonce", b)

    def test_no_board_inference_and_identity_mismatch(self):
        b = binding()
        port = {**b, "device": b["port"]}
        self.assertEqual(h.resolve_binding(b, {"ports": [port]}), port)
        for changed in ({"serial_number": "another"}, {"vid": 999}, {"device": "COM99"}):
            with self.assertRaises(ValueError):
                h.resolve_binding(b, {"ports": [{**port, **changed}]})
        with self.assertRaises(ValueError):
            h.resolve_binding({**b, "allow_probe": False}, {"ports": [port]})

    def test_binding_requires_physical_basis_and_unique_nodes(self):
        b = binding()
        config = {"schema": "ann.hardware.bindings.v1", "bindings": [b]}
        self.assertEqual(len(h.bindings_from(config)), 1)
        for candidate in ({**b, "physically_confirmed": False}, {**b, "serial_number": None},
                          {**b, "binding_basis": ""}):
            with self.assertRaises(ValueError):
                h.bindings_from({**config, "bindings": [candidate]})
        with self.assertRaises(ValueError):
            h.bindings_from({**config, "bindings": [b, b]})

    def test_disabled_or_oversized_or_unbounded_bench_rejected(self):
        bs = [binding(1), binding(2)]
        plan = self.plan()
        h.validate_plan(plan, bs)
        for change in ({"armed": False}, {"count": 1001}, {"frame_bytes": 251}, {"frame_bytes": 111}, {"frame_bytes": 119},
                       {"capture_seconds": 46}, {"max_runs": 2}, {"count": 1000, "interval_ms": 1000},
                       {"device_ids": ["board1", "board3"]}, {"echo": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                h.validate_plan({**plan, **change}, bs)

    @staticmethod
    def plan():
        return {"schema": "ann.hardware.bench.v1", "armed": True, "run_id": "fixture-run",
                "device_ids": ["board1", "board2"], "sender_id": "board1", "receiver_id": "board2",
                "count": 1, "interval_ms": 10, "frame_bytes": 128, "echo": True,
                "capture_seconds": 2, "max_runs": 1}

    def test_parser_and_command_boundaries(self):
        self.assertIsNone(h.parse_event(b"I (10) IDF: startup"))
        self.assertIsNone(h.parse_event(b'{"schema":"other"}'))
        self.assertIsNone(h.parse_event(b'[]'))
        self.assertIsNone(h.parse_event(b'{"schema":"other","schema":"ann.serial.v1"}'))
        self.assertIsNone(h.parse_event(b'{"schema":"ann.serial.v1","t_us":NaN}'))
        with self.assertRaises(ValueError):
            h.command_bytes({"cmd": "info", "nonce": "x" * 512})

    def test_oversized_serial_tail_cannot_be_nonce_response(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            cap = h.Capture(temp, evidence_kind="synthetic")
            port = FakePort(binding())
            port.buffer = b"x" * 4100
            self.assertEqual(cap.poll("board1", port), [])
            self.assertEqual(cap.poll("board1", port), [])
            port.buffer = json.dumps(info(binding(), "nonce")).encode() + b"\n"
            self.assertEqual(cap.poll("board1", port), [])
            port.buffer = json.dumps(info(binding(), "fresh")).encode() + b"\n"
            self.assertEqual(cap.poll("board1", port)[0]["nonce"], "fresh")
            cap.close()

    @contextlib.contextmanager
    def fake_root(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            (root / "coordination/templates").mkdir(parents=True)
            (root / "coordination/templates/RUN_MANIFEST.json").write_text("{}", encoding="utf-8")
            # Only the four M-frozen analyzer files, never E2 active tests.
            release = h.read_json(h.ROOT / "coordination/reviews/M-016-verification.json")["frozen"]["E2_analyzer_v2"]
            (root / "coordination/reviews").mkdir(parents=True)
            h.write_json(root / "coordination/reviews/M-016-verification.json", {"active_freezes": {"E2_analyzer": "E2_analyzer_v2"}, "frozen": {"E2_analyzer_v2": release}})
            for name in release:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(h.ROOT / name, target)
            config = root / "bindings.json"
            bs = [binding(1), binding(2)]
            config.write_text(json.dumps({"schema": "ann.hardware.bindings.v1", "bindings": bs}), encoding="utf-8")
            inventory = {"status": "enumerated", "ports": [{**b, "device": b["port"]} for b in bs]}
            out = root / "simulation/outputs/H-001/fixture-run"
            with patch.object(h, "ROOT", root), patch.object(h, "enumerate_ports", return_value=inventory):
                yield root, config, out, bs

    def test_default_once_never_opens_and_keeps_null(self):
        with self.fake_root() as (_, config, out, _), patch.object(h, "open_bound", side_effect=AssertionError("forbidden")) as opened:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--once", "--bindings", str(config), "--output", str(out)]), 0)
            opened.assert_not_called()
            self.assertEqual(h.read_json(out / "check.json")["status"], "waiting_hardware")
            for metric in h.read_json(out / "measurements.json")["metrics"].values():
                self.assertIsNone(metric["value"])
                self.assertEqual(metric["reason"], "hardware_not_available")
            with self.assertRaises(FileExistsError):
                h.main(["--once", "--bindings", str(config), "--output", str(out)])

    def test_armed_fake_bench_captures_all_and_stops(self):
        with self.fake_root() as (root, config, out, bs):
            # Firmware arm compares canonical lower-case node text exactly.
            bs[0]["node_id"] = "AA:BB:CC:DD:EE:01"
            config.write_text(json.dumps({"schema": "ann.hardware.bindings.v1", "bindings": bs}), encoding="utf-8")
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(self.plan()), encoding="utf-8")
            ports = {b["id"]: FakePort(b) for b in bs}
            capture_class = h.Capture
            with patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                 patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--bindings", str(config), "--bench", str(plan_path), "--output", str(out)]), 0)
            self.assertTrue(all(p.closed for p in ports.values()))
            self.assertTrue(all(p.commands[-1]["cmd"] == "stats" for p in ports.values()))
            self.assertEqual(sum(c["cmd"] == "bench" for p in ports.values() for c in p.commands), 1)
            self.assertTrue(all(p.commands[2]["cmd"] == "arm" for p in ports.values()))
            self.assertEqual(ports["board1"].commands[2]["node_id"], bs[0]["node_id"].lower())
            self.assertEqual(ports["board2"].commands[3]["cmd"], "start")
            events = [json.loads(line) for line in (out / "serial.jsonl").read_text().splitlines()]
            self.assertTrue(all(e["evidence_kind"] == "synthetic" for e in events))
            self.assertTrue(all(m["value"] is None for m in h.read_json(out / "measurements.json")["metrics"].values()))

    def test_armed_missing_member_opens_nothing(self):
        with self.fake_root() as (root, config, out, bs):
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(self.plan()), encoding="utf-8")
            inventory = {"status": "enumerated", "ports": [{**bs[0], "device": bs[0]["port"]}]}
            with patch.object(h, "enumerate_ports", return_value=inventory), \
                 patch.object(h, "open_bound", side_effect=AssertionError("must not open")) as opened, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--bindings", str(config), "--bench", str(plan_path), "--output", str(out)]), 1)
            opened.assert_not_called()
            self.assertFalse(h.read_json(out / "check.json")["arm_attempted"])

    def test_failed_arm_stops_every_opened_board_without_bench(self):
        class RejectArm(FakePort):
            def write(self, raw):
                result = super().write(raw)
                command = json.loads(raw)
                if command["cmd"] == "arm":
                    self.buffer = json.dumps({"schema": h.SCHEMA, "event": "error", "nonce": command["nonce"],
                                              "ok": False, "error": "fixture-rejected"}).encode() + b"\n"
                return result
        with self.fake_root() as (root, config, out, bs):
            plan_path = root / "plan.json"
            plan_path.write_text(json.dumps(self.plan()), encoding="utf-8")
            ports = {b["id"]: RejectArm(b) for b in bs}
            capture_class = h.Capture
            with patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                 patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--bindings", str(config), "--bench", str(plan_path), "--output", str(out)]), 1)
            self.assertTrue(all(p.closed and p.commands[-1]["cmd"] == "stop" for p in ports.values()))
            self.assertFalse(any(c["cmd"] == "bench" for p in ports.values() for c in p.commands))

    def test_h002_once_isolated_manifest_and_no_open(self):
        with self.fake_root() as (root, config, _, _), patch.object(h, "open_bound", side_effect=AssertionError("forbidden")) as opened:
            out = root / "simulation/outputs/H-002/fixture-check"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--task-id", "H-002", "--once", "--bindings", str(config), "--output", str(out)]), 0)
            opened.assert_not_called()
            self.assertEqual(h.read_json(out / "RUN_MANIFEST.json")["task_id"], "H-002")
            self.assertEqual(h.read_json(out / "check.json")["status"], "waiting_hardware")
            self.assertTrue(all(v["value"] is None for v in h.read_json(out / "measurements.json")["metrics"].values()))

    def test_h002_probe_uses_info_only(self):
        with self.fake_root() as (root, config, _, bs):
            out = root / "simulation/outputs/H-002/fixture-probe"
            ports = {b["id"]: FakePort(b) for b in bs}
            capture_class = h.Capture
            with patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                 patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--task-id", "H-002", "--once", "--probe", "--bindings", str(config), "--output", str(out)]), 0)
            self.assertTrue(all(p.closed and [c["cmd"] for c in p.commands] == ["info"] for p in ports.values()))
            self.assertEqual(h.read_json(out / "RUN_MANIFEST.json")["task_id"], "H-002")

    def test_h002_rejects_active_and_import_modes_before_any_io(self):
        with self.fake_root() as (root, config, _, _):
            out = root / "simulation/outputs/H-002/rejected"
            base = ["--task-id", "H-002", "--bindings", str(config), "--output", str(out)]
            for flags in ([], ["--once", "--bench", "no-plan.json"], ["--once", "--probe", "--command", "stop", "--device", "board1"],
                          ["--once", "--log", "no-log.jsonl"], ["--once", "--device", "board1"]):
                with self.subTest(flags=flags), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    h.main(base + flags)
                self.assertEqual(caught.exception.code, 2)
                self.assertFalse(out.exists())

    def test_task_id_cannot_write_cross_task_or_outside_repo(self):
        with self.fake_root() as (root, config, out, _):
            for task, path in (("H-002", out), ("H-001", root / "simulation/outputs/H-002/wrong"),
                               ("H-001", root / "outside"), ("H-001", out / "nested"), ("H-003", out)):
                with self.subTest(task=task, path=path), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    h.main(["--task-id", task, "--once", "--bindings", str(config), "--output", str(path)])
                self.assertEqual(caught.exception.code, 2)
                self.assertFalse(path.exists())

    def test_active_stop_preserves_identity_checks_and_sends_stop(self):
        class ActivePort(FakePort):
            def write(self, raw):
                count = super().write(raw)
                if json.loads(raw)["cmd"] == "info":
                    response = info(self.b, json.loads(raw)["nonce"])
                    response["mode"] = "active"
                    self.buffer = json.dumps(response).encode() + b"\n"
                return count
        with self.fake_root() as (_, config, out, bs):
            port = ActivePort(bs[0])
            capture_class = h.Capture
            with patch.object(h, "open_bound", return_value=port), \
                 patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--once", "--probe", "--device", "board1", "--command", "stop", "--bindings", str(config), "--output", str(out)]), 0)
            self.assertEqual([c["cmd"] for c in port.commands], ["info", "stop"])
            self.assertEqual(h.read_json(out / "check.json")["status"], "stopped")

    def test_active_regular_probe_and_bench_still_rejected(self):
        for bench in (False, True):
            with self.subTest(bench=bench), self.fake_root() as (root, config, out, bs):
                ports = {b["id"]: FakePort(b) for b in bs}
                real_validate = h.validate_info
                def active_validate(item, nonce, b, **kwargs):
                    return real_validate({**item, "mode": "active"}, nonce, b, **kwargs)
                plan = root / "plan.json"
                plan.write_text(json.dumps(self.plan()), encoding="utf-8")
                capture_class = h.Capture
                flags = ["--bench", str(plan)] if bench else ["--once", "--probe"]
                with patch.object(h, "validate_info", side_effect=active_validate), \
                     patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                     patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(h.main(flags + ["--bindings", str(config), "--output", str(out)]), 1)
                self.assertFalse(any(c["cmd"] != "info" for p in ports.values() for c in p.commands))

    def test_stop_rejects_bad_identity_nonce_and_wrong_ack(self):
        for fault in ("identity", "nonce", "ack", "timeout"):
            class FaultPort(FakePort):
                def write(self, raw):
                    count = super().write(raw)
                    request = json.loads(raw)
                    if request["cmd"] == "info" and fault in ("identity", "nonce"):
                        response = info(self.b, request["nonce"])
                        response["mode"] = "active"
                        response["node_id" if fault == "identity" else "nonce"] = binding(2)["node_id"] if fault == "identity" else "stale"
                        self.buffer = json.dumps(response).encode() + b"\n"
                    if request["cmd"] == "stop":
                        self.buffer = (json.dumps({"schema": h.SCHEMA, "event": "stats", "nonce": request["nonce"]}).encode() + b"\n") if fault == "ack" else b""
                    return count
            with self.subTest(fault=fault), self.fake_root() as (_, config, out, bs):
                port = FaultPort(bs[0])
                capture_class, wait = h.Capture, h.wait_response
                with patch.object(h, "open_bound", return_value=port), \
                     patch.object(h, "Capture", side_effect=lambda p: capture_class(p, evidence_kind="synthetic")), \
                     patch.object(h, "wait_response", side_effect=lambda d, p, c, n, end: wait(d, p, c, n, min(end, h.time.monotonic() + 0.04))), \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(h.main(["--once", "--probe", "--device", "board1", "--command", "stop", "--bindings", str(config), "--output", str(out)]), 1)
                self.assertEqual(h.read_json(out / "check.json")["status"], "failed")
                self.assertIn("error", h.read_json(out / "check.json"))
                if fault in ("identity", "nonce"):
                    self.assertEqual([c["cmd"] for c in port.commands], ["info"])

    def test_first_port_close_failure_does_not_skip_other_cleanup_or_artifacts(self):
        class CloseFail(FakePort):
            def close(self):
                raise OSError("fixture disconnected while closing")
        with self.fake_root() as (_, config, out, bs):
            ports = {"board1": CloseFail(bs[0]), "board2": FakePort(bs[1])}
            captures, capture_class = [], h.Capture
            def make_capture(path):
                capture = capture_class(path, evidence_kind="synthetic")
                captures.append(capture)
                return capture
            with patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                 patch.object(h, "Capture", side_effect=make_capture), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--once", "--probe", "--bindings", str(config), "--output", str(out)]), 1)
            self.assertTrue(ports["board2"].closed)
            self.assertTrue(captures[0].stream.closed)
            check = h.read_json(out / "check.json")
            self.assertEqual(check["status"], "cleanup_failed")
            self.assertEqual(check["cleanup_errors"][0]["id"], "board1")
            self.assertTrue((out / "measurements.json").is_file())
            self.assertEqual(h.read_json(out / "RUN_MANIFEST.json")["exit_code"], 1)

    def test_capture_close_failure_still_saves_all_artifacts(self):
        with self.fake_root() as (_, config, out, bs):
            ports = {b["id"]: FakePort(b) for b in bs}
            class CloseFailCapture(h.Capture):
                def __init__(self, path):
                    super().__init__(path, evidence_kind="synthetic")
                def close(self):
                    super().close()
                    raise OSError("fixture capture close failure")
            with patch.object(h, "open_bound", side_effect=lambda b, _: ports[b["id"]]), \
                 patch.object(h, "Capture", CloseFailCapture), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(h.main(["--once", "--probe", "--bindings", str(config), "--output", str(out)]), 1)
            self.assertTrue(all(p.closed for p in ports.values()))
            self.assertEqual(h.read_json(out / "check.json")["cleanup_errors"][0]["stage"], "capture_close")
            self.assertTrue((out / "measurements.json").is_file())
            self.assertEqual(h.read_json(out / "RUN_MANIFEST.json")["status"], "cleanup_failed")


if __name__ == "__main__":
    unittest.main()
