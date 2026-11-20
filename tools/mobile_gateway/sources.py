"""Independent local observation sources. No device configuration or radio writes."""
import copy, socket, threading, time
from tools.flight_link.gateway import Gateway as UdpGateway

class AsyncSnapshot:
 """Poll a potentially slow adapter without holding the source-manager lock."""
 def __init__(self,adapter,clock=time.monotonic,local_receiver=False):
  self.adapter=adapter;self.clock=clock;self.lock=threading.Lock();self.stop=threading.Event();self.cached=None;self.at=None;self.failed=False;self.local_receiver=local_receiver;self.request_failed=None
  self.thread=threading.Thread(target=self._run,daemon=True);self.thread.start()
 def _run(self):
  while not self.stop.is_set():
   try:
    value=self.adapter.topology()
    if not isinstance(value,dict) or value.get('schema')!='lora.topology.v1':raise ValueError('无效拓扑')
    with self.lock:self.cached=copy.deepcopy(value);self.at=self.clock();self.failed=False;self.request_failed=False
   except Exception as exc:
    with self.lock:self.failed=True;self.request_failed=True if isinstance(exc,OSError) else None
   self.stop.wait(1)
 def topology(self):
  with self.lock:
   value=copy.deepcopy(self.cached);at=self.at;failed=self.failed;request_failed=self.request_failed
  if value is None:value={'schema':'lora.topology.v1','source':'unavailable','receiver':{'state':'connecting','gateway_observed':False},'reports':[],'labels':{},'control':{'enabled':False,'reason':'等待接收来源'}}
  if self.local_receiver and request_failed is not None:value.setdefault('receiver',{})['local_receiver_unreachable']=request_failed
  if at is None:return value
  elapsed=max(0,int((self.clock()-at)*1000))
  for row in value.get('reports',[]):
   if type(row.get('pc_receive_age_ms')) is int:row['pc_receive_age_ms']+=elapsed
   for block in ('status','gps'):
    key=block+'_age_ms'
    if type(row.get(key)) is int:row[key]+=elapsed
   report=row.get('report')
   if isinstance(report,dict) and type(report.get('pc_receive_age_ms')) is int:report['pc_receive_age_ms']+=elapsed
  if failed or elapsed>3000:
   value.setdefault('receiver',{}).update(state='unavailable',gateway_observed=False)
   value['receiver'].pop('worker_state',None)
   if not failed:value['receiver'].pop('local_receiver_unreachable',None)
   value['control']={'enabled':False,'reason':'接收来源未响应'}
  return value
 def close(self):
  self.stop.set();self.thread.join(1)

