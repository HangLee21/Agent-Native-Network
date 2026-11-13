"""Read-only service/lease/USB inventory; does not open serial or reset boards."""
import argparse,datetime,json,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import status
from serial.tools import list_ports
p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
result=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),serial_ports_opened=0,lease=status(),services={})
for port in (8766,8767):
 try:result['services'][str(port)]=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status',timeout=3))
 except Exception as exc:result['services'][str(port)]=dict(error=repr(exc))
result['inventory']=[{k:getattr(z,k,None)for k in ('device','vid','pid','location')}for z in list_ports.comports()]
(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
