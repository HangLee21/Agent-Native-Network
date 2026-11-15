"""Correlate real source application receipts with destination UART and application bytes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path


def read_rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line]


def key(row):
    return row['origin'],row.get('origin_boot',row.get('boot')),row['seq'],row['dst']


def analyze(run):
    result=json.loads((run/'RESULT.json').read_text(encoding='utf-8'))
    checks={}
    def check(name,condition):
        checks[name]=bool(condition)
    native=[]
    for path in run.glob('owner-*/native.jsonl'):
        for line_no,row in enumerate(read_rows(path),1):
            native.append(dict(event=row['event'],path=str(path),line=line_no,host_monotonic_ns=row['host_monotonic_ns']))
    logs=[]
    for path in run.glob('agent-*/*.jsonl'):
        for line_no,row in enumerate(read_rows(path),1):
            logs.append(dict(row,path=str(path),line=line_no))
    accepted=[]
    for row in logs:
        if row['kind']=='send_receipt':
            receipt=row['receipt']
            admission=receipt.get('result',{})
            if admission.get('accepted'):
                accepted.append(dict(identity=key(admission),payload_hex=receipt['request']['payload_hex'],source_log=row['path'],source_line=row['line'],request_id=row['request_id']))
    endpoint={}
    for row in native:
        e=row['event']
        if e.get('event')=='rx_local' and e.get('dst')==e.get('node_id'):
            endpoint.setdefault(key(e),[]).append(row)
    app_receipts={}
    for row in logs:
        if row['kind']=='received':
            app_receipts.setdefault(key(row['packet']),[]).append(row)
    proofs=[]
    for row in accepted:
        matches=[x for x in endpoint.get(row['identity'],[]) if x['event']['payload_hex']==row['payload_hex']]
        applications=[x for x in app_receipts.get(row['identity'],[]) if x['payload_hex']==row['payload_hex']]
        proofs.append(dict(row,native_destination_matches=len(matches),application_matches=len(applications),native_sources=[dict(path=x['path'],line=x['line']) for x in matches],application_sources=[dict(path=x['path'],line=x['line']) for x in applications]))
    check('four_real_observers_and_no_host_model',result['boards']==4 and result['evidence_kind']=='single_Windows_PC_multiple_real_ESP_NOW_boards')
    check('new_gateway_initially_empty',not json.loads((run/'EMPTY_STATE.json').read_text())['nodes'])
    check('multi_round_random_business_from_each_observed_board',len(accepted)>8 and len({r['identity'][0] for r in accepted})==4)
    check('multi_round_exact_UART_delivery_from_each_source',sum(p['native_destination_matches']==1 for p in proofs)>8 and len({p['identity'][0] for p in proofs if p['native_destination_matches']==1})==4)
    check('independent_E2_application_delivery_from_each_source',sum(p['application_matches']==1 for p in proofs)>8 and len({p['identity'][0] for p in proofs if p['application_matches']==1})==4)
    for packet in proofs:
        packet['delivery_state']='destination_and_application_confirmed' if packet['native_destination_matches']==1 and packet['application_matches']==1 else 'destination_UART_only' if packet['native_destination_matches']==1 else 'destination_unconfirmed'
    check('original_packet_identities_unique',len({r['identity'] for r in accepted})==len(accepted))
    offline=result['offline_packet']
    original=offline['response']['result']
    offline_key=key(original)
    off,back=result['gateway_off_ms'],result['gateway_reconnected_ms']
    received=[r for r in app_receipts.get(offline_key,[]) if r['payload_hex']==offline['payload_hex']]
    received_native=[r for r in endpoint.get(offline_key,[]) if r['event']['payload_hex']==offline['payload_hex']]
    check('fresh_application_input_while_gateway_OS_process_exited',offline['gateway_process_exited'] and off<=offline['input_ms']<back)
    check('offline_packet_received_in_original_destination_UART',len(received_native)==1)
    check('offline_packet_application_bytes_observed_before_reconnect',len(received)==1 and off<=received[0]['recorded_at']*1000<back)
    outage_sends=[r for r in logs if r['kind']=='send_attempt' and off<=r['recorded_at']*1000<back]
    outage_receives=[r for r in logs if r['kind']=='received' and off<=r['recorded_at']*1000<back]
    check('random_generators_and_receivers_continue_during_outage',len(outage_sends)>4 and len(outage_receives)>4)
    final=json.loads((run/'STATE-final.json').read_text(encoding='utf-8'))
    check('reconnected_state_has_four_online_real_reporters',len(final['nodes'])==4 and all(n['telemetry_status']=='online' for n in final['nodes']))
    check('GPS_explicit_simulation_separate_from_unavailable_RSSI',all(n['position']['source']=='simulated' for n in final['nodes']) and all(e['rssi_dbm'] is None and e['rf_source']=='unavailable' for e in final['edges']))
    check('unknown_fifth_reporter_not_fabricated_from_neighbors',len({e['from'] for e in final['edges']})==5 and len(final['nodes'])==4)
    initial={}
    counter_deltas={}
    for path in run.glob('owner-*/ready.json'):
        before=json.loads(path.read_text())['info']
        after=json.loads((path.parent/'final.json').read_text())['info']
        initial[path.parent.name]=before
        check(path.parent.name+'_original_board_mode_boot_build_retained',all(before.get(k)==after.get(k) for k in ['boot_id','build_id','deployment_mode','group','channel','link_filter_enabled']) and after['radio'] is True)
        counter_deltas[path.parent.name]={k:after[k]-before[k] for k in ['control_submitted','control_hello_generated','control_ack_generated','route_control_frames','route_control_bytes','route_data_frames','route_data_bytes'] if k in before and k in after}
    check('all_capture_children_exit_zero_and_ports_released',result['all_children_stopped'] and all(p['exit_code']==0 for p in result['processes']) and not result['lease_after']['busy'])
    check('no_firmware_or_radio_configuration_writes',result['flash_writes']==0 and result['radio_or_config_commands']==0)
    browser=json.loads((run/'BROWSER_RECONNECTED.json').read_text(encoding='utf-8'))
    check('normal_browser_displays_actual_map_and_receipts_after_reconnect',browser['nodeCount']=='4' and browser['edgeCount']=='16' and len(browser['destinationReceipts'])>0 and '已读取' in browser['connection'])
    reports=read_rows(run/'gateway/reports.jsonl')
    cached=[r for r in reports if r['report'].get('report_age_ms',0)>1000]
    check('bounded_report_queue_replays_with_explicit_age',len(cached)>0 and all(r['report']['retained_limit']==120 for r in reports))
    source_root=Path(__file__).resolve().parents[2]
    source_drift=[file for file,sha in json.loads((run/'INPUT_HASHES.json').read_text()).items() if not (source_root/file).is_file() or hashlib.sha256((source_root/file).read_bytes()).hexdigest()!=sha]
    summary=dict(status='passed' if all(checks.values()) else 'failed',checks=checks,evidence_kind=result['evidence_kind'],accepted_random_packets=len(accepted),unique_endpoint_matches=sum(p['native_destination_matches']==1 for p in proofs),unique_application_matches=sum(p['application_matches']==1 for p in proofs),business_pairs=dict(collections.Counter(r['identity'][0]+' -> '+r['identity'][3] for r in accepted)),payload_byte_range=[min(len(bytes.fromhex(p['payload_hex'])) for p in proofs),max(len(bytes.fromhex(p['payload_hex'])) for p in proofs)],offline_identity=list(offline_key),offline_payload_bytes=len(bytes.fromhex(offline['payload_hex'])),offline_source=offline['source'],offline_target=offline['target'],gateway_outage_ms=back-off,outage_random_attempts=len(outage_sends),outage_application_receipts=len(outage_receives),offline_application_proofs=[dict(path=x['path'],line=x['line'],recorded_at=x['recorded_at']) for x in received],offline_UART_proofs=[dict(path=x['path'],line=x['line']) for x in received_native],board_counter_deltas=counter_deltas,accepted_telemetry_reports=len(reports),cached_reports=len(cached),source_drift_since_start=source_drift,real_RSSI=None,real_GPS=None,physical_Pis=0,flash_writes=0,limitations=['Four serial-observed real boards on one Windows PC; fifth board appears only in neighbor reports and its USB-error port was excluded.','Simulated GPS from E2 provider; existing firmware supplies real neighbor states but no RSSI.','No physical Pi, LAN/hotspot reach, GPS receiver, RSSI or RF isolation measurement.','Upstream E2 providers/reporting/check source changed during capture; input hashes and original raw records preserved, so this is an observed integration run, not a byte-frozen source reproduction.','Board counters are SDK/application quantities, not over-air retransmission bytes or airtime.'])
    summary.update(validation_scope='live ingestion/map plus multi-round delivery and gateway-outage independence; no 100-percent reliability requirement',
                   destination_unconfirmed=[dict(identity=p['identity'],request_id=p['request_id']) for p in proofs if p['delivery_state']=='destination_unconfirmed'],
                   destination_UART_only=[dict(identity=p['identity'],request_id=p['request_id']) for p in proofs if p['delivery_state']=='destination_UART_only'],
                   analysis_note='09 initial strict analysis preserved its two failed all-packets checks. This analysis evaluates the task acceptance criteria and explicitly retains every unconfirmed/application-missing packet; no RF run was repeated or loss removed.')
    return summary,proofs


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    summary,proofs=analyze(args.run)
    (args.output/'SUMMARY.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (args.output/'PACKET_PROOFS.json').write_text(json.dumps(proofs,indent=2),encoding='utf-8')
    (args.output/'SOURCES.json').write_text(json.dumps(dict(source_run=str(args.run.resolve()),derived_only=True),indent=2),encoding='utf-8')
    print(json.dumps(summary))
    if summary['status']!='passed':
        raise SystemExit(1)


if __name__=='__main__':
    main()
