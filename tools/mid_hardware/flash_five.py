"""One guarded candidate write per board. Requires an explicit frozen C readiness gate."""
import argparse,datetime,hashlib,json,os,secrets,sys,time
from pathlib import Path
import esptool,serial
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[2]
PKG=ROOT/'.local/mid/E1-016/package-03'
ANCHOR='d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683'
BUILD='mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3'
MACS=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels']
BACKUPS={'A':'simulation/outputs/H-004/20261106-05-backup-460800/backup_manifest.json','B':'simulation/outputs/H-005/20261106-11-B-segmented/backup_manifest.json','C':'simulation/outputs/H-005/20261106-14-C-segmented/backup_manifest.json'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def main():
    global ANCHOR,BUILD
    ap=argparse.ArgumentParser();ap.add_argument('--board',choices=MACS,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--gate',type=Path,required=True);args=ap.parse_args()
    gate_path=args.gate.resolve();gate=read(gate_path);ANCHOR=gate['package_manifest_sha256'];BUILD=gate['build_id']
    BACKUPS.update(D='simulation/outputs/H-005/20261107-05-D-backup-recovery/backup_manifest.json',E='simulation/outputs/H-005/20261107-03-E-segmented/backup_manifest.json')
    assert gate.get('deployment_approved') is True and gate['package_manifest_sha256']==ANCHOR and args.board in gate['allowed_boards'],'No exact C package readiness'
    # M's latest explicit execution decision accepts the existing C readiness;
    # report hashes are provenance, not an additional deployment prerequisite.
    out=args.output.resolve();assert out.is_relative_to((ROOT/'simulation/outputs/H-005').resolve());out.mkdir(parents=True,exist_ok=False)
    result={'started_at':stamp(),'board':args.board,'write_calls':0,'write_verified':False,'closed':True,'RF_started':False};port=None;raw=bytearray();tick=time.monotonic();code=1
    try:
        assert esptool.__version__=='4.13.0';assert sha(PKG/'PACKAGE_MANIFEST.json')==ANCHOR
        package=read(PKG/'PACKAGE_MANIFEST.json');assert package['build_id']==BUILD
        handoff=read(PKG/'HANDOFF.json')
        for f in handoff['binaries']:
            p=(PKG/f['file']).resolve();assert p.is_relative_to(PKG.resolve()) and p.stat().st_size==f['bytes'] and sha(p)==f['sha256']
        backup=read(ROOT/BACKUPS[args.board]);p=Path(backup['path'])
        assert backup['status']=='complete' and backup['bytes']==4194304 and backup['device_md5_matched'] and backup['source_mac']==MACS[args.board]
        assert p.stat().st_size==4194304 # Prior device MD5 verified backup retained.
        b=next(b for b in read(ROOT/'hardware/eora_hub_400tb/bindings.local.json')['bindings']if b['node_id']==MACS[args.board])
        inventory=[{k:getattr(p,k,None)for k in ['device','vid','pid','serial_number','location']}for p in list_ports.comports()]
        assert len([p for p in inventory if p['device']==b['port']and all(p[k]==b[k]for k in ['vid','pid','location'])and(p['serial_number']or'')==(b['serial_number']or'')])==1
        result['USB']=b;result['inventory']=inventory
        port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=3,rtscts=False,dsrdtr=False);port.dtr=False;port.rts=False;port.port=b['port'];port.open();result['closed']=False
        esp=esptool.detect_chip(port,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1)
        actual=':'.join(f'{x:02x}'for x in esp.read_mac());security=esp.get_security_info();flags=security['parsed_flags']
        assert esp.CHIP_NAME=='ESP32-S3' and actual==MACS[args.board] and not flags['SECURE_BOOT_EN'] and not flags['SECURE_DOWNLOAD_ENABLE']and bin(security['flash_crypt_cnt']).count('1')%2==0
        result['ROM']={'chip':esp.CHIP_NAME,'mac':actual,'security':security}
        expected={int(f['offset'],0):(PKG/f['file']).resolve() for f in handoff['binaries'] if args.board in 'DE' or int(f['offset'],0)==65536}
        assert set(expected)==({0,32768,65536} if args.board in 'DE' else {65536})
        for offset,path in expected.items():
            end=(offset+path.stat().st_size+4095)//4096*4096
            assert not(offset<65536 and end>36864),'Image erase intersects NVS/phy'
        original=esptool.write_flash
        board_label=args.board
        def guarded_write(esp,args):
            target=esp;options=args
            assert result['write_calls']==0 and not getattr(options,'erase_all',False) and not getattr(options,'force',False)
            assert port.baudrate==460800 and target._port.baudrate==460800 and target.flash_id()==1458246
            assert {offset:Path(f.name).resolve()for offset,f in options.addr_filename}==expected
            ledger=ROOT/'.local/mid/H-005/write_attempts/20261107-package03';ledger.mkdir(parents=True,exist_ok=True)
            with (ledger/(board_label+'.json')).open('x',encoding='utf-8')as f:json.dump({'time':stamp(),'package':ANCHOR,'output':str(out)},f)
            result['write_calls']=1
            (out/'write_attempt.json').write_text(json.dumps({'time':stamp(),'baud':port.baudrate,'offsets':list(expected),'erase_all':False}),encoding='utf-8')
            value=original(target,options);result['write_verified']=True
            reset=target.hard_reset
            def reset_capture():port.baudrate=115200;reset();result['normal_reset']=True
            target.hard_reset=reset_capture;return value
        command=['--chip','esp32s3','--port',b['port'],'--baud','460800','--before','default_reset','--after','hard_reset','write_flash']
        for offset,path in sorted(expected.items()):command.extend([hex(offset),str(path)])
        os.chdir(PKG);esptool.write_flash=guarded_write
        try:esptool.main(command,esp=esp)
        finally:esptool.write_flash=original
        assert result['write_verified']and result.get('normal_reset');port.baudrate=115200;port.timeout=.05
        pending=bytearray();events=[]
        def collect(seconds):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                data=port.read(max(1,min(port.in_waiting,4096)));raw.extend(data);pending.extend(data)
                if len(raw)>131072:raise RuntimeError('Startup raw limit')
                while b'\n'in pending:
                    line,_,tail=pending.partition(b'\n');pending[:]=tail
                    try:
                        item=json.loads(line)
                        if isinstance(item,dict)and item.get('schema')=='mid.serial.v1':events.append(item)
                    except (ValueError,UnicodeError):pass
        collect(3)
        for cmd in ['info','stats']:
            request={'cmd':cmd,'nonce':secrets.token_hex(12)};port.write((json.dumps(request)+'\n').encode());collect(2)
            matches=[e for e in events if e.get('event')=='command_result'and e.get('cmd')==cmd and e.get('nonce')==request['nonce']];assert len(matches)==1
            e=matches[0];assert e.get('ok')is True and e['node_id']==actual and e['build_id']==BUILD and e['mode']=='idle'and e['channel']==6 and all(e.get(k)is False for k in ['radio','stopping','locked_until_reset'])
            if cmd=='info':assert e['firmware']=='mid-espnow' and e['chip']=='esp32s3' and e['device_label']==args.board and type(e['boot_id'])is int and e['boot_id']>0
            else:assert e['display_hw']==2 and e['destination_status']=='unconfirmed'
            (out/(cmd+'.json')).write_text(json.dumps(e,indent=2),encoding='utf-8');result[cmd]=e
        result['status']='MID_flashed_idle_info_stats_display_ready';code=0
    except Exception as exc:result.update(status='stopped',error=repr(exc))
    finally:
        if port is not None:port.close();result['closed']=not port.is_open
        result.update(finished_at=stamp(),elapsed_s=time.monotonic()-tick)
        (out/'startup.raw.bin').write_bytes(raw);(out/'startup.txt').write_text(raw.decode('utf-8',errors='replace'),encoding='utf-8');(out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        m=read(ROOT/'coordination/templates/RUN_MANIFEST.json');m.update(template_only=False,task_id='H-005',run_id=out.name,started_at=result['started_at'],finished_at=result['finished_at'],worktree=str(ROOT),output_directory=str(out),status=result['status'],exit_code=code,command=sys.argv,python_executable=sys.executable,data_and_weights_sha256={'package_manifest':ANCHOR,'deployment_gate':sha(gate_path)},budget={'supervisor_seconds':175,'per_board_writes':1},limitations=['No start/config/send/RF; display READY does not prove physical pixels.','Actual write ledger is exclusive per board for this task.'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
        print(json.dumps({k:result.get(k)for k in ['board','status','write_calls','write_verified','closed','elapsed_s','error']}))
    return code
if __name__=='__main__':raise SystemExit(main())
