"""H-005 bounded inventory and one existing-firmware info request; never reset/flash/RF."""
import argparse,datetime,hashlib,json,secrets,sys,time
from pathlib import Path
import serial
from serial.tools import list_ports

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--binding-id',default='board1')
    parser.add_argument('--bindings',type=Path,required=True)
    parser.add_argument('--expect-build',required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2]
    result={'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'reset':False,'flash_writes':0,'commands':[],'closed':True}
    raw=bytearray();port=None
    try:
        inventory=[{key:getattr(p,key,None) for key in ('device','description','vid','pid','location','serial_number','hwid')}for p in list_ports.comports()]
        result['inventory']=inventory
        bindings=json.loads(args.bindings.read_text(encoding='utf-8-sig'))['bindings']
        rows=[b for b in bindings if b['id']==args.binding_id]
        if len(rows)!=1:raise RuntimeError('Binding missing or ambiguous')
        b=rows[0]
        if b.get('physically_confirmed') is not True:raise RuntimeError('Binding is not physically confirmed')
        match=[p for p in inventory if all(p[k]==b[k] for k in ('vid','pid','location','device') if k!='device')
               and p['device']==b['port'] and (p['serial_number'] or '')==(b['serial_number'] or '')]
        if len(match)!=1:raise RuntimeError('Bound USB/port association changed; no other port opened')
        result['unbound_usb_candidates']=[p for p in inventory if p['vid']==0x1a86 and p['pid']==0x7523 and p['device']!=b['port']]
        port=serial.Serial(port=None,baudrate=115200,timeout=.05,write_timeout=2,rtscts=False,dsrdtr=False)
        port.dtr=False;port.rts=False;port.port=b['port'];port.open()
        deadline=time.monotonic()+.2
        while time.monotonic()<deadline:raw.extend(port.read(max(1,min(port.in_waiting,4096))))
        request={'cmd':'info','nonce':secrets.token_hex(12)}
        port.write((json.dumps(request)+'\n').encode());result['commands'].append(request)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:raw.extend(port.read(max(1,min(port.in_waiting,4096))))
        events=[]
        for line in raw.splitlines():
            try:
                event=json.loads(line)
                if isinstance(event,dict) and event.get('nonce')==request['nonce']:events.append(event)
            except (ValueError,UnicodeError):pass
        if len(events)!=1:raise RuntimeError('No unique nonce-correlated info response')
        info=events[0];result['info']=info
        expected={'schema':'ann.serial.v1','event':'info','firmware':'ann-espnow','protocol':1,'ok':True,
                  'node_id':b['node_id'],'build_id':args.expect_build,'mode':'idle','chip':'esp32s3'}
        if any(info.get(key)!=value for key,value in expected.items()) or type(info.get('protocol')) is not int:
            raise RuntimeError('Existing ANN identity/build/idle mismatch; no write or RF action')
        result['status']='bound_A_existing_ANN_verified'
    except Exception as exc:result.update(status='stopped',error=repr(exc))
    finally:
        if port is not None:port.close();result['closed']=not port.is_open
        result['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        (out/'serial.raw.bin').write_bytes(raw);(out/'serial.txt').write_text(raw.decode('utf-8',errors='replace'),encoding='utf-8')
        m=json.loads((root/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
        m.update(template_only=False,task_id='H-005',run_id=out.name,started_at=result['started_at'],finished_at=result['finished_at'],worktree=str(root),output_directory=str(out),command=sys.argv,python_executable=sys.executable,dependency_snapshot={'pyserial':serial.VERSION},status=result['status'],git_commit='b7f16ea94c1f4e07045784d06f87362ebc3e84c3',dirty_files_sha256={str(Path(__file__).relative_to(root)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},limitations=['One finite inventory and existing-firmware info only.','No reset/Flash/eFuse/arm/start/bench; no unbound serial port opened.','A prior ANN verification is not a MID or new-display hardware test.'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result['status']!='bound_A_existing_ANN_verified'
if __name__=='__main__':raise SystemExit(main())
