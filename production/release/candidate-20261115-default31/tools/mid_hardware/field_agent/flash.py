"""Explicit H-017 app-only flash, guarded by fresh application and ROM identities.

Only use a formal package and retained rollback image; no unbound-port recovery.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import secrets
import sys
import time

import esptool
import serial
from tools.mid_hardware.console.lease import HardwareLease

ROOT=Path(__file__).resolve().parents[3]
PRIVATE={'ssid','password','passphrase','bssid'}


def redact(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if k.lower() in PRIVATE else redact(v)) for k,v in value.items()}
    if isinstance(value,list):
        return [redact(v) for v in value]
    return value


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['port','mac','current-build','target-build','sha256','rollback-sha256']:
        p.add_argument('--'+name,required=True)
    p.add_argument('--image',required=True,type=Path)
    p.add_argument('--rollback',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--task-id',choices=['H-017','H-018','H-019'],default='H-017')
    p.add_argument('--flash-baud',type=int,choices=[115200,460800],default=115200,
                   help='Flash transfer baud; ROM identity connects at 115200, application UART stays 460800')
    p.add_argument('--preserve-autostart',action='store_true',help='Keep saved autonomous operation after app-only upgrade')
    a=p.parse_args()
    image,rollback=a.image.resolve(),a.rollback.resolve()
    if digest(image)!=a.sha256 or digest(rollback)!=a.rollback_sha256 or not 0<image.stat().st_size<=0x100000:
        p.error('image SHA/rollback SHA/1MiB app bound failed')
    known=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
    if not any(x['node_id']==a.mac and x.get('physically_confirmed') for x in known):
        p.error('only physically registered MAC allowed')
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs'/a.task_id):
        p.error('new task-owned output required')
    out.mkdir(parents=True,exist_ok=False)
    result=dict(port=a.port,mac=a.mac,current_build=a.current_build,target_build=a.target_build,image=str(image),image_sha256=a.sha256,rollback=str(rollback),rollback_sha256=a.rollback_sha256,write_calls=0,offset=65536,erase_all=False,rom_connect_baud=115200,flash_baud=a.flash_baud,application_uart_baud=460800,success=False,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    wire=None
    buffer=bytearray()
    events=[]
    def command(name):
        nonce='h017-'+secrets.token_hex(8)
        wire.write((json.dumps(dict(cmd=name,nonce=nonce))+'\n').encode())
        until=time.monotonic()+4
        while time.monotonic()<until:
            buffer.extend(wire.read(4096))
            if len(buffer)>131072:
                raise RuntimeError('serial line budget exceeded')
            while b'\n' in buffer:
                line,_,tail=buffer.partition(b'\n')
                buffer[:]=tail
                try:
                    event=json.loads(line)
                except (ValueError,UnicodeError):
                    continue  # SDK boot text can contain a local SSID; never log it.
                events.append(redact(event))
                if event.get('nonce')==nonce:
                    if not event.get('ok'):
                        raise RuntimeError('board rejected '+name)
                    return event
        raise TimeoutError(name)
    with HardwareLease(a.task_id.replace('-','')):
        try:
            wire=serial.Serial(port=None,baudrate=460800,timeout=.05,write_timeout=2)
            wire.dtr=wire.rts=False
            wire.port=a.port
            wire.open()
            info=command('info')
            result['before_info']=redact(info)
            if info.get('node_id')!=a.mac or info.get('build_id')!=a.current_build or info.get('firmware')!='mid-espnow' or info.get('chip')!='esp32s3':
                raise RuntimeError('fresh board identity/current build mismatch; no reset or write')
            if a.preserve_autostart:
                result['before_field_status']=redact(command('field_status'))
                if not all(result['before_field_status'].get(k) for k in ('running','start_on_boot','discovery_autostart','ip_enabled')):
                    raise RuntimeError('saved field autostart prerequisites not present; no write')
            result['pre_flash_stop']=redact(command('stop'))
            stats=command('stats')
            if stats.get('radio') is not False or stats.get('queue_depth')!=0:
                raise RuntimeError('radio/queue not stopped; no flash')
            wire.baudrate=115200
            esp=esptool.detect_chip(wire,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1)
            actual=':'.join(format(x,'02x') for x in esp.read_mac())
            security=esp.get_security_info()
            result.update(rom_mac=actual,security=security)
            flags=security['parsed_flags']
            if actual!=a.mac or esp.CHIP_NAME!='ESP32-S3' or flags['SECURE_BOOT_EN'] or flags['SECURE_DOWNLOAD_ENABLE'] or bin(security['flash_crypt_cnt']).count('1')%2:
                raise RuntimeError('ROM identity/security guard failed')
            original=esptool.write_flash
            def guarded(esp,args):
                if result['write_calls'] or getattr(args,'erase_all',False) or getattr(args,'force',False) or {offset:Path(f.name).resolve() for offset,f in args.addr_filename}!={65536:image}:
                    raise RuntimeError('app-only one-write guard failed')
                result['write_calls']+=1
                response=original(esp,args)
                result['write_verified']=True
                reset=esp.hard_reset
                def runtime_reset():
                    wire.baudrate=460800
                    reset()
                esp.hard_reset=runtime_reset
                return response
            esptool.write_flash=guarded
            try:
                esptool.main(['--chip','esp32s3','--port',a.port,'--baud',str(a.flash_baud),'--after','hard_reset','write_flash','0x10000',str(image)],esp=esp)
            finally:
                esptool.write_flash=original
            wire.baudrate=460800
            time.sleep(1)
            buffer.clear()
            after=command('info')
            result['after_info']=redact(after)
            if after.get('node_id')!=a.mac or after.get('build_id')!=a.target_build:
                raise RuntimeError('target startup identity/build mismatch')
            if a.preserve_autostart:
                state=redact(command('field_status'))
                result['after_field_status']=state
                keys=('group','channel','deployment_mode','discovery_autostart','configured','start_on_boot','ip_enabled','link_filter_enabled')
                if any(state.get(k)!=result['before_field_status'].get(k) for k in keys) or not state.get('radio') or not state.get('running'):
                    raise RuntimeError('saved autonomous configuration not retained after flash')
                result['saved_configuration_retained']=True
            else:
                result['post_flash_stop']=redact(command('stop'))
                result['stats']=redact(command('stats'))
                if result['stats'].get('radio') is not False or result['stats'].get('queue_depth')!=0:
                    raise RuntimeError('post-flash radio did not stop')
            result['success']=True
        except Exception as exc:
            result['error']=repr(exc)
        finally:
            if wire:
                wire.close()
            result.update(all_ports_closed=True,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            (out/'events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
            m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
            m.update(template_only=False,task_id=a.task_id,run_id=out.name,started_at=result['started_at'],finished_at=result['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=__import__('os').getpid(),dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):digest(Path(__file__))},data_and_weights_sha256={str(image):a.sha256,str(rollback):a.rollback_sha256},output_directory=str(out),budget=dict(max_app_write_calls=1,offset=65536,erase_all=False),exit_code=0 if result['success'] else 1,status='passed' if result['success'] else 'failed',limitations=['No bootloader/partition/NVS-partition/eFuse write.','This entry verifies startup only, not zero-USB delivery.'])
            (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
            print(json.dumps(result))
    if not result['success']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
