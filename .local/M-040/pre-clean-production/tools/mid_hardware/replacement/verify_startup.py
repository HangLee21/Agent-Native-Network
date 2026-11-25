import argparse,json,time,secrets,serial,esptool
from pathlib import Path
r=Path(__file__).resolve().parents[3];ap=argparse.ArgumentParser();ap.add_argument('--label',choices=list('ABCDE'),required=True);ap.add_argument('--baud',type=int,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--reset',action='store_true');ap.add_argument('--build');a=ap.parse_args();g=a.output.resolve();assert g.is_relative_to(r/'simulation/outputs/H-006');g.mkdir(exist_ok=False);p=None;raw=bytearray();events=[];buf=bytearray();result={}
def collect(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  data=p.read(max(1,p.in_waiting));raw.extend(data);buf.extend(data)
  while b'\n' in buf:
   line,_,tail=buf.partition(b'\n');buf[:]=tail
   try:e=json.loads(line)
   except Exception:continue
   if isinstance(e,dict):events.append(e)
try:
 mac=json.loads((r/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels'][a.label];b=next(x for x in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']==mac)
 p=serial.Serial(port=None,baudrate=115200 if a.reset else a.baud,timeout=.05,write_timeout=2);p.dtr=False;p.rts=False;p.port=b['port'];p.open()
 if a.reset:
  esp=esptool.detect_chip(p,baud=115200,connect_mode='default_reset',connect_attempts=1);assert ':'.join(f'{v:02x}' for v in esp.read_mac())==mac;p.baudrate=a.baud;esp.hard_reset();result['normal_reset']=True
 collect(3 if a.reset else .2)
 for cmd in ['info','stats']:
  req=dict(cmd=cmd,nonce=secrets.token_hex(8));wire=(json.dumps(req,separators=(',',':'))+'\n').encode();assert p.write(wire)==len(wire);collect(2)
  replies=[e for e in events if e.get('nonce')==req['nonce']];assert len(replies)==1,(cmd,replies);e=replies[0];assert e.get('ok') and e['node_id']==mac and e['mode']=='idle' and not any(e[k] for k in ['radio','stopping','locked_until_reset'])
  if a.build:assert e['build_id']==a.build
  if cmd=='info':assert e['device_label']==a.label
  result[cmd]=e;(g/(cmd+'.json')).write_text(json.dumps(e,indent=2))
 result.update(success=True,flash_writes=0)
except Exception as exc:result.update(success=False,error=repr(exc))
finally:
 if p:p.close()
 result['closed']=p is None or not p.is_open;(g/'startup.raw.bin').write_bytes(raw);(g/'startup.txt').write_text(raw.decode(errors='replace'),encoding='utf-8');(g/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
raise SystemExit(not result.get('success'))
