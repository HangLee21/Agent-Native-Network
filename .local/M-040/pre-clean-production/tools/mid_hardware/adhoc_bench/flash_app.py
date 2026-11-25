"""H015 app-only write guarded by current idle info, exact ROM MAC and image SHA."""
import argparse,datetime,hashlib,json,os,secrets,sys,time
from pathlib import Path
import serial,esptool
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--board',required=True,choices=list('ABCD'));ap.add_argument('--image',required=True,type=Path);ap.add_argument('--sha256',required=True);ap.add_argument('--build',required=True);ap.add_argument('--output',required=True,type=Path);ap.add_argument('--flash-baud',type=int,choices=(115200,460800),default=460800);ap.add_argument('--recover-from',type=Path);ap.add_argument('--rom-remap',type=Path);a=ap.parse_args();image=a.image.resolve();assert sha(image)==a.sha256 and 0<image.stat().st_size<=0x100000
 out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-015');out.mkdir(parents=True,exist_ok=False)
 labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels'];b=next(x for x in json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']if x['node_id']==labels[a.board]);port=None;raw=bytearray();buf=bytearray();events=[];r=dict(board=a.board,port=b['port'],image=str(image),image_sha256=a.sha256,expected_build=a.build,write_calls=0,erase_all=False,offset=65536,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
 def cmd(name):
  c=dict(cmd=name,nonce='h015-'+secrets.token_hex(6));wire=(json.dumps(c)+'\n').encode();assert port.write(wire)==len(wire);end=time.monotonic()+2
  while time.monotonic()<end:
   data=port.read(max(1,min(port.in_waiting,4096)));raw.extend(data);buf.extend(data)
   while b'\n'in buf:
    line,_,tail=buf.partition(b'\n');buf[:]=tail
    try:e=json.loads(line)
    except Exception:continue
    events.append(e)
    if e.get('nonce')==c['nonce']:return e
  raise RuntimeError('timeout '+name)
 with HardwareLease('H015'):
  try:
   recovery=None
   if a.recover_from:
    source=a.recover_from.resolve();assert source.is_relative_to(ROOT/'simulation/outputs/H-015');recovery=json.loads(source.read_bytes());assert recovery['success'] is False and recovery['closed'] and recovery['write_calls']==1 and recovery['board']==a.board and recovery['rom_mac']==labels[a.board] and recovery['image_sha256']==a.sha256 and recovery['expected_build']==a.build
    if a.rom_remap:
     proof=a.rom_remap.resolve();assert proof.is_relative_to(ROOT/'simulation/outputs/H-015');mapping=json.loads(proof.read_bytes());assert any(x.get('success') and x['closed'] and x['rom_mac']==labels[a.board] and x['device']==b['port']for x in mapping['ports']);r['rom_remap_proof']=dict(path=str(proof),sha256=sha(proof))
    else:assert recovery['port']==b['port']
    r['recovery_basis']=dict(path=str(source),sha256=sha(source),reason='Previous owned app-only write interrupted; normal application may not boot')
   port=serial.Serial(port=None,baudrate=115200 if recovery else 460800,timeout=.02,write_timeout=2);port.dtr=False;port.rts=False;port.port=b['port'];port.open()
   if not recovery:
    info=cmd('info');r['before_info']=info;assert info['node_id']==labels[a.board] and info['mode']=='idle' and info['radio'] is False,'Not idle, wrong board, or user run in progress'
   port.baudrate=115200;esp=esptool.detect_chip(port,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1);actual=':'.join(f'{x:02x}'for x in esp.read_mac());security=esp.get_security_info();r['rom_mac']=actual;r['security']=security
   assert actual==labels[a.board] and esp.CHIP_NAME=='ESP32-S3';assert not security['parsed_flags']['SECURE_BOOT_EN'] and not security['parsed_flags']['SECURE_DOWNLOAD_ENABLE'] and bin(security['flash_crypt_cnt']).count('1')%2==0
   original=esptool.write_flash
   def guarded(esp,args):
    target,options=esp,args
    assert r['write_calls']==0 and not getattr(options,'erase_all',False) and not getattr(options,'force',False)
    assert {offset:Path(f.name).resolve()for offset,f in options.addr_filename}=={65536:image}
    r['write_calls']+=1;value=original(target,options);r['write_verified']=True;reset=target.hard_reset
    def reset_at_runtime():port.baudrate=460800;reset()
    target.hard_reset=reset_at_runtime;return value
   esptool.write_flash=guarded
   try:esptool.main(['--chip','esp32s3','--port',b['port'],'--baud',str(a.flash_baud),'--after','hard_reset','write_flash','0x10000',str(image)],esp=esp)
   finally:esptool.write_flash=original
   port.baudrate=460800;time.sleep(1);buf.clear();info=cmd('info');r['after_info']=info;assert info['node_id']==labels[a.board] and info['build_id']==a.build
   if info.get('radio') or info.get('mode')!='idle':r['post_boot_stop']=cmd('stop')
   r['stats']=cmd('stats');assert r['stats']['radio'] is False and r['stats']['queue_depth']==0;r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if port:port.close()
   r.update(closed=port is None or not port.is_open,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());(out/'startup.raw.bin').write_bytes(raw);(out/'events.json').write_text(json.dumps(events,indent=2));(out/'result.json').write_text(json.dumps(r,indent=2));print(json.dumps(r))
   m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes());m.update(template_only=False,task_id='H-015',run_id=out.name,started_at=r['started_at'],finished_at=r['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),data_and_weights_sha256={str(image):a.sha256},status='passed'if r.get('success')else'failed',exit_code=0 if r.get('success')else 1,budget=dict(max_app_write_calls=1,offset=65536,erase_all=False),limitations=['App-only update, no bootloader/partition/NVS partition/eFuse writes.','Driver status does not prove physical OLED pixels.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
 return 0 if r.get('success') else 1
if __name__=='__main__':raise SystemExit(main())
