import serial,json,time
from pathlib import Path
r=Path(__file__).resolve().parents[3];g=r/'simulation/outputs/H-006/20261107-B-input-before-fix';g.mkdir(exist_ok=False);raw=bytearray();tx=[];p=None
try:
 b=next(x for x in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']=='90:da:72:48:a5:cc')
 p=serial.Serial(port=None,baudrate=115200,timeout=0,write_timeout=2);p.dtr=False;p.rts=False;p.port=b['port'];p.open()
 requests=[dict(cmd='info',nonce='short01'),dict(cmd='info',nonce='L'*64),dict(cmd='send',nonce='send32',dst='90:da:72:48:a4:e0',payload_hex=bytes(range(32)).hex()),dict(cmd='stats',nonce='laststats')]
 for cmd in requests:
  wire=(json.dumps(cmd,separators=(',',':'))+'\n').encode();assert json.loads(wire)==cmd
  begin=time.monotonic_ns();n=p.write(wire);p.flush();tx.append(dict(command=cmd,wire_hex=wire.hex(),requested_bytes=len(wire),write_return=n,host_monotonic_ns=begin,single_writer=True));assert n==len(wire)
  until=time.monotonic()+2
  while time.monotonic()<until:
   if p.in_waiting:raw.extend(p.read(p.in_waiting))
   time.sleep(.003)
except Exception as e:tx.append(dict(error=repr(e)))
finally:
 if p:p.close()
 (g/'TX.json').write_text(json.dumps(tx,indent=2));(g/'RX.raw.bin').write_bytes(raw);(g/'RX.txt').write_text(raw.decode(errors='replace'))
 replies=[]
 for line in raw.splitlines():
  try:e=json.loads(line)
  except Exception:continue
  if e.get('event')=='command_result':replies.append(e)
 (g/'result.json').write_text(json.dumps(dict(tx=tx,replies=replies,closed=p is None or not p.is_open,RF_started=False),indent=2));print(json.dumps(dict(tx_bytes=[a.get('write_return') for a in tx],replies=[dict(cmd=e.get('cmd'),nonce=e.get('nonce'),ok=e.get('ok'),error=e.get('error'),radio=e.get('radio')) for e in replies],closed=p is None or not p.is_open)))
