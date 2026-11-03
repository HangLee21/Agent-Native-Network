"""Compile actual M-frozen C bytes, independently drive them; no firmware flash."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from wire_reference import encode
from analyze_logs import analyze_files

OWN=Path(__file__).resolve().parent
ROOT=OWN.parents[1]


class RealCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output=Path(os.environ["E2_TEST_OUTPUT"])
        frozen=json.loads((OWN/"core_freeze.json").read_text(encoding="utf-8"))
        source_root=ROOT/frozen["core_root"]
        if hashlib.sha256((source_root/"FREEZE.json").read_bytes()).hexdigest()!=frozen["freeze_sha256"]:
            raise RuntimeError("E1 full freeze changed")
        cls.source=cls.output/"E1-frozen-source";cls.source.mkdir()
        for name,expected in frozen["source_hashes"].items():
            data=(source_root/name).read_bytes()
            if hashlib.sha256(data).hexdigest()!=expected:raise RuntimeError("frozen E1 source mismatch: "+name)
            target=cls.source/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        compiler=shutil.which("gcc")
        if not compiler:raise RuntimeError("GCC missing; no compiler installed or fallback result")
        cls.exe=cls.output/"E2-core-driver.exe";cls.host=cls.output/"E1-ann-host.exe"
        include=["-I",str(cls.source/"include"),"-I",str(cls.source/"src")]
        units=[str(cls.source/"src"/n) for n in ["ann.c","ann_console.c","ann_log.c"]]
        commands=[]
        for main,exe in [(OWN/"core_driver.c",cls.exe),(cls.source/"host/main.c",cls.host)]:
            command=[compiler,"-std=c11","-O1","-Wall","-Wextra",*include,*units,str(main),"-o",str(exe)]
            result=subprocess.run(command,capture_output=True,timeout=30)
            (cls.output/(exe.stem+"-compiler.txt")).write_bytes(result.stdout+result.stderr)
            commands.append(dict(command=command,exit_code=result.returncode))
            if result.returncode:raise RuntimeError("actual C compilation failed: "+exe.name)
        version=subprocess.run([compiler,"--version"],capture_output=True,timeout=5)
        build=dict(compiler=compiler,compiler_version=version.stdout.decode("utf-8",errors="replace"),commands=commands,
                   actual_E1_core_compiled=True,frozen_source_sha256=frozen["source_hashes"],
                   binaries_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [cls.exe,cls.host]},
                   ESP_target_compiled=False,real_radio=False)
        (cls.output/"core_build.json").write_text(json.dumps(build,indent=2)+"\n",encoding="utf-8")

    def case(self,name):
        result=subprocess.run([str(self.exe),name],capture_output=True,timeout=10)
        (self.output/(name+".jsonl")).write_bytes(result.stdout)
        (self.output/(name+"-stderr.txt")).write_bytes(result.stderr)
        self.assertEqual(result.returncode,0,result.stderr.decode("utf-8",errors="replace"))
        rows=[json.loads(s) for s in result.stdout.splitlines() if s.startswith(b"{")]
        final=rows[-1];self.assertEqual(final["failures"],0);self.assertFalse(final["radio"])
        return rows

    def test_normal_actual_multihop(self):self.case("normal")
    def test_partition(self):self.case("partition")
    def test_alternate_path(self):self.case("alternate")
    def test_duplicate_data_and_ack_loss(self):self.case("duplicates")
    def test_cancellation(self):self.case("cancel")
    def test_late_ack_after_cancel_does_not_rollback_effect(self):self.case("cancel_late_ack")
    def test_cancelled_locally_queued_data_is_not_sent(self):self.case("cancel_queued_data")
    def test_late_rrep_cannot_underflow_deadline(self):self.case("late_rrep")
    def test_late_ack_cannot_confirm_expired_work(self):self.case("late_ack")
    def test_expiry_before_delivery(self):self.case("expiry")
    def test_source_and_relay_reboot(self):self.case("reboot")
    def test_queue_pending_limits(self):self.case("bounds")
    def test_outbound_and_event_queues_are_bounded(self):self.case("outbound_full")
    def test_state_latest_value_and_expiry(self):self.case("state")
    def test_100_sequential_live_duplicate_replay(self):self.case("continuous100")

    def test_independent_wire_and_C_encode_match(self):
        rows=self.case("wire")
        expected=encode(dict(type=4,ttl=8,path=[1,5],index=1,origin=1,dst=5,boot=100,seq=7,remaining_ms=5000,key=0,kind=1,payload=b"abc"))
        self.assertEqual(rows[0]["wire_hex"],expected.hex())

    def test_actual_log_fixture(self):
        rows=self.case("telemetry")
        config=self.output/"actual-C-log-config.json"
        config.write_text(json.dumps(dict(run_id="E2-echo",source_node_id="00:00:00:00:00:01",destination_id="00:00:00:00:00:05",mode="reliable",evidence_kind="synthetic",receiver_log_complete=True,measurement_duration_us=1000000,duration_clock="receiver_local_window")),encoding="utf-8")
        direct=analyze_files(config,[self.output/"telemetry.jsonl"])
        wrapped=self.output/"H-format-C-log.jsonl"
        wrapped.write_text("\n".join(json.dumps(dict(direction="device_rx",device_id=r.get("node_id"),event=r,evidence_kind="synthetic",raw=json.dumps(r))) for r in rows if r.get("schema")=="ann.serial.v1")+"\n",encoding="utf-8")
        envelope=analyze_files(config,[wrapped])
        for name in ["generated_unique","destination_unique_rx_observed","pdr","goodput_bps","rtt_p95_ms"]:
            self.assertEqual(direct[name],envelope[name])
        self.assertEqual(direct["generated_unique"],1)  # exclude generated reverse echo transaction
        self.assertEqual(direct["pdr"],1)
        self.assertEqual(direct["successful_same_boot_rtt_count"],1)
        self.assertIsNone(direct["range_m"])
        self.assertIsNone(direct["driver_accepted"])  # status0 announces a call, not SDK acceptance
        (self.output/"actual-C-analysis.json").write_text(json.dumps(direct,indent=2)+"\n",encoding="utf-8")
        (self.output/"H-format-C-analysis.json").write_text(json.dumps(envelope,indent=2)+"\n",encoding="utf-8")

    def test_actual_host_serial_interlock_and_line_recovery(self):
        lines=['{"cmd":"info","nonce":"n"}',
               '{"cmd":"start","nonce":"n","run_id":"r"}',
               '{"cmd":"info","cmd":"stop","nonce":"n"}',
               'x'*513,'{"cmd":"info","nonce":"fresh"}']
        result=subprocess.run([str(self.host),"--console"],input=("\n".join(lines)+"\n").encode(),capture_output=True,timeout=5)
        (self.output/"serial-interlock.jsonl").write_bytes(result.stdout)
        self.assertEqual(result.returncode,0,result.stderr)
        rows=[json.loads(s) for s in result.stdout.splitlines()]
        self.assertEqual(rows[0]["chip"],"host-synthetic")
        self.assertEqual(rows[0]["mode"],"idle")
        self.assertEqual(rows[1]["event"],"error")
        self.assertEqual(rows[2]["event"],"error")
        self.assertEqual(rows[3]["event"],"error")
        self.assertEqual(rows[-1]["nonce"],"fresh")
