"""Ubuntu userspace/PTTY checks. No USB passthrough or real radio is used."""
import argparse
import copy
import importlib.util
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import threading
import time
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mid_edge import Edge
from tools.mid_edge.linux_service import run,Rejected,gate
from tools.mid_edge.local_api import LocalClient
spec=importlib.util.spec_from_file_location('ubuntu_install',ROOT/'deploy/ubuntu/install.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
A='90:da:72:48:a4:f8';B='90:da:72:48:a5:cc'

class Board:
    def __init__(self,wrong_firmware=False):
        self.master,slave=os.openpty();self.device=os.ttyname(slave);os.close(slave)
        self.stop=False;self.commands=[];self.radio=False;self.wrong=wrong_firmware;self.closed=False;self.seq=0
        self.thread=threading.Thread(target=self.loop);self.thread.start()
    def loop(self):
        buffer=bytearray()
        while not self.stop:
            try:
                if not select.select([self.master],[],[],.05)[0]:continue
                buffer.extend(os.read(self.master,4096))
                while b'\n' in buffer:
                    raw,_,tail=buffer.partition(b'\n');buffer[:]=tail
                    try:q=json.loads(raw)
                    except ValueError:continue
                    self.commands.append(q);fields={}
                    if q['cmd']=='discover_start':self.radio=True
                    elif q['cmd']=='stop':self.radio=False
                    if q['cmd']=='info':fields=dict(firmware='other' if self.wrong else 'mid-espnow',chip='esp32s3',discovery_saved=True,discovery_fault=False,group=7,channel=6)
                    if q['cmd']=='neighbors':fields=dict(neighbors=[dict(node_id=B,state='bidirectional',boot_id=22,last_seen_ms=100,age_ms=4,last_confirmed_ms=99)])
                    if q['cmd']=='neighbor':fields=dict(neighbor=dict(node_id=q['node_id'],state='bidirectional',boot_id=22,age_ms=4))
                    if q['cmd']=='send':
                        self.seq+=1;fields=dict(packet_seq=self.seq,origin_boot=11)
                        for event in [dict(event='tx_queued',origin=A,origin_boot=11,seq=self.seq,dst=q['dst'],next_hop=q['dst']),dict(event='rx_local',origin=B,origin_boot=22,seq=55,dst=A,payload_hex=q['payload_hex'])]:
                            os.write(self.master,(json.dumps(dict(schema='mid.serial.v1',node_id=A,boot_id=11,**event))+'\n').encode())
                    e=dict(schema='mid.serial.v1',node_id=A,boot_id=11,event='command_result',cmd=q['cmd'],nonce=q['nonce'],ok=True,radio=self.radio,stopping=False,**fields)
                    os.write(self.master,(json.dumps(e)+'\n').encode())
            except (OSError,ValueError):time.sleep(.02)
    def close(self):
        if self.closed:return
        self.closed=True;self.stop=True;os.close(self.master);self.thread.join(1)

class LinuxChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if subprocess.run(['getent','group','mid-edge'],stdout=subprocess.DEVNULL).returncode:
            subprocess.run(['groupadd','--system','mid-edge'],check=True)
        if subprocess.run(['id','-u','mid-edge'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            subprocess.run(['useradd','--system','--gid','mid-edge','mid-edge'],check=True)
        cls.config=json.loads((ROOT/'deploy/ubuntu/config.example.json').read_bytes());cls.config.update(start_policy='saved',http_port=0)
        cls.props=dict(ID_PATH=cls.config['id_path'],ID_USB_INTERFACE_NUM='00',ID_VENDOR_ID='1a86',ID_MODEL_ID='7523')

    def test_package_and_exact_match(self):
        c=dict(self.config,http_port=8780);root=OUT/'rootfs';cfg=OUT/'test-config.json';cfg.write_text(json.dumps(c))
        subprocess.run([sys.executable,str(ROOT/'deploy/ubuntu/install.py'),'install','--config',str(cfg),'--root',str(root)],check=True)
        inventory=json.loads((root/'opt/mid-edge/INSTALL_MANIFEST.json').read_bytes());self.assertIn('tools/mid_edge/linux_service.py',inventory['files_sha256'])
        rule=(root/'etc/udev/rules.d/99-mid-edge.rules').read_text();unit=root/'etc/systemd/system/mid-edge@.service'
        self.assertIn(c['id_path'],rule);self.assertIn('ID_USB_INTERFACE_NUM',rule);self.assertIn('BindsTo=dev-%i.device',unit.read_text())
        report={}
        for command in [['systemd-analyze','verify',str(unit)],['udevadm','verify',str(root/'etc/udev/rules.d/99-mid-edge.rules')]]:
            result=subprocess.run(command,text=True,capture_output=True,timeout=20);report[command[0]]=dict(exit_code=result.returncode,stdout=result.stdout,stderr=result.stderr)
            self.assertEqual(result.returncode,0,report)
        (OUT/'unit-and-rule-verification.json').write_text(json.dumps(report,indent=2))
        for field in ['ID_PATH','ID_USB_INTERFACE_NUM','ID_VENDOR_ID','ID_MODEL_ID']:
            p=dict(self.props);p[field]='not-registered'
            with self.assertRaises(Rejected):run(c,'unopened',get_properties=lambda _:p,edge_factory=lambda *a,**kw:self.fail('unrelated serial opened'),state=OUT/'rejected')
        with self.assertRaises(ValueError):installer.rule(dict(c,id_path='*'))
        (root/'var/lib/mid-edge').mkdir(parents=True);(root/'var/lib/mid-edge/user-data').write_text('keep')
        subprocess.run([sys.executable,str(ROOT/'deploy/ubuntu/install.py'),'uninstall','--root',str(root)],check=True)
        self.assertTrue((root/'var/lib/mid-edge/user-data').exists());self.assertFalse(unit.exists())

    def test_wrong_firmware_info_only(self):
        board=Board(wrong_firmware=True)
        try:
            with self.assertRaises(Rejected):run(self.config,board.device,get_properties=lambda _:self.props,state=OUT/'wrong')
            self.assertEqual([q['cmd'] for q in board.commands],['info'])
        finally:board.close()

    def test_pty_local_api_unplug_reenumerate(self):
        sessions=[];all_commands=[];business_client=None;last_port=None
        for cycle in range(2):
            hold=None
            if cycle:hold=os.openpty()  # occupy old tty number so re-enumeration must change
            board=Board();ready=threading.Event();port=[];stop=threading.Event();errors=[]
            config=dict(self.config,http_port=last_port or 0)
            def worker():
                try:run(config,board.device,get_properties=lambda _:self.props,stop=stop,state=OUT/'session-state',on_ready=lambda p:(port.append(p),ready.set()))
                except Exception as e:errors.append(str(e))
            t=threading.Thread(target=worker);t.start()
            try:
                self.assertTrue(ready.wait(5),errors)
                if business_client is None:business_client=LocalClient(port[0]);last_port=port[0]
                self.assertEqual(port[0],last_port);client=business_client
                self.assertEqual(client.neighbors()['neighbors'][0]['node_id'],B)
                self.assertEqual(client.node_status(B)['neighbor']['state'],'bidirectional')
                self.assertTrue(client.events(0,0)['events'])
                sent=client.send(B,b'\x00\xffhello',request_id='pty-message-'+str(cycle))
                self.assertEqual(sent['result']['delivery_status'],'destination_unconfirmed')
                received=client.recv(2);self.assertEqual(received['payload'],b'\x00\xffhello');self.assertEqual(received['origin'],B)
                commands=[q['cmd'] for q in board.commands];self.assertEqual(commands[0],'info');self.assertEqual(commands.count('discover_start'),1)
                self.assertFalse(any(q in commands for q in ['discover_config','discover_clear','deploy','config','start','neighbor_probe']))
                # An exclusive second owner must fail while the original PTY is open.
                with self.assertRaises(Exception):
                    second=Edge(board.device,A,460800);second.close()
                if cycle==0:
                    board.close();t.join(5);self.assertFalse(t.is_alive())
                    self.assertTrue(errors)  # unplug observed, no serial re-open/retry
                else:
                    stop.set();t.join(5);self.assertFalse(t.is_alive());self.assertFalse(errors)
                sessions.append(dict(cycle=cycle,pty=board.device,port=port[0],errors=errors));all_commands.append(board.commands)
            finally:
                stop.set();board.close();t.join(5)
                if hold:
                    for fd in hold:os.close(fd)
        self.assertNotEqual(sessions[0]['pty'],sessions[1]['pty'])
        shutdowns=[json.loads(p.read_bytes()) for p in (OUT/'session-state').glob('*.shutdown.json')]
        self.assertEqual(len(shutdowns),2);self.assertTrue(all(r['serial_closed'] for r in shutdowns))
        self.assertEqual(sum(r['radio_stop_confirmed'] for r in shutdowns),1)  # unplug is unknown, normal stop confirmed
        (OUT/'pty-sessions.json').write_text(json.dumps(dict(sessions=sessions,commands=all_commands,rf_operations=0),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();OUT=Path(a.output);OUT.mkdir(parents=True,exist_ok=True)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(LinuxChecks)
    with (OUT/'tests.txt').open('w') as log:result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report=dict(status='passed' if result.wasSuccessful() else 'failed',tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),os_release=Path('/etc/os-release').read_text(),physical_usb_hotplug=False,systemd_pid1_lifecycle=False,physical_rf=False)
    (OUT/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));raise SystemExit(0 if result.wasSuccessful() else 1)
