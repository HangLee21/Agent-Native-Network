"""Apply formal field profiles to flashed boards; Wi-Fi credentials never enter logs."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

from tools.mid_edge.client import Edge
from tools.mid_hardware.console.lease import HardwareLease

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flash-result',required=True,type=Path)
    p.add_argument('--private-wifi',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    private=a.private_wifi.resolve()
    if not private.is_relative_to(ROOT/'.local/mid/H-017'):
        p.error('private local Wi-Fi input required')
    network=json.loads(private.read_text(encoding='utf-8'))['command']
    if network['cmd']!='ip_config' or network['channel'] not in range(1,14):
        p.error('invalid private ip_config')
    batch=json.loads(a.flash_result.read_text(encoding='utf-8'))
    if not batch['success'] or len(batch['boards'])!=5:
        p.error('successful five-board formal flash required')
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-017'):
        p.error('H-017 output required')
    out.mkdir(parents=True,exist_ok=False)
    roster=[r['result']['mac'] for r in batch['boards']]
    result=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),target=batch['target'],group=31,channel=network['channel'],pc_id=network['pc_id'],boards=[],credential_values_logged=False)
    with HardwareLease('H017'):
        try:
            for board in batch['boards']:
                flashed=board['result']
                row=dict(label=board['label'],port=flashed['port'],node_id=flashed['mac'],commands=[],success=False)
                result['boards'].append(row)
                with Edge(row['port'],row['node_id'],460800) as edge:
                    info=edge.identify()
                    row['before_info']=info
                    if info.get('build_id')!=batch['target'] or info.get('field_api')!=2 or info.get('radio'):
                        raise RuntimeError('fresh formal identity/idle prerequisite failed; no credential command')
                    def command(name,**fields):
                        answer=edge.command(name,timeout=5,**fields)
                        # Responses of formal credential command contain no secrets by contract.
                        # Keep only a minimal acknowledgement, not the input or raw UART.
                        row['commands'].append(dict(cmd=name,ok=answer.get('ok'),nonce=answer.get('nonce')))
                        return answer
                    command('field_pause')
                    command('stop')
                    command('route_clear')
                    command('deployment_clear')
                    command('ip_config',**{k:v for k,v in network.items() if k!='cmd'})
                    command('field_gateway',pc_id=network['pc_id'],agent_to_pc=True,report_period_ms=30000)
                    command('field_config',min_ms=2000,max_ms=3000,min_len=20,max_len=64,payload_mode='english',dest_mode='roster',roster=roster,start_on_boot=True,checkpoint_s=60,segment=1)
                    command('route_config',group=31,channel=network['channel'],autostart=True)
                    row['info']=edge.info()
                    row['field_status']=edge.command('field_status')
                    row['success']=True
                print(json.dumps(dict(label=row['label'],configured=True,radio=row['info'].get('radio'),channel=row['info'].get('channel'))),flush=True)
        finally:
            result.update(finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),all_ports_closed=True,success=len(result['boards'])==5 and all(r['success'] for r in result['boards']))
            (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
            m.update(template_only=False,task_id='H-017',run_id=out.name,started_at=result['started_at'],finished_at=result['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=__import__('os').getpid(),dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},data_and_weights_sha256={str(a.flash_result):hashlib.sha256(a.flash_result.read_bytes()).hexdigest()},output_directory=str(out),status='configured' if result['success'] else 'failed',exit_code=0 if result['success'] else 1,budget=dict(boards=5,group=31,channel=network['channel']),limitations=['SSID/password/BSSID inputs are private and never copied into provenance.','Configuration is not proof of Wi-Fi association, PC destination or zero USB.'])
            (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
