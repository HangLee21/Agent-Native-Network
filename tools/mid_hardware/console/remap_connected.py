import serial,json,time,secrets,datetime,hashlib
from pathlib import Path
from serial.tools import list_ports
from lease import ROOT,HardwareLease
out=ROOT/'simulation/outputs/H-007/20261107-08-current-MAC-remap';out.mkdir(exist_ok=False);labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels'];expected=set(labels.values());results=[]
with HardwareLease('H007-recovery'):
 for port in [p for p in list_ports.comports() if p.vid==6790 and p.pid==29987]:
  p=None;raw=bytearray();buf=bytearray();events=[];row=dict(USB={k:getattr(port,k,None) for k in ['device','vid','pid','location','serial_number','hwid']},stop_confirmed=False)
  def command(name):
   c=dict(cmd=name,nonce='map-'+secrets.token_hex(7));wire=(json.dumps(c,separators=(',',':'))+'\n').encode();n=p.write(wire);events.append(dict(kind='host_tx',command=c,wire_hex=wire.hex(),write_return=n,host_monotonic_ns=time.monotonic_ns()));assert n==len(wire);end=time.monotonic()+1.5
   while time.monotonic()<end:
    if p.in_waiting:
     d=p.read(p.in_waiting);raw.extend(d);buf.extend(d)
     while b'\n' in buf:
      line,_,tail=buf.partition(b'\n');buf[:]=tail
      try:e=json.loads(line)
      except Exception:continue
      events.append(dict(kind='device_rx',event=e,host_monotonic_ns=time.monotonic_ns()))
      if e.get('nonce')==c['nonce']:return e
    time.sleep(.003)
   raise RuntimeError('No reply '+name)
  try:
   p=serial.Serial(port=None,baudrate=460800,timeout=0,write_timeout=.5);p.dtr=False;p.rts=False;p.port=port.device;p.open();info=command('info');row['info']=info;assert info['node_id'] in expected and labels[info['device_label']]==info['node_id'];row['stop']=command('stop');state=command('stats');row['stats']=state;row['stop_confirmed']=state['node_id']==info['node_id'] and state['mode']=='idle' and state['queue_depth']==0 and all(state.get(k) is False for k in ['radio','stopping','locked_until_reset'])
  except Exception as exc:row['error']=repr(exc)
  finally:
   if p:p.close()
   row['closed']=p is None or not p.is_open;row['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();results.append(row);(out/(port.device+'.raw.bin')).write_bytes(raw);(out/(port.device+'.events.json')).write_text(json.dumps(events,indent=2));(out/(port.device+'.json')).write_text(json.dumps(row,indent=2));print(json.dumps({k:v for k,v in row.items() if k not in ['info','stop','stats','USB']}|dict(port=port.device,node=row.get('info',{}).get('node_id'),label=row.get('info',{}).get('device_label'))),flush=True)
(out/'result.json').write_text(json.dumps(results,indent=2))
# Only commit a complete one-to-one observed mapping; retain prior mapping as evidence.
if len(results)==5 and {x.get('info',{}).get('node_id') for x in results}==expected and all(x['stop_confirmed'] and x['closed'] for x in results):
 bp=ROOT/'hardware/eora_hub_400tb/bindings.local.json';b=json.loads(bp.read_text());(out/'bindings-before.json').write_text(json.dumps(b,indent=2))
 for row in results:
  i=row['info'];item=next(x for x in b['bindings'] if x['node_id']==i['node_id']);usb=row['USB'];item.update({k:v for k,v in usb.items() if k!='device'});item.update(port=usb['device'],last_verified_boot_id=i['boot_id'],verified_build_id=i['build_id'],runtime_uart_baud=i['uart_baud'],last_info_source=str(out/(usb['device']+'.json')),last_info_sha256=hashlib.sha256((out/(usb['device']+'.json')).read_bytes()).hexdigest(),firmware_state='Actual MAC remapped after reconnection, stop/stats verified',allow_probe=False)
 bp.write_text(json.dumps(b,indent=2));(out/'mapping.json').write_text(json.dumps({x['info']['device_label']:x['USB']['device'] for x in results},indent=2));print('Complete actual MAC mapping committed')
else:print('Mapping incomplete, binding not changed')
