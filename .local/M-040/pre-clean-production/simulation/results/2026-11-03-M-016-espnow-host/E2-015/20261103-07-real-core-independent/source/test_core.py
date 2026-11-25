"""Compile actual M-frozen C bytes, independently drive them; no firmware flash."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

from wire_reference import encode

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
    def test_expiry_before_delivery(self):self.case("expiry")
    def test_source_and_relay_reboot(self):self.case("reboot")
    def test_queue_pending_limits(self):self.case("bounds")
    def test_100_sequential_live_duplicate_replay(self):self.case("continuous100")

    def test_independent_wire_and_C_encode_match(self):
        rows=self.case("wire")
        expected=encode(dict(type=4,ttl=8,path=[1,5],index=1,origin=1,dst=5,boot=100,seq=7,remaining_ms=5000,key=0,kind=1,payload=b"abc"))
        self.assertEqual(rows[0]["wire_hex"],expected.hex())

    def test_actual_log_fixture(self):self.case("telemetry")

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
