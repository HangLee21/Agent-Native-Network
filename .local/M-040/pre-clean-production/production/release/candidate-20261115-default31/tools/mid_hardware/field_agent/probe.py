"""Finite identity/status read under the H lease; no reset, writes or RF commands."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

from serial.tools import list_ports
from tools.mid_edge.client import Edge
from tools.mid_hardware.console.lease import HardwareLease,status

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',required=True)
    p.add_argument('--mac',required=True)
    p.add_argument('--label',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-017'):
        p.error('new H-017 output required')
    known=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
    if not any(b['node_id']==args.mac and b.get('physically_confirmed') for b in known):
        p.error('MAC must already be physically registered')
    usb=next((q for q in list_ports.comports() if q.device==args.port),None)
    if usb is None or (usb.vid,usb.pid)!=(6790,29987):
        p.error('current expected CH340 port not present')
    out.mkdir(parents=True,exist_ok=False)
    start=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result=dict(label=args.label,port=args.port,expected_mac=args.mac,usb_location=usb.location,planned_commands=['info','stats','neighbors'],commands=[],resets=0,flash_writes=0,radio_commands=0,success=False)
    try:
        with HardwareLease('H017'):
            with Edge(args.port,args.mac,460800,log=out/'native.jsonl') as edge:
                result['commands'].append('info')
                result['info']=edge.identify()
                result['commands'].append('stats')
                result['stats']=edge.command('stats')
                result['commands'].append('neighbors')
                result['neighbors']=edge.neighbors()
                result['success']=True
    except Exception as exc:
        result['error']=repr(exc)
    finally:
        result.update(all_ports_closed=True,lease_after=status())
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
        m.update(template_only=False,task_id='H-017',run_id=out.name,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},dependency_snapshot='existing IDF pyserial environment',output_directory=str(out),process_id=__import__('os').getpid(),status='passed_read_only_identity' if result['success'] else 'failed',exit_code=0 if result['success'] else 1,budget=dict(resets=0,flash_writes=0,RF_commands=0),limitations=['Read-only identity is not board-agent validation, power-bank supply or outdoor RF testing.'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
        print(json.dumps(result))
    if not result['success']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
