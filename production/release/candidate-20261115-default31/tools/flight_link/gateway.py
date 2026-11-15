"""RHF2S008 Semtech UDP control service; H owns the production socket."""
import argparse,base64,collections,copy,hashlib,json,math,os,re,secrets,socket,sqlite3,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from firmware.mid_baseline.field_agent.lora_ref.decoder import decode_frame
from .archive import Archive

MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
EUI=re.compile(r'^[0-9a-f]{16}$')

class Gateway:
 def __init__(self,gateway_eui,gateway_ip,tx_config,*,clock=time.monotonic,encoder=None,ack_decoder=None,state_file=None):
  if not EUI.fullmatch(gateway_eui):raise ValueError('exact lowercase gateway EUI required')
  socket.inet_aton(gateway_ip)
  required={'freq','rfch','powe','modu','datr','codr','ipol','ncrc'}
  if tx_config is not None:
   if set(tx_config)!=required or tx_config['modu']!='LORA' or tx_config['ipol'] is not False or tx_config['ncrc'] is not False:raise ValueError('explicit TX freq/rfch/powe/modu/datr/codr/ipol required')
   if type(tx_config['freq']) not in (int,float) or not math.isfinite(tx_config['freq']) or not 400<=tx_config['freq']<=500 or type(tx_config['powe']) is not int or type(tx_config['rfch']) is not int:raise ValueError('invalid explicit TX parameters')
  self.eui,self.ip,self.tx=gateway_eui,gateway_ip,copy.deepcopy(tx_config);self.clock=clock;self.encoder=encoder;self.ack_decoder=ack_decoder
  self.lock=threading.RLock();self.pull=None;self.nodes={};self.retired={};self.commands=collections.OrderedDict();self.pending={};self.stats=collections.Counter();self.sock=None;self.last_gateway_send=float('-inf')
  self.state_file=Path(state_file) if state_file else None
  archive_path=self.state_file.with_name(self.state_file.name+'.archive.sqlite3') if self.state_file else None
  self.archive_marker=self.state_file.with_name(self.state_file.name+'.archive-required') if self.state_file else None
  if self.archive_marker and self.archive_marker.exists():
   if self.archive_marker.read_text(encoding='utf-8')!=self.eui or not archive_path.is_file():raise ValueError('required command archive missing or mismatched')
  self.archive=Archive(archive_path,self.eui,required=bool(self.archive_marker and self.archive_marker.exists()))
  if self.state_file and (self.state_file.exists() or self.state_file.with_name(self.state_file.name+'.bak').exists()):
   backup=self.state_file.with_name(self.state_file.name+'.bak');valid=[];primary_bad=False
   for path in (self.state_file,backup):
    try:
     obj=json.loads(path.read_text(encoding='utf-8'))
     if isinstance(obj,dict) and 'payload' in obj:
      payload=obj['payload']
      if not isinstance(payload,str) or obj.get('sha256')!=hashlib.sha256(payload.encode('utf-8')).hexdigest():raise ValueError('journal checksum mismatch')
      obj=json.loads(payload)
     elif path==backup:raise ValueError('backup checksum missing')
     valid.append(self.validate_journal(obj))
    except (FileNotFoundError,ValueError,KeyError,TypeError,UnicodeError):
     if path==self.state_file:primary_bad=True
   if not valid:raise ValueError('invalid command journal and no verified backup')
   saved=valid[0]
   if primary_bad:
    if self.state_file.exists():
     evidence=self.state_file.with_name(self.state_file.name+'.corrupt.'+secrets.token_hex(8))
     with evidence.open('xb') as f:f.write(self.state_file.read_bytes());f.flush();os.fsync(f.fileno())
    self.stats['journal_backup_restored']+=1
   if len(valid)==2 and valid[0]!=valid[1]:
    combined=collections.OrderedDict((c['cmd_id'],c) for c in valid[0]['commands'])
    for other in valid[1]['commands']:
     current=combined.get(other['cmd_id'])
     if current and current['request']!=other['request']:raise ValueError('conflicting journal copies')
     if not current or other['attempts']>current['attempts']:combined[other['cmd_id']]=other
    if len(combined)>256:raise ValueError('journal recovery exceeds capacity')
    for cmd in combined.values():
     if cmd.get('receipt') is None:cmd['state']='execution_unknown_restart' if cmd['attempts'] else 'restart_not_sent'
    saved=dict(schema='flight-command-journal.v1',gateway_eui=self.eui,commands=list(combined.values()))
    self.stats['journal_copies_reconciled']+=1
   for cmd in saved['commands']:
    if cmd['cmd_id'] in self.commands:raise ValueError('duplicate command in journal')
    if cmd['state'] in ('queued','gateway_sent','gateway_accepted','gateway_rejected','target_received'):
     cmd['state']='execution_unknown_restart' if cmd['attempts'] else 'restart_not_sent'
    archived=self.archive.get(cmd['cmd_id'])
    if archived:
     self.archive.put(cmd);self.stats['archive_reconciled']+=1
    else:self.commands[cmd['cmd_id']]=cmd
   self.persist()
 def validate_journal(self,saved):
  if not isinstance(saved,dict) or saved.get('schema')!='flight-command-journal.v1' or saved.get('gateway_eui')!=self.eui or not isinstance(saved.get('commands'),list) or len(saved['commands'])>256:raise ValueError('invalid command journal')
  ids=set()
  for cmd in saved['commands']:
   if not isinstance(cmd,dict) or not isinstance(cmd.get('cmd_id'),str) or not re.fullmatch(r'[0-9a-f]{16}',cmd['cmd_id']) or cmd['cmd_id'] in ids or not isinstance(cmd.get('request'),dict) or not isinstance(cmd.get('state'),str) or type(cmd.get('attempts')) is not int or not 0<=cmd['attempts']<=3:raise ValueError('invalid command entry')
   ids.add(cmd['cmd_id'])
  return saved
 def persist(self):
  if not self.state_file:return
  self.state_file.parent.mkdir(parents=True,exist_ok=True)
  payload=json.dumps(dict(schema='flight-command-journal.v1',gateway_eui=self.eui,commands=list(self.commands.values())),allow_nan=False,separators=(',',':'))
  backup=self.state_file.with_name(self.state_file.name+'.bak')
  envelope=json.dumps(dict(payload=payload,sha256=hashlib.sha256(payload.encode('utf-8')).hexdigest()),separators=(',',':'))
  for target,data in ((self.state_file,envelope),(backup,envelope)):
   tmp=target.with_name(target.name+'.tmp')
   with tmp.open('w',encoding='utf-8') as f:f.write(data);f.flush();os.fsync(f.fileno())
   os.replace(tmp,target)
 def ingest(self,packet):
  try:
   if not isinstance(packet,dict):raise ValueError('rxpk entry must be an object')
   if packet.get('stat')!=1:raise ValueError('radio CRC not valid')
   data=base64.b64decode(packet['data'],validate=True)
   if packet.get('size')!=len(data):raise ValueError('radio frame size mismatch')
   if data.startswith(b'LRN1'):
    report=decode_frame(data);node=report['observer_id'];boot=report['observer_boot'];seq=report['report_seq'];now=self.clock()
    with self.lock:
     old=self.nodes.get(node)
     if boot in self.retired.get(node,set()):self.stats['retired_reports']+=1;return
     if old and old['boot']==boot and (seq<=old['seq'] or report['snapshot_at_ms']<old['report']['snapshot_at_ms']):self.stats['old_reports']+=1;return
     if old and old['boot']!=boot:
      retired=self.retired.setdefault(node,set())
      if len(retired)>=256:raise ValueError('retired boot capacity reached')
      retired.add(old['boot'])
     if not old and len(self.nodes)>=64:raise ValueError('node capacity reached')
     self.nodes[node]=dict(boot=boot,seq=seq,report=report,received=now,lora={k:packet.get(k) for k in ('rssi','lsnr','freq','chan','datr')});self.stats['reports']+=1
    return
   if self.ack_decoder is None:self.stats['unknown_payload']+=1;return
   ack=self.ack_decoder(data)
   with self.lock:
    cmd=self.commands.get(ack['cmd_id']);archived=cmd is None
    if archived:cmd=self.archive.get(ack['cmd_id'])
    if not cmd or (ack['target'],ack['target_boot'],ack.get('report_seq'),ack.get('operation'))!=(cmd['target'],cmd['target_boot'],cmd['request']['report_seq'],cmd['request']['operation']) or (ack.get('executed') and ack.get('operation')=='echo' and ack.get('value')!=cmd['request'].get('value',0)):self.stats['unmatched_receipts']+=1;return
    if cmd.get('receipt') is not None:self.stats['duplicate_receipts']+=1;return
    cmd['receipt']=ack;cmd['receipt_at_monotonic']=self.clock();cmd['state']='executed' if ack.get('executed') is True else 'target_rejected';self.stats['matched_receipts']+=1
    if archived:self.archive.put(cmd)
    else:self.persist()
  except (KeyError,ValueError,TypeError,OverflowError):
   with self.lock:self.stats['invalid_frames']+=1
 def snapshot(self):
  with self.lock:
   now=self.clock();reports=[]
   for node,v in self.nodes.items():
    report=copy.deepcopy(v['report']);age=max(0,int((now-v['received'])*1000));report.update(pc_receive_age_ms=age,transport_age_ms=None)
    for r in report['neighbors']:
     r['gateway_elapsed_ms']=age;r['age_is_lower_bound']=True
    reports.append(dict(gateway_id=self.eui,gateway_boot=0,report=report,lora=v['lora'],pc_receive_age_ms=age))
   latest=min((r['pc_receive_age_ms'] for r in reports),default=None)
   receiver_state='idle' if latest is None else 'receiving' if latest<=30000 else 'stale'
   pull_age=max(0,int((now-self.pull['time'])*1000)) if self.pull else None
   return dict(schema='lora.topology.v1',source='gateway_udp_lrn1',control=dict(enabled=self.tx is not None,reason=None if self.tx is not None else '下行发射参数尚未配置，只接收遥测'),labels={self.eui:'RHF2S008'},receiver=dict(gateway_id=self.eui,state=receiver_state,last_rx_age_ms=latest,recent_threshold_ms=30000,gateway_last_pull_age_ms=pull_age,gateway_observed=pull_age is not None and pull_age<=30000,frames=self.stats['reports'],bad_frames=self.stats['invalid_frames']),reports=reports,commands=copy.deepcopy(list(self.commands.values())),counters=dict(self.stats))
 def enqueue(self,request):
  if self.tx is None:raise ValueError('下行控制未配置；当前仅接收遥测')
  if set(request)-{'cmd_id','target','target_boot','report_seq','operation','value','ttl_ms'}:raise ValueError('unknown command fields')
  cmd_id=request.get('cmd_id');target=request.get('target');boot=request.get('target_boot');op=request.get('operation');ttl=request.get('ttl_ms');seq=request.get('report_seq')
  if not isinstance(cmd_id,str) or not re.fullmatch(r'[0-9a-f]{16}',cmd_id) or int(cmd_id,16)==0 or not isinstance(target,str) or not MAC.fullmatch(target):raise ValueError('16-digit hex cmd_id and canonical target required')
  if type(boot) is not int or not 1<=boot<=0xffffffff or type(seq) is not int or not 1<=seq<=0xffffffff or op not in ('echo','status') or type(ttl) is not int or not 1000<=ttl<=60000:raise ValueError('invalid target boot, report anchor, LRC2 v1 operation or ttl')
  value=request.get('value',0)
  if type(value) is not int or not 0<=value<=0xffffffff or op=='status' and value!=0:raise ValueError('echo value is uint32; status value must be zero')
  with self.lock:
   prior=self.commands.get(cmd_id) or self.archive.get(cmd_id)
   if prior:
    if prior['request']!=request:raise ValueError('command ID already used with different content')
    return copy.deepcopy(prior)
   if len(self.commands)>=256:self.archive_one()
   if sum(x['state']=='queued' for x in self.commands.values())>=64:raise ValueError('command queue full')
   if self.encoder is None:raise ValueError('E1 flight-link command codec unavailable; firmware contract not yet integrated')
   node=self.nodes.get(target)
   if not node or node['boot']!=boot or node['seq']!=seq:raise ValueError('current target boot and most recent observed LRN1 report_seq required')
   if self.clock()-node['received']>=ttl/1000:raise ValueError('local report receipt age already exceeds ttl; get a new report')
   if type(node['lora'].get('freq')) not in (int,float) or abs(node['lora']['freq']-self.tx['freq'])>.0005:raise ValueError('explicit downlink frequency must match the target observed uplink frequency')
   if any(c['target']==target and c['state'] not in ('executed','target_rejected','execution_unknown_timeout','expired_before_gateway_send','target_reboot_invalidated','gateway_send_error','execution_unknown_restart','restart_not_sent') for c in self.commands.values()):raise ValueError('target already has an in-flight command')
   frame=self.encoder(request)
   if not isinstance(frame,bytes) or not 1<=len(frame)<=250:raise ValueError('invalid encoded control frame')
   cmd=dict(cmd_id=cmd_id,target=target,target_boot=boot,request=copy.deepcopy(request),frame_hex=frame.hex(),queued_at_monotonic=self.clock(),expires_monotonic=node['received']+ttl/1000,state='queued',gateway_tx_ack=None,receipt=None,attempts=0,tx_history=[])
   self.commands[cmd_id]=cmd
   try:self.persist()
   except OSError:del self.commands[cmd_id];raise
   return copy.deepcopy(cmd)
 def archive_one(self):
  eligible=('executed','target_rejected','execution_unknown_timeout','expired_before_gateway_send','target_reboot_invalidated','gateway_send_error','execution_unknown_restart','restart_not_sent')
  candidate=next((v for v in self.commands.values() if v['state'] in eligible),None)
  if candidate is None:raise ValueError('active command capacity reached')
  if self.archive_marker and not self.archive_marker.exists():
   with self.archive_marker.open('x',encoding='utf-8') as f:f.write(self.eui);f.flush();os.fsync(f.fileno())
  self.archive.put(candidate)
  del self.commands[candidate['cmd_id']]
  try:self.persist()
  except (OSError,sqlite3.Error):self.commands[candidate['cmd_id']]=candidate;raise
  self.pending={token:ident for token,ident in self.pending.items() if ident!=candidate['cmd_id']}
  self.stats['archived_commands']+=1
 def command(self,cmd_id):
  with self.lock:
   result=self.commands.get(cmd_id) or self.archive.get(cmd_id)
   return copy.deepcopy(result) if result else None
 def flush(self):
  with self.lock:
   now=self.clock()
   changed=False
   for cmd in self.commands.values():
    old_state=cmd['state']
    node=self.nodes.get(cmd['target'])
    if cmd['state'] in ('queued','gateway_sent','gateway_accepted','gateway_rejected') and node and node['boot']!=cmd['target_boot']:
     cmd['state']='target_reboot_invalidated'
    if now>=cmd['expires_monotonic']:
     if cmd['state']=='queued':cmd['state']='expired_before_gateway_send'
     elif cmd['state'] in ('gateway_sent','gateway_accepted','gateway_rejected','target_received'):cmd['state']='execution_unknown_timeout'
    changed|=old_state!=cmd['state']
   if changed:self.persist()
   if not self.pull or now-self.pull['time']>30 or self.sock is None or now-self.last_gateway_send<1:return
   eligible=[c for c in self.commands.values() if c['state']=='queued' or c['state'] in ('gateway_sent','gateway_accepted','gateway_rejected') and c['attempts']<3 and now-c['gateway_sent_at_monotonic']>=1]
   cmd=min(eligible,key=lambda c:(c['attempts'],c['queued_at_monotonic'])) if eligible else None
   if not cmd:return
   while True:
    token=secrets.token_bytes(2)
    if token not in self.pending:break
   payload=bytes.fromhex(cmd['frame_hex']);txpk=dict(self.tx,imme=True,size=len(payload),data=base64.b64encode(payload).decode())
   frame=bytes([2])+token+bytes([3])+json.dumps({'txpk':txpk},separators=(',',':')).encode()
   cmd['attempts']+=1;cmd['tx_history'].append(dict(token=token.hex(),sent_at_monotonic=now,tx_ack=None));cmd.update(state='gateway_sent',gateway_token=token.hex(),gateway_sent_at_monotonic=now)
   self.persist() # durable intent before UDP: a crash is uncertain, never auto-replayed
   try:self.sock.sendto(frame,self.pull['addr'])
   except (OSError,sqlite3.Error) as exc:
    cmd.update(state='gateway_send_error',error=str(exc));self.stats['gateway_send_errors']+=1;self.persist();return
   self.last_gateway_send=now;self.pending[token]=cmd['cmd_id']
 def handle(self,data,addr):
  if addr[0]!=self.ip or len(data)<12 or data[0]!=2 or data[4:12].hex()!=self.eui:self.stats['rejected_gateway_datagrams']+=1;return
  token=data[1:3];kind=data[3]
  if kind==0:
   self.sock.sendto(bytes([2])+token+bytes([1]),addr)
   try:
    obj=json.loads(data[12:]);packets=obj.get('rxpk',[])
    if not isinstance(packets,list):raise ValueError('rxpk must be a list')
    for pkt in packets[:256]:self.ingest(pkt)
   except (ValueError,TypeError,UnicodeDecodeError):self.stats['invalid_push']+=1
  elif kind==2:
   self.sock.sendto(bytes([2])+token+bytes([4]),addr)
   with self.lock:self.pull=dict(addr=addr,time=self.clock())
  elif kind==5:
   with self.lock:
    key=self.pending.pop(token,None)
    if key is None:self.stats['unmatched_tx_ack']+=1;return
    try:ack=json.loads(data[12:]) if data[12:] else {};error=ack.get('txpk_ack',{}).get('error','NONE')
    except (ValueError,TypeError,AttributeError):error='INVALID_TX_ACK'
    cmd=self.commands[key]
    for attempt in cmd['tx_history']:
     if attempt['token']==token.hex():attempt['tx_ack']=error;break
    if cmd['gateway_token']==token.hex():
     cmd['gateway_tx_ack']=error
     if cmd['receipt'] is None and cmd['state'] not in ('execution_unknown_timeout','target_reboot_invalidated'):cmd['state']='gateway_accepted' if error=='NONE' else 'gateway_rejected'
    self.stats['tx_ack']+=1
    self.persist()
  else:self.stats['unknown_gateway_datagrams']+=1

