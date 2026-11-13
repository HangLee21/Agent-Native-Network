"""Read current app identity on previously approved CH340 USB locations; no reset."""
import argparse,json,secrets,sys,time,datetime
from pathlib import Path
import serial
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_bytes())['bindings'];allowed={(b['vid'],b['pid'],b['location'])for b in bindings};ports=[x for x in list_ports.comports()if (x.vid,x.pid,x.location)in allowed];results=[]
with HardwareLease('H012'):
 for usb in ports:
  port=None;raw=bytearray();r={k:getattr(usb,k,None)for k in ('device','vid','pid','location','hwid')}
  try:
   port=serial.Serial(port=None,baudrate=460800,timeout=.02,write_timeout=1);port.dtr=port.rts=False;port.port=usb.device;port.open();nonce='h012-'+secrets.token_hex(5);port.write((json.dumps(dict(cmd='info',nonce=nonce))+'\n').encode());end=time.monotonic()+2
   while time.monotonic()<end:
    raw.extend(port.read(max(1,min(port.in_waiting,4096))))
    for line in bytes(raw).splitlines():
     try:event=json.loads(line)
     except Exception:continue
     if event.get('nonce')==nonce:r['info']=event;break
    if 'info'in r:break
  except Exception as exc:r['error']=repr(exc)
  finally:
   if port:port.close()
   r['closed']=port is None or not port.is_open;(out/(usb.device+'.raw.bin')).write_bytes(raw);results.append(r);print(json.dumps(r),flush=True)
(out/'result.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),ports=results),indent=2))
