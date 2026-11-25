import serial,json,time,secrets,argparse,datetime
from pathlib import Path
from lease import ROOT,HardwareLease
ap=argparse.ArgumentParser();ap.add_argument('--run-id',required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-007');out.mkdir(exist_ok=False);p=None;raw=bytearray();buf=bytearray();rows=[];result=dict(run_id=a.run_id,flash_writes=0,data_sends=0,RF_started=False,stop_confirmed=False)
def cmd(name):
 c=dict(cmd=name,nonce='recovery-'+secrets.token_hex(6));wire=(json.dumps(c,separators=(',',':'))+'\n').encode();n=p.write(wire);rows.append(dict(kind='host_tx',command=c,wire_hex=wire.hex(),write_return=n,requested_bytes=len(wire),host_monotonic_ns=time.monotonic_ns()));assert n==len(wire)
 end=time.monotonic()+2
 while time.monotonic()<end:
  if p.in_waiting:
   d=p.read(p.in_waiting);raw.extend(d);buf.extend(d)
   while b'\n' in buf:
    line,_,tail=buf.partition(b'\n');buf[:]=tail
    try:e=json.loads(line)
    except Exception:continue
    rows.append(dict(kind='device_rx',event=e,host_monotonic_ns=time.monotonic_ns()))
    if e.get('nonce')==c['nonce']:return e
  time.sleep(.003)
 raise RuntimeError('timeout '+name)
with HardwareLease('H007-recovery'):
 try:
  from serial.tools import list_ports
  b=next(x for x in json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings'] if x['node_id']=='90:da:72:48:a4:f8');inv=[{k:getattr(z,k,None) for k in ['device','vid','pid','location']} for z in list_ports.comports()];assert any(z['device']==b['port'] and z['location']==b['location'] and z['vid']==b['vid'] and z['pid']==b['pid'] for z in inv);result.update(USB=b,inventory=inv,baud=460800)
  p=serial.Serial(port=None,baudrate=460800,timeout=0,write_timeout=.5);p.dtr=False;p.rts=False;p.port=b['port'];p.open();i=cmd('info');assert i['node_id']==b['node_id'] and i['device_label']=='A' and i['uart_baud']==460800;result['info']=i;result['stop']=cmd('stop');s=cmd('stats');assert s['node_id']==b['node_id'];result['stats']=s;result['stop_confirmed']=s.get('mode')=='idle' and all(s.get(k) is False for k in ['radio','stopping','locked_until_reset']) and s.get('queue_depth')==0;result['success']=result['stop_confirmed']
 except Exception as exc:result.update(success=False,error=repr(exc))
 finally:
  if p:p.close()
  result.update(closed=p is None or not p.is_open,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/'raw.bin').write_bytes(raw);(out/'events.json').write_text(json.dumps(rows,indent=2));(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ['USB','inventory']}))
raise SystemExit(not result.get('success'))
