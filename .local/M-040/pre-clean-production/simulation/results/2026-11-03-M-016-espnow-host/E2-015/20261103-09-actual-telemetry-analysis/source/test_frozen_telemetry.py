"""Actual C-produced v3 logs retained by E2, no read of active firmware/H code."""
import json
import os
from pathlib import Path
import unittest
from analyze_logs import analyze_files

ROOT=Path(__file__).resolve().parents[2]


class FrozenTelemetryTests(unittest.TestCase):
    def test_actual_C_log_and_H_envelope(self):
        old=ROOT/"simulation/outputs/E2-015/20261103-08-v3-regression-and-telemetry"
        output=Path(os.environ["E2_TEST_OUTPUT"])
        raw=old/"telemetry.jsonl";config=old/"actual-C-log-config.json"
        rows=[json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
        wrapped=output/"actual-C-H-envelope.jsonl"
        wrapped.write_text("\n".join(json.dumps(dict(direction="device_rx",event=r,evidence_kind="synthetic",raw=json.dumps(r))) for r in rows if r.get("schema")=="ann.serial.v1")+"\n",encoding="utf-8")
        a=analyze_files(config,[raw],[old/"manifest.json"])
        b=analyze_files(config,[wrapped],[old/"manifest.json"])
        for name in ["pdr","goodput_bps","rtt_p95_ms","generated_unique","destination_unique_rx_observed"]:
            self.assertEqual(a[name],b[name])
        self.assertEqual(a["generated_unique"],1)
        self.assertEqual(a["pdr"],1)
        self.assertEqual(a["goodput_bps"],128)
        self.assertEqual(a["successful_same_boot_rtt_count"],1)
        self.assertIsNone(a["driver_accepted"])
        self.assertTrue(a["link_callbacks_success"]>0)
        self.assertTrue(a["clock_order_warnings"])
        self.assertIsNone(a["range_m"])
        self.assertEqual(a["evidence_kind"],"synthetic")
        (output/"actual-C-analysis.json").write_text(json.dumps(a,indent=2)+"\n",encoding="utf-8")
        (output/"actual-C-H-analysis.json").write_text(json.dumps(b,indent=2)+"\n",encoding="utf-8")
