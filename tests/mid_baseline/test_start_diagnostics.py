"""Portable startup diagnostic regression; no network or running service is touched."""
import contextlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.mid_baseline.gateway_probe import start_frontend


def topology(worker='running', observed=True, state='idle'):
    return {'schema': 'lora.topology.v1', 'source': 'gateway_udp_lrn1',
            'receiver': {'worker_state': worker, 'gateway_observed': observed,
                         'state': state, 'gateway_id': 'gateway', 'frames': 0},
            'reports': [], 'labels': {}}


class StartupDiagnostics(unittest.TestCase):
    def run_start(self, value):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['start_frontend', '--skip-lab', '--no-browser']), \
             patch.object(start_frontend, 'port_open', return_value=True), \
             patch.object(start_frontend, 'http_json', return_value=value), \
             patch.object(start_frontend, 'port_open_on', return_value=True) as probe, \
             patch.object(start_frontend, 'gateway_nic_present', return_value=True) as nic, \
             contextlib.redirect_stdout(output):
            self.assertEqual(start_frontend.main(), 0)
            return output.getvalue(), probe.call_count, nic.call_count

    def test_observed_gateway_without_node_frames(self):
        text, probes, _ = self.run_start(topology())
        self.assertIn('gateway heartbeat is healthy; waiting for new node reports', text)
        self.assertNotIn('gateway reachable but silent', text)
        self.assertNotIn('server_address', text)
        self.assertEqual(probes, 0)

    def test_receiver_failure_has_priority(self):
        for state in ('starting', 'recovering', 'stopped'):
            with self.subTest(worker_state=state):
                text, probes, _ = self.run_start(topology(worker=state, observed=False))
                self.assertIn('receiver health is not ready', text)
                self.assertNotIn('gateway reachable but silent', text)
                self.assertEqual(probes, 0)

    def test_unobserved_gateway_can_show_existing_advice(self):
        text, probes, _ = self.run_start(topology(observed=False))
        self.assertIn('gateway reachable but silent', text)
        self.assertEqual(probes, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
