"""Only static GETs against a temporary server with a fake serial Edge."""
import hashlib
import json
from pathlib import Path
import sys
import threading
import urllib.request
import urllib.error
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mid_edge.client import Edge
from tools.mid_edge.hostcheck import FakeSerial,A
from tools.mid_sim_console.local_edge import LocalEdge,Handler,ThreadingHTTPServer

def check(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    with Edge('synthetic-A',A,transport=FakeSerial(A,{})) as edge:
        app=LocalEdge(edge,out/'state.json')
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.app=app
        thread=threading.Thread(target=server.serve_forever);thread.start()
        try:
            base='http://127.0.0.1:'+str(server.server_port)
            with urllib.request.urlopen(base+'/route-view.js',timeout=5) as response:
                assert response.status==200
                mime=response.headers['Content-Type'];assert mime=='application/javascript; charset=utf-8'
                data=response.read()
            asset=ROOT/'research/agent_native_network/mid_sim_console/route-view.js'
            assert data==asset.read_bytes() and data
            denied=[]
            for path in ['/unlisted.js','/%2e%2e/tools/mid_console/server.py','/route-view.js/../sender.js']:
                try:urllib.request.urlopen(base+path,timeout=5);raise AssertionError('unexpected allowed resource')
                except urllib.error.HTTPError as exc:assert exc.code==404;denied.append(path)
            result=dict(status='passed',path='/route-view.js',http_status=200,content_type=mime,bytes=len(data),asset_sha256=hashlib.sha256(data).hexdigest(),denied_http404=denied,evidence_kind='temporary_local_http_fake_edge_static_only',serial_commands=0,real_serial_opens=0,rf_packets=0,existing_services_changed=False)
            (out/'checks.json').write_text(json.dumps(result,indent=2),encoding='utf-8');return result
        finally:
            server.shutdown();server.server_close();thread.join(2);app.stopping=True;app.thread.join(1)

if __name__=='__main__':print(json.dumps(check(sys.argv[1])))
