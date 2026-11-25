"""Real HTTP entry with synthetic serial endpoints; never opens real ports."""
import json
from pathlib import Path
import sys
import threading
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mid_edge.client import Edge
from tools.mid_edge.hostcheck import FakeSerial,A,B,C
from tools.mid_sim_console.local_edge import LocalEdge,Handler,ThreadingHTTPServer

def check(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);bus={};FakeSerial(B,bus)
    with Edge('synthetic-A',A,transport=FakeSerial(A,bus)) as a,Edge('synthetic-C',C,transport=FakeSerial(C,bus)) as c:
        apps=[LocalEdge(a,out/'a-state.json'),LocalEdge(c,out/'c-state.json')];servers=[];threads=[]
        try:
            for app in apps:
                server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=app;servers.append(server)
                t=threading.Thread(target=server.serve_forever);t.start();threads.append(t)
            def call(index,path,data=None):
                base='http://127.0.0.1:'+str(servers[index].server_port)
                req=urllib.request.Request(base+path,None if data is None else json.dumps(data).encode(),headers={'Origin':base,'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=5) as r:return r.read()
            assert b'<html' in call(0,'/') or b'<!doctype' in call(0,'/').lower()
            assert b'api/edge/send' in call(0,'/sender.js')
            snapshot=json.loads(call(0,'/api/snapshot'));assert snapshot['labels']['A']==A
            assert json.loads(call(0,'/api/reset',{}))==snapshot
            payload='你好，C！'.encode();q=dict(request_id='http_message_001',dst=C,payload_hex=payload.hex())
            first=json.loads(call(0,'/api/edge/send',q));assert first==json.loads(call(0,'/api/edge/send',q))
            deadline=time.monotonic()+2;received=[]
            while time.monotonic()<deadline:
                received=json.loads(call(1,'/api/edge/inbox'))['records']
                if received:break
                time.sleep(.02)
            assert len(received)==1 and bytes.fromhex(received[0]['payload_hex'])==payload
            for k in ['origin','origin_boot','seq','dst']:assert first['result'][k]==received[0][k]
            assert first['delivery_status']=='destination_unconfirmed' and received[0]['delivery_status']=='destination_received'
            result=dict(evidence_kind='synthetic_serial_real_local_http',payload_hex=payload.hex(),send=first,inbox=received,hardware_operations=0,physical_hosts=0)
            (out/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            return result
        finally:
            for server in servers:server.shutdown();server.server_close()
            for t in threads:t.join(2)
            for app in apps:app.stopping=True;app.thread.join(1)

if __name__=='__main__':print(json.dumps(check(sys.argv[1]),ensure_ascii=False))
