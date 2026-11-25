"""E2 independent frozen H Capture -> API checks; no ports, all synthetic."""
import hashlib
import importlib.util
from importlib import import_module
import json
import os
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
ANCHOR="2e7ada3487c8e202c764680bc93b7ae6e3e4c5a420b5d2aff88643d7a7838d56"
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open("x",encoding="utf-8") as stream:json.dump(value,stream,indent=2);stream.write("\n")


class MemoryInput:
    """A finite byte buffer; never a serial adapter."""
    def __init__(self,data):self.data=data
    @property
    def in_waiting(self):return len(self.data)
    def read(self,count):
        value=self.data[:min(count,37)];self.data=self.data[len(value):];return value


class FinalCaptureIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ["E2_TEST_OUTPUT"])
        freeze=ROOT/"simulation/outputs/H-001/20261103-20-final-h-freeze/freeze.json"
        if sha(freeze)!=ANCHOR:raise RuntimeError("H freeze anchor changed; stop")
        cls.frozen=json.loads(freeze.read_text("utf-8"))["source_hashes"]
        if len(cls.frozen)!=12 or any(sha(ROOT/n)!=h for n,h in cls.frozen.items()):
            raise RuntimeError("H final source drift; stop")
        registry=json.loads((ROOT/"coordination/reviews/M-016-verification.json").read_text("utf-8-sig"))
        cls.api=registry["frozen"]["E2_analyzer_v2"]
        if registry["active_freezes"].get("H")!="H_capture_v5" or registry["active_freezes"].get("E2_analyzer")!="E2_analyzer_v2":
            raise RuntimeError("M active freezes changed; stop")
        if any(sha(ROOT/n)!=h for n,h in cls.api.items()):raise RuntimeError("API drift; stop")
        snapshot=cls.out/"H-frozen-source"
        for name in cls.frozen:
            target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        shutil.copyfile(freeze,cls.out/"H-freeze.json")
        folder=snapshot/"tools/espnow_hardware"
        spec=importlib.util.spec_from_file_location("e2_h_final",folder/"__init__.py",submodule_search_locations=[str(folder)])
        package=importlib.util.module_from_spec(spec);sys.modules[spec.name]=package;spec.loader.exec_module(package)
        cls.h=import_module("e2_h_final.hardware_tool")
        cls.bridge=import_module("e2_h_final.analysis_bridge")
        cls.guard1=patch.object(cls.h,"enumerate_ports",side_effect=AssertionError("real enumeration prohibited"));cls.guard1.start()
        cls.guard2=patch.object(cls.h,"open_bound",side_effect=AssertionError("real serial prohibited"));cls.guard2.start()
        source=ROOT/"simulation/outputs/E2-015/20261103-13-final-core-contract"
        index=json.loads((ROOT/"tests/espnow/RUN_INDEX.json").read_text("utf-8"))
        record=next(r for r in index["runs"] if r["run_id"]==source.name)
        if sha(source/"manifest.json")!=record["manifest_sha256"]:raise RuntimeError("completed C source manifest changed")
        cls.raw=cls.out/"actual-v4-C-telemetry.jsonl";shutil.copyfile(source/"telemetry.jsonl",cls.raw)
        save(cls.out/"integration_inputs.json",dict(evidence_kind="synthetic",H_freeze_sha256=ANCHOR,H_source_hashes=cls.frozen,
             E2_analyzer_hashes=cls.api,source_C_manifest_sha256=sha(source/"manifest.json"),source_C_build_sha256=sha(source/"core_build.json"),
             raw_C_trace_sha256=sha(cls.raw),actual_C_compiled_this_run=False,source_run=source.name,
             limits="synthetic counters/window; no current C compilation, physical serial or RF"))

    @classmethod
    def tearDownClass(cls):
        cls.guard2.stop();cls.guard1.stop()
        if any(sha(ROOT/n)!=h for n,h in cls.frozen.items()) or any(sha(ROOT/n)!=h for n,h in cls.api.items()):
            raise AssertionError("frozen input changed during integration")

    def fixture(self,name,*,outer="synthetic",fault=None):
        output=self.out/name;output.mkdir()
        capture=self.h.Capture(output,evidence_kind=outer)
        try:
            for raw in self.raw.read_bytes().splitlines():
                row=self.h.parse_event(raw)
                if not row:continue
                device="board"+str(int(row["node_id"].split(":")[-1],16))
                port=MemoryInput(raw+b"\n")
                while port.in_waiting:capture.poll(device,port)
            if fault=="malformed":capture.record("board5","device_rx",b'{"schema":"ann.serial.v1",bad}')
            if fault=="partial":capture.poll("board5",MemoryInput(b'{"schema":'))
            if fault=="boot":capture.observed_boots["board5"].add("different-boot")
        finally:capture.close()
        self.assertTrue(capture.stream.closed)
        devices=sorted(capture.observed_boots)
        by_id={d:{"node_id":"00:00:00:00:00:"+f"{int(d[5:]):02x}"} for d in devices}
        infos=[dict(id=d,info=dict(boot_id=f"{99+int(d[5:]):08x}",chip="host-synthetic")) for d in devices]
        plan=dict(run_id="E2-echo",device_ids=devices,sender_id="board1",receiver_id="board5",count=1)
        result=dict(status="hardware_capture_unanalyzed",probes=infos,cleanup_errors=[],stop_attempts=[dict(id=d,acknowledged=True) for d in devices])
        baseline={p["id"]:dict(boot_id=p["info"]["boot_id"],delivered=0,event_overflow=0,queue_overflow=0) for p in infos}
        final={d:dict(s,delivered=len(capture.unique_rx.get(d,set()))) for d,s in baseline.items()}
        runtime=dict(baseline_stats=baseline,final_stats=final,window_start_ns=1_000_000_000,window_end_ns=2_000_000_000)
        if fault=="counter":runtime["final_stats"]["board5"]["delivered"]+=1
        if fault=="overflow":runtime["final_stats"]["board5"]["event_overflow"]=1
        if fault=="stop":result["status"]="stop_unconfirmed";result["stop_attempts"][0]["acknowledged"]=False
        if fault=="window":runtime["window_end_ns"]=None
        self.h.write_json(output/"measurements.json",self.h.measurement_ledger())
        return output,plan,result,capture,by_id,runtime

    def finalize(self,args):return self.bridge.finalize_capture(ROOT,*args)

    def assert_no_measurement(self,args):
        self.assertFalse((args[0]/"measurement_updates.jsonl").exists())
        self.assertTrue(all(x["value"] is None and x["source"] is None for x in self.h.read_json(args[0]/"measurements.json")["metrics"].values()))

    def test_actual_capture_poll_v4_C_to_API_preserves_sources_and_null_hardware(self):
        args=self.fixture("positive");before=sha(args[0]/"measurements.json")
        outcome=self.finalize(args);analysis=self.h.read_json(outcome["analysis"])
        self.assertEqual(analysis["evidence_kind"],"synthetic")
        self.assertEqual((analysis["generated_unique"],analysis["destination_unique_rx_observed"],analysis["successful_same_boot_rtt_count"]),(1,1,1))
        self.assertEqual(analysis["pdr"],1);self.assertIsNone(analysis["driver_accepted"])
        self.assertTrue(analysis["link_callbacks_success"]>0)
        for key in ("range_m","one_way_delay_ms","rf_retry_count","airtime_us"):self.assertIsNone(analysis[key])
        context=args[0]/"capture_context.json"
        self.assertEqual(analysis["source_manifests"][0]["sha256"],sha(context))
        self.assertEqual(analysis["source_logs"][0]["sha256"],sha(args[3].path))
        self.assertEqual(self.h.read_json(context)["log_sha256"],{str(args[3].path.resolve()):sha(args[3].path)})
        self.assertEqual(before,sha(args[0]/"measurements.json"));self.assert_no_measurement(args)
        self.assertEqual(outcome["measurement_update"]["status"],"synthetic_or_unknown_not_imported")

    def test_capture_integrity_faults_keep_delivery_unknown(self):
        for fault in ("malformed","partial","boot","counter","overflow"):
            with self.subTest(fault=fault):
                args=self.fixture("coverage-"+fault,fault=fault);outcome=self.finalize(args)
                analysis=self.h.read_json(outcome["analysis"]);context=self.h.read_json(outcome["context"])
                self.assertFalse(context["receiver_log_complete"]);self.assertTrue(context["coverage_reasons"])
                self.assertIsNone(analysis["pdr"]);self.assertIsNone(analysis["goodput_bps"])
                self.assert_no_measurement(args)

    def test_missing_window_keeps_goodput_unknown(self):
        args=self.fixture("missing-window",fault="window");outcome=self.finalize(args)
        analysis=self.h.read_json(outcome["analysis"])
        self.assertEqual(analysis["pdr"],1);self.assertIsNone(analysis["goodput_bps"]);self.assert_no_measurement(args)

    def test_unconfirmed_stop_saves_context_without_analysis(self):
        args=self.fixture("unconfirmed-stop",fault="stop");outcome=self.finalize(args)
        self.assertEqual(outcome["status"],"capture_failed_not_analyzed")
        self.assertFalse((args[0]/"synthetic").exists());self.assert_no_measurement(args)

    def test_hardware_envelope_cannot_promote_actual_synthetic_C(self):
        args=self.fixture("no-promotion",outer="hardware_serial")
        with self.assertRaisesRegex(ValueError,"synthetic"):self.finalize(args)
        self.assert_no_measurement(args)

    def test_actual_capture_context_wrong_run_and_log_hash_are_rejected(self):
        for fault in ("run","hash"):
            with self.subTest(fault=fault):
                args=self.fixture("provenance-"+fault,outer="hardware_serial")
                context=self.bridge.capture_context(*args[1:]);config={k:context[k] for k in ("run_id","source_node_id","destination_id","evidence_kind","receiver_log_complete","measurement_duration_us","duration_clock")};config["mode"]="reliable"
                if fault=="run":context["run_id"]="other-run"
                else:context["log_sha256"][str(args[3].path.resolve())]="0"*64
                cp=args[0]/"wrong-context.json";cfg=args[0]/"config.json";save(cp,context);save(cfg,config)
                analyzer,_=self.bridge.load_analyzer(ROOT)
                with self.assertRaisesRegex(ValueError,"same-run|log_sha256"):analyzer.analyze_files(cfg,[args[3].path],[cp])
                self.assert_no_measurement(args)
