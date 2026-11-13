import json,time,argparse,serial
from pathlib import Path
r=Path(__file__).resolve().parents[3];ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();g=a.output.resolve();assert g.is_relative_to(r/'simulation/outputs/H-006');g.mkdir(exist_ok=False);p=None;raw=bytearray();tx=[];events=[];pending=bytearray()
def receive():
 if p.in_waiting:
  data=p.read(p.in_waiting);raw.extend(data);pending.extend(data)
  while b'\n' in pending:
   line,_,tail=pending.partition(b'\n');pending[:]=tail
   try:e=json.loads(line)
   except Exception:continue
   events.append(dict(host_monotonic_ns=time.monotonic_ns(),event=e))
try:
 b=next(x for x in json.loads((r/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']=='90:da:72:48:a5:cc');p=serial.Serial(port=None,baudrate=460800,timeout=0,write_timeout=2);p.dtr=False;p.rts=False;p.port=b['port'];p.open()
 requests=[dict(cmd='info',nonce='post-info')]
 for i in range(20):
  nonce=('post-long-'+str(i)+'-'+'X'*64)[:64] if i%2 else f'post-short-{i}'
  requests.append(dict(cmd='send',nonce=nonce,dst='90:da:72:48:a4:e0',payload_hex=bytes(range(32)).hex()) if i%3==0 else dict(cmd='info',nonce=nonce))
 requests.append(dict(cmd='stats',nonce='post-final-stats'))
 start=time.monotonic()
 for i,cmd in enumerate(requests):
  while time.monotonic()<start+i*.1:receive();time.sleep(.002)
  wire=(json.dumps(cmd,separators=(',',':'))+'\n').encode();assert json.loads(wire)==cmd;n=p.write(wire);p.flush();tx.append(dict(command=cmd,wire_hex=wire.hex(),write_return=n,requested_bytes=len(wire),host_monotonic_ns=time.monotonic_ns()));assert n==len(wire);receive()
 end=time.monotonic()+3
 while time.monotonic()<end:receive();time.sleep(.002)
except Exception as exc:tx.append(dict(error=repr(exc)))
finally:
 if p:p.close()
 replies={x['event'].get('nonce'):x['event'] for x in events if x['event'].get('event')=='command_result'};good=[]
 for item in tx:
  if 'command' not in item:continue
  c=item['command'];e=replies.get(c['nonce']);good.append(bool(e and e.get('cmd')==c['cmd'] and (e.get('ok') if c['cmd']!='send' else e.get('error')=='inactive_or_no_config')))
 stats=replies.get('post-final-stats');result=dict(success=len(good)==22 and all(good) and stats is not None,associated_commands=sum(good),requested_commands=22,final_stats=stats,closed=p is None or not p.is_open,RF_started=False)
 (g/'result.json').write_text(json.dumps(result,indent=2));(g/'TX.json').write_text(json.dumps(tx,indent=2));(g/'events.json').write_text(json.dumps(events,indent=2));(g/'RX.raw.bin').write_bytes(raw);print(json.dumps(result))
raise SystemExit(not result['success'])
