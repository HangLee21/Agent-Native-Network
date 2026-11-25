import serial,esptool,json,time,secrets
from pathlib import Path
r=Path(__file__).resolve().parents[3];g=r/'simulation/outputs/H-006/20261107-00-A-recovery';g.mkdir(exist_ok=False);p=None;raw=bytearray();result={}
try:
 b=next(x for x in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']=='90:da:72:48:a4:f8')
 p=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2);p.dtr=False;p.rts=False;p.port=b['port'];p.open()
 esp=esptool.detect_chip(p,baud=115200,connect_mode='default_reset',connect_attempts=1);mac=':'.join(f'{v:02x}' for v in esp.read_mac());assert mac==b['node_id'];result['ROM_MAC']=mac
 p.baudrate=115200;esp.hard_reset();until=time.monotonic()+4
 while time.monotonic()<until:raw.extend(p.read(max(1,p.in_waiting)))
 request={'cmd':'info','nonce':secrets.token_hex(12)};p.write((json.dumps(request)+'\n').encode());until=time.monotonic()+2
 while time.monotonic()<until:raw.extend(p.read(max(1,p.in_waiting)))
 infos=[]
 for line in raw.splitlines():
  try:e=json.loads(line)
  except Exception:continue
  if e.get('nonce')==request['nonce']:infos.append(e)
 assert len(infos)==1 and infos[0]['node_id']==mac and infos[0]['mode']=='idle';result.update(success=True,info=infos[0],flash_writes=0)
except Exception as exc:result.update(success=False,error=repr(exc))
finally:
 if p:p.close()
 result['closed']=p is None or not p.is_open;(g/'result.json').write_text(json.dumps(result,indent=2));(g/'startup.raw.bin').write_bytes(raw);(g/'startup.txt').write_text(raw.decode(errors='replace'));print(json.dumps(result))
raise SystemExit(not result.get('success'))
