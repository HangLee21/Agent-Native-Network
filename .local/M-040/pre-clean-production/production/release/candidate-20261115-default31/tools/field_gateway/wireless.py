"""Bounded UDP transport to independent wireless entries. No serial or RF planner."""
import collections
import copy
import ipaddress
import json
import secrets
import socket
import threading
import time
from . import protocol as p
from .application import NoWirelessPath
from .routing import Entries
from .direct import DirectQueries


def endpoint(text):
    host, sep, port = text.rpartition(':')
    if not sep:
        host, port = text, '8792'
    address = ipaddress.IPv4Address(host)
    if address.is_multicast or address.is_unspecified or not 1 <= int(port) <= 65535:
        raise ValueError('unicast entry IPv4:port required')
    return str(address), int(port)


class WirelessLink:
    def __init__(self, host='0.0.0.0', port=8793, *, debug_entries=(), broadcast=None,
                 lease_s=10, query_timeout=2, neighbor_snapshots=False):
        ipaddress.IPv4Address(host)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.socket.bind((host, port))
            self.socket.settimeout(.1)
        except Exception:
            self.socket.close()
            raise
        self.debug = set(endpoint(v) for v in debug_entries)
        self.broadcast = (str(ipaddress.IPv4Address(broadcast)), 8792) if broadcast else None
        self.registry = Entries(self.query, lease_s=lease_s, query_timeout=query_timeout,
                                max_payload=p.MAX_PAYLOAD)
        self.stop = threading.Event()
        self.guard = threading.RLock()
        self.seen = collections.OrderedDict()
        self.cursors, self.received_cursors = {}, {}
        self.pending_hello = {}
        self.counters = collections.Counter()
        self.event_types = collections.Counter()
        self.callback = None
        self.pc_id = self.pc_boot = None
        self.thread = None
        self.direct = DirectQueries() if neighbor_snapshots else None

    def attach(self, callback, pc_id, pc_boot):
        self.callback, self.pc_id, self.pc_boot = callback, pc_id, pc_boot
        self.thread = threading.Thread(target=self.loop, name='field-wireless-ip')
        self.thread.start()

    def status(self):
        status = self.registry.status()
        with self.guard:
            return dict(status, neighbor_snapshots_enabled=self.direct is not None,
                        wire_protocol=p.SCHEMA, udp_bind=list(self.socket.getsockname()),
                        counters=dict(self.counters), decoded_event_types=dict(self.event_types),
                        event_cursors=[dict(entry_id=k[0],entry_boot=k[1],after=v,
                                            pending=len(self.received_cursors.get(k,())))
                                       for k,v in self.cursors.items()], serial_access=False,
                        debug_seed_addresses=[list(a) for a in sorted(self.debug)])

    def select(self, dst):
        return self.registry.select(dst)

    def _send(self, address, op, **fields):
        raw = p.encode(op, pc_id=self.pc_id, pc_session=self.pc_boot, **fields)
        sent = self.socket.sendto(raw, tuple(address))
        if sent != len(raw):
            raise OSError('short UDP write; business outcome unknown')
        with self.guard:
            self.counters['ip_' + op + '_sent'] += 1

    def hello(self, address):
        self._send(address, 'hello')

    def query(self, row, dst, query_id):
        self._send(row['address'], 'route', entry_boot=row['boot_id'], dst=dst, transaction=query_id)

    def send(self, record):
        selected = record['entry']
        if not self.registry.valid_sender(selected['node_id'], selected['boot_id'], selected['address']):
            raise NoWirelessPath('selected entry expired before UDP write; not automatically retried')
        if time.monotonic() >= selected['evidence_expires_at']:
            raise NoWirelessPath('selected proof expired before UDP write; no business sent')
        self._send(selected['address'], 'send', entry_boot=selected['boot_id'],
                   transaction=record['transaction_id'], dst=record['request']['dst'],
                   payload_hex=record['request']['payload_hex'])

    def _notice(self, kind, **fields):
        self.callback(dict(type=kind, **fields))

    def handle(self, raw, address):
        value = p.decode(raw)
        with self.guard:
            self.counters['decoded_datagrams'] += 1
            self.event_types[value['event']] += 1
        if value['pc_id'] != self.pc_id:
            raise ValueError('another PC logical destination')
        name, node, boot = value['event'], value['entry_id'], value['entry_boot']
        if name == 'register':
            with self.guard:
                self.pending_hello[(tuple(address), node, boot)] = time.monotonic()
                while len(self.pending_hello) > 32:
                    self.pending_hello.pop(next(iter(self.pending_hello)))
            self._send(address, 'lease', entry_boot=boot,
                       lease_ms=max(1000, min(10000, int(self.registry.lease_s*1000))))
            # Also read back status for builds where lease applies without reply.
            self.hello(address)
            return
        if name in ('status', 'hello', 'lease'):
            with self.guard:
                pending = self.pending_hello.get((tuple(address), node, boot))
            if value.get('pc_session') != self.pc_boot or pending is None or time.monotonic()-pending > 4:
                raise ValueError('entry has no current PC-session handshake')
            if value.get('max_payload_bytes') != p.MAX_PAYLOAD or value.get('online') is False:
                raise ValueError('entry handshake/capability mismatch')
            lifetime = value.get('lease_remaining_ms')
            if type(lifetime) is not int or not 0 < lifetime <= 10000:
                raise ValueError('entry has no current board lease evidence')
            previous = self.registry.valid_sender(node, boot, address)
            capabilities = next((row.get('status',{}) for row in self.registry.status()['entries']
                                 if row['node_id']==node and row['boot_id']==boot),{})
            self.registry.register(node, boot, address, lease_s=lifetime/1000,
                                   metadata=dict(capabilities,**{k:value[k] for k in ('pc_id','pc_session','ip_enabled','ip_connected','channel_pinned','service_live',
                                       'lease_remaining_ms','max_payload_bytes','latest_cursor','oldest_cursor',
                                       'event_overflow','udp_rx_drops','udp_send_fail','channel','neighbors_api') if k in value}))
            if not previous:
                self._notice('entry_registered', entry_id=node, entry_boot=boot, address=list(address), raw=value)
            self._range(node, boot, value)
            return
        if not self.registry.valid_sender(node, boot, address):
            raise ValueError('event is not from a current independent entry lease')
        if name == 'neighbors':
            if self.direct is None:
                raise ValueError('active neighbor snapshots disabled')
            proof = self.direct.receive(value, address, self.pc_boot)
            self.callback(dict(type='neighbor_snapshot', proof=proof))
            with self.guard:
                self.counters['neighbor_snapshots_matched'] += 1
            return
        if name in ('route', 'route_result'):
            if value.get('pc_session') != self.pc_boot:
                raise ValueError('route evidence belongs to another PC session')
            path = value.get('path')
            dst = p.mac(value['dst'])
            if value.get('reachable') is not True or not isinstance(path, list) or not 1 <= len(path) <= 5:
                return
            for hop in path:
                p.mac(hop)
            if path[0] != node or path[-1] != dst:
                raise ValueError('board reachability path endpoints mismatch')
            self.registry.route_evidence(node, boot, value['transaction'], dst,
                                         len(path)-1, value['expires_in_ms'], raw=value)
            return
        self._range(node, boot, value)
        cursor = value.get('event_cursor')
        if cursor is not None:
            if type(cursor) is not int or cursor < 1:
                raise ValueError('positive event_cursor required')
            identity = (node, boot, cursor)
            with self.guard:
                duplicate = identity in self.seen
                if duplicate:
                    self.counters['event_duplicates'] += 1
                else:
                    self.seen[identity] = True
                while len(self.seen) > 16384:
                    self.seen.popitem(last=False)
                key = node, boot
                seen = self.received_cursors.setdefault(key, set())
                floor = self.cursors.get(key, 0)
                seen.difference_update(c for c in tuple(seen) if c <= floor)
                if cursor > floor:
                    seen.add(cursor)
                previous_floor = floor
                while floor+1 in seen:
                    floor += 1
                    seen.remove(floor)
                self.cursors[key] = floor
                if floor > previous_floor:
                    self.counters['event_cursor_advances'] += 1
                while len(self.cursors) > 32:
                    old = next(iter(self.cursors))
                    self.cursors.pop(old)
                    self.received_cursors.pop(old, None)
                if len(seen) > 64:
                    self.counters['cursor_gap_overflow'] += 1
                    self.cursors[key] = min(seen)-1
                    seen.clear()
            if duplicate:
                return
        base = dict(entry_id=node, entry_boot=boot, pc_id=value['pc_id'], raw=value)
        base['pc_session'] = value['pc_session']
        base['receiver_pc_session'] = self.pc_boot
        if name in ('accepted', 'rejected', 'delivery'):
            transaction = p.uint32(value['transaction'], 'transaction')
            event = dict(base, type='destination_received' if name == 'delivery' else name,
                         transaction_id=transaction)
            for key in ('dst', 'origin', 'origin_boot', 'seq', 'payload_hex', 'error'):
                if key in value:
                    event[key] = value[key]
            self.callback(event)
        elif name == 'inbox':
            data = p.payload(value['payload_hex'])
            logical = value.get('logical_dst')
            if logical not in ('pc:' + str(self.pc_id), 'pc:' + format(self.pc_id, '08x')):
                raise ValueError('wrong logical PC inbox destination')
            self.callback(dict(base, type='pc_received', origin=p.mac(value['origin']),
                               origin_boot=p.uint32(value['origin_boot'], 'origin_boot'),
                               seq=p.uint32(value['seq'], 'seq'),
                               transaction_id=p.uint32(value['transaction'], 'transaction'),
                               payload_hex=data.hex()))
        elif name == 'report':
            try:
                report = normalize_report(value)
            except Exception as exc:
                with self.guard:
                    self.counters['report_normalization_rejected'] += 1
                self._notice('report_rejected', stage='normalize_report', error=str(exc), raw=value)
                raise
            with self.guard:
                self.counters['reports_normalized'] += 1
            self.callback(dict(type='report', report=report, raw=value))
        elif name not in ('idle', 'route_pending'):
            self._notice('wireless_status', **base)

    def _range(self, node, boot, value):
        oldest = value.get('oldest_cursor')
        gap = False
        if type(oldest) is int and oldest > 0:
            with self.guard:
                key = node, boot
                if self.cursors.get(key, 0) < oldest-1:
                    self.cursors[key] = oldest-1
                    self.counters['entry_event_gaps'] += 1
                    gap = True
        if gap:
            self._notice('entry_event_gap', entry_id=node, entry_boot=boot, oldest_cursor=oldest)

    def loop(self):
        next_poll = 0
        while not self.stop.is_set():
            now = time.monotonic()
            if now >= next_poll:
                status = self.registry.status()
                addresses = self.debug | {tuple(e['address']) for e in status['entries']}
                if self.broadcast:
                    addresses.add(self.broadcast)
                for address in addresses:
                    try:
                        self.hello(address)
                    except OSError:
                        with self.guard:
                            self.counters['discovery_send_failures'] += 1
                for entry in status['entries']:
                    if entry['connected']:
                        try:
                            self._send(entry['address'], 'poll', entry_boot=entry['boot_id'],
                                       after=self.cursors.get((entry['node_id'], entry['boot_id']), 0))
                        except OSError:
                            with self.guard:
                                self.counters['poll_failures'] += 1
                if self.direct is not None:
                    for address, fields in self.direct.requests(status['entries']):
                        try:
                            self._send(address, 'neighbors', **fields)
                        except OSError:
                            with self.guard:
                                self.counters['neighbor_snapshot_send_failures'] += 1
                next_poll = now + 1
            try:
                raw, address = self.socket.recvfrom(p.MAX_DATAGRAM + 1)
            except socket.timeout:
                continue
            except OSError:
                if not self.stop.is_set():
                    with self.guard:
                        self.counters['socket_errors'] += 1
                continue
            with self.guard:
                self.counters['received_datagrams'] += 1
            try:
                self.handle(raw, address)
            except Exception as exc:
                with self.guard:
                    self.counters['rejected_datagrams'] += 1
                self._notice('rejected_wireless_datagram', address=list(address), error=str(exc))

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(3)
        self.socket.close()


