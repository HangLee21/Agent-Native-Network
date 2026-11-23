"""Bounded, read-only CH340 identification and observation under one lease."""
import json,re,secrets,threading,time
from .node_serial import SerialTopology

MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
CH340={(0x1a86,0x7523),(0x1a86,0x55d4)}

class Disabled:
 def __init__(self,mac,reason):self.mac=mac;self.reason=reason
 def topology(self):
  return dict(schema='lora.topology.v1',source='lora_received_snapshot',receiver=dict(mode='node_serial',gateway_id=self.mac,identity_verified=True,gateway_observed=False,serial_open=False,state='not_receiving'),reports=[],labels={},control=dict(enabled=False,reason=self.reason),receive_capable=False)

class SerialDiscovery:
 def __init__(self,sources,lease_dir,*,node_mac=None,location=None,port=None,start=True,port_list=None,serial_factory=None,clock=time.monotonic):
  self.sources=sources;self.clock=clock;self.stop=threading.Event();self.lease=SerialTopology(None,lease_dir=lease_dir,start=False);self.port_list=port_list;self.serial_factory=serial_factory;self.sessions={};self.thread=None;self.error=None
  self.node_mac=node_mac.lower() if node_mac else None;self.location=location;self.port=port;self.cursor=0
  if self.node_mac and not MAC.fullmatch(self.node_mac):raise ValueError('串口节点 MAC 格式无效')
  if start:self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def command(self,wire,name,timeout=1.2):
  if name not in ('info','lora_ref_status'):raise ValueError('只允许只读识别命令')
  nonce=secrets.token_hex(12);request=json.dumps({'cmd':name,'nonce':nonce},separators=(',',':')).encode()+b'\n'
  for offset in range(0,len(request),32):
   part=request[offset:offset+32]
   if wire.write(part)!=len(part):raise OSError('串口写入不完整')
   time.sleep(.012)
  end=self.clock()+timeout;buffer=bytearray()
  while self.clock()<end and not self.stop.is_set():
   buffer.extend(wire.read(512))
   if len(buffer)>8192:raise ValueError('串口响应过长')
   while b'\n' in buffer:
    line,_,tail=buffer.partition(b'\n');buffer=bytearray(tail)
    try:obj=json.loads(line)
    except (ValueError,UnicodeError):continue
    if isinstance(obj,dict) and obj.get('schema')=='mid.serial.v1' and obj.get('event')=='command_result' and obj.get('nonce')==nonce:
     if obj.get('ok') is not True:raise ValueError('设备拒绝只读查询')
     return obj
  raise TimeoutError('设备未响应只读查询')
 def probe(self,port):
  import serial
  factory=self.serial_factory or serial.Serial
  wire=factory(port=None,baudrate=460800,timeout=.05,write_timeout=.5);wire.dtr=False;wire.rts=False;wire.port=port.device
  try:
   wire.open();info=self.command(wire,'info');mac=str(info.get('node_id','')).lower()
   if info.get('firmware')!='mid-espnow' or info.get('chip')!='esp32s3' or not MAC.fullmatch(mac):raise ValueError('不是受支持的节点')
   if self.node_mac and mac!=self.node_mac:raise ValueError('接收节点 MAC 与配置不匹配')
   if info.get('lora_ref_api')!=1:
    self.sources.add_serial(mac,Disabled(mac,'节点不支持 LoRa 参考接收'));return None
   status=self.command(wire,'lora_ref_status')
   generation=status.get('requested_generation');applied=status.get('applied_generation')
   if str(status.get('node_id',mac)).lower()!=mac or status.get('lora_ref_requested_role')!='rx' or status.get('lora_ref_worker_state')!=1 or type(generation) is not int or generation!=applied:
    self.sources.add_serial(mac,Disabled(mac,'节点当前未运行 LoRa RX；未修改设备配置'));return None
   if any(s['mac']==mac for s in self.sessions.values()):raise ValueError('相同节点身份出现于多个串口')
   with self.sources.lock:
    entry=self.sources.entries.get('serial:'+mac);prior=entry['adapter'] if entry else None
    adapter=prior if isinstance(prior,SerialTopology) else SerialTopology(mac,start=False)
    self.sources.add_serial(mac,adapter)
   with adapter.lock:adapter.serial_open=True;adapter.verified=True;adapter.state='receiving';adapter.error=None
   session={'wire':wire,'adapter':adapter,'buffer':bytearray(),'mac':mac};wire=None;return session
  finally:
   if wire is not None:wire.close()
 def scan_once(self,ports=None):
  if ports is None:
   if self.port_list is None:
    from serial.tools.list_ports import comports
    ports=comports()
   else:ports=self.port_list()
  ports=list(ports)
  if self.location:
   candidates=[p for p in ports if p.location==self.location]
  elif self.port:
   candidates=[p for p in ports if p.device.lower()==self.port.lower()]
  else:
   matches=[p for p in ports if (p.vid,p.pid) in CH340]
   # Rotate the bounded batch so an explicitly named MAC can be found beyond
   # the first eight devices without dropping already-open sessions.
   if matches:
    offset=self.cursor%len(matches);ordered=matches[offset:]+matches[:offset];candidates=ordered[:8];self.cursor=(offset+len(candidates))%len(matches)
   else:candidates=[]
  if (self.location or self.port) and len(candidates)!=1:candidates=[]
  current={p.device for p in (ports if not self.location and not self.port else candidates)}
  for name in list(self.sessions):
   if name not in current:self.drop(name)
  for p in candidates:
   if self.stop.is_set():break
   if p.device in self.sessions:continue
   try:
    session=self.probe(p)
    if session:self.sessions[p.device]=session
   except (OSError,ValueError,TimeoutError):continue
 def drain(self):
  for name,s in list(self.sessions.items()):
   try:
    wire=s['wire'];s['buffer'].extend(wire.read(min(max(wire.in_waiting,1),4096)))
    if len(s['buffer'])>8192:raise ValueError('串口数据过长')
    while b'\n' in s['buffer']:
     line,_,tail=s['buffer'].partition(b'\n');s['buffer']=bytearray(tail)
     if b'lora_ref_rx' in line:
      try:s['adapter'].ingest(line.decode('utf-8'))
      except (ValueError,KeyError,TypeError,UnicodeError) as exc:
       if 'MAC' in str(exc):raise ValueError('串口节点身份变化')
   except (OSError,ValueError):self.drop(name)
 def drop(self,name):
  s=self.sessions.pop(name)
  try:s['wire'].close()
  finally:
   with s['adapter'].lock:s['adapter'].serial_open=False;s['adapter'].verified=False;s['adapter'].state='unavailable'
 def run(self):
  while not self.stop.is_set():
   handle=None
   try:
    handle=self.lease.acquire_lease();next_scan=0
    while not self.stop.is_set():
     if self.clock()>=next_scan:self.scan_once();next_scan=self.clock()+5
     self.drain();self.stop.wait(.05)
   except Exception as exc:self.error=str(exc)
   finally:
    for name in list(self.sessions):self.drop(name)
    if handle:handle.close()
   self.stop.wait(2)
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(15)
