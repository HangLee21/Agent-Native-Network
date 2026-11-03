"""Finite C-017 H-v2 audit: synthetic ports only; every write stays in this new run."""
import contextlib
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
assert OUT.parent == ROOT / "simulation/outputs/C-017"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def main():
    began = time.monotonic()
    manifest = json.loads((ROOT / "coordination/templates/RUN_MANIFEST.json").read_text("utf-8-sig"))
    manifest.update(template_only=False, task_id="C-017", run_id=OUT.name,
                    started_at=utc_now(), worktree=str(ROOT),
                    git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=2, text=True).strip(),
                    command=[sys.executable, "-B", str(Path(__file__).resolve())],
                    python_executable=sys.executable, process_id=os.getpid(),
                    dependency_snapshot={"python": sys.version, "external_packages": "none used for serial access"},
                    budget={"wall_seconds": 60, "task_cumulative_seconds": 600, "output_bytes": 104857600},
                    output_directory=str(OUT), status="running", evidence_kind="synthetic",
                    review_reference="coordination/reviews/C-017.md",
                    limitations=["No physical ports, OS inventory, H-002 run, RF, model, build or E1 source access",
                                 "Author temporary directories redirected into C-017 only",
                                 "Fake H task roots are nested C-017 fixtures, not live task outputs"])
    expected = json.loads((ROOT / "coordination/reviews/M-016-verification.json").read_text("utf-8-sig"))["frozen"]["H_task_isolation_v2"]
    checked = {name: {"expected": value, "actual": sha(ROOT / name)} for name, value in expected.items()}
    if any(entry["expected"] != entry["actual"] for entry in checked.values()):
        raise RuntimeError("H freeze changed; no tests executed")
    manifest["dirty_files_sha256"] = {name: item["actual"] for name, item in checked.items()}
    manifest["dirty_files_sha256"][str(Path(__file__).resolve().relative_to(ROOT))] = sha(__file__)
    manifest["data_and_weights_sha256"] = {"coordination/tasks/C-017.md": sha(ROOT / "coordination/tasks/C-017.md")}
    save(OUT / "RUN_MANIFEST.started.json", manifest)
    save(OUT / "source_hashes.json", checked)
    fixture_base = OUT / "fixtures"
    fixture_base.mkdir(exist_ok=False)
    real_temporary_directory = tempfile.TemporaryDirectory

    def scoped_temporary_directory(*args, **kwargs):
        kwargs["dir"] = str(fixture_base)
        return real_temporary_directory(*args, **kwargs)

    from tools.espnow_hardware import hardware_tool as h
    spec = importlib.util.spec_from_file_location("c017_h_author_tests", ROOT / "tools/espnow_hardware/tests/test_hardware_tool.py")
    author = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(author)

    observations = {}

    class IndependentRecoveryTests(unittest.TestCase):
        def test_stop_can_reach_an_active_bound_board(self):
            class ActivePort(author.FakePort):
                def write(self, raw):
                    command = json.loads(raw)
                    self.commands.append(command)
                    reply = (dict(author.info(self.b, command["nonce"]), mode="active")
                             if command["cmd"] == "info" else
                             {"schema": h.SCHEMA, "event": command["cmd"], "nonce": command["nonce"]})
                    self.buffer += json.dumps(reply).encode() + b"\n"
                    return len(raw)

            with author.HardwareTests().fake_root() as (root, config, out, bindings):
                port = ActivePort(bindings[0])
                capture_class = h.Capture
                with patch.object(h, "open_bound", return_value=port), \
                     patch.object(h, "Capture", side_effect=lambda target: capture_class(target, evidence_kind="synthetic")), \
                     contextlib.redirect_stdout(io.StringIO()):
                    result = h.main(["--once", "--probe", "--device", "board1", "--command", "stop",
                                     "--bindings", str(config), "--output", str(out)])
                observations["active_stop"] = {
                    "exit_code": result, "commands": [item["cmd"] for item in port.commands],
                    "closed": port.closed, "check": h.read_json(out / "check.json")}
                self.assertEqual(result, 0, "an already active bound board must accept the stop recovery path")
                self.assertIn("stop", observations["active_stop"]["commands"])

        def test_close_failure_preserves_evidence_and_closes_remaining_ports(self):
            class BadClosePort(author.FakePort):
                def close(self):
                    self.closed = True
                    raise OSError("synthetic disconnected-port close failure")

            with author.HardwareTests().fake_root() as (root, config, out, bindings):
                ports = {bindings[0]["id"]: BadClosePort(bindings[0]),
                         bindings[1]["id"]: author.FakePort(bindings[1])}
                capture_class = h.Capture
                captures = []

                def capture_factory(target):
                    capture = capture_class(target, evidence_kind="synthetic")
                    captures.append(capture)
                    return capture

                raised = None
                result = None
                try:
                    with patch.object(h, "open_bound", side_effect=lambda binding, _: ports[binding["id"]]), \
                         patch.object(h, "Capture", side_effect=capture_factory), \
                         contextlib.redirect_stdout(io.StringIO()):
                        result = h.main(["--once", "--probe", "--bindings", str(config), "--output", str(out)])
                except Exception as exc:
                    raised = type(exc).__name__ + ": " + str(exc)
                finally:
                    observations["close_failure"] = {
                        "exception": raised, "exit_code": result,
                        "port_closed": {key: value.closed for key, value in ports.items()},
                        "capture_closed_before_audit_cleanup": [capture.stream.closed for capture in captures],
                        "artifacts": {name: (out / name).exists() for name in
                                      ("inventory.json", "serial.jsonl", "check.json", "measurements.json", "RUN_MANIFEST.json")}}
                    for capture in captures:
                        if not capture.stream.closed:
                            capture.close()
                    for port in ports.values():
                        port.closed = True  # Audit-owned fake cleanup; never call a real serial backend.
                self.assertIsNone(raised, "close failure must be recorded instead of bypassing finalization")
                self.assertTrue(all(observations["close_failure"]["port_closed"].values()))
                self.assertTrue(observations["close_failure"]["artifacts"]["RUN_MANIFEST.json"])

    with (OUT / "unittest.txt").open("x", encoding="utf-8") as test_log, \
         patch.object(tempfile, "TemporaryDirectory", side_effect=scoped_temporary_directory), \
         patch.object(h, "enumerate_ports", side_effect=AssertionError("real inventory prohibited")), \
         patch.object(h, "open_bound", side_effect=AssertionError("real serial open prohibited")):
        author_result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(author))
        independent_result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(IndependentRecoveryTests))
    summary = {
        "schema": "C-017.H-v2-audit/1", "evidence_kind": "synthetic",
        "author_tests": {"run": author_result.testsRun, "failures": len(author_result.failures), "errors": len(author_result.errors)},
        "independent_recovery_tests": {"run": independent_result.testsRun, "failures": len(independent_result.failures), "errors": len(independent_result.errors)},
        "observations": observations,
        "physical_ports_opened": 0, "os_enumerations": 0, "actual_H002_runs": 0,
        "elapsed_seconds": time.monotonic() - began,
    }
    after = {name: sha(ROOT / name) == value for name, value in expected.items()}
    summary["frozen_sources_unchanged_after_tests"] = all(after.values())
    save(OUT / "summary.json", summary)
    manifest.update(finished_at=utc_now(), exit_code=0 if author_result.wasSuccessful() and independent_result.wasSuccessful() else 1,
                    status="passed" if author_result.wasSuccessful() and independent_result.wasSuccessful() else "findings_reproduced",
                    elapsed_seconds=summary["elapsed_seconds"])
    save(OUT / "RUN_MANIFEST.json", manifest)
    output_bytes = sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file())
    if output_bytes > 104857600 or summary["elapsed_seconds"] > 60:
        raise RuntimeError("C-017 budget exceeded; stop")
    print(json.dumps({"author_tests": summary["author_tests"], "independent_tests": summary["independent_recovery_tests"],
                      "elapsed_seconds": summary["elapsed_seconds"], "output_bytes": output_bytes,
                      "sources_unchanged": summary["frozen_sources_unchanged_after_tests"]}))
    return manifest["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