class Sources:
 def __init__(self, primary=None, kind=None, udp_port=None, udp_host='0.0.0.0', clock=time.monotonic, start=True):
  self.lock=threading.RLock();self.clock=clock;self.entries={};self.selected=None;self.selection_epoch=0;self.manual=None;self.stop=threading.Event();self.sock=None;self.thread=None;self.error=None
  if primary is not None:self.add(kind,primary,{'http':'HTTP 接收器','serial':'串口接收节点','legacy':'本机 UDP 接收器'}.get(kind,kind))
  if udp_port is not None and start:
   try:
    self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.sock.bind((udp_host,udp_port));self.sock.settimeout(.2);self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()
   except OSError as exc:
    self.error=str(exc)
    if self.sock:self.sock.close();self.sock=None
 def add(self,kind,adapter,label):
  if kind in ('http','legacy'):adapter=AsyncSnapshot(adapter,clock=self.clock,local_receiver=(kind=='legacy'))
  with self.lock:self.entries[kind+':configured']={'kind':kind,'adapter':adapter,'label':label}
 def add_serial(self,mac,adapter):
  with self.lock:self.entries['serial:'+mac]={'kind':'serial','adapter':adapter,'label':'串口节点 '+mac}
 def _choose(self,source_id):
  if self.selected!=source_id:self.selected=source_id;self.selection_epoch+=1
 def _loop(self):
  while not self.stop.is_set():
   try:data,addr=self.sock.recvfrom(65535);self.ingest(data,addr)
   except socket.timeout:continue
   except OSError:
    if not self.stop.is_set():self.error='UDP 接收中断'
    break
 def ingest(self,data,addr):
  if len(data)<12 or data[0]!=2 or data[3] not in (0,2):return
  eui=data[4:12].hex();key='udp:'+eui+'@'+addr[0]
  with self.lock:
   entry=self.entries.get(key)
   if entry is None:
    if sum(e['kind']=='udp' for e in self.entries.values())>=32:return
    gateway=UdpGateway(eui,addr[0],None,clock=self.clock);gateway.sock=self.sock
    entry={'kind':'udp','adapter':gateway,'label':'UDP '+eui,'last':None};self.entries[key]=entry
   entry['last']=self.clock();entry['adapter'].handle(data,addr)
 def _snapshot(self,entry):
  try:
   a=entry['adapter'];v=a.snapshot() if entry['kind']=='udp' else a.topology()
   if not isinstance(v,dict) or v.get('schema')!='lora.topology.v1':raise ValueError('无效拓扑')
   v=copy.deepcopy(v);r=v.setdefault('receiver',{})
   if entry['kind']=='udp':
    active=entry['last'] is not None and self.clock()-entry['last']<=30 and self.sock is not None
    r['gateway_observed']=active
    if not active:r['state']='unavailable'
    v['labels']={}
    for row in v.get('reports',[]):
     period=row.get('report',{}).get('report_period_ms',10000);age=row.get('pc_receive_age_ms')
     if type(period) is not int or period<0:period=10000
     threshold=max(35000,3*period+5000);row['recent_threshold_ms']=threshold
     row['node_observation_state']='recent' if type(age) is int and age<=threshold else 'timed_out'
   return v
  except Exception as exc:return {'schema':'lora.topology.v1','source':'unavailable','receiver':{'state':'unavailable','gateway_observed':False,'error':str(exc)},'reports':[],'labels':{},'control':{'enabled':False,'reason':'来源不可用'}}
 def _all(self):
  rows=[];snapshots={}
  for key,entry in list(self.entries.items()):
   v=self._snapshot(entry);snapshots[key]=v;r=v.get('receiver',{});available=r.get('gateway_observed') is True;verified=bool(r.get('identity_verified',available)) or (entry['kind']=='udp' and entry['last'] is not None)
   c=v.get('control') or {};rows.append(dict(id=key,kind=entry['kind'],label=entry['label'],gateway_id=r.get('gateway_id'),state=r.get('state','unavailable'),available=available,verified=verified,selected=False,capabilities=dict(receive=v.get('receive_capable',True),transmit=bool(c.get('enabled')) and verified and available,reason=c.get('reason'))))
  active={r['id'] for r in rows if r['available'] and r['verified']}
  if self.manual in active:self._choose(self.manual)
  elif self.selected not in active and active:self._choose(sorted(active)[0])
  for row in rows:row['selected']=row['id']==self.selected
  return rows,snapshots
 def sources(self):
  with self.lock:
   rows,_=self._all();return dict(schema='lora.sources.v1',selection='manual' if self.manual else 'auto',preferred_source_id=self.manual,selected_source_id=self.selected,selection_epoch=self.selection_epoch,sources=rows,udp_error=self.error)
 def select(self,source_id):
  with self.lock:
   rows,_=self._all()
   if source_id is not None:
    if not isinstance(source_id,str) or not any(r['id']==source_id and r['verified'] for r in rows):raise ValueError('未知或未经验证的来源')
    self.manual=source_id
    if any(r['id']==source_id and r['available'] for r in rows):self._choose(source_id)
   else:self.manual=None
   return self.sources()
 def topology(self):
  with self.lock:
   _,snapshots=self._all()
   value=snapshots.get(self.selected,{'schema':'lora.topology.v1','source':'unavailable','receiver':{'gateway_id':None,'state':'unavailable','gateway_observed':False},'reports':[],'labels':{},'control':{'enabled':False,'reason':'没有可用来源'}})
   if self.selected is None:
    # Surface local receiver health without selecting or asserting an identity.
    local=snapshots.get('legacy:configured',{}).get('receiver',{})
    if type(local.get('local_receiver_unreachable')) is bool:
     value['receiver']['local_receiver_unreachable']=local['local_receiver_unreachable']
    if local.get('state')!='unavailable' and local.get('worker_state') in ('starting','running','recovering','stopped'):
     for key in ('worker_state','worker_error','last_worker_error','last_ack_error','worker_restarts','ack_errors'):
      if key in local:value['receiver'][key]=local[key]
   value['source_id']=self.selected;value['selection_epoch']=self.selection_epoch;return value
 @property
 def info(self):
  r=self.topology().get('receiver',{});return {'state':'connected' if r.get('gateway_observed') else 'unavailable','gateway_observed':r.get('gateway_observed') is True}
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(2)
  if self.sock:self.sock.close()
  for e in self.entries.values():
   a=e['adapter']
   if e['kind']=='udp':a.archive.close()
   elif hasattr(a,'close'):a.close()
