"""PC business state. Entry acceptance never substitutes for endpoint evidence."""
import collections
import copy
import json
from pathlib import Path
import re
import threading
import time
import uuid
from .store import Store
from .observations import FieldState

MAC = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')
REQUEST = re.compile(r'^[a-zA-Z0-9_-]{8,64}$')


class NoWirelessPath(RuntimeError):
    pass


class Application:
    def __init__(self, output, link, *, report_forward=None, pc_id=None):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.link = link
        self.lock = threading.RLock()
        self.journal = (self.output / ('pc-' + uuid.uuid4().hex + '.jsonl')).open('x', encoding='utf-8')
        self.store = Store(self.output / 'pc.sqlite3', pc_id=pc_id)
        self.events = collections.deque(maxlen=8192)
        self.cursor = 0
        self.map = FieldState()
        self.report_counts = collections.Counter()
        self.report_rejections = collections.deque(maxlen=16)
        self.report_forward = report_forward
        self.instance_id = uuid.uuid4().hex
        self.link.attach(self.handle, self.store.pc_id, self.store.pc_boot)

    def log(self, kind, **fields):
        with self.lock:
            row = dict(kind=kind, received_at=time.time(), **fields)
            self.journal.write(json.dumps(row, allow_nan=False) + '\n')
            self.journal.flush()
            self.cursor += 1
            self.events.append(dict(row, cursor=self.cursor))

    def status(self):
        link = self.link.status()
        with self.lock:
            telemetry = dict(map_outcomes=dict(self.report_counts),
                             recent_rejections=copy.deepcopy(list(self.report_rejections)),
                             map_nodes=len(self.map.nodes),
                             producer='native_report_and_opt_in_neighbor_snapshot', post_reports_supported=False)
        return dict(ok=True, schema_version=1, pc_id=self.store.pc_id, pc_boot=self.store.pc_boot,
                    pc_session=self.store.pc_boot,
                    pc_address='pc:' + format(self.store.pc_id, '08x'), instance_id=self.instance_id,
                    pc_service_mac='02:ff:' + ':'.join(f'{b:02x}' for b in self.store.pc_id.to_bytes(4,'big')),
                    entry=link.get('last_selected'), entries=link.get('entries', []),
                    wireless=link, connected=link.get('connected', False),
                    max_payload_bytes=link.get('max_payload_bytes'), serial_access=False,
                    telemetry=telemetry,
                    pc_is_independent_endpoint=True, map_nodes_from_observations_only=True,
                    counters=self.store.counters())

    def send(self, value):
        if not isinstance(value, dict) or set(value) != {'request_id', 'dst', 'payload_hex'}:
            raise ValueError('request_id/dst/payload_hex required')
        if not isinstance(value['request_id'], str) or not REQUEST.fullmatch(value['request_id']):
            raise ValueError('request_id must have 8..64 ASCII letters/digits/_/-')
        dst, raw = value['dst'], value['payload_hex']
        if not isinstance(dst, str) or not MAC.fullmatch(dst):
            raise ValueError('destination must be a canonical lowercase board MAC')
        if not isinstance(raw, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2})*', raw):
            raise ValueError('payload_hex must contain complete bytes')
        request = dict(dst=dst, payload_hex=raw.lower())
        with self.lock:
            old = self.store.get(value['request_id'])
            if old:
                if old['request'] != request:
                    raise ValueError('request_id binds another destination/payload')
                return old
            link = self.link.status()
            limit = link.get('max_payload_bytes')
            if limit is None or not link.get('connected'):
                raise NoWirelessPath('no confirmed wireless entry; no business datagram sent')
            if len(raw)//2 > limit:
                raise ValueError('cross-network payload exceeds ' + str(limit) + ' bytes; no truncation')
        # Routing evidence queries carry no business bytes. The receive worker must
        # remain free to deliver their answers while selection waits for its deadline.
        selected = self.link.select(dst)
        with self.lock:
            record, fresh = self.store.reserve(value['request_id'], request,
                                                selected)
            if fresh:
                self.log('send_reserved', record=record)
                try:
                    self.link.send(record)
                except Exception as exc:
                    record = self.store.get(value['request_id'])
                    record['error'] = str(exc)
                    if isinstance(exc, NoWirelessPath):
                        record.update(state='not_submitted', business_submitted=False)
                    self.store.update(record)
                    self.log('send_outcome_unknown', request_id=value['request_id'], error=str(exc))
                # Callbacks may have already updated the durable record.
            return self.store.get(value['request_id'])

    def handle(self, event):
        with self.lock:
            kind = event['type']
            if kind == 'neighbor_snapshot':
                self.map.accept_direct(event['proof'])
                self.log('neighbor_snapshot', proof=event['proof'])
                return
            if kind == 'report':
                report = event['report']
                try:
                    outcome = self.map.accept(report)
                except Exception as exc:
                    self.report_counts['rejected'] += 1
                    failure = dict(stage='map.accept',node_id=report.get('node_id'),error=str(exc),received_at=time.time())
                    self.report_rejections.append(failure)
                    self.log('wireless_report_rejected', diagnostic=failure, raw=event)
                    raise
                self.report_counts[outcome['status']] += 1
                self.log('wireless_report', node_id=report['node_id'], map_outcome=outcome, raw=event)
                if self.report_forward:
                    self.report_forward(report)
                return
            if kind in ('accepted', 'destination_received', 'rejected'):
                record = self.store.by_transaction(event['transaction_id'])
                if not record or event.get('pc_id') != record['pc_id'] or event.get('pc_session') != record.get('pc_session', record['pc_boot']):
                    self.log('unmatched_receipt', raw=event)
                    return
                if kind in ('accepted', 'rejected') and (event.get('entry_id') != record['entry']['node_id'] or event.get('entry_boot') != record['entry']['boot_id']):
                    self.log('entry_mismatch_receipt', raw=event)
                    return
                if kind == 'destination_received' and 'dst' not in event and event.get('raw', {}).get('transport') == 'wifi_direct' and event.get('entry_id') == record['request']['dst']:
                    event = dict(event, dst=record['request']['dst'],
                                 dst_basis='correlated_direct_destination_entry')
                if kind == 'destination_received' and event.get('dst') != record['request']['dst']:
                    self.log('destination_mismatch_receipt', raw=event)
                    return
                if kind == 'destination_received' and event.get('payload_hex', '').lower() != record['request']['payload_hex']:
                    self.log('payload_mismatch_receipt', raw=event)
                    return
                if kind in ('accepted','destination_received'):
                    origin, origin_boot, seq = event.get('origin'), event.get('origin_boot'), event.get('seq')
                    if origin != record['entry']['node_id'] or origin_boot != record['entry']['boot_id'] or type(seq) is not int or not 1 <= seq <= 0xffffffff:
                        self.log('source_identity_mismatch_receipt', raw=event)
                        return
                    packet = dict(origin=origin, origin_boot=origin_boot, seq=seq, dst=record['request']['dst'])
                    if record.get('source_packet') and record['source_packet'] != packet:
                        self.log('source_sequence_mismatch_receipt', raw=event)
                        return
                    record['source_packet'] = packet
                record['receipts'] = (record.get('receipts', []) + [event])[-16:]
                if kind == 'accepted':
                    record.update(entry_accepted=True)
                    if not record['destination_received']:
                        record['state'] = 'entry_accepted'
                elif kind == 'destination_received':
                    record.update(state='destination_received', destination_received=True,
                                  delivery_status='destination_received')
                elif not record['destination_received']:
                    record.update(state='entry_rejected', error=event.get('error', 'rejected'))
                self.store.update(record)
                self.log(kind, request_id=record['request_id'], raw=event)
            elif kind == 'pc_received':
                if event.get('pc_id') != self.store.pc_id:
                    self.log('wrong_pc_destination', raw=event)
                    return
                # A logical message can traverse another entry with a fresh radio
                # seq. Its original logical identity remains the deduplication key.
                identity = {k:event[k] for k in ('origin', 'origin_boot', 'transaction_id')}
                row = dict(event, dst=self.status()['pc_address'], received_at=time.time(),
                           delivery_status='pc_received', pc_received=True)
                if self.store.receive(identity, row):
                    self.log('pc_received', record=row)
                else:
                    self.log('duplicate_pc_receive', identity=identity)
            else:
                self.log(kind, raw=event)

    def history(self, after=0):
        with self.lock:
            if after < 0:
                raise ValueError('nonnegative event cursor required')
            oldest = self.events[0]['cursor'] if self.events else self.cursor+1
            return dict(events=copy.deepcopy([e for e in self.events if e['cursor'] > after]),
                        cursor=self.cursor, oldest_cursor=oldest,
                        truncated=bool(after and after < oldest-1), instance_id=self.instance_id)

    def close(self):
        self.link.close()
        self.log('stopped')
        self.journal.close()
        self.store.close()
