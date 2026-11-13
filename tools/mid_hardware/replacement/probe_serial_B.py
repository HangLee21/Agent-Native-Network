import serial,json,time,secrets
from pathlib import Path
r=Path(__file__).resolve().parents[3];g=r/'simulation/outputs/H-006/20261107-serial-pilot';g.mkdir(exist_ok=False);p=None;raw=bytearray();records=[];result={}
def collect(s):
 end=time.monotonic()+s
 while time.monotonic()<end:
  n=p.in_waiting
  if n:raw.extend(p.read(n))
  time.sleep(.003)
try:
 b=next(x for x in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']=='90:da:72:48:a5:cc')
 p=serial.Serial(port=None,baudrate=115200,timeout=0,write_timeout=2);p.dtr=False;p.rts=False;p.port=b['port'];p.open();collect(.2)
 p.write(b'\n');collect(.1)
 for name in ['stop','info','stats']:
  cmd=dict(cmd=name,nonce='paced-'+secrets.token_hex(5));wire=(json.dumps(cmd,separators=(',',':'))+'\n').encode();records.append(cmd)
  for start in range(0,len(wire),32):p.write(wire[start:start+32]);time.sleep(.012)
  collect(1)
 for line in raw.splitlines():
  try:e=json.loads(line)
  except Exception:continue
  if e.get('nonce') in [c['nonce'] for c in records]:records.append(dict(reply=e))
 replies=[x['reply'] for x in records if 'reply' in x];result=dict(success=len(replies)==3 and all(x.get('ok') for x in replies),replies=replies,stop_confirmed=any(x.get('cmd')=='stats' and not any(x[k] for k in ['radio','stopping','locked_until_reset']) for x in replies))
except Exception as e:result.update(success=False,error=repr(e))
finally:
 if p:p.close()
 result['closed']=p is None or not p.is_open;(g/'raw.bin').write_bytes(raw);(g/'result.json').write_text(json.dumps(result,indent=2));(g/'commands.json').write_text(json.dumps(records,indent=2));print(json.dumps(result))
