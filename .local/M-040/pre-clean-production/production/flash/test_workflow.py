"""Fake transports only: no port enumeration, reset or external hardware."""
import tempfile
import unittest
import json
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
import workflow

MAC='90:da:72:48:a4:f8'
NEW='90:da:72:48:a6:98'
FIRMWARE={'firmware':{'partition_table_sha256':'a'*64,'sha256':'b'*64,'build_id':'new-build'}}
CONFIG={'nodes':[{'mac':MAC,'node_id':1}], 'network':{'group':31,'channel':11}}


class FakeBoard:
    def __init__(self, mac=MAC, fault=None, saved=True):
        self.mac,self.fault,self.saved=mac,fault,saved
        self.written=False;self.closed=False;self.num=None;self.commands=[]
    def info(self):
        if self.fault=='disconnect': raise OSError('USB disconnected')
        if self.fault=='identity' and self.written: self.mac=NEW
        return {'node_id':self.mac,'chip':'esp32s3','firmware':'mid-espnow','build_id':'new-build' if self.written else 'old-build','boot_id':8,'discovery_fault':False,'discovery_saved':self.saved,'discovery_autostart':self.saved,'group':31 if self.saved else None,'channel':11,'node_number':self.num,'node_number_source':'unset' if self.num is None else 'nvs'}
    def prepare_rom(self,mac,sha):
        if self.fault=='partition': raise ValueError('分区不一致')
    def flash(self,image): self.written=True;self.write_verified=True
    def command(self,name,**kwargs):
        self.commands.append((name,kwargs))
        if self.fault=='config' and name=='route_config': raise OSError('NVS error')
        if name=='node_id_set': self.num=kwargs['node_number']
        if name=='route_config': self.saved=True
        if name=='node_id_get': return {'node_id':self.mac,'node_number':self.num,'node_number_schema':'node.number.v1'}
        return {}
    def close(self): self.closed=True


class Transport:
    def __init__(self,board): self.board=board
    def ports(self): return ['fake-only']
    def Board(self,port): return self.board
    def location(self,port): return 'fixture-usb-1'