def normalize_report(value):
    observer = p.mac(value['observer_id'])
    boot = p.uint32(value['observer_boot'], 'observer_boot')
    seq = p.uint32(value.get('report_seq', value.get('seq')), 'report seq')
    known_age = value.get('transport_age_ms')
    rows = []
    for row in value.get('rf_neighbors', value.get('neighbors', []))[:2]:
        peer = p.mac(row['peer_id'])
        state = row.get('state', 'unknown')
        state = 'confirmed' if state == 'bidirectional' else state
        source = row.get('rf_source', 'unavailable')
        rssi = row.get('rssi_dbm') if source in ('measured', 'simulated') else None
        lower = row.get('sample_age_ms')
        lower_only = row.get('age_is_lower_bound') is True
        rows.append(dict(peer_id=peer, state=state, rssi_dbm=rssi, rf_source=source,
                         sample_age_ms=lower if type(lower) is int and type(known_age) is int and not lower_only else None,
                         sample_age_lower_bound_ms=lower,age_is_lower_bound=lower_only or type(known_age) is not int,
                         direction='peer_to_reporter', raw=row,
                         **{key:row[key] for key in ('peer_boot','sample_at_ms','sample_count','channel') if key in row}))
    return dict(schema_version=1, node_id=observer, boot_id=boot, session_id='field:' + str(boot),
                seq=seq, label=value.get('label', observer), position=None, neighbors=rows, events=[],
                report_age_ms=known_age if type(known_age) is int else 0,
                freshness_known=type(known_age) is int, transport_age_ms=known_age,
                report_scope='partial_rotating_rows',neighbors_partial=True, segment=value.get('segment'),
                counts=value.get('counts', {k:value[k] for k in ['source_admitted','relay_submitted','destination_received','record_overwritten'] if k in value}), raw=value,
                received_via_entry=value['entry_id'], source='board_wireless_summary')
