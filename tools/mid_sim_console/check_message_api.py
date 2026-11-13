"""Synthetic contract tests; never opens physical ports or invokes hardware."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from contextlib import nullcontext
import unittest
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/mid_console'))
spec=importlib.util.spec_from_file_location('bench_server',ROOT/'tools/mid_console/server.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
from tools.mid_sim_console.local_edge import LocalEdge
from tools.mid_edge.client import Edge
from tools.mid_edge.hostcheck import FakeSerial,A,C

class MessageChecks(unittest.TestCase):
    def test_plan_payload_and_request_binding(self):
        console=bench.Console()
        console.hardware_status=lambda src:dict(ready_nodes=list('ABC'))
        console.solve=lambda q,live:dict(ok=True,node_set=list('ABC'),availability=dict(runnable=False,reasons=[]),src=q['src'],dst=q['dst'])
        q=dict(src='A',dst='C',mode='hops',hops=2,count=1,payload_hex='00ff'+ '你好'.encode().hex(),request_id='message_001')
        first=console.plan(q);self.assertEqual(first['payload_hex'],q['payload_hex']);self.assertEqual(console.plan(q)['plan_id'],first['plan_id'])
        with self.assertRaises(bench.RequestError):console.plan(dict(q,payload_hex='0000'))
        for invalid in ['0','zz','aa'*161]:
            with self.assertRaises(ValueError):console.plan(dict(q,payload_hex=invalid))
        # Caller mutation cannot change the frozen plan.
        q['payload_hex']='abcd';self.assertNotEqual(console.plans[first['plan_id']]['plan']['payload_hex'],q['payload_hex'])

    def test_edge_send_once_and_uncertain_restart(self):
        bus={};serial=FakeSerial(A,bus)
        scope=ROOT/'simulation/outputs/E2-024/host-tests';scope.mkdir(parents=True,exist_ok=True)
        with nullcontext(tempfile.mkdtemp(dir=scope)) as folder,Edge('fake-A',A,transport=serial) as edge:
            path=Path(folder)/'requests.json';app=LocalEdge(edge,path)
            try:
                q=dict(dst=C,payload_hex='00ff6869',request_id='local_001')
                first=app.send(q);second=app.send(q)
                self.assertEqual(first,second);self.assertEqual(serial.seq,1)
                with self.assertRaises(ValueError):app.send(dict(q,dst=A))
                app.requests['uncertain_001']=dict(request=dict(q,request_id='uncertain_001',payload_hex='ff'),state='outcome_unknown')
                with self.assertRaises(ValueError):app.send(dict(q,request_id='another_001',payload_hex='ff'))
                restarted=LocalEdge(edge,path)
                try:self.assertEqual(restarted.send(q),first);self.assertEqual(serial.seq,1)
                finally:restarted.stopping=True;restarted.thread.join(1)
            finally:app.stopping=True;app.thread.join(1)

if __name__=='__main__':unittest.main()
