"""E1-012 task isolation, reservations, and visual/format scoring checks."""
import argparse
import json
from pathlib import Path
import unittest

from .a0_task import TaskLedger, evaluate, prompt_context
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
