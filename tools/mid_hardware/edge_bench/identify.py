"""Bounded info/stats on three already-bound boards; no reset, stop or RF."""
import argparse,datetime,json,secrets,sys,time
from pathlib import Path
import serial
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels'];bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'];results=[]
with HardwareLease('H012'):
 for label in 'ABC':
  binding=next(b for b in bindings if b['node_id']==labels[label]);port=None;raw=bytearray();buf=bytearray();events=[];r=dict(label=label,port=binding['port'],expected_mac=labels[label])
  def command(name):
   c=dict(cmd=name,nonce='h012-'+secrets.token_hex(6));wire=(json.dumps(c)+'\n').encode();assert port.write(wire)==len(wire);events.append(dict(host_tx=c));end=time.monotonic()+2
   while time.monotonic()<end:
    if port.in_waiting:
     d=port.read(port.in_waiting);raw.extend(d);buf.extend(d)
     while b'\n'in buf:
      line,_,tail=buf.partition(b'\n');buf[:]=tail
      try:e=json.loads(line)
      except Exception:continue
      events.append(dict(device_rx=e))
      if e.get('nonce')==c['nonce']:return e
    time.sleep(.003)
   raise RuntimeError('timeout '+name)
  try:
   port=serial.Serial(port=None,baudrate=binding.get('runtime_uart_baud',460800),timeout=0,write_timeout=1);port.dtr=False;port.rts=False;port.port=binding['port'];port.open()
   r['info']=command('info');assert r['info']['node_id']==labels[label];r['stats']=command('stats');assert r['stats']['mode']=='idle' and r['stats']['radio'] is False;r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if port:port.close()
   r.update(closed=port is None or not port.is_open,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/(label+'.raw.bin')).write_bytes(raw);(out/(label+'.events.json')).write_text(json.dumps(events,indent=2));results.append(r);print(json.dumps(r),flush=True)
  if not r['success']:break
(out/'result.json').write_text(json.dumps(results,indent=2));raise SystemExit(not(len(results)==3 and all(r['success']for r in results)))
