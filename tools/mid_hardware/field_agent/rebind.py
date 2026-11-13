"""Read actual MID identities after a physical swap, selecting fresh USB locations only."""
import argparse
import datetime
import json
from pathlib import Path
import secrets
import time

import serial
from serial.tools import list_ports
from tools.mid_hardware.console.lease import HardwareLease,status

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--location',action='append',required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-017'):
        p.error('H-017 output required')
    out.mkdir(parents=True,exist_ok=False)
    known={b['node_id'] for b in json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']}
    inventory=[dict(device=q.device,vid=q.vid,pid=q.pid,location=q.location,hwid=q.hwid) for q in list_ports.comports()]
    result=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),inventory=inventory,selected_locations=a.location,ports=[],resets=0,flash_writes=0,radio_commands=0)
    try:
        with HardwareLease('H017'):
            selected=[q for q in inventory if q['location'] in a.location and (q['vid'],q['pid'])==(6790,29987)]
            for usb in selected:
                row=dict(usb=usb,open_attempted=True)
                result['ports'].append(row)
                wire=serial.Serial(port=None,baudrate=460800,timeout=.1,write_timeout=1)
                wire.dtr=wire.rts=False
                wire.port=usb['device']
                try:
                    wire.open()
                    nonce='h017-rebind-'+secrets.token_hex(8)
                    wire.write((json.dumps(dict(cmd='info',nonce=nonce))+'\n').encode())
                    buffer=bytearray()
                    end=time.monotonic()+4
                    while time.monotonic()<end and 'info' not in row:
                        buffer.extend(wire.read(4096))
                        if len(buffer)>131072:
                            raise ValueError('serial evidence budget exceeded')
                        while b'\n' in buffer:
                            line,_,tail=buffer.partition(b'\n')
                            buffer[:]=tail
                            try:
                                event=json.loads(line)
                            except (ValueError,UnicodeError):
                                continue
                            with (out/(usb['device']+'.jsonl')).open('a',encoding='utf-8') as log:
                                log.write(json.dumps(event)+'\n')
                            if event.get('nonce')==nonce and event.get('cmd')=='info' and event.get('ok'):
                                if event.get('node_id') not in known or event.get('firmware')!='mid-espnow' or event.get('chip')!='esp32s3':
                                    raise ValueError('MID/registered identity mismatch')
                                row['info']=event
                    if 'info' not in row:
                        raise TimeoutError('no MID info; no reset attempted')
                    row['success']=True
                except Exception as exc:
                    row.update(success=False,error=repr(exc))
                finally:
                    wire.close()
                    row['closed']=True
    finally:
        result.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),all_ports_closed=True,lease_after=status())
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))


if __name__=='__main__':
    main()
