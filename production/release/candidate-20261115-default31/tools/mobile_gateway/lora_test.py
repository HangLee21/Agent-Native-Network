"""Synthetic projection/clock tests; never open a physical port."""
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

from tools.mid_edge.lora import decoder
from .lora import LoRaTopology
from .server import ROOT


class ProjectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.clock = [100.0]
        with patch('threading.Thread.start'):
            self.view = LoRaTopology(self.directory.name, {'90:da:72:48:a4:f8':'A'}, lambda:self.clock[0])
        line = (ROOT/'firmware/mid_baseline/field_agent/lora_ref/samples/serial_rx.json').read_text()
        self.event = decoder().decode_serial_line(line)
        self.event['gateway_id'] = '90:da:72:48:a4:f8'
        self.view.begin_session()

    def tearDown(self):
        self.view.journal.close()
        self.directory.cleanup()

    def test_duplicate_and_reordered_reports_do_not_renew_clock(self):
        self.view.ingest(self.event)
        self.clock[0] += 10
        self.view.ingest(copy.deepcopy(self.event))
        older = copy.deepcopy(self.event)
        older['report']['report_seq'] -= 1
        self.view.ingest(older)
        result = self.view.snapshot()
        self.assertEqual(result['reports'][0]['pc_receive_age_ms'], 10000)
        self.assertEqual(result['receiver']['duplicates'], 2)
        self.assertFalse(result['renew_wifi_mutual'])
        self.assertEqual(result['reports'][0]['report']['snapshot_at_ms'], self.event['report']['snapshot_at_ms'])

    def test_new_gateway_boot_clears_other_reporters(self):
        self.view.ingest(self.event)
        other = copy.deepcopy(self.event)
        other['report']['observer_id'] = '90:da:72:48:a6:98'
        other['gateway_boot'] += 1
        self.view.ingest(other)
        self.assertEqual(len(self.view.snapshot()['reports']), 1)
        self.view.ingest(self.event)
        self.assertEqual(len(self.view.snapshot()['reports']), 1)

    def test_observer_boot_retires_old_boot(self):
        self.view.ingest(self.event)
        rebooted = copy.deepcopy(self.event)
        rebooted['report']['observer_boot'] += 1
        rebooted['report']['report_seq'] = 1
        self.view.ingest(rebooted)
        self.clock[0] += 5
        self.view.ingest(self.event)
        row = self.view.snapshot()['reports'][0]
        self.assertEqual(row['report']['observer_boot'], rebooted['report']['observer_boot'])
        self.assertEqual(row['pc_receive_age_ms'], 5000)

    def test_status_does_not_activate_reader_and_reconnect_is_empty(self):
        self.view.snapshot(touch=False)
        self.assertFalse(self.view.active())
        self.view.ingest(self.event)
        previous = self.view.snapshot()['receiver']['reader_session']
        self.clock[0] += 26
        self.assertEqual(self.view.snapshot(touch=False)['receiver']['state'], 'stale')
        self.assertFalse(self.view.active())
        self.view.begin_session()
        current = self.view.snapshot(touch=False)
        self.assertNotEqual(current['receiver']['reader_session'], previous)
        self.assertEqual(current['reports'], [])
        self.assertIsNone(current['receiver']['last_rx_age_ms'])


if __name__ == '__main__':
    unittest.main()

