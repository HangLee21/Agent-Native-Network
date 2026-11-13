"""Real Linux PTYs/local HTTP with explicitly synthetic autonomous board events."""
import json
import os
from pathlib import Path
import select
import sys
import threading
import time
import urllib.error
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from tools.mid_edge.linux_service import run
from tools.mid_edge.local_api import LocalClient
A='90:da:72:48:a4:f8';B='90:da:72:48:a5:cc';C='90:da:72:48:a4:e0';D='90:da:72:48:a5:20'

class Board:
    def __init__(self,mac,bus):
        self.mac=mac;bus[mac]=self;self.bus=bus;self.boot=11 if mac==A else 33
        self.master,slave=os.openpty();self.device=os.ttyname(slave);os.close(slave)
        self.done=False;self.commands=[];self.radio=False;self.seq=0;self.timers=[]
        self.thread=threading.Thread(target=self.loop);self.thread.start()
    def emit(self,**fields):
        if not self.done:os.write(self.master,(json.dumps(dict(schema='mid.serial.v1',node_id=self.mac,boot_id=self.boot,**fields))+'\n').encode())
    def later(self,delay,fn):
        t=threading.Timer(delay,fn);self.timers.append(t);t.start()
    def outcome(self,q,identity,request):
        if q['dst']==C:
            self.emit(event='route_selected',origin=A,origin_boot=11,seq=request,dst=C,request=request,path=[A,B,C])
            self.emit(event='tx_submit',next_hop=B,**identity);self.emit(event='tx_link_ok',next_hop=B,**identity)
            self.bus[C].emit(event='rx_local',payload_hex=q['payload_hex'],**identity)
        else:self.emit(event='route_no_route',request=request,reason=3,**identity)
    def loop(self):
        buf=bytearray()
        while not self.done:
            try:
                if not select.select([self.master],[],[],.05)[0]:continue
                buf.extend(os.read(self.master,4096))
                while b'\n' in buf:
                    line,_,tail=buf.partition(b'\n');buf[:]=tail
                    try:q=json.loads(line)
                    except ValueError:continue
                    self.commands.append(q);fields={}
                    if q['cmd']=='route_start':self.radio=True
                    if q['cmd']=='stop':self.radio=False
                    if q['cmd']=='info':fields=dict(firmware='mid-espnow',chip='esp32s3',deployment_mode='autonomous',discovery_saved=True,discovery_fault=False,group=29,channel=6)
                    if q['cmd']=='routes':fields=dict(routes=[dict(dst=C,request=37,path=[A,B,C],expires_ms=10000)])
                    if q['cmd']=='send':
                        self.seq+=1;identity=dict(origin=self.mac,origin_boot=self.boot,seq=self.seq,dst=q['dst']);request=36+self.seq
                        self.emit(event='tx_queued',**identity)
                        fields=dict(origin=self.mac,origin_boot=self.boot,packet_seq=self.seq,dst=q['dst'])
                        self.emit(event='route_accepted',request=request,**identity)
                        self.emit(event='route_waiting',request=request,**identity)
                        self.later(.8,lambda q=q,i=identity,r=request:self.outcome(q,i,r))
                    self.emit(event='command_result',nonce=q['nonce'],cmd=q['cmd'],ok=True,radio=self.radio,stopping=False,**fields)
            except (OSError,ValueError):time.sleep(.01)
    def close(self):
        self.done=True
        for timer in self.timers:timer.cancel();timer.join(1)
        os.close(self.master);self.thread.join(1)

def check(output):
    out=Path(output);out.mkdir(parents=True,exist_ok=True);bus={};boards=[Board(A,bus),Board(C,bus)];services=[];errors=[]
    config=json.loads((ROOT/'deploy/ubuntu/config.example.json').read_bytes());config.update(start_policy='saved',http_port=0)
    props=dict(ID_PATH=config['id_path'],ID_USB_INTERFACE_NUM=config['interface'],ID_VENDOR_ID=config['vid'],ID_MODEL_ID=config['pid'])
    try:
        clients=[]
        for board in boards:
            ready=threading.Event();ports=[];stop=threading.Event();cfg=dict(config,node_id=board.mac)
            def worker(b=board,c=cfg,s=stop,p=ports,r=ready):
                try:run(c,b.device,get_properties=lambda _:props,stop=s,state=out/b.mac.replace(':',''),on_ready=lambda port:(p.append(port),r.set()))
                except Exception as exc:errors.append(str(exc))
            t=threading.Thread(target=worker);t.start();services.append((stop,t));assert ready.wait(5),errors;clients.append(LocalClient(ports[0]))
        source,destination=clients;payload=bytes(range(160));request='autonomous-message-001'
        send=source.send(C,payload,request_id=request);assert send==source.send(C,payload,request_id=request)
        assert send['result']['accepted'] and send['result']['admission_state']=='locally_queued'
        pending=source.request_status(request);assert pending['progress']['queue_status']=='waiting_route'
        received=destination.recv(5);assert received['payload']==payload
        progress=source.request_status(request);assert progress['progress']['transmission_status']=='radio_api_accepted'
        assert progress['progress']['delivery_status']=='destination_unconfirmed'
        assert progress['progress']['board_selected_paths'][0]['path']==[A,B,C]
        identity={k:received[k] for k in ['origin','origin_boot','seq','dst']}
        assert destination.packet_status(**identity)['delivery_status']=='destination_received'
        assert source.routes()['source']=='local_board_cache'
        failed=source.send(D,b'no route',request_id='autonomous-message-002');deadline=time.monotonic()+4
        while True:
            no_route=source.request_status('autonomous-message-002')
            if no_route['progress']['board_terminal']=='route_no_route':break
            assert time.monotonic()<deadline;time.sleep(.05)
        assert no_route['progress']['transmission_status']=='not_observed'
        assert no_route['progress']['delivery_status']=='destination_unconfirmed'
        try:source._call('/api/edge/route/config',dict(group=29,channel=6,autostart=True,path=[A,B,C]));raise AssertionError('remote path accepted')
        except urllib.error.HTTPError as exc:assert exc.code==400
        sends=[q for q in boards[0].commands if q['cmd']=='send'];assert len(sends)==2
        for q in sends:assert set(q)=={'schema','cmd','nonce','dst','payload_hex'}
        for board in boards:
            names=[q['cmd'] for q in board.commands];assert names[0]=='info' and names.count('route_start')==1
            assert not any(n in names for n in ['discover_start','route_config','config','deploy','link_filter'])
        serializable=dict(received);serializable['payload']=serializable['payload'].hex()
        result=dict(status='passed',evidence_kind='Ubuntu_PTY_synthetic_board_events_actual_local_API',pending=pending,source_progress=progress,destination_application=serializable,no_route=no_route,host_routes_computed=0,physical_rf=False)
    finally:
        for stop,t in services:stop.set();t.join(8);assert not t.is_alive()
        for board in boards:board.close()
    assert not errors,errors
    result['commands']=[b.commands for b in boards];(out/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print('Ubuntu autonomous saved-start, queue/submit/receive/no-route and API checks passed')

if __name__=='__main__':check(sys.argv[1])
