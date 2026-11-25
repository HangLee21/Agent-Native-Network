"""Causal isolation/arrival/budget checks, no model weights or network calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
import unittest
from unittest.mock import patch

from .common import OUTPUT_ROOT, complete_run, new_run
from .model_backend import SmolVLMBackend
from .runtime import BudgetStop, FixtureBackend, Runtime, encode, parse_action, sha, write_json


def nodes():
    return {"a": {"a:img": {"kind": "private_text", "text": "LOCAL_A_秘密"}},
            "b": {"b:img": {"kind": "private_text", "text": "PRIVATE_B_远端"}},
            "c": {"c:img": {"kind": "private_text", "text": "PRIVATE_C_不可见"}}}


class CausalChecks(unittest.TestCase):
    scratch = None
    def runtime(self, scripts=None, **kwargs):
        return Runtime(nodes(), FixtureBackend(scripts or {}), **kwargs)

    def exchange(self):
        return self.runtime({
            "a": [dict(tool="request", peer="b", query="请返回本地证据", deadline_s=2),
                  dict(tool="consume", message_id="m000002"),
                  dict(tool="finish", answer="received", evidence_refs=["m000002"])],
            "b": [dict(tool="respond", request_id="m000001", body="PRIVATE_B_远端", evidence_refs=["b:img"])]})

    def test_private_contexts_never_share_inputs(self):
        r = self.runtime()
        encoded = encode(r.context("a"))
        self.assertNotIn(b"PRIVATE_B", encoded)
        self.assertNotIn(b"PRIVATE_C", encoded)
        self.assertNotIn("c:img", r.visible_evidence("a"))

    def test_context_mutation_cannot_change_runtime(self):
        class Mutating:
            label = FixtureBackend.label
            def decide(self, node_id, context):
                context["private_and_arrived_evidence"]["a:img"]["text"] = "changed"
                return encode(dict(tool="finish", answer="ok", evidence_refs=["a:img"])).decode()
        original = nodes()
        r = Runtime(original, Mutating())
        original["a"]["a:img"]["text"] = "outside changed"
        r.call("a")
        self.assertEqual(r.nodes["a"]["a:img"]["text"], "LOCAL_A_秘密")

    def test_complete_arrival_boundary(self):
        r = self.exchange()
        r.call("a")
        with self.assertRaises(ValueError):
            r.apply("b", dict(tool="respond", request_id="m000001", body="x", evidence_refs=["b:img"]), "test")
        r.deliver_until(0.249)
        self.assertEqual(r.inboxes["b"], [])
        r.deliver_until(0.25)
        self.assertEqual(r.inboxes["b"], ["m000001"])
        r.call("b")
        self.assertNotIn(b"PRIVATE_B", encode(r.context("a")))
        with self.assertRaises(ValueError):
            r.apply("a", dict(tool="consume", message_id="m000002"), "test")
        r.deliver_until(0.5)
        self.assertIn(b"PRIVATE_B", encode(r.context("a")))
        self.assertNotIn(b"PRIVATE_B", encode(r.context("c")))

    def test_consumption_chain_and_unique_consumption(self):
        r = self.exchange()
        r.call("a"); r.deliver_until(.25); r.call("b"); r.deliver_until(.5)
        r.call("a"); r.call("a")
        events = {e["event_id"]: e for e in r.events}
        consumed = next(e for e in r.events if e["kind"] == "consumed")
        kinds = [events[parent]["kind"] for parent in consumed["parent_event_ids"]]
        self.assertEqual(kinds, ["call_finished", "arrived_complete"])
        with self.assertRaises(ValueError):
            r.apply("a", dict(tool="consume", message_id="m000002"), "test")
        self.assertEqual(r.summary()["consumed"], 1)

    def test_illegal_reference_preserves_failure_and_raw_output(self):
        raw = dict(tool="finish", answer="invalid", evidence_refs=["b:img"])
        r = self.runtime({"a": [raw]})
        with self.assertRaisesRegex(ValueError, "unavailable"):
            r.call("a")
        self.assertEqual(r.status, "failed")
        event = r.events[-1]
        self.assertEqual(event["kind"], "tool_or_backend_failed")
        self.assertEqual(json.loads(event["details"]["raw_output"]), raw)

    def test_call_budget_stops_before_backend(self):
        r = self.runtime(max_calls=0)
        with self.assertRaises(BudgetStop):
            r.call("a")
        self.assertEqual(r.calls, 0)
        self.assertEqual(r.events[-1]["details"]["reason"], "model_or_fixture_calls")

    def test_wire_budget_stops_without_partial_message(self):
        r = self.exchange()
        r.max_wire_bytes = 1
        with self.assertRaises(BudgetStop):
            r.call("a")
        self.assertEqual(r.messages, {})
        self.assertEqual(r.wire_bytes, 0)
        self.assertFalse(any(e["kind"] == "sent" for e in r.events))

    def test_wall_budget_stops(self):
        r = self.runtime(max_wall_s=1)
        r.started = time.monotonic() - 2
        with self.assertRaises(BudgetStop):
            r.call("a")
        self.assertEqual(r.calls, 0)

    def test_utf8_serialized_bytes_and_hash_match(self):
        r = self.exchange()
        r.call("a")
        raw = r.messages["m000001"]["raw"]
        generated = next(e for e in r.events if e["kind"] == "generated")["details"]
        self.assertEqual(len(raw), generated["payload_bytes"])
        self.assertEqual(sha(raw), generated["payload_sha256"])
        self.assertGreater(len(raw), len(raw.decode("utf-8")))

    def test_expiry_never_exposes_remote_body(self):
        r = self.runtime({"a": [dict(tool="request", peer="b", query="x", deadline_s=.1)]})
        r.call("a"); r.deliver_until(.25)
        self.assertEqual(r.inboxes["b"], [])
        self.assertEqual(r.events[-1]["kind"], "expired")

    def test_invalid_json_no_scripted_repair(self):
        for raw in ('not json', '[]', '{"tool":"no-such-tool"}',
                    '{"tool":"finish","answer":"x","evidence_refs":[],"hidden":1}',
                    '{"tool":"request","peer":"b","query":"x","deadline_s":true}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parse_action(raw)

    def test_schema_and_parent_causality(self):
        r = self.exchange()
        r.call("a"); r.deliver_until(.25); r.call("b"); r.deliver_until(.5); r.call("a")
        schema = json.loads(Path(__file__).with_name("event_schema.json").read_text(encoding="utf-8"))
        previous = set()
        for event in r.events:
            self.assertEqual(set(event), set(schema["required"]))
            self.assertIn(event["kind"], schema["properties"]["kind"]["enum"])
            self.assertTrue(set(event["parent_event_ids"]).issubset(previous))
            previous.add(event["event_id"])
        self.assertEqual(r.summary()["actual_model_forwards"], 0)

    def test_received_evidence_requires_explicit_consumption_before_finish(self):
        r = self.exchange()
        r.call("a"); r.deliver_until(.25); r.call("b"); r.deliver_until(.5)
        with self.assertRaisesRegex(ValueError, "explicitly consume"):
            r.apply("a", dict(tool="finish", answer="x", evidence_refs=["m000002"]), "test")

    def test_output_scope_and_existing_dir_refused(self):
        with self.assertRaises(ValueError):
            new_run(OUTPUT_ROOT.parent / "other-task", "test", {})
        with self.assertRaises(ValueError):
            new_run(OUTPUT_ROOT, "test", {})  # OUTPUT_ROOT itself is also forbidden.

    def test_model_failure_never_substitutes_fixture(self):
        import subprocess
        directory = self.scratch / "model-failure"
        directory.mkdir()
        backend = SmolVLMBackend("unused-python", "unused-model", "0" * 40, directory, "unused-worker")
        with patch("subprocess.run", return_value=subprocess.CompletedProcess([], 7)):
            with self.assertRaisesRegex(RuntimeError, "model call failed"):
                backend.decide("a", self.runtime().context("a"))
        self.assertEqual(backend.label, "smolvlm_local_model")
        self.assertEqual(backend.attempts, 1)
        self.assertEqual(backend.forward_started, 0)
        process = json.loads((directory / "call-01/process.json").read_text(encoding="utf-8"))
        self.assertEqual(process["exit_code"], 7)

    def test_model_timeout_saved_and_invocation_capped(self):
        import subprocess
        directory = self.scratch / "model-timeout"
        directory.mkdir()
        backend = SmolVLMBackend("unused-python", "unused-model", "0" * 40, directory, "unused-worker")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("stub", 180)):
            with self.assertRaises(RuntimeError):
                backend.decide("a", self.runtime().context("a"))
        process = json.loads((directory / "call-01/process.json").read_text(encoding="utf-8"))
        self.assertTrue(process["timed_out"])
        backend.attempts = 4
        with self.assertRaisesRegex(RuntimeError, "budget exhausted"):
            backend.decide("a", self.runtime().context("a"))
        self.assertFalse((directory / "call-02").exists())


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    args = p.parse_args()
    out, manifest = new_run(args.output, "offline_causal_checks", dict(model_forwards=0, wall_s=30))
    CausalChecks.scratch = out / "scratch"
    CausalChecks.scratch.mkdir()
    # Refusal of an existing run must leave its manifest unchanged.
    initial = (out / "manifest.json").read_bytes()
    try:
        new_run(out, "test", {})
    except FileExistsError:
        pass
    else:
        raise AssertionError("existing run accepted")
    assert (out / "manifest.json").read_bytes() == initial
    with (out / "checks.txt").open("w", encoding="utf-8") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CausalChecks))
    details = dict(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   successful=result.wasSuccessful(), actual_model_forwards=0)
    write_json(out / "result.json", details)
    complete_run(out, manifest, "passed" if result.wasSuccessful() else "failed", 0 if result.wasSuccessful() else 1,
                 backend="fixture_scripted_not_model", actual_model_forwards=0)
    print(encode(details).decode())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
