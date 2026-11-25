"""Independent checks of M-frozen H code; never enumerate/open real devices."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from analyze_logs import validate_measurement_record

OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[1]


class FrozenHTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("E2_RUN_FROZEN_H") != "1":
            raise unittest.SkipTest("H v2 tests frozen; H currently active, await M complete refreeze")
        frozen=json.loads((OWN/"frozen_inputs.json").read_text(encoding="utf-8"))["files"]
        for name,expected in frozen.items():
            if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=expected:
                raise RuntimeError("M-frozen dependency changed: "+name)
        spec=importlib.util.spec_from_file_location("e2_frozen_h",ROOT/"tools/espnow_hardware/hardware_tool.py")
        cls.h=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.h)

    def test_real_profile_does_not_assert_board_or_measurement(self):
        profile=json.loads((ROOT/"hardware/eora_hub_400tb/profile.json").read_text(encoding="utf-8"))
        self.assertFalse(profile["physical_board_verified"])
        self.assertFalse(profile["status"]["hardware_available"])
        self.assertFalse(profile["serial"]["default_open"])
        self.assertEqual(profile["identity"]["board"],"unverified")
        self.assertIsNone(profile["transport"]["channel"])

    def test_actual_examples_have_no_binding_and_disarmed_plan(self):
        bindings=json.loads((ROOT/"hardware/eora_hub_400tb/bindings.example.json").read_text(encoding="utf-8"))
        plan=json.loads((ROOT/"hardware/eora_hub_400tb/bench.example.json").read_text(encoding="utf-8"))
        self.assertEqual(self.h.bindings_from(bindings),[])
        self.assertFalse(plan["armed"])
        with self.assertRaises(ValueError):self.h.validate_plan(plan,[])

    def test_actual_default_measurement_factory_is_all_null(self):
        ledger=self.h.measurement_ledger()
        self.assertEqual(ledger["evidence_kind"],"not_measured")
        self.assertEqual(set(ledger["metrics"]),set(self.h.METRICS))
        for datum in ledger["metrics"].values():
            self.assertIsNone(datum["value"]);self.assertIsNone(datum["source"])
            self.assertEqual(datum["status"],"not_measured")
            self.assertEqual(datum["reason"],"hardware_not_available")
        flat=dict(status="not_measured",reason="hardware_not_available",source=None,
                  **{k:ledger["metrics"][k]["value"] for k in ["range_m","pdr","goodput_bps","rtt_p95_ms"]})
        validate_measurement_record(flat)

    def test_host_synthetic_info_cannot_register_as_board(self):
        binding={"node_id":"02:00:00:00:00:01"}
        info=dict(schema="ann.serial.v1",event="info",nonce="n",firmware="ann-espnow",protocol=1,
                  node_id=binding["node_id"],chip="host-synthetic",mode="idle",boot_id="b",build_id="test",board="unverified")
        with self.assertRaises(ValueError):self.h.validate_info(info,"n",binding)

    def test_probe_cannot_accept_just_usb_match(self):
        binding=dict(id="fixture",port="COM9",node_id="02:00:00:00:00:01",allow_probe=True,
                     physically_confirmed=False,binding_basis="USB CH340 label",vid=1,pid=2,serial_number="fake")
        with self.assertRaises(ValueError):self.h.bindings_from(dict(schema="ann.hardware.bindings.v1",bindings=[binding]))

    def test_wrong_os_identity_rejected_before_open(self):
        binding=dict(port="COM9",allow_probe=True,vid=1,pid=2,serial_number="fixture")
        with self.assertRaises(ValueError):self.h.resolve_binding(binding,{"ports":[dict(device="COM9",vid=1,pid=2,serial_number="other")]})

    def test_mocked_default_entry_never_opens_or_fills_measurements(self):
        # E2 output only. H ROOT/OS enumeration/Git are replaced for this fixture.
        with tempfile.TemporaryDirectory(dir=os.environ["E2_TEST_OUTPUT"],prefix="H-fixture-") as temp:
            root=Path(temp); (root/"coordination/templates").mkdir(parents=True)
            (root/"coordination/templates/RUN_MANIFEST.json").write_text("{}",encoding="utf-8")
            config=root/"bindings.json";config.write_text('{"schema":"ann.hardware.bindings.v1","bindings":[]}',encoding="utf-8")
            output=root/"simulation/outputs/H-001/synthetic-once"
            inventory=dict(status="enumerated",ports=[dict(device="COM9",description="CH340")],board_identity="unverified")
            with patch.object(self.h,"ROOT",root),patch.object(self.h,"enumerate_ports",return_value=inventory) as enumeration, \
                 patch.object(self.h,"open_bound",side_effect=AssertionError("physical serial forbidden")) as opened, \
                 patch.object(self.h.subprocess,"run",return_value=SimpleNamespace(stdout="frozen-test-base")), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.h.main(["--once","--bindings",str(config),"--output",str(output)]),0)
            enumeration.assert_called_once();opened.assert_not_called()
            check=json.loads((output/"check.json").read_text(encoding="utf-8"))
            self.assertEqual(check["status"],"waiting_hardware")
            self.assertFalse(check["bench_started"])
            values=json.loads((output/"measurements.json").read_text(encoding="utf-8"))
            self.assertTrue(all(v["value"] is None and v["source"] is None for v in values["metrics"].values()))

    def test_task_output_root_mismatch_rejected_before_enumeration(self):
        with patch.object(self.h,"enumerate_ports",side_effect=AssertionError("must reject first")), \
             patch.object(self.h,"open_bound",side_effect=AssertionError("must not open")), \
             contextlib.redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):
            self.h.main(["--once","--output",str(ROOT/"simulation/outputs/E2-015/not-H")])
