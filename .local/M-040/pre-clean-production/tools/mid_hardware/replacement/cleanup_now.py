import serial,json,time,secrets,datetime
from pathlib import Path
r=Path(__file__).resolve().parents[3];g=r/'simulation/outputs/H-006/20261107-fault04-cleanup';g.mkdir(exist_ok=False);results=[]
for b in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']:
 p=None;raw=bytearray();buf=bytearray();events=[];row=dict(expected_MAC=b['node_id'],port=b['port'],stop_confirmed=False)
 def command(name):
  req=dict(cmd=name,nonce=secrets.token_hex(6));wire=(json.dumps(req,separators=(',',':'))+'\n').encode();assert p.write(wire)==len(wire);end=time.monotonic()+1.2
  while time.monotonic()<end:
   if p.in_waiting:
    data=p.read(p.in_waiting);raw.extend(data);buf.extend(data)
    while b'\n' in buf:
     line,_,tail=buf.partition(b'\n');buf[:]=tail
     try:e=json.loads(line)
     except Exception:continue
     events.append(e)
     if e.get('nonce')==req['nonce']:return e
   time.sleep(.003)
  raise RuntimeError('No reply '+name)
 try:
  p=serial.Serial(port=None,baudrate=b.get('runtime_uart_baud',460800),timeout=0,write_timeout=.3);p.dtr=False;p.rts=False;p.port=b['port'];p.open();info=command('info');assert info['node_id']==b['node_id'];row['info']=info;row['stop']=command('stop');row['stats']=command('stats');row['stop_confirmed']=all(row['stats'].get(k) is False for k in ['radio','stopping','locked_until_reset'])
 except Exception as e:row['error']=repr(e)
 finally:
  if p:p.close()
  row['closed']=p is None or not p.is_open;row['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();results.append(row);(g/(b['port']+'.raw.bin')).write_bytes(raw);(g/(b['port']+'.events.json')).write_text(json.dumps(events,indent=2));print(json.dumps(row),flush=True)
(g/'result.json').write_text(json.dumps(results,indent=2))