class WorkflowTests(unittest.TestCase):
    def test_summary_keeps_distinct_macs_and_unresolved(self):
        a={'mac':MAC,'port':'COM1','usb_location':'u1','result':'failed'}
        b={'mac':NEW,'port':'COM1','usb_location':'u1','result':'success'}
        rows,ok=workflow.summarize_results([a,b],{})
        self.assertFalse(ok);self.assertEqual(len(rows),2)
        changed=dict(a,result='success',port='COM2',usb_location='u2')
        rows,ok=workflow.summarize_results([a,changed],{})
        self.assertTrue(ok);self.assertEqual(len(rows),1)
        rows,ok=workflow.summarize_results([changed],{'attempt':{'mac':MAC}})
        self.assertFalse(ok);self.assertEqual(rows[0]['result'],'unknown')
        unknown={'port':'COM3','usb_location':'u3','result':'failed'}
        rows,ok=workflow.summarize_results([unknown,b],{})
        self.assertFalse(ok);self.assertEqual(len(rows),2)
        rows,ok=workflow.summarize_results([a,b,changed,dict(b,result='failed')],{})
        self.assertFalse(ok);self.assertEqual(len(rows),2)
        self.assertEqual({r['mac']:r['result'] for r in rows},{MAC:'success',NEW:'failed'})
        rows,ok=workflow.summarize_results([a,changed],{})
        self.assertTrue(ok)
        rows,ok=workflow.summarize_results([dict(unknown,result='failed')],{'x':{'mac':MAC,'node_id':1}})
        self.assertFalse(ok);self.assertEqual(len(rows),2)

    def run_fake(self,board,config=CONFIG):
        with tempfile.TemporaryDirectory() as d:
            registry=Path(d)/'registry.json'
            rows=workflow.execute(Transport(board),config,FIRMWARE,'fixture.bin',registry,lambda *_:None)
            return rows,workflow.load_registry(registry,{r['mac']:r['node_id'] for r in config['nodes']})
    def test_known_board_success_and_id_readback(self):
        b=FakeBoard(); rows,registry=self.run_fake(b)
        self.assertEqual(rows[0]['result'],'success');self.assertEqual(rows[0]['node_id'],1)
        self.assertEqual(registry[MAC],1);self.assertTrue(b.closed)
        call=next(x for x in b.commands if x[0]=='node_id_set')
        self.assertEqual(call[1],{'node_number':1,'target_mac':MAC,'target_boot':8})
        self.assertFalse(rows[0]['power_cycle_verified'])
    def test_new_board_gets_stable_id_and_auto_profile(self):
        b=FakeBoard(NEW,saved=False);rows,registry=self.run_fake(b)
        self.assertEqual(registry[NEW],2);self.assertEqual(rows[0]['result'],'success')
        self.assertIn(('route_config',{'group':31,'channel':11,'autostart':True}),b.commands)
    def test_missing_profile_does_not_write(self):
        b=FakeBoard(NEW,saved=False); rows,_=self.run_fake(b,{'nodes':CONFIG['nodes']})
        self.assertEqual(rows[0]['result'],'failed');self.assertFalse(b.written)
    def test_disconnect_identity_partition_and_config_errors(self):
        for fault in ('disconnect','identity','partition','config'):
            with self.subTest(fault=fault):
                b=FakeBoard(fault=fault,saved=fault!='config');rows,_=self.run_fake(b)
                self.assertEqual(rows[0]['result'],'failed');self.assertTrue(b.closed)
                if fault in ('disconnect','partition'): self.assertFalse(b.written)
                if fault in ('identity','config'): self.assertTrue(b.written)
    def test_registry_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'registry.json';p.write_text('{"schema_version":1,"nodes":[{"mac":"90:da:72:48:a6:98","node_id":1}]}')
            with self.assertRaises(workflow.ProvisionError): workflow.load_registry(p,{MAC:1})

    def test_registry_duplicate_rows_and_cross_file_match(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'registry.json'
            def write(rows): p.write_text(json.dumps({'schema_version':1,'nodes':rows}),encoding='utf-8')
            row={'mac':MAC,'node_id':1}
            write([row]); self.assertEqual(workflow.load_registry(p,{MAC:1})[MAC],1)
            for rows in ([row,row],[row,{'mac':MAC,'node_id':2}],[row,{'mac':NEW,'node_id':1}]):
                write(rows)
                with self.assertRaises(workflow.ProvisionError): workflow.load_registry(p,{})
            p.write_text('{invalid',encoding='utf-8')
            with self.assertRaises(workflow.ProvisionError): workflow.load_registry(p,{})

    def test_interrupted_process_persists_attempt_and_blocks_reflash(self):
        with tempfile.TemporaryDirectory() as d:
            code='''import os,sys,json\nfrom pathlib import Path\nimport workflow\nfrom test_workflow import FakeBoard,Transport,CONFIG,FIRMWARE\nclass Crash(FakeBoard):\n def flash(self,image): os._exit(19)\nd=Path(sys.argv[1]);f=(d/'flash-crash.jsonl').open('x',encoding='utf-8')\ndef rec(x):\n f.write(json.dumps(x)+'\\n');f.flush();os.fsync(f.fileno())\nworkflow.execute(Transport(Crash()),CONFIG,FIRMWARE,'fixture.bin',d/'registry.json',lambda *_:None,rec)'''
            result=subprocess.run([sys.executable,'-c',code,d],cwd=Path(__file__).parent,timeout=10)
            self.assertEqual(result.returncode,19)
            events=[json.loads(line) for line in (Path(d)/'flash-crash.jsonl').read_text().splitlines()]
            self.assertEqual(events[-1]['event'],'write_attempted')
            self.assertTrue(events[-1]['flash_attempted'])
            blocked=workflow.unresolved_writes(d);self.assertEqual(blocked,{MAC})
            board=FakeBoard();result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,blocked_macs=blocked)
            self.assertFalse(board.written);self.assertEqual(result[0]['result'],'failed');self.assertTrue(board.closed)

    def test_write_success_readback_failure_remains_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            records=[];board=FakeBoard(fault='identity')
            result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,lambda e:records.append(json.loads(json.dumps(e))))
            self.assertEqual(result[0]['result'],'failed');self.assertTrue(board.closed)
            p=Path(d)/'flash-test.jsonl';p.write_text(''.join(json.dumps(e)+'\n' for e in records))
            self.assertEqual(workflow.unresolved_writes(d),{MAC})
            self.assertIn('write_completed',[e['event'] for e in records])
            self.assertNotIn('readback_verified',[e['event'] for e in records])

    def test_journal_failure_prevents_write(self):
        with tempfile.TemporaryDirectory() as d:
            board=FakeBoard()
            def record(value):
                if value['event']=='write_attempted': raise OSError('disk full')
            result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,record)
            self.assertEqual(result[0]['result'],'failed');self.assertFalse(board.written);self.assertTrue(board.closed)

    def test_incomplete_journal_tail_keeps_durable_attempt(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'flash-01.jsonl'
            attempt={'event':'write_attempted','mac':MAC,'attempt_id':'a','target':{}}
            path.write_text(json.dumps(attempt)+'\n'+ '{"event":"readback_',encoding='utf-8')
            self.assertEqual(workflow.unresolved_writes(d),{MAC})
            path.write_text(json.dumps(attempt)+'\ninvalid complete line\n',encoding='utf-8')
            with self.assertRaises(workflow.ProvisionError): workflow.pending_writes(d)

    def test_rom_recovery_and_same_image_guards(self):
        class RomBoard(FakeBoard):
            def __init__(self,mac=MAC): super().__init__(mac); self.verified=False
            def info(self):
                if not self.written: raise OSError('app unavailable')
                return super().info()
            def probe_rom(self): return self.mac
            def verify_rom(self,actual,expected,sha):
                if actual!=expected or sha!='a'*64: raise OSError('ROM identity or partition mismatch')
                self.verified=True
            def flash(self,image):
                if not self.verified: raise AssertionError('unverified ROM')
                super().flash(image)
        target={'image_sha256':'b'*64,'partition_sha256':'a'*64,'build_id':'new-build','node_id':1,'saved':True,'group':31,'channel':11,'usb_location':'fixture-usb-1'}
        pending={'attempt-old':{'event':'write_attempted','mac':MAC,'attempt_id':'attempt-old','target':target}}
        with tempfile.TemporaryDirectory() as d:
            log=Path(d)/'flash-01.jsonl';log.write_text(json.dumps(pending['attempt-old'])+'\n')
            board=RomBoard(); records=[]
            result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,lambda x:records.append(json.loads(json.dumps(x))),pending=pending)
            self.assertEqual(result[0]['result'],'success');self.assertTrue(board.verified);self.assertTrue(board.written)
            log2=Path(d)/'flash-02.jsonl';log2.write_text(''.join(json.dumps(r)+'\n' for r in records))
            self.assertEqual(workflow.pending_writes(d),{})
            wrong=dict(target,image_sha256='c'*64);board=RomBoard()
            pending_bad={'a':{'mac':MAC,'target':wrong}}
            result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,pending=pending_bad)
            self.assertEqual(result[0]['result'],'failed');self.assertFalse(board.written);self.assertFalse(board.verified)
            board=RomBoard('90:da:72:48:a4:e0')
            result=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,pending=pending)
            self.assertEqual(result[0]['result'],'failed');self.assertFalse(board.written)

    def test_intact_current_app_recovers_without_reflash(self):
        class Current(FakeBoard):
            def __init__(self): super().__init__();self.num=1
            def info(self):
                info=super().info();info['build_id']='new-build';return info
        target={'image_sha256':'b'*64,'partition_sha256':'a'*64,'build_id':'new-build','node_id':1,'saved':True,'group':31,'channel':11,'usb_location':'fixture-usb-1'}
        pending={'old':{'mac':MAC,'target':target}}
        with tempfile.TemporaryDirectory() as d:
            records=[];board=Current()
            rows=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,lambda x:records.append(x),pending=pending)
            self.assertEqual(rows[0]['result'],'success');self.assertTrue(rows[0]['recovered']);self.assertFalse(board.written)
            self.assertTrue(any(r['event']=='readback_verified' and r['attempt_id']=='old' for r in records))
            board=Current();rows=workflow.execute(Transport(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None)
            self.assertTrue(rows[0]['already_current']);self.assertFalse(board.written)

    def test_changed_com_and_usb_location_guard(self):
        class Rom(FakeBoard):
            def __init__(self): super().__init__();self.rom_called=False
            def info(self):
                if not self.written: raise OSError('app unavailable')
                return super().info()
            def probe_rom(self): self.rom_called=True;return MAC
            def verify_rom(self,a,b,c): pass
        class Changed(Transport):
            def ports(self): return ['COM-reassigned-fake']
        class WrongLocation(Changed):
            def location(self,port): return 'another-usb-port'
        target={'image_sha256':'b'*64,'partition_sha256':'a'*64,'build_id':'new-build','node_id':1,'saved':True,'group':31,'channel':11,'usb_location':'fixture-usb-1'}
        pending={'old':{'mac':MAC,'target':target}}
        with tempfile.TemporaryDirectory() as d:
            board=Rom();rows=workflow.execute(Changed(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,pending=pending)
            self.assertEqual(rows[0]['result'],'success');self.assertTrue(board.rom_called)
            board=Rom();rows=workflow.execute(WrongLocation(board),CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',lambda *_:None,pending=pending)
            self.assertEqual(rows[0]['result'],'failed');self.assertFalse(board.rom_called);self.assertFalse(board.written)

    def test_process_killed_releases_real_os_lock(self):
        import flash_nodes
        with tempfile.TemporaryDirectory() as d:
            code='''import sys\nfrom pathlib import Path\nimport flash_nodes\nflash_nodes.ROOT=Path(sys.argv[1])\nwith flash_nodes.exclusive_flash():\n print("READY",flush=True)\n input()'''
            child=subprocess.Popen([sys.executable,'-u','-c',code,d],cwd=Path(__file__).parent,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(),'READY')
                with patch.object(flash_nodes,'ROOT',Path(d)):
                    with self.assertRaises(flash_nodes.Blocked):
                        with flash_nodes.exclusive_flash(): pass
                    child.kill();child.wait(timeout=10)
                    with flash_nodes.exclusive_flash(): pass
                    self.assertTrue((Path(d)/'production/local/flash.lock').exists())
            finally:
                if child.poll() is None: child.kill();child.wait(timeout=10)
                child.stdin.close();child.stdout.close();child.stderr.close()

    def test_same_entry_retries_when_usb_appears(self):
        class Late(Transport):
            def __init__(self,b): super().__init__(b);self.scans=0
            def ports(self):
                self.scans+=1
                return [] if self.scans==1 else ['new-com']
        with tempfile.TemporaryDirectory() as d:
            b=FakeBoard();transport=Late(b);delays=[];log=Path(d)/'flash-fixture.jsonl'
            def record(v):
                with log.open('a',encoding='utf-8') as f: f.write(json.dumps(v)+'\n')
            rows=workflow.run_with_retries(transport,CONFIG,FIRMWARE,'fixture.bin',Path(d)/'registry.json',d,lambda *_:None,record,delays.append,lambda:None)
            self.assertEqual(rows[0]['result'],'success');self.assertEqual(transport.scans,2);self.assertEqual(delays,[5])


if __name__=='__main__': unittest.main(verbosity=2)
