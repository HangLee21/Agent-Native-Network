"""Executable synthetic serial contract check. No physical ports or RF."""
import contextlib
import io
import json
import queue
import sys
import threading
import unittest
from unittest.mock import patch
from .client import Edge, EdgeError

A='90:da:72:48:a4:f8'; B='90:da:72:48:a5:cc'; C='90:da:72:48:a4:e0'

class FakeSerial:
    def __init__(self, mac, bus):
        self.mac=mac;self.bus=bus;bus[mac]=self;self.rx=queue.Queue();self.buf=bytearray();self.closed=False;self.seq=0
    def emit(self, **v):
        self.rx.put((json.dumps(dict(schema='mid.serial.v1',node_id=self.mac,boot_id=11,**v))+'\n').encode())
    def read(self,n):
        try:return self.rx.get(timeout=.02)
        except queue.Empty:return b''
    def close(self): self.closed=True
    def write(self,data):
        self.buf.extend(data)
        if b'\n' not in self.buf:return len(data)
        line,_,tail=self.buf.partition(b'\n');self.buf[:]=tail;q=json.loads(line);fields={}
        if q['cmd']=='send':
            self.seq+=1;p=dict(origin=self.mac,origin_boot=11,seq=self.seq,dst=q['dst'])
            self.emit(event='tx_queued',next_hop=B,**p)
            if B in self.bus:self.bus[B].emit(event='rx_relay',**p);self.bus[B].emit(event='tx_queued',next_hop=C,**p)
            if q['dst'] in self.bus:self.bus[q['dst']].emit(event='rx_local',payload_hex=q['payload_hex'],**p)
            fields=dict(packet_seq=self.seq,origin_boot=11)
        self.emit(event='command_result',cmd=q['cmd'],nonce=q['nonce'],ok=True,**fields)
        return len(data)

class ContractChecks(unittest.TestCase):
    def test_actual_profile_command(self):
        from tools.mid_baseline.edge_profiles.make_profile import make
        profile=make(['A','B','C'],False,'host-profile')
        bus={};serial=FakeSerial(B,bus)
        with Edge('fake-B',B,transport=serial) as board:
            self.assertTrue(board.deploy(profile)['ok'])
            self.assertNotIn('publisher_boot',profile)

    def test_bytes_and_identity_while_receiving(self):
        bus={}
        with Edge('fake-A',A,transport=FakeSerial(A,bus)) as a, Edge('fake-B',B,transport=FakeSerial(B,bus)) as b, Edge('fake-C',C,transport=FakeSerial(C,bus)) as c:
            self.assertEqual(a.info()['node_id'],A)
            payload=b'\x00\xffedge\n\xe4\xbd\xa0'
            received=[];thread=threading.Thread(target=lambda:received.append(c.recv(3)));thread.start()
            receipt=a.send(C,payload);thread.join(4);self.assertFalse(thread.is_alive())
            self.assertEqual(receipt['delivery_status'],'destination_unconfirmed')
            self.assertEqual(received[0]['payload'],payload)
            for key in ['origin','origin_boot','seq','dst']:self.assertEqual(receipt[key],received[0][key])
            self.assertEqual(received[0]['delivery_status'],'destination_received')
            self.assertTrue(any(e['event']=='rx_relay' for e in b.events()))
            with self.assertRaises(TimeoutError):b.recv(.05)
            with self.assertRaises(ValueError):a.send(C,b'x'*161)
            with self.assertRaises(ValueError):a.deploy(dict(node_id=C))

    def test_port_identity_fault(self):
        bus={};serial=FakeSerial(C,bus)
        with Edge('fake-wrong',A,transport=serial) as edge:
            with self.assertRaises(EdgeError):edge.info()

    def test_cli_jsonl_actual_entry(self):
        from . import __main__ as cli
        bus={};serial=FakeSerial(A,bus)
        factory=lambda port,node_id,baudrate,**kw:Edge(port,node_id,baudrate,transport=serial)
        commands='\n'.join(json.dumps(x) for x in [dict(op='info'),dict(op='send',dst=C,payload_hex='00ff6869'),dict(op='stats'),dict(op='stop')])+'\n'
        output=io.StringIO()
        with patch.object(sys,'argv',['mid_edge','--port','fake-A','--node-id',A,'--baud','460800']),patch.object(sys,'stdin',io.StringIO(commands)),patch.object(cli,'Edge',factory),contextlib.redirect_stdout(output):cli.main()
        rows=[json.loads(x) for x in output.getvalue().splitlines()]
        self.assertTrue(rows[0]['ready']);self.assertEqual(len(rows),5)
        self.assertTrue(all(x['ok'] for x in rows[1:]))

if __name__=='__main__':unittest.main()
