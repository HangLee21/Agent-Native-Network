"""E1-012 task isolation, reservations, and visual/format scoring checks."""
import argparse
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import subprocess

from .a0_task import TaskLedger, evaluate, prompt_context, resource_ok, monitored_worker
from .common import ROOT, complete_run, new_run
from .runtime import write_json
from .test_runtime import CausalChecks
from .test_source_identity import SourceIdentityChecks


class TaskChecks(unittest.TestCase):
    scratch = None

    def test_new_scope_cannot_write_old_output(self):
        with self.assertRaises(ValueError):
            new_run(ROOT / "simulation/outputs/E1-010/forbidden-new-run", "unit", {}, task_id="E1-012")

    def test_four_start_cap_survives_restart(self):
        path = self.scratch / "four.jsonl"
        for i in range(4):
            ledger = TaskLedger(path)
            record = ledger.reserve("unit")
            self.assertEqual(record["worker_id"], i + 1)
            ledger.append("worker_finished", worker_id=i + 1, wall_seconds=1, actual_forward_started=False)
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            TaskLedger(path).reserve("unit")

    def test_interrupted_start_charged_without_reset(self):
        path = self.scratch / "interrupted.jsonl"
        TaskLedger(path).reserve("unit")
        state = TaskLedger(path).state()
        self.assertEqual(state["charged_worker_seconds"], 180)
        self.assertEqual(TaskLedger(path).reserve("unit")["worker_id"], 2)

    def test_remaining_total_limits_next_worker(self):
        ledger = TaskLedger(self.scratch / "total.jsonl")
        ledger.reserve("unit")
        ledger.append("worker_finished", worker_id=1, wall_seconds=710, actual_forward_started=True)
        record = ledger.reserve("unit")
        self.assertEqual(record["timeout_s"], 10)
        with self.assertRaises(RuntimeError):
            ledger.reserve("unit")

    def test_max_tokens_enforced(self):
        ledger = TaskLedger(self.scratch / "tokens.jsonl")
        for value in (257, 0, True):
            with self.assertRaises(ValueError):
                ledger.reserve("unit", value)
        self.assertEqual(ledger.state()["worker_starts"], 0)

    def test_prompt_has_no_color_label_or_other_context(self):
        image = dict(path="neutral.png", sha256="x" * 64, width=64, height=64)
        spec = prompt_context("participant-0", image, 0)
        text = spec["prompt"].lower()
        self.assertNotIn("red", text)
        self.assertNotIn("blue", text)
        self.assertNotIn("sha256", json.dumps(spec["context"]))
        self.assertEqual(spec["context"]["visible_evidence_ids"], ["local-image"])

    def test_visual_and_format_grades_separate(self):
        result = evaluate("The image is red.")
        self.assertFalse(result["format_valid"])
        self.assertEqual(result["visual_color"], "red")
        result = evaluate('{"tool":"finish","answer":"blue","evidence_refs":["wrong"]}')
        self.assertTrue(result["format_valid"])
        self.assertFalse(result["legal_reference"])
        self.assertEqual(result["visual_color"], "blue")

    def test_resource_gate_rejects_either_low_memory(self):
        def sample(ram, vram):
            return dict(free_ram_bytes=ram, gpu_query=dict(stdout=f"GPU, 8188 MiB, {vram} MiB, driver"))
        self.assertTrue(resource_ok(sample(2 * 1024 ** 3, 2560)))
        self.assertFalse(resource_ok(sample(2 * 1024 ** 3 - 1, 2560)))
        self.assertFalse(resource_ok(sample(2 * 1024 ** 3, 2559)))
        self.assertFalse(resource_ok({}))
        self.assertTrue(resource_ok(sample(1610612736, 2560), 1610612736))
        self.assertFalse(resource_ok(sample(1610612735, 2560), 1610612736))

    def monitor_case(self, name, reader, timeout=180):
        class Child:
            pid = 123
            killed = False
            ended = False
            waits = 0
            def poll(self):
                return (-9 if self.killed else 0) if self.ended else None
            def kill(self):
                self.killed = True
            def wait(self, timeout):
                self.waits += 1
                if self.killed or self.waits >= 3:
                    self.ended = True
                    return self.poll()
                raise subprocess.TimeoutExpired("unit-child", timeout)
        child = Child()
        times = iter((0, 0.1, 0.3, 0.5, 0.7, 0.9))
        with patch("simulation.edge_agent_entry.a0_task.subprocess.Popen", return_value=child):
            record = monitored_worker(["unit-child"], {}, None, timeout, self.scratch / f"{name}.jsonl",
                                      ram_reader=reader, clock=lambda: next(times))
        self.assertTrue(record["worker_reaped"])
        return child, record

    def test_monitor_kills_and_reaps_only_own_low_ram_child(self):
        values = iter((2 * 1024 ** 3, 512 * 1024 ** 2 - 1))
        child, record = self.monitor_case("low", lambda: next(values))
        self.assertTrue(child.killed)
        self.assertEqual(record["monitor_stop_reason"], "low_system_ram")

    def test_monitor_failure_kills_and_reaps(self):
        def unavailable():
            raise OSError("unit RAM API unavailable")
        child, record = self.monitor_case("unavailable", unavailable)
        self.assertTrue(child.killed)
        self.assertEqual(record["monitor_stop_reason"], "monitor_unavailable")

    def test_monitor_wall_timeout_kills_and_reaps(self):
        child, record = self.monitor_case("timeout", lambda: 2 * 1024 ** 3, 0.2)
        self.assertTrue(child.killed)
        self.assertTrue(record["timed_out"])

    def test_monitor_normal_exit_does_not_kill(self):
        child, record = self.monitor_case("normal", lambda: 2 * 1024 ** 3)
        self.assertFalse(child.killed)
        self.assertIsNone(record["monitor_stop_reason"])

    def test_monitor_protection_stop_blocks_restart(self):
        path = self.scratch / "protected-stop.jsonl"
        ledger = TaskLedger(path)
        ledger.reserve("unit")
        ledger.append("worker_finished", worker_id=1, wall_seconds=1, actual_forward_started=False,
                      monitor_stop_reason="low_system_ram")
        with self.assertRaisesRegex(RuntimeError, "no automatic retry"):
            TaskLedger(path).reserve("unit-resume")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    out, manifest = new_run(args.output, "E1-012_task_scope_regression", dict(model_forwards=0), task_id="E1-012")
    suite = unittest.TestSuite()
    for cls in (TaskChecks, CausalChecks, SourceIdentityChecks):
        cls.scratch = out / cls.__name__
        cls.scratch.mkdir()
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    with (out / "checks.txt").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    record = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                  successful=result.wasSuccessful(), actual_model_forwards=0)
    write_json(out / "result.json", record)
    complete_run(out, manifest, "passed" if result.wasSuccessful() else "failed", 0 if result.wasSuccessful() else 1,
                 actual_model_forwards=0)
    print(json.dumps(record))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
