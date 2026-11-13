"""One persistent LoRa configuration, then bounded worker/readback verification."""
import argparse
import datetime
import json
from pathlib import Path
import sys
import time

from tools.mid_edge.client import Edge
from tools.mid_hardware.console.lease import HardwareLease, status

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--mac', required=True)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--role', choices=['off','rx','tx'], required=True)
    parser.add_argument('--period-ms', type=int, default=10000)
    parser.add_argument('--frequency-hz', type=int, default=470000000,
                        help='Sub-GHz centre frequency; the LR1121 candidate accepts 410..493 MHz only')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 410000000 <= args.frequency_hz <= 493000000:
        parser.error('--frequency-hz must be 410000000..493000000 (Sub-GHz band of this board)')
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'simulation/outputs/H-019'):
        parser.error('New H-019 output required')
    bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
    if not any(row['node_id']==args.mac and row.get('physically_confirmed') for row in bindings):
        parser.error('Registered physical MAC required')
    output.mkdir(parents=True, exist_ok=False)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    fields=dict(role=args.role, report_period_ms=args.period_ms, jitter_ms=250,
        frequency_hz=args.frequency_hz, sf=7, bandwidth_hz=125000, coding_rate=5,
        tx_power_dbm=0, sync_word=18, preamble_symbols=8, start_on_boot=True)
    result=dict(success=False, port=args.port, mac=args.mac, expected_build=args.build_id,
        requested=fields, config_commands=0, flash_writes=0, resets=0)
    try:
        with HardwareLease('H019'), Edge(args.port,args.mac,460800,log=output/'serial.jsonl') as edge:
            result['before_info']=edge.identify()
            if result['before_info']['build_id']!=args.build_id:
                raise RuntimeError('Current build mismatch; no configuration sent')
            result['before_field_status']=edge.command('field_status')
            result['before_lora_status']=edge.lora_status()
            result['config_commands']=1
            result['configuration']=edge.lora_config(**fields)
            deadline=time.monotonic()+10
            result['status_reads']=[]
            while time.monotonic()<deadline:
                current=edge.lora_status()
                result['status_reads'].append(current)
                if current.get('lora_ref_worker_state')==-1:
                    raise RuntimeError('LoRa worker initialization/configuration failed; saved outcome retained')
                if current.get('requested_generation')==current.get('applied_generation') and current.get('lora_ref_worker_state')=={'off':0,'rx':1,'tx':2}[args.role]:
                    result['applied_status']=current
                    break
                time.sleep(.25)
            else:
                raise TimeoutError('Configuration saved but worker apply not verified; no automatic retry')
            mismatches={key:current.get(key) for key,value in fields.items()
                if current.get('lora_ref_requested_role' if key=='role' else key)!=value}
            if mismatches:
                raise RuntimeError('Saved/applied readback mismatch: '+json.dumps(mismatches))
            result['after_field_status']=edge.command('field_status')
            keys=('group','channel','deployment_mode','discovery_autostart','configured','start_on_boot','ip_enabled','link_filter_enabled')
            if any(result['before_field_status'].get(key)!=result['after_field_status'].get(key) for key in keys):
                raise RuntimeError('Existing autonomous field configuration changed')
            result['field_configuration_retained']=True
            result['success']=True
    except Exception as exc:
        result['error']=repr(exc)
    result.update(all_ports_closed=True, lease_after=status(), finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    manifest.update(template_only=False,task_id='H-019',run_id=output.name,started_at=started,
        finished_at=result['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],
        python_executable=sys.executable,output_directory=str(output),status='config_verified' if result['success'] else 'config_unverified',
        limitations=['Configuration/worker readiness does not prove a LoRa packet reached A.',
            'Nominal 0dBm follows the official EBYTE BSP; output power is not externally measured.'])
    (output/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({key:result.get(key) for key in ('success','error','config_commands','all_ports_closed','lease_after')}))
    if not result['success']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
