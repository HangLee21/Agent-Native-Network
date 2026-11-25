"""Causality and fairness checks, not tests asserting shared policies win."""

from dataclasses import replace
import unittest
import json
from pathlib import Path
import tempfile

import numpy as np
import simpy

from simulation.prospecting import (
    Config, LINKS, Link, Network, Observation, load_world, synthetic_world, run_episode,
)


class Receiver:
    node = 1

    def __init__(self):
        self.received = []

    def receive(self, obs):
        self.received.append(obs)


class SimulationTests(unittest.TestCase):
    def test_disconnected_is_local_and_terminal_union_is_fair(self):
        world = synthetic_world(3, Config())
        local, _ = run_episode(world, "local")
        disconnected, _ = run_episode(world, "shared", LINKS["disconnected"])
        self.assertEqual(local["decisions"], disconnected["decisions"])
        self.assertEqual(local["heldout_rmse"], disconnected["heldout_rmse"])
        self.assertEqual(local["samples"], disconnected["samples"])
        self.assertEqual(disconnected["delivered_messages"], 0)
        self.assertEqual(disconnected["undelivered_messages"], disconnected["samples"])

    def test_repeatability_and_budget_and_holdout(self):
        world = synthetic_world(2, Config(budget_s=40))
        first, events = run_episode(world, "shared", LINKS["intermittent"], trace=True)
        second, _ = run_episode(world, "shared", LINKS["intermittent"])
        self.assertEqual(first, second)
        self.assertTrue(all(e["time_s"] <= 40 for e in events))
        for event in events:
            if event["event"] == "sample":
                self.assertFalse(world.holdout[event["site"]])
        self.assertEqual(first["samples"], first["unique_sites"])

    def test_delivery_and_consumption_causality(self):
        _, events = run_episode(synthetic_world(4, Config()), "shared", LINKS["good"], trace=True)
        generated, delivered, consumed = {}, {}, {}
        for event in events:
            if event["event"] == "sample":
                generated[event["oid"]] = event["time_s"]
            elif event["event"] == "deliver":
                self.assertIn(event["oid"], generated)
                self.assertGreaterEqual(event["time_s"], generated[event["oid"]] + 0.02)
                delivered[event["node"], event["oid"]] = event["time_s"]
            elif event["event"] == "consume":
                self.assertLessEqual(delivered[event["node"], event["oid"]], event["time_s"])
                consumed[event["node"], event["oid"]] = event["time_s"]
            elif event["event"] == "decision":
                for oid in event["known_ids"]:
                    if oid // 1_000_000 != event["node"]:
                        self.assertIn((event["node"], oid), consumed)

    def test_contact_and_serialization_exact_time(self):
        env, receiver = simpy.Environment(), Receiver()
        # Payload is 24+4*4 = 40 bytes = 320 bits; needs two 2-second windows.
        link = Link("test", 100, 0.5, 10, 2)
        network = Network(env, link, lambda *args, **kwargs: None)
        obs = Observation(0, 0, 1, 0, np.ones(4, dtype=np.float32))
        network.send(obs, receiver)
        env.run(until=11.69)
        self.assertEqual(receiver.received, [])
        env.run(until=11.71)
        self.assertEqual(len(receiver.received), 1)
        self.assertAlmostEqual(network.delays[0], 11.7)
        self.assertEqual(network.enqueued_bytes, 40)

    def test_partial_service_accounting(self):
        env, receiver = simpy.Environment(), Receiver()
        network = Network(env, Link("slow", 10, 0), lambda *a, **k: None)
        network.send(Observation(0, 0, 1, 0, np.ones(4)), receiver)
        env.run(until=3)
        self.assertEqual(network.served_at(3), 30)
        self.assertFalse(receiver.received)

    def test_static_plan_does_not_read_fine_truth(self):
        world = synthetic_world(7, Config())
        before, _ = run_episode(world, "static")
        world._truth[:] = 0.9  # Adversarial environment change; prior stays fixed.
        after, _ = run_episode(world, "static")
        self.assertEqual(before["decisions"], after["decisions"])
        self.assertNotEqual(before["heldout_rmse"], after["heldout_rmse"])

    def test_no_free_measurements_with_insufficient_budget(self):
        world = synthetic_world(1, Config(budget_s=1))
        for mode, link in (("static", None), ("local", None), ("shared", LINKS["ideal"])):
            result, _ = run_episode(world, mode, link)
            self.assertEqual(result["samples"], 0)
            self.assertEqual(result["heldout_rmse"], result["prior_rmse"])

    def test_perfect_prior_negative_control(self):
        cfg = replace(Config(), prior_block=1, prior_noise_std=0, noise_std=0)
        world = synthetic_world(3, cfg)
        for mode, link in (("static", None), ("local", None), ("shared", LINKS["ideal"])):
            result, _ = run_episode(world, mode, link)
            self.assertEqual(result["prior_rmse"], 0)
            self.assertLess(result["heldout_rmse"], 1e-7)

    def test_payload_is_a_copy(self):
        original = Observation(5, 1, 8, 3.5, np.array([0.1, 0.2, 0.3]))
        decoded = Observation.decode(original.encode())
        self.assertEqual((decoded.oid, decoded.site, decoded.generated_s), (5, 8, 3.5))
        np.testing.assert_allclose(decoded.spectrum, original.spectrum)
        decoded.spectrum[0] = 0.9
        self.assertEqual(original.spectrum[0], 0.1)

    def test_no_delivery_after_episode_deadline(self):
        world = synthetic_world(2, Config(budget_s=20))
        result, events = run_episode(world, "shared", Link("late", 1000, 100), trace=True)
        self.assertGreater(result["samples"], 0)
        self.assertEqual(result["delivered_messages"], 0)
        self.assertEqual(result["samples"], result["undelivered_messages"])
        self.assertFalse(any(e["event"] == "deliver" for e in events))

    def test_external_data_requires_provenance_and_preserves_holdout(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "scene.npz"
            cube = np.full((6, 6, 4), 0.4)
            np.savez(path, cube=cube, provenance=json.dumps({"kind": "test"}))
            with self.assertRaises(ValueError):
                load_world(path, Config(), 0)
            provenance = {
                "kind": "synthetic_test", "source_url": "test-fixture",
                "license_or_access_terms": "generated locally",
                "preprocessing": "constant reflectance",
            }
            np.savez(path, cube=cube, provenance=json.dumps(provenance))
            world = load_world(path, Config(), 0)
            self.assertEqual(world.shape, (6, 6, 4))
            self.assertEqual(len(world.provenance["sha256"]), 64)
            _, events = run_episode(world, "local", trace=True)
            self.assertTrue(all(not world.holdout[e["site"]]
                                for e in events if e["event"] == "sample"))


if __name__ == "__main__":
    unittest.main()