class Handler(BaseHTTPRequestHandler):
 def reply(self,code,obj):
  body=json.dumps(obj,allow_nan=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if urlsplit(self.path).path in ('/','/api/v1/lora/topology'):return self.reply(200,self.server.gateway.snapshot())
  path=urlsplit(self.path).path
  if re.fullmatch(r'/api/v1/commands/[0-9a-f]{16}',path):
   cmd=self.server.gateway.command(path.rsplit('/',1)[1]);return self.reply(200,cmd) if cmd else self.reply(404,{'error':'command not found'})
  return self.reply(404,{'error':'not found'})
 def do_POST(self):
  host=self.headers.get('Host');port=self.server.server_port
  if self.headers.get_all('Host')!=[host] or host not in (f'127.0.0.1:{port}',f'localhost:{port}') or self.headers.get_all('Origin')!=['http://'+host]:return self.reply(403,{'error':'loopback same origin required'})
  if urlsplit(self.path).path!='/api/v1/commands':return self.reply(404,{'error':'not found'})
  try:
   size=int(self.headers.get('Content-Length','0'))
   if not 0<size<=2048 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('bounded JSON required')
   return self.reply(200,self.server.gateway.enqueue(json.loads(self.rfile.read(size))))
  except (ValueError,TypeError,KeyError,OSError,sqlite3.Error) as e:return self.reply(400,{'error':str(e)})
 def log_message(self,*args):pass

def run(args):
 try:
  from .codec import encode_command,decode_receipt
 except ImportError:encode_command=decode_receipt=None
 gateway=Gateway(args.gateway_eui,args.gateway_ip,json.loads(Path(args.tx_config).read_text(encoding='utf-8')) if args.tx_config else None,encoder=encode_command,ack_decoder=decode_receipt,state_file=args.state_file)
 udp=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);udp.bind((args.udp_host,args.udp_port));udp.settimeout(.2);gateway.sock=udp
 http=ThreadingHTTPServer(('127.0.0.1',args.http_port),Handler);http.gateway=gateway;http.daemon_threads=True
 stop=threading.Event()
 def worker():
  while not stop.is_set():
   try:data,addr=udp.recvfrom(65535);gateway.handle(data,addr)
   except socket.timeout:pass
   except (OSError,sqlite3.Error) as exc:
    if not stop.is_set():
     gateway.udp_fatal_error=str(exc);stop.set()
     if not args.duration:http.shutdown()
    break
   try:gateway.flush()
   except OSError as exc:
    gateway.udp_fatal_error='command journal error: '+str(exc);stop.set()
    if not args.duration:http.shutdown()
    break
 thread=threading.Thread(target=worker);thread.start();print(json.dumps(dict(status='ready',udp=list(udp.getsockname()),http_port=http.server_port,codec_available=encode_command is not None)),flush=True)
 try:
  if args.duration:
   http.timeout=.2;until=time.monotonic()+args.duration
   while time.monotonic()<until and not stop.is_set():http.handle_request()
  else:http.serve_forever()
 finally:stop.set();http.server_close();thread.join(2);udp.close();gateway.archive.close()
 if getattr(gateway,'udp_fatal_error',None):raise RuntimeError('gateway UDP loop stopped: '+gateway.udp_fatal_error)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--udp-host',required=True);p.add_argument('--udp-port',type=int,required=True);p.add_argument('--http-port',type=int,default=8780);p.add_argument('--gateway-ip',required=True);p.add_argument('--gateway-eui',required=True);p.add_argument('--tx-config',help='omit for receive-only mode');p.add_argument('--state-file',type=Path,help='durable command journal; use stable writable path');p.add_argument('--duration',type=float,default=0,help='Finite seconds for isolated tests; 0 serves until stopped');a=p.parse_args()
 if a.duration<0:p.error('duration must be nonnegative')
 run(a)
if __name__=='__main__':main()
