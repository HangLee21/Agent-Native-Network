"""Independent C probes on byte-matching H display, no hardware actions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]
ANCHOR='2d72ee784757d881a6b77108bf886e5e6e0591934c94693d5baee0330e4da9aa'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

class FrozenDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=Path(os.environ['E2_MID_TEST_OUTPUT']);freeze=ROOT/'firmware/mid_display/FREEZE.json'
        if sha(freeze)!=ANCHOR:raise RuntimeError('H freeze anchor changed; stop')
        cls.f=json.loads(freeze.read_text());cls.hashes={r['path']:r['sha256'] for r in cls.f['files']}
        if any(sha(ROOT/n)!=h for n,h in cls.hashes.items()):raise RuntimeError('H source drift; stop')
        dest=cls.out/'H-frozen-source'
        for name in cls.hashes:
            p=dest/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
            if sha(p)!=cls.hashes[name]:raise RuntimeError('copied source differs; stop')
        shutil.copyfile(freeze,cls.out/'H-FREEZE.json')
        dp=ROOT/'simulation/outputs/D-015/20261106-01-source-freeze';dhash=json.loads((dp/'DOCUMENT_HASHES.json').read_text())
        for name,h in dhash.items():
            source=dp/Path(name).name
            if sha(source)!=h:raise RuntimeError('D frozen checkpoint drift; stop')
            (cls.out/'D-source-checkpoint').mkdir(exist_ok=True);shutil.copyfile(source,cls.out/'D-source-checkpoint'/source.name)
        inputs=dict(H_freeze_sha256=ANCHOR,H_files=cls.hashes,D_document_hashes=dhash,board_sources={},evidence_kind='synthetic',physical_operations=0)
        for name in ['BOARD_INVENTORY_20261106_AB.json','BOARD_LABELS_20261106_AB.json']:
            p=ROOT/'hardware/mid_baseline'/name;inputs['board_sources'][name]=sha(p);shutil.copyfile(p,cls.out/name)
        (cls.out/'frozen_inputs.json').write_text(json.dumps(inputs,indent=2)+'\n')
        module=dest/'firmware/mid_display';gcc=shutil.which('gcc')
        if not gcc:raise RuntimeError('existing gcc unavailable; no install')
        common=[gcc,'-std=c11','-Wall','-Wextra','-Werror','-I'+str(module/'include'),'-I'+str(module/'src')]
        sources=[str(module/'src/mid_display_model.c'),str(module/'src/mid_display_render.c')]
        cls.model=cls.out/'e2_model.exe';cls.backend=cls.out/'e2_backend.exe';records=[]
        commands=[common+sources+[str(Path(__file__).with_name('display_model_probe.c')),'-o',str(cls.model)],common+['-I'+str(module/'tests/fakes')]+sources+[str(module/'src/mid_display_idf.c'),str(Path(__file__).with_name('display_fault_probe.c')),'-o',str(cls.backend)]]
        for i,command in enumerate(commands):
            p=subprocess.run(command,capture_output=True,timeout=30)
            (cls.out/f'compile-{i}.stdout').write_bytes(p.stdout);(cls.out/f'compile-{i}.stderr').write_bytes(p.stderr)
            records.append(dict(command=command,exit_code=p.returncode))
            (cls.out/'display_build.json').write_text(json.dumps(dict(commands=records,compiler=gcc,evidence_kind='synthetic',ESP_target_build=False),indent=2)+'\n')
            if p.returncode:raise RuntimeError('independent host compile failed; see output')
        (cls.out/'display_binaries.json').write_text(json.dumps({str(p):sha(p) for p in [cls.model,cls.backend]},indent=2)+'\n')

    @classmethod
    def tearDownClass(cls):
        if any(sha(ROOT/n)!=h for n,h in cls.hashes.items()):raise RuntimeError('frozen H changed during probes')

    def probe(self,binary,n):
        p=subprocess.run([str(binary),str(n)],capture_output=True,timeout=5)
        (self.out/f'{binary.stem}-{n}.stdout').write_bytes(p.stdout);(self.out/f'{binary.stem}-{n}.stderr').write_bytes(p.stderr)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'))

    def test_mid_command_link_and_local_receiver_semantics(self):self.probe(self.model,0)
    def test_old_callback_ann_confirmation_and_clock_rejection(self):self.probe(self.model,1)
    def test_unknown_refs_configuration_and_latched_fault(self):self.probe(self.model,2)
    def test_renderer_does_not_change_protocol_snapshot_or_overrun_frame(self):self.probe(self.model,3)
    def test_allocation_task_probe_and_frame_fault_boundaries(self):
        for n in range(5):
            with self.subTest(fault=n):self.probe(self.backend,n)
