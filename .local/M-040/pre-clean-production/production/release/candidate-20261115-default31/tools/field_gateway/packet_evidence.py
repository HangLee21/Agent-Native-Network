"""Packet evidence for H/D. Pure projection; no send, timeout or route inference."""
import re

MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
ALIASES={'source_admitted':'tx_queued','source_submitted':'tx_submit',
         'relay_received':'rx_relay','relay_submitted':'tx_submit','destination_received':'rx_local'}


def summarize_packets(events, *, history_gap=False):
    """Accept canonical events or H timeline rows, keyed by original source epoch.

    Absence of receiver evidence never becomes packet loss. Observer identity and
    original source identity are separate; board uptime is never compared across boards.
    """
    packets={}
    for index,item in enumerate(events):
        event=item.get('data',item)
        kind=event.get('event',item.get('type',event.get('kind')))
        kind=ALIASES.get(kind,kind)
        if event.get('sequence_scope')=='route_request' or event.get('packet_kind','DATA')!='DATA':
            continue
        if kind=='field_pc_envelope' or event.get('payload_scope')=='FG02_envelope':
            continue
        if kind not in ('tx_queued','tx_submit','rx_relay','rx_local','route_no_route',
                        'send_rejected','delivery_unknown','tx_link_fail','tx_api_failed','route_drop'):
            continue
        origin,dst=event.get('origin'),event.get('dst')
        boot,seq=event.get('origin_boot'),event.get('seq')
        if not isinstance(origin,str) or not MAC.fullmatch(origin) or not isinstance(dst,str) or not MAC.fullmatch(dst):
            continue
        if any(type(v) is not int or not 1<=v<=0xffffffff for v in (boot,seq)):
            continue
        observer=event.get('observer_id',event.get('node_id',item.get('node_id',event.get('entry_id'))))
        observer_boot=event.get('observer_boot',event.get('entry_boot',event.get('boot_id')))
        source=observer==origin and (observer_boot is None or observer_boot==boot)
        payload=None
        if 'payload_hex' in event:
            try:
                raw=bytes.fromhex(event['payload_hex'])
                if len(raw)<=160:payload=raw.hex()
            except (TypeError,ValueError):pass
        key=(origin,boot,seq,dst)
        packet=packets.setdefault(key,dict(origin=origin,origin_boot=boot,seq=seq,dst=dst,
            source_admitted_observed=False,source_submitted_observed=False,relay_observers=set(),
            destination_observed=False,source_payloads=set(),destination_payloads=set(),
            explicit_no_route=False,explicit_rejection=False,source_cancelled=False,local_errors=[],coverage_limited=history_gap,
            last_observation=None,evidence_count=0))
        packet['coverage_limited'] |= bool(event.get('record_overwritten',0) or event.get('sampled_records_skipped',0))
        packet['evidence_count']+=1
        packet['last_observation']=dict(event=kind,observer_id=observer,observer_boot=observer_boot,
            received_ms=item.get('received_ms'),cursor=item.get('cursor'),index=index)
        if source and payload is not None:packet['source_payloads'].add(payload)
        if kind=='tx_queued' and source:packet['source_admitted_observed']=True
        elif kind=='tx_submit':
            if source:packet['source_submitted_observed']=True
            elif isinstance(observer,str):packet['relay_observers'].add(observer)
        elif kind=='rx_relay' and isinstance(observer,str):packet['relay_observers'].add(observer)
        elif kind=='rx_local' and observer==dst and payload is not None:
            packet['destination_observed']=True;packet['destination_payloads'].add(payload)
        elif kind=='route_no_route' and source:
            if event.get('reason')==6:packet['source_cancelled']=True
            else:packet['explicit_no_route']=True
        elif kind=='send_rejected' and source:packet['explicit_rejection']=True
        elif kind in ('delivery_unknown','tx_link_fail','tx_api_failed','route_drop'):
            packet['local_errors'].append(dict(event=kind,observer_id=observer,reason=event.get('reason',event.get('error'))))
    result=[]
    for packet in packets.values():
        source,destination=packet.pop('source_payloads'),packet.pop('destination_payloads')
        conflict=len(source)>1 or len(destination)>1 or bool(source and destination and source!=destination)
        packet['bytes_match_source']=next(iter(source))==next(iter(destination)) if len(source)==len(destination)==1 else None
        if conflict:state='evidence_conflict'
        elif packet['destination_observed']:state='destination_received'
        elif packet['source_cancelled'] and not packet['source_submitted_observed']:state='cancelled_before_submission'
        elif packet['explicit_rejection'] and not packet['source_submitted_observed']:state='explicit_rejection'
        elif packet['explicit_no_route'] and not packet['source_submitted_observed'] and not packet['relay_observers']:state='explicit_no_route'
        elif packet['local_errors']:state='delivery_unknown'
        elif packet['relay_observers']:state='relayed_pending'
        elif packet['source_submitted_observed']:state='submitted_pending'
        elif packet['source_admitted_observed']:state='queued_only'
        else:state='observed_only'
        packet.update(state=state,relay_observers=sorted(packet['relay_observers']),
            payload_hex=next(iter(destination or source)) if len(destination or source)==1 else None,
            absence_means_loss=False,
            note='retained_or_sampled_history_cannot_establish_loss' if packet['coverage_limited'] else 'receiver_evidence_may_arrive_later')
        result.append(packet)
    return result
