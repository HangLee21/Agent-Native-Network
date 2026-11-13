"""H-only finite read of already bound MID boards; never resets, flashes or starts radio."""
import argparse
import json
from pathlib import Path
import secrets
import sys
import time

import serial
from serial.tools import list_ports
from tools.mid_edge.client import Edge
from tools.mid_hardware.console.lease import HardwareLease, status

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--identify-replugged',action='store_true',help='read MID info on currently enumerated CH340 ports; accept only already bound MACs')
    args=p.parse_args()
    output=args.output.resolve()
    if not output.is_relative_to(ROOT/'simulation/outputs/H-016'):
        p.error('H-016 output required')
    output.mkdir(parents=True,exist_ok=False)
    bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
    ports={p.device:dict(device=p.device,vid=p.vid,pid=p.pid,location=p.location) for p in list_ports.comports()}
    result=dict(inventory=list(ports.values()),lease_before=status(),boards=[],radio_commands=0,flash_writes=0,all_ports_closed=False)
    if result['lease_before']['busy']:
        raise SystemExit('hardware already in use; no ports opened')
    try:
        with HardwareLease('H016'):
            if args.identify_replugged:
                known={b['node_id'] for b in bindings}
                for port,usb in ports.items():
                    if (usb['vid'],usb['pid'])!=(6790,29987):
                        continue
                    row=dict(port=port,usb=usb,commands=['info'])
                    result['boards'].append(row)
                    try:
                        wire=serial.Serial(port=None,baudrate=460800,timeout=.1,write_timeout=1)
                        wire.dtr=wire.rts=False
                        wire.port=port
                        try:
                            wire.open()
                            nonce='h016-'+secrets.token_hex(8)
                            wire.write((json.dumps(dict(cmd='info',nonce=nonce))+'\n').encode())
                            buffer=bytearray()
                            deadline=time.monotonic()+3
                            while time.monotonic()<deadline:
                                buffer.extend(wire.read(4096))
                                if len(buffer)>65536:
                                    raise ValueError('UART evidence limit')
                                while b'\n' in buffer:
                                    line,_,buffer=buffer.partition(b'\n')
                                    with (output/(port+'.raw.jsonl')).open('ab') as capture:
                                        capture.write(line+b'\n')
                                    try:
                                        event=json.loads(line)
                                    except (ValueError,UnicodeError):
                                        continue
                                    if event.get('nonce')==nonce and event.get('event')=='command_result' and event.get('cmd')=='info' and event.get('ok'):
                                        row['info']=event
                                if 'info' in row:
                                    break
                            if 'info' not in row:
                                raise TimeoutError('no MID info reply; no reset attempted')
                            info=row['info']
                            row['identity_matched']=info.get('node_id') in known and info.get('firmware')=='mid-espnow' and info.get('chip')=='esp32s3'
                            if not row['identity_matched']:
                                raise ValueError('not an already bound MID identity; no further command')
                        finally:
                            wire.close()
                    except Exception as exc:
                        row['error']=repr(exc)
                    row['closed']=True
                return
            for binding in bindings:
                if binding['port'] not in ports:
                    continue
                row=dict(port=binding['port'],expected_mac=binding['node_id'])
                result['boards'].append(row)
                try:
                    with Edge(binding['port'],binding['node_id'],binding.get('runtime_uart_baud',460800),log=output/(binding['port']+'.jsonl')) as edge:
                        row['info']=edge.identify()
                        row['stats']=edge.command('stats')
                        row['identity_matched']=True
                except Exception as exc:
                    row['error']=repr(exc)
                row['closed']=True
    finally:
        result['all_ports_closed']=True
        result['lease_after']=status()
        (output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result))


if __name__=='__main__':
    main()
