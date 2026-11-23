"""Receive-only Semtech UDP appliance, standard library, Python 3.4 syntax."""
import argparse,base64,binascii,json,os,re,socket,socketserver,sys,threading,time
from http.server import BaseHTTPRequestHandler,HTTPServer
from .compat_decoder import decode_frame
SCHEMA='ann.gateway.discover.v1'
class State(object):
 def __init__(self,eui):
  self.eui=eui;self.lock=threading.RLock();self.pull=None;self.nodes={};self.retired={};self.reports=0;self.bad=0
 def ingest(self,p):
  try:
   if p.get('stat')!=1:raise ValueError('CRC invalid')
   raw=base64.b64decode(p['data'].encode('ascii'),validate=True)
   if p['size']!=len(raw):raise ValueError('size mismatch')
   report=decode_frame(raw);node=report['observer_id'];boot=report['observer_boot'];seq=report['report_seq'];now=time.monotonic()
   with self.lock:
    old=self.nodes.get(node)
    if boot in self.retired.get(node,set()):return
    if old and old['boot']==boot and (seq<=old['seq'] or report['snapshot_at_ms']<old['report']['snapshot_at_ms']):return
    if old and old['boot']!=boot:
     retired=self.retired.setdefault(node,set())
     if len(retired)>=256:raise ValueError('boot capacity')
     retired.add(old['boot'])
    if not old and len(self.nodes)>=64:raise ValueError('node capacity')
    self.nodes[node]=dict(boot=boot,seq=seq,report=report,received=now,lora={k:p.get(k) for k in ('rssi','lsnr','freq','chan','datr')});self.reports+=1
  except (KeyError,ValueError,TypeError,UnicodeError,binascii.Error):
   with self.lock:self.bad+=1
 def topology(self):
  with self.lock:
   now=time.monotonic();rows=[]
   for v in self.nodes.values():
    report=dict(v['report']);age=max(0,int((now-v['received'])*1000));report.update(pc_receive_age_ms=age,transport_age_ms=None)
    report['neighbors']=[dict(r,gateway_elapsed_ms=age,age_is_lower_bound=True) for r in report['neighbors']]
    rows.append(dict(gateway_id=self.eui,gateway_boot=0,report=report,lora=v['lora'],pc_receive_age_ms=age))
   age=min((r['pc_receive_age_ms'] for r in rows),default=None);pull_age=max(0,int((now-self.pull)*1000)) if self.pull is not None else None
   return dict(schema='lora.topology.v1',source='gateway_udp_lrn1',control={'enabled':False,'reason':'下行未启用'},labels={self.eui:'RHF2S008'},receiver=dict(gateway_id=self.eui,state='idle' if age is None else 'receiving' if age<=30000 else 'stale',last_rx_age_ms=age,recent_threshold_ms=30000,gateway_last_pull_age_ms=pull_age,gateway_observed=pull_age is not None and pull_age<=30000,frames=self.reports,bad_frames=self.bad),reports=rows,commands=[],counters={})
class Server(socketserver.ThreadingMixIn,HTTPServer):
 daemon_threads=True
class Handler(BaseHTTPRequestHandler):
 def reply(self,code,obj):
  b=json.dumps(obj,ensure_ascii=False).encode('utf-8');self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_GET(self):
  path=self.path.split('?',1)[0]
  if path=='/api/v1/appliance':return self.reply(200,dict(schema='ann.gateway.appliance.v1',gateway_eui=self.server.state.eui,api_version=1,ready=True))
  if path=='/api/v1/lora/topology':return self.reply(200,self.server.state.topology())
  return self.reply(404,{'error':'not found'})
 def do_POST(self):return self.reply(403,{'error':'remote control disabled'})
 def log_message(self,*args):pass

def bind_interface(sock,name):
 if not name:return
 if not re.match(r'^[A-Za-z0-9_.:-]{1,15}$',name):raise ValueError('invalid interface name')
 if not hasattr(socket,'SO_BINDTODEVICE'):raise OSError('SO_BINDTODEVICE unavailable on this platform')
 sock.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,name.encode('ascii')+b'\x00')

