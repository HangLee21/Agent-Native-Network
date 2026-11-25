"""Partial frozen checkpoint core only; current native interface is not consumed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class CandidateCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['E2_MID_TEST_OUTPUT']);p=ROOT/'simulation/outputs/E1-016/20261106-02-checkpoint/FREEZE.json'
        if sha(p)!='d99ef0bd18d2e80fb8fad1050139e749fe8cf800dda4f02753dfcb530edbce41':raise RuntimeError('candidate freeze anchor drift')
        f=json.loads(p.read_text());cls.inputs={n:f['source_hashes'][n] for n in ['firmware/mid_baseline/mid.c','firmware/mid_baseline/mid.h']}
        if any(sha(ROOT/n)!=h for n,h in cls.inputs.items()):raise RuntimeError('candidate core bytes changed; stop branch')
        folder=cls.out/'E1-frozen-core';folder.mkdir()
        for n,h in cls.inputs.items():shutil.copyfile(ROOT/n,folder/Path(n).name)
        shutil.copyfile(p,cls.out/'E1-checkpoint-FREEZE.json')
        gcc=shutil.which('gcc')
        if not gcc:raise RuntimeError('existing gcc missing; no install')
        cls.binary=cls.out/'independent_candidate_core.exe';command=[gcc,'-std=c99','-Wall','-Wextra','-Werror','-pedantic','-I'+str(folder),str(folder/'mid.c'),str(Path(__file__).with_name('candidate_core_probe.c')),'-o',str(cls.binary)]
        result=subprocess.run(command,capture_output=True,timeout=30);(cls.out/'compile.stdout').write_bytes(result.stdout);(cls.out/'compile.stderr').write_bytes(result.stderr)
        (cls.out/'core_build.json').write_text(json.dumps(dict(command=command,exit_code=result.returncode,source_hashes=cls.inputs,binary_sha256=sha(cls.binary) if result.returncode==0 else None,actual_E1_core_compiled=True if result.returncode==0 else False,ESP_target=False,native_interface_consumed=False,limitations='Only checkpoint1 mid.c/mid.h; active INTERFACE changed and was not read.'),indent=2)+'\n')
        if result.returncode:raise RuntimeError('candidate host compile failed')
    @classmethod
    def tearDownClass(cls):
        if any(sha(ROOT/n)!=h for n,h in cls.inputs.items()):raise RuntimeError('candidate source changed during check')
    def check(self,n):
        p=subprocess.run([str(self.binary),str(n)],capture_output=True,timeout=5);(self.out/f'probe-{n}.stdout').write_bytes(p.stdout);(self.out/f'probe-{n}.stderr').write_bytes(p.stderr);self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'))
    def test_twenty_peer_source_destination_pairs(self):self.check(0)
    def test_weight_boundary_and_period_hold(self):self.check(1)
    def test_same_source_two_destinations(self):self.check(2)
    def test_control_identity_and_wire_boundaries(self):self.check(3)
