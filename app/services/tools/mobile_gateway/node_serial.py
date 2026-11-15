"""Node-1 serial LoRa observation; port selection requires a verified USB location."""
import copy,datetime,json,msvcrt,os,threading,time
from pathlib import Path
from firmware.mid_baseline.field_agent.lora_ref.decoder import decode_serial_line

class SerialTopology:
 def __init__(self,mac,location=None,port=None,lease_dir=None,clock=time.monotonic,start=True):
  self.mac=mac;self.location=location;self.port=port;self.lease_dir=Path(lease_dir) if lease_dir else None;self.clock=clock;self.lock=threading.RLock();self.stop=threading.Event();self.rows={};self.retired={};self.serial_open=False;self.verified=False;self.last_rx=None;self.error=None;self.state='connecting';self.info={'state':'unavailable','gateway_observed':False};self.thread=None
  if start:self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
 def ingest(self,line):
  event=decode_serial_line(line)
  if event['gateway_id']!=self.mac:raise ValueError('接收节点 MAC 与节点1不匹配')
  r=event['report'];node=r['observer_id'];boot=r['observer_boot'];seq=r['report_seq']
  with self.lock:
   old=self.rows.get(node)
   if boot in self.retired.get(node,set()):return False
   if old:
    previous=old['event']['report']
    if boot==previous['observer_boot'] and not 0<((seq-previous['report_seq'])&0xffffffff)<0x80000000:return False
    if boot!=previous['observer_boot']:
     retired=self.retired.setdefault(node,set())
     if len(retired)>=256:raise ValueError('节点启动记录已满')
     retired.add(previous['observer_boot'])
   if node not in self.rows and len(self.rows)>=64:raise ValueError('节点数超过上限')
   now=self.clock();self.rows[node]={'event':event,'received':now,'at':datetime.datetime.now(datetime.timezone.utc).isoformat()};self.last_rx=now;self.verified=True;self.state='receiving';self.error=None;return True
 def topology(self):
  with self.lock:
   now=self.clock();observed=self.serial_open and self.verified;last=None if self.last_rx is None else max(0,int((now-self.last_rx)*1000));reports=[]
   for item in self.rows.values():
    row=copy.deepcopy(item['event']);age=max(0,int((now-item['received'])*1000));period=row['report'].get('report_period_ms',10000);threshold=max(35000,3*period+5000);row.update(pc_receive_age_ms=age,pc_received_at=item['at'],node_observation_state='recent' if age<=threshold else 'timed_out',recent_threshold_ms=threshold);reports.append(row)
   state=self.state if not observed else ('stale' if last is not None and last>35000 else 'receiving')
   self.info={'state':'connected' if observed else 'unavailable','gateway_observed':observed}
   return dict(schema='lora.topology.v1',source='lora_received_snapshot',labels={},receiver=dict(mode='node_serial',gateway_id=self.mac,gateway_observed=observed,serial_open=self.serial_open,state=state,last_rx_age_ms=last,error=self.error,identity_verified=self.verified),reports=reports,control={'enabled':False,'reason':'节点串口仅接收'})
 def select_port(self):
  if not self.location and not self.port:raise ValueError('等待节点1串口身份确认')
  from serial.tools.list_ports import comports
  ports=list(comports())
  if self.location:
   matched=[p.device for p in ports if p.location==self.location]
   if len(matched)!=1:raise ValueError('已核验 USB 位置不可用或不唯一')
   return matched[0]
  if self.port:
   if sum(p.device.lower()==self.port.lower() for p in ports)!=1:raise ValueError('已核验串口不可用')
   return self.port
  raise ValueError('等待节点1串口身份确认')
 def acquire_lease(self):
  if not self.lease_dir:raise ValueError('等待 H 指定共享串口租约目录')
  self.lease_dir.mkdir(parents=True,exist_ok=True)
  reservation=self.lease_dir/'reservation.json'
  if reservation.exists():
   value=json.loads(reservation.read_text(encoding='utf-8'))
   if value.get('owner')!='H020-Studio-LoRa':raise ValueError('串口已由其他任务保留')
  handle=(self.lease_dir/'serial.lock').open('a+b')
  try:
   if handle.seek(0,2)==0:handle.write(b'0');handle.flush()
   handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
   (self.lease_dir/'owner.json').write_text(json.dumps(dict(owner='H020-Studio-LoRa',pid=os.getpid(),started_at=time.time())),encoding='utf-8')
   return handle
  except Exception:handle.close();raise
 def run(self):
  import serial
  while not self.stop.is_set():
   wire=None;lease=None
   try:
    lease=self.acquire_lease();port=self.select_port();wire=serial.Serial(port=None,baudrate=460800,timeout=.2);wire.dtr=False;wire.rts=False;wire.port=port;wire.open()
    with self.lock:self.serial_open=True;self.verified=False;self.state='connecting';self.error=None
    buffer=bytearray();discard=False
    while not self.stop.is_set():
     part=wire.read(min(max(wire.in_waiting,1),4096));buffer.extend(part)
     while b'\n' in buffer:
      line,_,remaining=buffer.partition(b'\n');buffer=bytearray(remaining)
      if discard or len(line)>2048:discard=False;continue
      try:
       if b'lora_ref_rx' in line:self.ingest(line.decode('utf-8'))
      except (ValueError,KeyError,TypeError,UnicodeError) as exc:
       if 'MAC' in str(exc):raise ValueError(str(exc))
     if len(buffer)>2048:buffer.clear();discard=True
   except Exception as exc:
    with self.lock:self.error=str(exc);self.state='busy' if isinstance(exc,serial.SerialException) or (lease is None and isinstance(exc,OSError)) else 'unavailable'
   finally:
    if wire:
     try:wire.close()
     except Exception:pass
    if lease:lease.close()
    with self.lock:self.serial_open=False;self.verified=False
   self.stop.wait(2)
 def close(self):
  self.stop.set()
  if self.thread:self.thread.join(5)
