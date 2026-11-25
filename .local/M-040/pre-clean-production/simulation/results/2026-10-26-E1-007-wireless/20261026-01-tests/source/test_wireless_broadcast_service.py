"""Bounded service-only semantic checks; --output must be a new directory."""
import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import sys
import unittest

from wireless_broadcast_service import WirelessBroadcastService, US_PER_MODEL, ppdu_duration_us

EVIDENCE = []


def time_us(value):
    return value / US_PER_MODEL


def state(source=0, seq=1, generated=0):
    return json.dumps(dict(kind="self_state", source=source, generated_at=generated,
        state=dict(source=source, seq=seq, mode="idle", target=-1)), sort_keys=True).encode()


def scene(source=0, task=1, version=1):
    return json.dumps(dict(kind="task_scene", source=source, generated_at=0,
        scene=dict(task=task, phase="open", workers=[], witnesses=[source],
                   version=[0, 0, source, version], observed_at=0)), sort_keys=True).encode()


def draw(source, count=1, seed=0):
    raw = hashlib.sha256(f"E1-007|{seed}|{source}|{count}".encode()).digest()
    return int.from_bytes(raw[:8], "big") % 16


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.services = []

    def service(self, **kwargs):
        service = WirelessBroadcastService(**kwargs)
        self.services.append(service)
        return service

    def tearDown(self):
        EVIDENCE.append(dict(test=self.id(), services=[dict(ledger=s.ledger, final_stats=s.stats(s._now))
                                                       for s in self.services]))

    def drain(self, service):
        deliveries = []
        for _ in range(200):
            when = service.next_event_time()
            if when == math.inf:
                return deliveries
            deliveries.extend(service.pop_due(when))
        self.fail("event loop did not drain")

    def test_01_ppdu_formula(self):
        self.assertEqual(ppdu_duration_us(0), 112)
        self.assertEqual(ppdu_duration_us(100), 244)
        self.assertEqual(ppdu_duration_us(1472), 2072)
        with self.assertRaises(ValueError):
            ppdu_duration_us(1473)

    def test_02_full_arrival_and_no_future_cost(self):
        s = self.service()
        s.submit(0, 0, [1, 2, 1], "data", b"a" * 100)
        start = 34 + 9 * draw(0)
        end = start + 244
        self.assertEqual(s.stats(time_us(start - .1))["airtime_attempt_us"], 0)
        self.assertEqual(s.pop_due(time_us(end - .1)), [])
        self.assertEqual(s.stats(time_us(end - .1))["airtime_attempt_us"], 243)
        due = s.pop_due(time_us(end))
        self.assertEqual([d["recipient"] for d in due], [1, 2])
        self.assertEqual(s.stats(time_us(end))["channel_busy_us"], 244)
        self.assertEqual(s.pop_due(time_us(end)), [])

    def test_03_simultaneous_unequal_collision(self):
        pair = next((a, b) for a in range(20) for b in range(a + 1, 20) if draw(a) == draw(b))
        a, b = pair
        s = self.service()
        s.submit(0, a, [99], "data", b"a")
        s.submit(0, b, [99], "data", b"b" * 100)
        start = 34 + 9 * draw(a)
        partial = s.stats(time_us(start + 50))
        self.assertEqual(partial["airtime_attempt_us"], 100)
        self.assertEqual(partial["channel_busy_us"], 50)
        self.assertEqual(self.drain(s), [])
        stats = s.stats(s._now)
        self.assertEqual(stats["collided"], 2)
        self.assertEqual(stats["airtime_attempt_us"], ppdu_duration_us(1) + 244)
        self.assertEqual(stats["channel_busy_us"], 244)
        self.assertEqual(stats["buffer_occupied_bytes"], 0)

    def test_04_busy_freezes_remaining_slots(self):
        a, b = next((a, b) for a in range(20) for b in range(20) if draw(a) < draw(b))
        s = self.service()
        s.submit(0, a, [99], "data", b"a")
        s.submit(0, b, [99], "data", b"b")
        self.drain(s)
        starts = [e for e in s.ledger if e["event"] == "tx_started"]
        self.assertEqual(starts[1]["time_us"], starts[0]["finish_us"] + 34 + 9 * (draw(b) - draw(a)))
        frozen = next(e for e in s.ledger if e["event"] == "backoff_frozen")
        self.assertEqual(frozen["remaining_slots"], draw(b) - draw(a))

    def test_05_arrival_while_busy(self):
        s = self.service()
        s.submit(0, 0, [9], "data", b"x" * 100)
        start = 34 + 9 * draw(0)
        s.submit(time_us(start + 20), 1, [9], "data", b"y")
        self.drain(s)
        starts = [e for e in s.ledger if e["event"] == "tx_started"]
        self.assertEqual(starts[1]["time_us"], start + 244 + 34 + draw(1) * 9)

    def test_06_submicro_arrival_and_roundtrip(self):
        s = self.service()
        s.submit(time_us(.1), 0, [9], "data", b"x")
        submitted = s.ledger[0]
        self.assertEqual(submitted["eligibility_us"], 1)
        expected_start = 43 + draw(0) * 9
        self.assertEqual(s.next_event_time(), time_us(expected_start))
        self.assertEqual(s.pop_due(s.next_event_time()), [])
        finish = expected_start + ppdu_duration_us(1)
        self.assertEqual(s.pop_due(time_us(finish - .1)), [])
        self.assertEqual(len(s.pop_due(s.next_event_time())), 1)
        self.assertEqual(s.next_event_time(), math.inf)

    def test_07_latest_preserves_head_backoff(self):
        s = self.service(policy="latest_state")
        first = s.submit(0, 0, [1], "self_state", state(seq=1))
        when = s.next_event_time()
        second = s.submit(time_us(1), 0, [1], "self_state", state(seq=2))
        self.assertEqual(s.next_event_time(), when)
        due = self.drain(s)
        self.assertEqual([d["message_id"] for d in due], [second])
        self.assertEqual(s._records[0]["status"], "replaced")
        self.assertEqual(len([e for e in s.ledger if e["event"] == "head_activated"]), 1)
        self.assertNotEqual(first, second)

    def test_08_task_scene_keys_keep_distinct_objects(self):
        s = self.service(policy="latest_state")
        s.submit(0, 0, [1], "task_scene", scene(task=1))
        other = s.submit(0, 0, [1], "task_scene", scene(task=2))
        newer = s.submit(0, 0, [1], "task_scene", scene(task=1, version=2))
        due = self.drain(s)
        self.assertEqual([d["message_id"] for d in due], [newer, other])
        self.assertEqual(s.stats(s._now)["replaced"], 1)

    def test_09_inflight_cannot_be_replaced(self):
        s = self.service(policy="latest_state")
        old = s.submit(0, 0, [1], "self_state", state(seq=1))
        start = s.next_event_time()
        s.pop_due(start)
        new = s.submit(start, 0, [1], "self_state", state(seq=2))
        due = self.drain(s)
        self.assertEqual([d["message_id"] for d in due], [old, new])
        self.assertEqual(s.stats(s._now)["replaced"], 0)

    def test_10_duplicate_stale_conflict_and_refresh(self):
        s = self.service(policy="latest_state")
        body = state(seq=2)
        s.submit(0, 0, [1], "self_state", body)
        s.submit(0, 0, [1], "self_state", body)
        s.submit(0, 0, [1], "self_state", state(seq=1))
        s.submit(0, 0, [1], "self_state", state(seq=2, generated=1))
        self.assertEqual(len(self.drain(s)), 1)
        s.submit(1, 0, [1], "self_state", body)
        due = self.drain(s)
        self.assertEqual(due[0]["information_generated_at"], 0)
        self.assertEqual(due[0]["enqueued_at"], 1)
        stats = s.stats(s._now)
        self.assertEqual(stats["rejection_reasons"], {"stale_version": 1, "same_version_conflict": 1})
        self.assertEqual(stats["coalesced"], 1)
        self.assertGreater(stats["information_age_max"], stats["latency_max"])

    def test_11_capacity_replacement_and_inflight_occupancy(self):
        body = state(seq=1)
        s = self.service(policy="latest_state", capacity_bytes=len(body) + 64)
        s.submit(0, 0, [1], "self_state", body)
        new = s.submit(0, 0, [1], "self_state", state(seq=2))
        s.submit(0, 0, [1], "self_state", state(seq=1000))
        s.pop_due(s.next_event_time())
        s.submit(s._now, 0, [1], "data", b"")
        due = self.drain(s)
        self.assertEqual(due[0]["message_id"], new)
        self.assertEqual(s.stats(s._now)["rejection_reasons"], {"tail_drop_capacity": 2})

    def test_12_frame_limit(self):
        s = self.service()
        s.submit(0, 0, [1], "data", b"a" * 1473)
        s.submit(0, 0, [1], "data", b"b" * 1472)
        self.assertEqual(len(self.drain(s)), 1)
        self.assertEqual(s.stats(s._now)["rejection_reasons"], {"frame_too_large": 1})

    def test_13_fifo_never_replaces(self):
        s = self.service()
        s.submit(0, 0, [1], "self_state", state(seq=2))
        s.submit(0, 0, [1], "self_state", state(seq=1))
        self.assertEqual(len(self.drain(s)), 2)
        self.assertEqual(s.stats(s._now)["replaced"], 0)

    def test_14_long_idle_jumps_and_stats_do_not_consume(self):
        s = self.service()
        s.submit(200, 0, [1], "data", b"x")
        self.assertEqual(len(s.ledger), 3)
        s.stats(201)
        self.assertEqual(s.stats(201)["ready_deliveries"], 1)
        self.assertEqual(len(s.pop_due(s.next_event_time())), 1)
        self.assertLess(len(s.ledger), 10)
        self.assertEqual(s.next_event_time(), math.inf)

    def test_15_validation_and_unknown_schema_fifo(self):
        s = self.service(policy="latest_state")
        with self.assertRaises(TypeError):
            s.submit(0, 0, [1], "data", "text")
        with self.assertRaises(ValueError):
            s.submit(0, 0, [], "data", b"x")
        with self.assertRaises(ValueError):
            s.pop_due(-1)
        s.submit(0, 0, [1], "self_state", b"{}")
        s.submit(0, 0, [1], "self_state", b"{}")
        self.assertEqual(len(self.drain(s)), 2)

    def test_16_source_order_does_not_resolve_collision(self):
        a, b = next((a, b) for a in range(20) for b in range(a + 1, 20) if draw(a) == draw(b))
        results = []
        for order in ((a, b), (b, a)):
            s = self.service()
            for source in order:
                s.submit(0, source, [99], "data", b"x")
            self.drain(s)
            results.append(sorted((e["source"], e["time_us"], e["finish_us"], e["collision"])
                                  for e in s.ledger if e["event"] == "tx_started"))
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    source_dir = out / "source"
    source_dir.mkdir()
    files = [Path(__file__), Path(__file__).with_name("wireless_broadcast_service.py")]
    manifest = dict(command=sys.argv, interpreter=sys.executable, python=sys.version,
                    sources={str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    for path in files:
        shutil.copyfile(path, source_dir / path.name)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ServiceTests))
    log = stream.getvalue()
    (out / "tests.txt").write_text(log, encoding="utf-8")
    (out / "evidence.json").write_text(json.dumps(EVIDENCE, indent=2), encoding="utf-8")
    manifest.update(tests_run=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                    successful=result.wasSuccessful())
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(log)
    sys.exit(0 if result.wasSuccessful() else 1)
