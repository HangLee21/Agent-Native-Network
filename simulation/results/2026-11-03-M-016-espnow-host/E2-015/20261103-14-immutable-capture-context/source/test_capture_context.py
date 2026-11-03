"""Use completed actual-C v4 logs with an immutable context manifest, H format."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from analyze_logs import analyze_files

ROOT=Path(__file__).resolve().parents[2]


class ImmutableCaptureContextTests(unittest.TestCase):
    def test_completed_C_v4_sources_and_context_hash_survive_analysis(self):
        source=ROOT/"simulation/outputs/E2-015/20261103-13-final-core-contract"
        out=Path(os.environ["E2_TEST_OUTPUT"])
        raw=source/"telemetry.jsonl";config=source/"actual-C-log-config.json"
        wrapped=out/"H-format-v4-capture.jsonl"
        rows=[json.loads(s) for s in raw.read_text(encoding="utf-8").splitlines()]
        wrapped.write_text("\n".join(json.dumps(dict(direction="device_rx",event=r,evidence_kind="synthetic",raw=json.dumps(r))) for r in rows if r.get("schema")=="ann.serial.v1")+"\n",encoding="utf-8")
        context=out/"CAPTURE_CONTEXT.json"
        data=dict(schema="ann.capture.context.v1",task_id="E2-015",run_id=out.name,status="synthetic_capture_complete",evidence_kind="synthetic",
                  source_core_manifest=str(source/"manifest.json"),
                  source_core_manifest_sha256=hashlib.sha256((source/"manifest.json").read_bytes()).hexdigest(),
                  source_core_build_sha256=hashlib.sha256((source/"core_build.json").read_bytes()).hexdigest(),
                  log_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [raw,wrapped]},
                  limitation="virtual host test clock/window, not hardware PDR/RTT/goodput")
        context.write_text(json.dumps(data,indent=2)+"\n",encoding="utf-8");before=context.read_bytes()
        a=analyze_files(config,[raw],[context]);b=analyze_files(config,[wrapped],[context])
        self.assertEqual(context.read_bytes(),before)
        self.assertEqual(a["source_manifests"][0]["sha256"],hashlib.sha256(before).hexdigest())
        self.assertEqual(a["pdr"],b["pdr"])
        self.assertEqual(a["pdr"],1)
        self.assertEqual(a["successful_same_boot_rtt_count"],1)
        self.assertEqual(a["evidence_kind"],"synthetic")
        self.assertIsNone(a["airtime_us"])
        self.assertIsNone(a["range_m"])
        (out/"actual-C-v4-analysis.json").write_text(json.dumps(a,indent=2)+"\n",encoding="utf-8")
        (out/"H-envelope-v4-analysis.json").write_text(json.dumps(b,indent=2)+"\n",encoding="utf-8")
