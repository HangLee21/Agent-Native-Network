"""Bounded durable observation queue; gateway failures never gate business sends."""
import json
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import uuid


class ReportQueue:
    def __init__(self, path, limit=120):
        if not 1 <= limit <= 10000:
            raise ValueError('report queue must hold 1..10000 snapshots')
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.limit = limit
        self.db.execute('CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, body TEXT NOT NULL, created REAL NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL)')
        self.db.execute("INSERT OR IGNORE INTO counters VALUES ('dropped_reports', 0)")
        self.db.commit()
        # A reduced limit also applies to reports retained by an earlier run.
        with self.lock, self.db:
            self._trim()

    def _trim(self):
        count = self.db.execute('SELECT COUNT(*) FROM reports').fetchone()[0]
        excess = max(0, count - self.limit)
        if excess:
            self.db.execute('DELETE FROM reports WHERE id IN (SELECT id FROM reports ORDER BY id LIMIT ?)', (excess,))
            self.db.execute("UPDATE counters SET value=value+? WHERE name='dropped_reports'", (excess,))

    def put(self, report):
        with self.lock, self.db:
            self.db.execute('INSERT INTO reports (body,created) VALUES (?,?)', (json.dumps(report), time.time()))
            self._trim()

    def peek(self):
        with self.lock:
            row = self.db.execute('SELECT id,body,created FROM reports ORDER BY id LIMIT 1').fetchone()
            return (row[0], json.loads(row[1]), row[2]) if row else None

    def ack(self, key):
        with self.lock, self.db:
            self.db.execute('DELETE FROM reports WHERE id=?', (key,))

    def stats(self):
        with self.lock:
            return dict(pending_reports=self.db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],
                        dropped_reports=self.db.execute("SELECT value FROM counters WHERE name='dropped_reports'").fetchone()[0],
                        retained_limit=self.limit)

    def close(self):
        self.db.close()


class GatewayReporter:
    def __init__(self, url, queue, journal, timeout=1, retry_s=1):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('gateway HTTP(S) base URL required')
        self.url = url.rstrip('/') + '/api/v1/reports'
        self.queue, self.journal = queue, journal
        self.timeout, self.retry_s = timeout, retry_s
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def run(self, stop):
        offline = False
        while not stop.is_set():
            item = self.queue.peek()
            if item is None:
                stop.wait(.1)
                continue
            key, report, created = item
            report['report_age_ms'] = max(0, int((time.time() - created) * 1000))
            try:
                request = urllib.request.Request(self.url, json.dumps(report).encode(),
                                                 headers={'Content-Type': 'application/json'})
                with self.opener.open(request, timeout=self.timeout) as response:
                    response.read(65536)
                self.queue.ack(key)
                if offline:
                    self.journal.write('gateway_reconnected')
                offline = False
                self.journal.write('report_accepted', session_id=report['session_id'], seq=report['seq'],
                                   report_age_ms=report['report_age_ms'])
            except Exception as exc:
                if not offline:
                    self.journal.write('gateway_offline', error=str(exc))
                offline = True
                stop.wait(self.retry_s)


def neighbor_report(raw, telemetry=None):
    """Missing RF measurements stay null; GPS never enters this function."""
    from .traffic import mac
    result = []
    peers = {p.get('peer_id', p.get('node_id')): dict(p) for p in raw.get('neighbors', [])}
    for sample in (telemetry or {}).get('rf_neighbors', []):
        peer_id = sample.get('peer_id')
        peers[peer_id] = dict(peers.get(peer_id, {}), **sample)
    for peer in peers.values():
        try:
            peer_id = mac(peer.get('peer_id', peer.get('node_id')))
        except ValueError:
            continue
        source = peer.get('rf_source', 'unavailable')
        if source not in ('measured', 'simulated', 'unavailable'):
            source = 'unavailable'
        rssi = peer.get('rssi_dbm') if source != 'unavailable' else None
        state = peer.get('state', 'unknown')
        state = 'confirmed' if state == 'bidirectional' else state
        age = peer.get('sample_age_ms', peer.get('age_ms'))
        result.append(dict(peer_id=peer_id, state=state, rssi_dbm=rssi,
                           sample_age_ms=age,
                           rf_source=source, direction='peer_to_reporter', raw=peer))
    return result


def event_report(event, observer_id, default_rf_source='unavailable'):
    name = event.get('event', 'unknown')
    if name in ('command_result', 'boot', 'info'):
        return None
    if name == 'rx_local':
        kind = 'received'
    elif name == 'rx_relay':
        kind = 'relayed'
    elif name in ('tx_queued', 'tx_submit', 'tx_link_ok', 'tx_link_fail', 'tx_drop'):
        kind = 'sent'
    else:
        kind = 'control' if name.startswith(('route_', 'neighbor', 'position', 'rssi')) else 'status'
    packet = None
    route_round = name in ('route_request', 'route_candidate', 'route_selected')
    control_packet = event.get('packet_kind', 'DATA') != 'DATA'
    if not route_round and not control_packet and all(k in event for k in ('origin', 'origin_boot', 'seq', 'dst')):
        packet = dict(origin=event['origin'], boot=event['origin_boot'], seq=event['seq'], dst=event['dst'])
    if kind == 'sent' and (packet is None or event.get('packet_kind', 'DATA') != 'DATA'):
        kind = 'control'
    source = event.get('rf_source', default_rf_source)
    if source not in ('measured', 'simulated', 'unavailable'):
        source = 'unavailable'
    return dict(kind=kind, event=name, observer_id=observer_id, packet=packet,
                sequence_scope='route_request' if route_round else 'control' if control_packet else 'business' if packet else None,
                **(packet or {}), **({'payload_hex': event['payload_hex']} if 'payload_hex' in event else {}),
                rf_source=source, raw=event,
                delivery_status='destination_received' if kind == 'received' else 'destination_unconfirmed')