def activated_sockets(interface,http_host,http_port,discovery_host,discovery_port):
 if not interface or not re.match(r'^[A-Za-z0-9_.:-]{1,15}$',interface):raise ValueError('valid interface is required for socket activation')
 if not sys.platform.startswith('linux'):raise ValueError('systemd socket activation requires Linux')
 try:pid=int(os.environ.get('LISTEN_PID',''));count=int(os.environ.get('LISTEN_FDS',''))
 except ValueError:raise ValueError('invalid systemd activation environment')
 if pid!=os.getpid() or count!=2:raise ValueError('systemd activation PID or descriptor count mismatch')
 sockets=[];found={}
 try:
  for fd in (3,4):
   sock=socket.socket(fileno=fd);sockets.append(sock)
   kind=sock.getsockopt(socket.SOL_SOCKET,socket.SO_TYPE)
   if kind not in (socket.SOCK_STREAM,socket.SOCK_DGRAM) or kind in found:raise ValueError('activation socket types mismatch')
   domain=sock.getsockopt(socket.SOL_SOCKET,getattr(socket,'SO_DOMAIN',39))
   if domain!=socket.AF_INET:raise ValueError('activation socket family mismatch')
   device=sock.getsockopt(socket.SOL_SOCKET,getattr(socket,'SO_BINDTODEVICE',25),16).split(b'\x00',1)[0]
   if device!=interface.encode('ascii'):raise ValueError('activation socket interface mismatch')
   expected=(http_host,http_port) if kind==socket.SOCK_STREAM else (discovery_host,discovery_port)
   if sock.getsockname()!=expected:raise ValueError('activation socket address or port mismatch')
   if kind==socket.SOCK_STREAM and sock.getsockopt(socket.SOL_SOCKET,getattr(socket,'SO_ACCEPTCONN',30))!=1:raise ValueError('HTTP socket not listening')
   found[kind]=sock
  for key in ('LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES'):os.environ.pop(key,None)
  return found[socket.SOCK_STREAM],found[socket.SOCK_DGRAM]
 except Exception:
  for sock in sockets:sock.close()
  raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--gateway-eui',required=True);p.add_argument('--forwarder-host',default='127.0.0.1');p.add_argument('--forwarder-port',type=int,default=1680);p.add_argument('--http-host',default='0.0.0.0');p.add_argument('--http-port',type=int,default=8780);p.add_argument('--discovery-host',default='0.0.0.0');p.add_argument('--discovery-port',type=int,default=8781);p.add_argument('--state-file');p.add_argument('--interface',help='restrict HTTP and discovery to this Linux interface');p.add_argument('--systemd-sockets',action='store_true',help='use systemd-passed HTTP and discovery sockets');a=p.parse_args()
 if a.forwarder_host!='127.0.0.1' or not re.match(r'^[0-9a-f]{16}$',a.gateway_eui):p.error('loopback forwarder and lowercase EUI required')
 if a.interface and not a.systemd_sockets and not hasattr(socket,'SO_BINDTODEVICE'):p.error('SO_BINDTODEVICE unavailable on this platform')
 if a.systemd_sockets:
  http_socket,discovery=activated_sockets(a.interface,a.http_host,a.http_port,a.discovery_host,a.discovery_port)
  http=Server((a.http_host,a.http_port),Handler,bind_and_activate=False);http.socket.close();http.socket=http_socket;http.server_address=http_socket.getsockname();http.server_name=a.http_host;http.server_port=a.http_port
 else:
  discovery=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);bind_interface(discovery,a.interface);discovery.bind((a.discovery_host,a.discovery_port))
  http=Server((a.http_host,a.http_port),Handler,bind_and_activate=False);bind_interface(http.socket,a.interface);http.server_bind();http.server_activate()
 state=State(a.gateway_eui);udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind((a.forwarder_host,a.forwarder_port));udp.settimeout(.25);discovery.settimeout(.25);http.state=state;stop=threading.Event()
 def receive():
  while not stop.is_set():
   try:
    data,addr=udp.recvfrom(65535)
    if addr[0]!='127.0.0.1' or len(data)<12 or data[0]!=2 or binascii.hexlify(data[4:12]).decode('ascii')!=state.eui:continue
    kind=data[3]
    if kind==0:
     udp.sendto(data[:3]+bytes([1]),addr)
     try:
      obj=json.loads(data[12:].decode('utf-8'));packets=obj.get('rxpk',[])
      if isinstance(packets,list):
       for packet in packets[:256]:state.ingest(packet)
     except (ValueError,UnicodeError,AttributeError):pass
    elif kind==2:
     udp.sendto(data[:3]+bytes([4]),addr)
     with state.lock:state.pull=time.monotonic()
   except socket.timeout:pass
   except OSError:break
 def discover():
  while not stop.is_set():
   try:
    raw,addr=discovery.recvfrom(1024);v=json.loads(raw.decode('utf-8'));nonce=v.get('nonce')
    if not isinstance(v,dict) or v.get('schema')!=SCHEMA or not isinstance(nonce,str) or not re.match(r'^[0-9a-f]{32}$',nonce):continue
    result=dict(schema=SCHEMA,nonce=nonce,gateway_eui=state.eui,api_version=1,http_port=http.server_port);discovery.sendto(json.dumps(result,separators=(',',':')).encode('utf-8'),addr)
   except (socket.timeout,ValueError,UnicodeError,AttributeError):continue
   except OSError:break
 threads=[threading.Thread(target=receive),threading.Thread(target=discover)]
 for t in threads:t.start()
 print(json.dumps(dict(status='ready',forwarder_port=udp.getsockname()[1],http_port=http.server_port,discovery_port=discovery.getsockname()[1],gateway_eui=state.eui)),flush=True)
 try:http.serve_forever(poll_interval=.2)
 finally:
  stop.set();http.server_close();udp.close();discovery.close()
  for t in threads:t.join(2)
if __name__=='__main__':main()
