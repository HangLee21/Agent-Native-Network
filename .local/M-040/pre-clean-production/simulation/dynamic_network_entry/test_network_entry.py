"""Synthetic log fixtures verify the checker, not the wireless model."""
import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("network_entry", Path(__file__).with_name("network_entry.py"))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


def fixture():
    rows = []
    for seq in range(110):
        t = 5 + .5 * seq
        rows += [{"kind": "app_generated", "node": 0, "t_s": t, "seq": seq, "bytes": 512},
                 {"kind": "socket_result", "node": 0, "t_s": t, "seq": seq, "return_bytes": 512}]
    for seq in (0, 80, 81, 82):
        t = 5 + .5 * seq
        rows += [{"kind": "ip_forward", "node": 1, "seq": seq, "t_s": t + .005, "ttl": 63},
                 {"kind": "ip_deliver", "node": 2, "seq": seq, "t_s": t + .01, "ttl": 63},
                 {"kind": "app_rx", "node": 2, "seq": seq, "t_s": t + .01, "bytes": 512, "generated_s": t}]
    for t, category in ((1., "aodv"), (5., "application")):
        rows += [{"kind": "phy_tx", "node": 0, "t_s": t, "frame_bytes": 100, "category": category},
                 {"kind": "phy_tx_interval", "node": 0, "t_s": t, "start_s": t, "duration_s": .001}]
    rows.append({"kind": "simulation_end", "t_s": 60, "node": 0})
    return rows


class LogInvariantTests(unittest.TestCase):
    def test_valid_fixture_conserves_all_110_without_hiding_106_undelivered(self):
        r = entry.analyze_events(fixture(), "dynamic")
        self.assertTrue(r["passed"], r["errors"])
        self.assertEqual(r["not_received_by_stop"], 106)
        self.assertEqual(r["hop_histogram_received"], {2: 4})

    def test_partition_delivery_is_not_allowed_even_with_relay_log(self):
        rows = fixture()
        rows += [{"kind": "ip_forward", "node": 1, "seq": 40, "t_s": 25.01, "ttl": 63},
                 {"kind": "ip_deliver", "node": 2, "seq": 40, "t_s": 25.02, "ttl": 63},
                 {"kind": "app_rx", "node": 2, "seq": 40, "t_s": 25.02, "bytes": 512, "generated_s": 25}]
        self.assertIn("delivery_during_physical_partition", entry.analyze_events(rows, "dynamic")["errors"])

    def test_missing_relay_evidence_fails(self):
        rows = [x for x in fixture() if x["kind"] != "ip_forward"]
        self.assertIn("missing_actual_two_hop_relay_evidence", entry.analyze_events(rows, "dynamic")["errors"])

    def test_no_end_marker_cannot_pass(self):
        self.assertIn("missing_clean_simulation_end", entry.analyze_events(fixture()[:-1], "dynamic")["errors"])

    def test_no_recovery_cannot_pass(self):
        rows = [x for x in fixture() if not (x["kind"] in ("app_rx", "ip_deliver") and x.get("seq", 0) >= 80)]
        self.assertIn("no_three_fresh_recovery_deliveries", entry.analyze_events(rows, "dynamic")["errors"])

    def test_unknown_request_receive_fails(self):
        rows = fixture() + [{"kind": "app_rx", "node": 2, "seq": 999, "t_s": 50, "bytes": 512, "generated_s": 49}]
        self.assertFalse(entry.analyze_events(rows, "dynamic")["passed"])

    def test_missing_source_sequence_fails(self):
        rows = [x for x in fixture() if not (x["kind"] == "app_generated" and x["seq"] == 20)]
        self.assertIn("generated_sequence_not_complete_110", entry.analyze_events(rows, "dynamic")["errors"])

    def test_direct_hop_cannot_claim_two_hops(self):
        rows = copy.deepcopy(fixture())
        for x in rows:
            if x["kind"] == "ip_deliver": x["ttl"] = 64
        self.assertIn("missing_actual_two_hop_relay_evidence", entry.analyze_events(rows, "dynamic")["errors"])

    def test_retry_frames_are_charged_again(self):
        rows = fixture()
        rows += [{"kind": "phy_tx", "node": 0, "t_s": 5.1, "frame_bytes": 100, "category": "application"},
                 {"kind": "phy_tx_interval", "node": 0, "t_s": 5.1, "start_s": 5.1, "duration_s": .001}]
        r = entry.analyze_events(rows, "dynamic")
        self.assertEqual(r["actual_phy_cost_by_category"]["application"]["attempts"], 2)
        self.assertAlmostEqual(r["actual_phy_cost_by_category"]["application"]["airtime_s"], .002)

    def test_unmatched_airtime_does_not_silently_pass(self):
        rows = [x for x in fixture() if x["kind"] != "phy_tx_interval"]
        self.assertIn("unmatched_phy_transmission_interval", entry.analyze_events(rows, "dynamic")["errors"])

    def test_scope_escape_is_rejected(self):
        with self.assertRaises(ValueError): entry.inside(entry.ROOT / "outside", entry.OUTPUTS)

    def test_physical_guard_excludes_direct_and_partition_paths(self):
        self.assertLess(100, entry.CONFIG["wireless"]["range_cutoff_m"])
        self.assertGreater(200, entry.CONFIG["wireless"]["range_cutoff_m"])
        self.assertGreater((100 ** 2 + 400 ** 2) ** .5, entry.CONFIG["wireless"]["range_cutoff_m"])


if __name__ == "__main__":
    unittest.main()
