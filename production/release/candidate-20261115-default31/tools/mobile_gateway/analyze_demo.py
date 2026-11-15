"""Correlate finite demo raw logs; output is derived, never a radio measurement."""
import argparse
import collections
import json
from pathlib import Path


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def identity(packet):
    return (packet['origin'], packet.get('origin_boot',packet.get('boot')), packet['seq'], packet['dst'])


def analyze(run):
    result = json.loads((run/'RESULT.json').read_text(encoding='utf-8'))
    journal = rows(run/'gateway/reports.jsonl')
    model = rows(run/'model/model-events.jsonl')
    life = rows(run/'lifecycle.jsonl')
    checks = {}
    def check(name, value):
        checks[name] = bool(value)
    check('all_children_exited_zero', all(not p['running'] and p['exit_code']==0 for p in result['processes']))
    check('completed_and_gateway_reconnected',result['status']=='completed' and result['gateway_reconnected'])
    first_labels = list(dict.fromkeys(row['report']['label'] for row in journal))
    check('observed_arrival_order_C_B_A_D_E',first_labels==list('CBADE'))
    single_C = any(row['report']['label']=='C' and not row['report']['neighbors'] for row in journal[:4])
    check('C_single_point_reported',single_C)
    check('B_hears_C_before_mutual',any(row['report']['label']=='B' and any(n['peer_id'].endswith(':03') and n['state']=='heard' for n in row['report']['neighbors']) for row in journal))
    check('A_initially_only_heard_by_B',any(row['report']['label']=='B' and any(n['peer_id'].endswith(':01') and n['state']=='heard' for n in row['report']['neighbors']) for row in journal))
    for label in 'ABCDE':
        positions = {(r['report']['position']['lat'],r['report']['position']['lon']) for r in journal if r['report']['label']==label and r['report'].get('position')}
        check(label+'_continuous_position_changes',len(positions)>2)
    initials = [next(r['report']['position'] for r in journal if r['report']['label']==label) for label in 'ABCDE']
    check('independent_GPS_starts',len({(p['lat'],p['lon']) for p in initials})==5)
    check('all_GPS_explicitly_simulated',all(r['report']['position'] is None or r['report']['position']['source']=='simulated' for r in journal))
    check('all_quality_explicitly_simulated',all(n['rf_source']=='simulated' for r in journal for n in r['report']['neighbors']))
    check('BC_degrades_then_lost',any(n['rssi_dbm']==-94 for r in journal for n in r['report']['neighbors']) and any(n['state']=='lost' for r in journal for n in r['report']['neighbors']))
    e_sessions = {r['report']['session_id'] for r in journal if r['report']['label']=='E'}
    check('E_reporter_restart_distinct_session_same_board_boot',len(e_sessions)==2 and len({r['report']['boot_id'] for r in journal if r['report']['label']=='E'})==1)
    state32 = json.loads((run/'state-32.json').read_text(encoding='utf-8'))
    check('E_offline_is_visible',any(n['label']=='E' and n['telemetry_status']=='offline' for n in state32['nodes']))
    delivery = [m for m in model if m['kind']=='delivery']
    ac_paths = [m['path'] for m in delivery if m['identity']['origin'].endswith(':01') and m['identity']['dst'].endswith(':03')]
    check('business_uses_ABC_and_ADC_in_model',list('ABC') in ac_paths and list('ADC') in ac_paths)
    offline = result['offline_packet']
    key = identity(offline['receipt'])
    off, back = result['gateway_off_ms'],result['gateway_reconnected_ms']
    check('fresh_business_input_while_gateway_process_absent',offline['gateway_exited'] and offline['model_running'] and off<=offline['input_ms']<back)
    matches = [d for d in delivery if identity(d['identity'])==key and d['payload_hex']==offline['payload_hex']]
    check('independent_transport_delivers_original_offline_payload',len(matches)==1 and off<=matches[0]['host_ms']<back)
    receives=[]
    agent_logs=[]
    for path in run.glob('agent-*/*.jsonl'):
        records=rows(path)
        agent_logs+=records
        receives.extend(r for r in records if r['kind']=='received')
    end_matches=[r for r in receives if identity(r['packet'])==key and r['payload_hex']==offline['payload_hex']]
    check('actual_E2_destination_agent_records_bytes_during_outage',len(end_matches)==1 and off<=end_matches[0]['recorded_at']*1000<back)
    sends=[r for r in agent_logs if r['kind']=='send_attempt']
    check('E2_agents_generate_new_business_during_outage',any(off<=r['recorded_at']*1000<back for r in sends))
    nodes=[]
    for path in run.glob('node-*/*.jsonl'):
        nodes+=rows(path)
    check('node_reporter_detects_outage_and_recovers',any(n['kind']=='gateway_offline' for n in nodes) and any(n['kind']=='gateway_reconnected' for n in nodes))
    final=json.loads((run/'last-state.json').read_text(encoding='utf-8'))
    check('reconnect_restores_current_five_nodes',len(final['nodes'])==5 and all(n['telemetry_status']=='online' for n in final['nodes']))
    check('bounded_report_queue_and_aged_replay',any(r['report'].get('report_age_ms',0)>400 for r in journal) and all(r['report'].get('retained_limit')==120 for r in journal))
    event_counts=collections.Counter(m['event']['event'] for m in model if m['kind']=='board_model_event')
    identities={identity(d['identity']) for d in delivery}
    report_bytes=sum(len(json.dumps(r['report'],ensure_ascii=False).encode()) for r in journal)
    summary=dict(status='passed' if all(checks.values()) else 'failed',checks=checks,evidence_kind='single_Windows_PC_host_transport_model_actual_E2_modules',offline_identity=list(key),offline_payload_bytes=len(bytes.fromhex(offline['payload_hex'])),arrival_order=first_labels,model_delivery_count=len(identities),model_business_payload_bytes=sum(len(bytes.fromhex(d['payload_hex'])) for d in delivery),model_event_counts=dict(event_counts),telemetry_accepted_reports=len(journal),telemetry_JSON_bytes_reencoded=report_bytes,model_Hello_air_bytes=None,real_RF_bytes=None,real_RSSI=None,physical_boards=0,real_Pi=0,real_GPS=0,limitations=['Host model uses scenario graph/BFS, not ESP-NOW or M-029 board algorithm.','GPS positions come from actual E2 fake provider, not a GPS receiver.','HTTP byte total is reencoded accepted report bodies only, not IP/air accounting.','This analyzer reads original evidence; it does not replay business requests.'])
    return summary


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path,help='new derived evidence directory')
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    summary=analyze(args.run)
    (args.output/'SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (args.output/'SOURCES.json').write_text(json.dumps(dict(source_run=str(args.run.resolve()),derived_only=True),indent=2),encoding='utf-8')
    print(json.dumps(summary))
    if summary['status']!='passed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
