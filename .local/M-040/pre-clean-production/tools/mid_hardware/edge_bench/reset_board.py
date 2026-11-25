"""Bounded ROM identity read and normal reset; never writes flash or eFuse."""
import argparse,datetime,json,sys,time
from pathlib import Path
import esptool,serial
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease

def main():
 p=argparse.ArgumentParser();p.add_argument('--board',required=True,choices=list('ABC'));p.add_argument('--output',type=Path,required=True);p.add_argument('--stop-autostart',action='store_true');a=p.parse_args()
 out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
 labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels'];b=next(x for x in json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']if x['node_id']==labels[a.board])
 r=dict(board=a.board,port=b['port'],started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),flash_writes=0);port=None;raw=bytearray()
 with HardwareLease('H012'):
  try:
   port=serial.Serial(port=None,baudrate=115200,timeout=.02,write_timeout=2);port.dtr=port.rts=False;port.port=b['port'];port.open()
   esp=esptool.detect_chip(port,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1)
   r['rom_mac']=':'.join(f'{x:02x}'for x in esp.read_mac());assert r['rom_mac']==labels[a.board] and esp.CHIP_NAME=='ESP32-S3'
   port.baudrate=460800;esp.hard_reset();end=time.monotonic()+2
   while time.monotonic()<end:raw.extend(port.read(max(1,min(port.in_waiting,4096))))
   if a.stop_autostart:
    port.close();sys.path.insert(0,str(ROOT));from tools.mid_edge import Edge
    with Edge(b['port'],labels[a.board],460800)as local:
     r['after_info']=local.info();assert r['after_info']['deployment_mode']=='offline_table' and r['after_info']['deployment_saved'];r['stop']=local.command('stop');r['stats']=local.command('stats');assert r['stats']['radio'] is False and r['stats']['queue_depth']==0
   r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if port:port.close()
   r.update(closed=port is None or not port.is_open,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/'startup.raw.bin').write_bytes(raw);(out/'result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
 return 0 if r.get('success') else 1
if __name__=='__main__':raise SystemExit(main())
