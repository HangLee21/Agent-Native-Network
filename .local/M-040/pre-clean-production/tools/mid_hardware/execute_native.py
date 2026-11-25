"""Bounded real serial capture of E2 frozen native actions; no data retry/ACK."""
import argparse,datetime,hashlib,json,sys,time
from pathlib import Path
import serial
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/mid_baseline/validation'))
import native
MACS={'A':native.A,'B':native.B,'C':'90:da:72:48:a4:e0'}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--case',choices=['AB','AC','BC','AC_controlled_two_hop'],required=True);ap.add_argument('--output',required=True,type=Path);args=ap.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);run=out.name
    labels=['A','B']if args.case=='AB'else['A','B','C'];ports={};buffers={};raws={};events=[];infos={};plan=None;rf_start=None;rf_end=None;success=False;error=None
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();logpath=out/'native.jsonl';log=logpath.open('x',encoding='utf-8')
    def record(obj):obj['host_monotonic_ns']=time.monotonic_ns();log.write(json.dumps(obj)+'\n');log.flush()
    def collect(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            for mac,p in ports.items():
                data=p.read(min(p.in_waiting,8192))if p.in_waiting else b''
                if not data:continue
                raws[mac].write(data);raws[mac].flush();buffers[mac].extend(data)
                while b'\n'in buffers[mac]:
                    line,_,tail=buffers[mac].partition(b'\n');buffers[mac][:]=tail
                    try:e=json.loads(line)
                    except (ValueError,UnicodeError):continue
                    if isinstance(e,dict)and e.get('schema')=='mid.serial.v1':
                        record({'direction':'device_rx','evidence_kind':'hardware_serial','port':p.port,'event':e});events.append(e)
                        if e.get('event')in ['input_queue_overflow','callback_timeout']:raise RuntimeError('Device fatal: '+e['event'])
            time.sleep(.003)
    def command(mac,cmd,timeout=1):
        record({'direction':'host_tx','evidence_kind':'hardware_serial','node_id':mac,'command':cmd});ports[mac].write((json.dumps(cmd)+'\n').encode())
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            collect(.015)
            replies=[e for e in events if e.get('node_id')==mac and e.get('event')=='command_result'and e.get('nonce')==cmd['nonce']]
            if replies:
                if replies[-1].get('ok')is not True:raise RuntimeError('Command rejected: '+str(replies[-1]))
                return replies[-1]
        raise RuntimeError('Reply timeout '+cmd['nonce'])
    try:
        bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text(encoding='utf-8'))['bindings'];inventory=list(list_ports.comports())
        for label in labels:
            mac=MACS[label];b=next(x for x in bindings if x['node_id']==mac)
            assert len([p for p in inventory if p.device==b['port']and p.vid==b['vid']and p.pid==b['pid']and p.location==b['location']])==1
            p=serial.Serial(port=None,baudrate=115200,timeout=0,write_timeout=2,rtscts=False,dsrdtr=False);p.dtr=False;p.rts=False;p.port=b['port'];p.open();ports[mac]=p;buffers[mac]=bytearray();raws[mac]=(out/(label+'.raw.bin')).open('xb')
        collect(.2)
        for label in labels:
            mac=MACS[label];infos[mac]=command(mac,{'cmd':'info','nonce':'identify-'+label});assert infos[mac]['node_id']==mac
            (out/('info-'+label+'.json')).write_text(json.dumps(infos[mac],indent=2),encoding='utf-8')
        plan=native.materialize(infos[native.A],infos[native.B],run)if args.case=='AB'else native.materialize_abc(infos[native.A],infos[native.B],infos[MACS['C']],run,args.case)
        (out/'plan.json').write_text(json.dumps(plan,indent=2),encoding='utf-8')
        ledger=ROOT/'.local/mid/H-005/RF_runs';ledger.mkdir(parents=True,exist_ok=True);assert len(list(ledger.glob('*.json')))<6
        with(ledger/(run+'.json')).open('x')as f:json.dump({'case':args.case,'max_seconds':plan['max_wall_seconds'],'started_at':started},f)
        rf_start=time.monotonic();config_start=None
        for a in plan['actions']:
            if time.monotonic()-rf_start>=plan['max_wall_seconds']:raise RuntimeError('RF run wall limit')
            if 'command'in a:
                if 'at_config_seconds'in a:
                    if config_start is None:config_start=time.monotonic()
                    wait=config_start+a['at_config_seconds']-time.monotonic()
                    if wait>0:collect(wait)
                command(a['board'],a['command'])
                if a.get('interval_ms'):collect(a['interval_ms']/1000)
            elif a['gate']=='bounded drain':collect(a['seconds'])
            elif 'config_applied'in a['gate']:
                deadline=min(rf_start+plan['max_wall_seconds'],time.monotonic()+a['timeout_seconds']);target=max(x['command']['frame_hex']and int.from_bytes(bytes.fromhex(x['command']['frame_hex'])[18:22],'little')for x in plan['actions']if x.get('command',{}).get('cmd')=='config')
                while time.monotonic()<deadline:
                    collect(.03)
                    configured=all(any(e.get('node_id')==m and e.get('event')=='config_applied'and e.get('seq',0)>=target for e in events)for m in ports)
                    rows=a.get('required_routes')
                    if rows:
                        routed=all(any(e.get('event')=='route_selected'and e.get('node_id')==r['node']and e.get('src')==r['src']and e.get('dst')==r['dst']and e.get('next_hop')in[g['node']for g in r['gateways']] for e in events)for r in rows if r['gateways'])
                    else:routed=all(any(e.get('event')=='route_selected'and e.get('node_id')==m and e.get('next_hop')==d for e in events)for m,d in [(native.A,native.B),(native.B,native.A)])
                    if configured and routed:break
                else:raise RuntimeError('Config/route gate timed out; no user data sent')
            else:
                deadline=time.monotonic()+a.get('timeout_seconds',2)
                while time.monotonic()<deadline:
                    states=[command(m,{'cmd':'stats','nonce':'stop-check-'+m[-2:]+'-'+str(time.monotonic_ns())})for m in ports]
                    if all(all(s.get(k)is False for k in ['radio','stopping','locked_until_reset'])for s in states):break
                else:raise RuntimeError('Stop state not confirmed')
        success=True
    except Exception as exc:error=repr(exc)
    finally:
        stopped={}
        for m in ports:
            try:
                command(m,{'cmd':'stop','nonce':'cleanup-'+m[-2:]},.7)
                s=command(m,{'cmd':'stats','nonce':'cleanup-state-'+m[-2:]},.7);stopped[m]=all(s.get(k)is False for k in ['radio','stopping','locked_until_reset'])
            except Exception:stopped[m]=False
        rf_end=time.monotonic()
        for p in ports.values():p.close()
        for f in raws.values():f.close()
        log.close()
        duration=int((rf_end-rf_start)*1e6)if rf_start else 0
        context={'task_id':'H-005','run_id':run,'status':'capture_complete'if success and all(stopped.values())else'capture_failed','evidence_kind':'hardware_measured','package_manifest_sha256':native.PACKAGE_HASH,'log_sha256':{str(logpath):hashlib.sha256(logpath.read_bytes()).hexdigest()},'coverage':{m:success and stopped.get(m,False)for m in ports},'measurement_duration_us':duration,'duration_clock':'host_monotonic_controlled_window'}
        (out/'context.json').write_text(json.dumps(context,indent=2),encoding='utf-8');result={'success':success,'error':error,'stop_confirmed':stopped,'all_ports_closed':all(not p.is_open for p in ports.values()),'RF_window_seconds':duration/1e6,'rx_local_observed':sum(e.get('event')=='rx_local'for e in events)}
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return not success
if __name__=='__main__':raise SystemExit(main())
