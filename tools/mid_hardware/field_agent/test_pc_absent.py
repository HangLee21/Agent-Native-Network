"""Bounded actual-PC-process outage; correlate fresh board RAM endpoint bytes."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

from .wire_operator import Operator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    out = args.output.resolve()
    if not out.is_relative_to(root / 'simulation/outputs/H-017'):
        parser.error('new H-017 output required')
    out.mkdir(parents=True, exist_ok=False)
    op = Operator()
    result = dict(physical_supply='USB power, user confirmed no power banks available',
                  serial_opens=0, host_business_send_calls=0,
                  topology='prior controlled bidirectional A-B-C-E-D RF filters remain active',
                  clock_method='same-boot uptime anchors bracketing each native status request',
                  clock_limit='2 second guard at both ends; oscillator drift not measured',
                  records={}, before={}, after={}, errors=[])
    old = op.client.status()
    nodes = [r['node_id'] for r in old['entries'] if r['connected']]
    if len(nodes) != 5:
        raise RuntimeError('all five actual entries required before the finite outage')
    for node in nodes:
        start = time.time()
        result['before'][node] = dict(request_start=start, response=op.native(node, 'field_status'), request_end=time.time())
    expected_pid = json.loads((root/'simulation/outputs/H-017/20261109-18-pc-maintenance/PROCESS.json').read_text())['pid']
    proc = None
    paused = []
    def restart():
        nonlocal proc
        command = [sys.executable, '-X', 'utf8', '-m', 'tools.mid_hardware.field_agent.lease_fault_server',
                   '--fault-file', '.local/mid/H-017/formal-lease-control.json',
                   '--fault-log', str(out/'lease-faults.jsonl'),
                   '--maintenance-file', '.local/mid/H-017/maintenance-control.json',
                   'serve', '--state', '.local/mid/H-017/formal-pc-310031',
                   '--pc-id', '310031', '--http-port', '8791', '--udp-port', '8793',
                   '--stop-file', str(out/'STOP')]
        with (out/'stdout.txt').open('xb') as stdout, (out/'stderr.txt').open('xb') as stderr:
            proc = subprocess.Popen(command, cwd=root, stdout=stdout, stderr=stderr,
                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result['restarted_pid'] = proc.pid
        (out/'PROCESS.json').write_text(json.dumps(dict(pid=proc.pid,command=command,serial_access=False)),encoding='utf-8')
        until = time.monotonic()+20
        while time.monotonic()<until:
            if proc.poll() is not None:
                raise RuntimeError('restored service exited; see stderr')
            try:
                current=op.client.status()
                if len([r for r in current['entries'] if r['connected']]) == 5:
                    result['restored_pc_session']=current['pc_session']
                    return
            except OSError:
                pass
            time.sleep(.1)
        raise TimeoutError('all five entries did not return within 20 seconds')
    try:
        (root/'simulation/outputs/H-017/20261109-18-pc-maintenance/STOP').touch()
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            check=subprocess.run(['powershell.exe','-NoProfile','-Command',
                                  f'if (Get-Process -Id {expected_pid} -ErrorAction SilentlyContinue) {{ exit 1 }}'],capture_output=True)
            try:
                op.client.status()
                absent=False
            except OSError:
                absent=True
            if check.returncode==0 and absent:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('old PC process/HTTP did not stop; no outage claimed')
        result['process_absent_start']=time.time()
        print('Actual PC endpoint stopped; observing 20 seconds without host business or serial.',flush=True)
        time.sleep(20)
        result['process_absent_end']=time.time()
        restart()
        print('Actual PC endpoint restored; freezing generators only to export existing RAM evidence.',flush=True)
        for node in nodes:
            if result['before'][node]['response']['reply']['agent_running']:
                paused.append(node)
                op.native(node,'agent',{'running':False})
        for node in nodes:
            after=op.native(node,'field_status')
            result['after'][node]=after
            before=result['before'][node]['response']['reply']
            if after['reply']['entry_boot'] != before['entry_boot']:
                raise RuntimeError('boot changed; cannot correlate board clocks')
            result['records'][node]=op.records(node,after=before['latest_record_cursor'],limit=128)
        pairs=[]
        for origin, rows in result['records'].items():
            anchor=result['before'][origin]
            uptime=anchor['response']['reply']['entry_uptime_ms']
            for item in rows:
                s=item['reply']
                if s['kind']!='source_admitted' or s['origin']!=origin or s['dst'] not in result['records']:
                    continue
                delta=(s['at_ms']-uptime)/1000
                if anchor['request_start']+delta < result['process_absent_start']+12 or anchor['request_end']+delta > result['process_absent_end']-2:
                    continue
                for received in result['records'][s['dst']]:
                    d=received['reply']
                    if d['kind']!='destination_received' or any(s[k]!=d[k] for k in ('origin','origin_boot','seq','dst','payload_hex')):
                        continue
                    dest_anchor=result['before'][s['dst']]
                    dd=(d['at_ms']-dest_anchor['response']['reply']['entry_uptime_ms'])/1000
                    if dest_anchor['request_start']+dd < result['process_absent_start']+12 or dest_anchor['request_end']+dd > result['process_absent_end']-2:
                        continue
                    pairs.append(dict(identity=[s[k] for k in ('origin','origin_boot','seq','dst')],payload_hex=s['payload_hex'],source_record=s,destination_record=d))
        result['fresh_source_destination_matches_during_PC_absence']=pairs
        result['status']='passed_board_delivery_during_PC_process_absence' if pairs else 'no_complete_retained_endpoint_pair'
    except Exception as exc:
        result['errors'].append(repr(exc))
        result['status']='incomplete'
    finally:
        try:
            op.client.status()
        except OSError:
            if proc is None:
                try: restart()
                except Exception as exc: result['errors'].append('restore: '+repr(exc))
        for node in paused:
            try: op.native(node,'agent',{'running':True})
            except Exception as exc: result['errors'].append('resume '+node+': '+repr(exc))
        try:
            result['final_PC_status']=op.client.status()
            result['final_board_status']={n:op.native(n,'field_status') for n in nodes}
        except Exception as exc:
            result['errors'].append('final status: '+repr(exc))
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=result['status'],endpoint_matches=len(result.get('fresh_source_destination_matches_during_PC_absence',[])),errors=result['errors'],service_pid=result.get('restarted_pid'))),flush=True)


if __name__=='__main__':
    main()
