"""Finite actual UDP fixture for selective lease loss, explicitly not Wi-Fi or RF."""
import argparse
import json
from pathlib import Path

from tools.field_gateway.application import Application
from tools.field_gateway.check_field import A,B,C,D,Entry,until
from .lease_fault_server import LeaseFaultLink


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    control=args.output/'fault-control.json'
    control.write_text(json.dumps({'withhold_lease_nodes':[]}),encoding='utf-8')
    link=LeaseFaultLink('127.0.0.1',0,lease_s=1.2,fault_file=control,fault_log=args.output/'faults.jsonl')
    app=Application(args.output/'pc',link,pc_id=91)
    bus={}
    a=Entry(A,link.socket.getsockname(),bus,[A,D,C])
    b=Entry(B,link.socket.getsockname(),bus,[B,C])
    checks={}
    try:
        def connected():
            return {r['node_id'] for r in link.status()['entries'] if r['connected']}
        until(lambda:connected()=={A,B})
        checks['two_simulated_entries_have_independent_actual_UDP_leases']=True
        control.write_text(json.dumps({'withhold_lease_nodes':[B]}),encoding='utf-8')
        until(lambda:connected()=={A},timeout=5)
        checks['target_B_lease_expires_while_A_remains_online']=True
        checks['both_entry_fixture_sockets_continue_running']=a.thread.is_alive() and b.thread.is_alive() and not a.offline and not b.offline
        checks['only_B_has_lease_renewals_withheld']=link.status()['H017_fault']['withhold_lease_nodes']==[B] and link.status()['H017_fault']['withheld_count']>0
        control.write_text(json.dumps({'withhold_lease_nodes':[]}),encoding='utf-8')
        until(lambda:connected()=={A,B},timeout=5)
        checks['empty_control_restores_normal_B_renewal']=True
        (args.output/'STATUS.json').write_text(json.dumps(app.status(),indent=2),encoding='utf-8')
    finally:
        a.close()
        b.close()
        app.close()
    result=dict(status='passed' if all(checks.values()) else 'failed',checks=checks,evidence_kind='synthetic_entries_real_loopback_UDP_no_RF',physical_boards=0,serial_opens=0,hotspot_changes=0,firewall_rules=0)
    (args.output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))
    if result['status']!='passed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
