"""ROM-read only for the two approved A/C USB ports lacking app responses."""
import argparse,datetime,json,sys,time
from pathlib import Path
import esptool,serial
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];allowed={labels[k]for k in 'AC'};missing=[x for x in json.loads(a.source.read_bytes())['ports']if 'info'not in x];assert {x['device']for x in missing}=={'COM7','COM12'};results=[]
with HardwareLease('H012'):
 for usb in missing:
  port=None;raw=bytearray();r=dict(usb,flash_writes=0)
  try:
   port=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=2);port.dtr=port.rts=False;port.port=usb['device'];port.open();esp=esptool.detect_chip(port,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1);r['rom_mac']=':'.join(f'{x:02x}'for x in esp.read_mac());assert r['rom_mac']in allowed and esp.CHIP_NAME=='ESP32-S3';port.baudrate=460800;esp.hard_reset();end=time.monotonic()+1.5
   while time.monotonic()<end:raw.extend(port.read(max(1,min(port.in_waiting,4096))))
   r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if port:port.close()
   r['closed']=port is None or not port.is_open;results.append(r);(out/(usb['device']+'.raw.bin')).write_bytes(raw);print(json.dumps(r),flush=True)
(out/'result.json').write_text(json.dumps(dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),ports=results),indent=2))
raise SystemExit(not(all(x.get('success')for x in results) and {x['rom_mac']for x in results}==allowed))
