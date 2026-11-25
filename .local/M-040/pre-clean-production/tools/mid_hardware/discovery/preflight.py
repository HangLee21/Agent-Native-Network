"""H014 service/USB readiness only. Never opens or resets a serial port."""
import argparse,datetime,hashlib,json,os,sys,urllib.request
from pathlib import Path
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import status

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-014');out.mkdir(parents=True,exist_ok=False)
 started=datetime.datetime.now(datetime.timezone.utc).isoformat();r=dict(started_at=started,lease=status(),services={},serial_ports_opened=0,RF_packets=0,host_platform=sys.platform,Ubuntu_physical_hotplug_verified=False)
 for port in (8766,8767):
  try:
   with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status',timeout=3)as response:r['services'][str(port)]=json.load(response)
  except Exception as exc:r['services'][str(port)]=dict(error=repr(exc))
 r['inventory']=[{k:getattr(x,k,None)for k in ('device','vid','pid','location')}for x in list_ports.comports()]
 path=ROOT/'hardware/eora_hub_400tb/bindings.local.json';data=path.read_bytes();r['binding_snapshot_sha256']=hashlib.sha256(data).hexdigest();(out/'bindings.snapshot.json').write_bytes(data)
 r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'result.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes());m.update(template_only=False,task_id='H-014',run_id=out.name,started_at=started,finished_at=r['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),data_and_weights_sha256={'bindings.snapshot.json':r['binding_snapshot_sha256']},status='completed_read_only_preflight',exit_code=0,budget=dict(serial_opens=0,RF_packets=0),limitations=['USB presence and saved bindings do not prove current board identity or idle application.','This Windows preflight is not Ubuntu physical unplug/replug evidence.'])
 (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(dict(lease=r['lease'],services={k:{n:v.get(n)for n in ('busy','active_run_id','run_available','mode')}for k,v in r['services'].items()},USB_ports=r['inventory'],serial_ports_opened=0)))
if __name__=='__main__':main()
