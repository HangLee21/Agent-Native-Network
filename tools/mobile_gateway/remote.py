"""Bounded LAN-only discovery and authenticated-by-EUI read-only topology fetch."""
import copy,ipaddress,json,secrets,select,socket,threading,time,urllib.request

def private_ip(host):
 try:
  ip=ipaddress.IPv4Address(host);return ip.is_private or ip.is_link_local or ip.is_loopback
 except ValueError:return False

def get_json(url):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=.7) as response:return json.load(response)

class RemoteGateway:
 def __init__(self,eui,candidates,http_port=8780,discovery_port=8781,broadcast='255.255.255.255'):
  self.eui=eui.lower();self.candidates=[x for x in candidates if private_ip(x)];self.http_port=http_port;self.discovery_port=discovery_port;self.broadcast=broadcast;self.lock=threading.Lock();self.last_at=0;self.cached=None;self.last_good=None;self.good_at=0;self.info={'state':'connecting'}
 def discover(self):
  nonce=secrets.token_hex(16);sockets=[]
  # Bind a separate broadcast socket to each local private IPv4 interface; a
  # direct Ethernet link need not own the machine's default route.
  interfaces=[]
  if self.broadcast=='255.255.255.255':
   try:
    for item in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET,socket.SOCK_DGRAM):
     host=item[4][0]
     if private_ip(host) and not ipaddress.IPv4Address(host).is_loopback and host not in interfaces:interfaces.append(host)
   except OSError:pass
  if not interfaces:interfaces=['0.0.0.0']
  message=json.dumps({'schema':'ann.gateway.discover.v1','nonce':nonce}).encode()
  try:
   for host in interfaces[:16]:
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
     sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);sock.bind((host,0));sock.sendto(message,(self.broadcast,self.discovery_port));sockets.append(sock)
    except OSError:sock.close()
   end=time.monotonic()+.35
   while sockets and time.monotonic()<end:
    readable,_,_=select.select(sockets,[],[],max(0,end-time.monotonic()))
    if not readable:break
    for sock in readable:
     try:raw,addr=sock.recvfrom(2048);v=json.loads(raw.decode('utf-8'))
     except (OSError,ValueError,UnicodeError):continue
     if isinstance(v,dict) and v.get('schema')=='ann.gateway.discover.v1' and v.get('nonce')==nonce and v.get('gateway_eui')==self.eui and v.get('api_version')==1 and type(v.get('http_port')) is int and 1<=v['http_port']<=65535 and private_ip(addr[0]):return addr[0],v['http_port']
  finally:
   for sock in sockets:sock.close()
  return None
 def topology(self):
  with self.lock:
   now=time.monotonic()
   if now-self.last_at<1 and self.cached is not None:return self.cached
   selected=self.discover();targets=([selected] if selected else [])+[(x,self.http_port) for x in self.candidates];seen=set()
   for host,port in targets:
    if (host,port) in seen:continue
    seen.add((host,port));base='http://%s:%d'%(host,port)
    try:
     identity=get_json(base+'/api/v1/appliance')
     if identity.get('schema')!='ann.gateway.appliance.v1' or identity.get('gateway_eui')!=self.eui or identity.get('api_version')!=1 or identity.get('ready') is not True:continue
     topo=get_json(base+'/api/v1/lora/topology')
     if topo.get('schema')!='lora.topology.v1' or topo.get('receiver',{}).get('gateway_id')!=self.eui:continue
     self.info={'state':'connected','gateway_observed':topo['receiver'].get('gateway_observed') is True};self.cached=topo;self.last_at=time.monotonic();self.last_good=copy.deepcopy(topo);self.good_at=self.last_at;return topo
    except (OSError,ValueError,AttributeError):continue
   self.info={'state':'unavailable','gateway_observed':False};now=time.monotonic()
   self.cached=copy.deepcopy(self.last_good) if self.last_good else {'schema':'lora.topology.v1','source':'gateway_udp_lrn1','labels':{},'reports':[],'receiver':{'gateway_id':self.eui}}
   elapsed=max(0,int((now-self.good_at)*1000)) if self.last_good else 0
   for row in self.cached.get('reports',[]):
    if type(row.get('pc_receive_age_ms')) is int:row['pc_receive_age_ms']+=elapsed
   self.cached['receiver'].update(state='unavailable',gateway_observed=False);self.cached['control']={'enabled':False,'reason':'网关未连接'};self.last_at=now;return self.cached
