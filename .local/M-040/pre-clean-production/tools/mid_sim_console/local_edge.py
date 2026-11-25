"""Local visual sender: one board, one serial owner, loopback browser only."""
import argparse
import collections
import json
import re
import sys
import threading
import time
import copy
import uuid
from urllib.parse import urlsplit,unquote,parse_qs
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mid_edge import Edge
from tools.mid_edge.client import EdgeError

class LocalEdge:
    def __init__(self,edge,state):
        self.edge=edge;self.info=edge.info();self.lock=threading.RLock();self.state=Path(state)
        self.state.parent.mkdir(parents=True,exist_ok=True)
        self.requests=json.loads(self.state.read_bytes()) if self.state.exists() else {}
        self.inbox=collections.deque(maxlen=256);self.cursor=0;self.stopping=False;self.instance_id=uuid.uuid4().hex
        self.thread=threading.Thread(target=self.receive,daemon=True);self.thread.start()
        self.snapshot_path=ROOT/'tools/mid_sim_console/edge_assets/snapshot.json'
    def snapshot(self):
        raw=json.loads(self.snapshot_path.read_bytes());labels=json.loads((Path(__file__).parent/'edge_assets/labels.json').read_bytes())['labels']
        links=[dict(src=e['src'],dst=e['dst'],**e['defaults'],fail=False) for e in raw['edges']]
        settings=dict(schema='mid.measured.settings.v1',preset='measured',snapshot_id=raw['snapshot_id'],duration_s=60,seed=11,fault_start_s=20,fault_end_s=40,offline_nodes=[],links=links,src=next((k for k,v in labels.items() if v==self.edge.node_id),'A'),dst='C',hops=None,both_directions=False)
        return dict(raw,settings=settings,labels=labels)
    def persist(self):
        temp=self.state.with_suffix('.tmp');temp.write_text(json.dumps(self.requests),encoding='utf-8');temp.replace(self.state)
    def receive(self):
        while not self.stopping:
            try:item=self.edge.recv(.2)
            except TimeoutError:continue
            except Exception:return
            item.pop('payload',None)
            with self.lock:
                self.cursor+=1;item['inbox_cursor']=self.cursor;self.inbox.append(item)
    def send(self,q):
        if set(q)!={'request_id','dst','payload_hex'}:raise ValueError('request_id/dst/payload_hex required')
        if not isinstance(q['request_id'],str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',q['request_id']):raise ValueError('invalid request_id')
        if not isinstance(q['dst'],str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',q['dst']):raise ValueError('invalid destination MAC')
        if not isinstance(q['payload_hex'],str) or not re.fullmatch(r'(?:[a-fA-F0-9]{2}){0,160}',q['payload_hex']):raise ValueError('payload exceeds160 bytes or invalid hex')
        with self.lock:
            key=q['request_id'];old=self.requests.get(key)
            if old:
                if old['request']!=q:raise ValueError('request_id binds another destination/payload')
                if old.get('source_node_id',old.get('result',{}).get('origin'))!=self.edge.node_id:raise ValueError('request does not belong to this local STA identity; inspect retained ledger')
                return old
            if any(r.get('state')=='outcome_unknown' and r['request']['dst'].lower()==q['dst'].lower() and r['request']['payload_hex'].lower()==q['payload_hex'].lower() for r in self.requests.values()):
                raise ValueError('earlier identical message outcome unknown; inspect its request/log before a new send')
            record=dict(request=dict(q),source_node_id=self.edge.node_id,state='outcome_unknown',delivery_status='destination_unconfirmed')
            self.requests[key]=record;self.persist()  # reserve before serial side effect; never auto resend
            try:record.update(state='locally_accepted',result=self.edge.send(q['dst'],bytes.fromhex(q['payload_hex'])))
            except Exception as exc:record['error']=str(exc)
            self.persist();return record

    def request_status(self,request_id):
        with self.lock:
            if request_id not in self.requests:raise KeyError('unknown local request')
            record=copy.deepcopy(self.requests[request_id])
        receipt=record.get('result')
        progress=self.edge.packet_status(**{k:receipt[k] for k in ['origin','origin_boot','seq','dst']}) if receipt else None
        return dict(record,progress=progress)

PAGE='''<!doctype html><meta charset="utf-8"><title>本机消息收发</title><style>body{font:16px system-ui;max-width:800px;margin:30px auto;padding:20px}input,textarea,button{font:inherit;padding:10px;margin:8px 0}input,textarea{display:block;width:95%}pre{white-space:pre-wrap}button{cursor:pointer}</style><h1>本机消息收发</h1><p id="identity"></p><label>目的板MAC<input id="dst" placeholder="90:da:72:48:a4:e0"></label><label>文字消息<textarea id="message">你好，C</textarea></label><p id="size"></p><button id="send">发送到目的板</button><pre id="result"></pre><h2>本板收件</h2><button id="read">读取收件</button><pre id="inbox"></pre><script>
const $=x=>document.getElementById(x);let request=null;async function api(p,q){const r=await fetch(p,q?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(q)}:{});const v=await r.json();if(!r.ok)throw Error(v.error);return v}function edit(){request=null;const n=new TextEncoder().encode($('message').value).length;$('size').textContent=n+' / 160 字节';$('send').disabled=n>160}for(const id of ['dst','message'])$(id).oninput=edit;edit();api('/api/edge/status').then(s=>$('identity').textContent='本板 '+s.node_id+'；分机发送只确认本地接纳。');$('send').onclick=async()=>{$('send').disabled=true;try{if(!request)request={request_id:crypto.randomUUID(),dst:$('dst').value,payload_hex:Array.from(new TextEncoder().encode($('message').value),x=>x.toString(16).padStart(2,'0')).join('')};$('result').textContent=JSON.stringify(await api('/api/edge/send',request),null,2)}catch(e){$('result').textContent=e.message}finally{$('send').disabled=false}};$('read').onclick=async()=>{$('inbox').textContent=JSON.stringify(await api('/api/edge/inbox'),null,2)};
</script>'''

class Handler(BaseHTTPRequestHandler):
    def reply(self,code,value):
        raw=value.encode() if isinstance(value,str) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(code);self.send_header('Content-Type','text/html; charset=utf-8' if isinstance(value,str) else 'application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.handle_api(False)
    def do_POST(self):self.handle_api(True)
    def handle_api(self,write):
        try:
            self.connection.settimeout(10);host=self.headers.get('Host');port=self.server.server_port
            if self.headers.get_all('Host')!=[host] or host not in [f'localhost:{port}',f'127.0.0.1:{port}']:return self.reply(403,dict(error='loopback Host required'))
            origin=self.headers.get('Origin')
            if len(self.headers.get_all('Origin',[]))>1 or (write or origin is not None) and origin!='http://'+host:return self.reply(403,dict(error='same origin required'))
            app=self.server.app
            url=urlsplit(self.path);path=url.path;query=parse_qs(url.query)
            if not write and path in ['/','/index.html','/workbench.js','/sender.js','/route-view.js','/neighbors.js']:
                file=ROOT/'research/agent_native_network/mid_sim_console'/('index.html' if path=='/' else path.lstrip('/'))
                if file.is_file():
                    content=file.read_bytes();self.send_response(200);self.send_header('Content-Type','application/javascript; charset=utf-8' if file.suffix=='.js' else 'text/html; charset=utf-8');self.send_header('Content-Length',str(len(content)));self.end_headers();return self.wfile.write(content)
                if path in ['/','/index.html']:return self.reply(200,PAGE)
            if not write and path in ['/api/snapshot','/api/measured-defaults']:return self.reply(200,dict(app.snapshot(),ok=True))
            if write and path=='/api/reset':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=128 or json.loads(self.rfile.read(n))!={}:raise ValueError('reset expects {}')
                return self.reply(200,dict(app.snapshot(),ok=True))
            if not write and path=='/api/status':return self.reply(200,dict(ok=True,mode='single_local_board',busy=False,runs=[],simulation_available=False))
            if write and path in ['/api/plan','/api/run']:return self.reply(422,dict(error='本机单板模式使用板内预配置路径；集中规划和仿真请使用独立工作台。'))
            if not write and path=='/api/edge/status':
                app.edge.health()
                app.info=app.edge.info()
                return self.reply(200,dict(ok=True,node_id=app.edge.node_id,info=app.info,info_basis='fresh_local_info_read_no_RF',mode='single_local_board',wireless_mode=app.info.get('deployment_mode'),discovery_supported='discovery_saved' in app.info,routing_supported=app.info.get('deployment_mode')=='autonomous',routing_capability_basis='native_configured_mode',connected=True,instance_id=app.instance_id,remote_delivery_confirmation=False,labels=app.snapshot()['labels']))
            if not write and path=='/api/edge/routes':return self.reply(200,dict(app.edge.routes(),source='local_board_cache',host_planner_used=False))
            if not write and path=='/api/edge/neighbors':return self.reply(200,dict(app.edge.neighbors(),source='local_firmware_table',rf_probe_started=False))
            if not write and path=='/api/edge/telemetry':
                try:return self.reply(200,app.edge.telemetry())
                except EdgeError as exc:
                    if 'unknown_command' in str(exc):return self.reply(422,dict(error='mobile telemetry unsupported by this firmware'))
                    raise
            if write and path=='/api/edge/position':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=1024 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('bounded position JSON required')
                q=json.loads(self.rfile.read(n))
                from tools.mid_edge.mobile_position import validate_position
                q=validate_position(q)
                try:return self.reply(200,app.edge.set_position(**q))
                except EdgeError as exc:
                    if 'unknown_command' in str(exc):return self.reply(422,dict(error='position injection unsupported by this firmware'))
                    raise
            if not write and path.startswith('/api/edge/nodes/'):return self.reply(200,app.edge.node_status(path[len('/api/edge/nodes/'):] ))
            if write and path in ['/api/edge/route/start','/api/edge/route/clear','/api/edge/radio/stop']:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=128 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json' or json.loads(self.rfile.read(n))!={}:raise ValueError('explicit operation expects {}')
                command={'/api/edge/route/start':'route_start','/api/edge/route/clear':'route_clear','/api/edge/radio/stop':'stop'}[path]
                result=app.edge.route_start() if command=='route_start' else app.edge.route_clear() if command=='route_clear' else app.edge.command(command)
                app.info=app.edge.info();return self.reply(200,result)
            if write and (path in ['/api/edge/discovery/config','/api/edge/route/config'] or path.endswith('/probe') and path.startswith('/api/edge/nodes/')):
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=512 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('bounded JSON body required')
                q=json.loads(self.rfile.read(n))
                if path.endswith('/probe'):
                    if q!={}:raise ValueError('probe expects {}')
                    return self.reply(200,app.edge.neighbor_probe(path[len('/api/edge/nodes/'):-len('/probe')]))
                if not isinstance(q,dict) or set(q)-{'group','channel','autostart'}:raise ValueError('group/channel/autostart required')
                configure=app.edge.route_config if path=='/api/edge/route/config' else app.edge.discover_config
                value=configure(q['group'],q['channel'],q.get('autostart',True));app.info=app.edge.info()
                return self.reply(200,value)
            if not write and path=='/api/edge/events':
                after=int(query.get('after',['0'])[0]);wait=float(query.get('wait',['0'])[0]);events=app.edge.wait_events(after,wait)
                return self.reply(200,dict(ok=True,events=events,cursor=events[-1]['edge_cursor'] if events else after,instance_id=app.instance_id))
            if not write and path.startswith('/api/edge/requests/'):
                request_id=path[len('/api/edge/requests/'):]
                if not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}',request_id):raise ValueError('invalid request_id')
                return self.reply(200,dict(ok=True,**app.request_status(request_id)))
            if not write and path=='/api/edge/packet':
                identity={k:query[k][0] for k in ['origin','origin_boot','seq','dst']}
                identity['origin_boot']=int(identity['origin_boot']);identity['seq']=int(identity['seq'])
                return self.reply(200,dict(ok=True,**app.edge.packet_status(**identity)))
            if not write and path=='/api/edge/inbox':
                after=int(query.get('after',['0'])[0])
                with app.lock:
                    if after<0 or after>app.cursor:raise ValueError('invalid inbox cursor')
                    if app.inbox and after and after<app.inbox[0]['inbox_cursor']-1:return self.reply(409,dict(error='inbox cursor expired; consult persistent serial log'))
                    return self.reply(200,dict(ok=True,records=[r for r in app.inbox if r['inbox_cursor']>after],cursor=app.cursor,instance_id=app.instance_id,scope='local_destination_rx_only',retained_limit=256))
            if write and path=='/api/edge/send':
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=4096 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('invalid JSON body')
                return self.reply(200,dict(ok=True,**app.send(json.loads(self.rfile.read(n)))))
            self.reply(404,dict(error='endpoint not found'))
        except (ValueError,TypeError,KeyError) as exc:self.reply(400,dict(error=str(exc)))
        except (EdgeError,TimeoutError) as exc:self.reply(503,dict(ok=False,error=str(exc)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--serial-port',required=True);p.add_argument('--node-id',required=True);p.add_argument('--baud',type=int,required=True);p.add_argument('--port',type=int,default=8780);p.add_argument('--state',required=True);p.add_argument('--log',required=True);p.add_argument('--snapshot',help='Explicit historical measurement snapshot JSON; default packaged H011 snapshot');a=p.parse_args()
    with Edge(a.serial_port,a.node_id,a.baud,log=a.log) as edge:
        app=LocalEdge(edge,a.state)
        if a.snapshot:app.snapshot_path=Path(a.snapshot)
        server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.app=app
        print(f'本机收发 http://127.0.0.1:{a.port}/',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:app.stopping=True;app.thread.join(1);server.server_close()

if __name__=='__main__':main()
