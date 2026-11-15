"""Explicit HOST MODEL of five local Edge APIs; no serial, ESP-NOW or GPS inference.

Business forwarding lives in this separate process, never in the observation gateway.
Its deterministic graph is a scenario fixture; its BFS is NOT the board algorithm.
"""
import argparse
import collections
import json
from pathlib import Path
import signal
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

IDS = {label: '02:00:00:00:30:' + format(i, '02x') for i, label in enumerate('ABCDE', 1)}
LABELS = {v: k for k, v in IDS.items()}


class Model:
    def __init__(self, output, scale):
        self.output, self.scale, self.start = output, scale, time.monotonic()
        self.lock = threading.RLock()
        self.rows = {label: dict(seq=0, events=collections.deque(maxlen=4096), inbox=collections.deque(maxlen=512), cursor=0, inbox_cursor=0, instance=uuid.uuid4().hex, boot=3000+i, requests={}) for i, label in enumerate('ABCDE')}
        self.log = (output / 'model-events.jsonl').open('x', encoding='utf-8')
        self.last_topology = None

    def elapsed(self):
        return (time.monotonic() - self.start) / self.scale

    def active(self, label):
        t = self.elapsed()
        return t >= dict(C=0, B=3, A=7, D=14, E=18)[label] and not (label == 'E' and 28 <= t < 38)

    def directions(self):
        t = self.elapsed()
        edges = set()
        def both(a, b):
            edges.update(((a, b), (b, a)))
        if t >= 3:
            edges.add(('C', 'B'))
        if t >= 6:
            both('B', 'C')
        if t >= 7:
            edges.add(('A', 'B'))
        if t >= 11:
            both('A', 'B')
        if t >= 14:
            both('A', 'D'); both('D', 'C')
        if t >= 18:
            both('D', 'E'); both('C', 'E')
        if 24 <= t < 42:
            edges.discard(('B', 'C')); edges.discard(('C', 'B'))
        return {(a, b) for a, b in edges if self.active(a) and self.active(b)}

    def write(self, kind, **fields):
        self.log.write(json.dumps(dict(kind=kind, host_ms=int(time.time()*1000), scenario_s=self.elapsed(), evidence_kind='host_model_not_RF', **fields))+'\n')
        self.log.flush()

    def event(self, label, kind, **fields):
        row = self.rows[label]
        row['cursor'] += 1
        event = dict(schema='mid.serial.v1', node_id=IDS[label], event=kind, edge_cursor=row['cursor'], rf_source='simulated', transport_source='host_model', **fields)
        row['events'].append(event)
        self.write('board_model_event', observer=label, event=event)
        return event

    def neighbors(self, label):
        edges = self.directions()
        result = [dict(peer_id=IDS[a], state='confirmed' if (label, a) in edges else 'heard', rssi_dbm=(-94 if 20 <= self.elapsed() < 24 and {a, label} == {'B', 'C'} else -58 - (ord(a)+ord(label)) % 17), sample_age_ms=0, rf_source='simulated') for a, b in sorted(edges) if b == label]
        t = self.elapsed()
        previous = [('B', 'C', 6), ('A', 'B', 11), ('A', 'D', 14), ('D', 'C', 14), ('D', 'E', 18), ('C', 'E', 18)]
        for a, b, since in previous:
            peer = b if a == label else a if b == label else None
            if peer and t >= since and (peer, label) not in edges:
                result.append(dict(peer_id=IDS[peer], state='lost', rssi_dbm=-94, sample_age_ms=int(max(0, t - (28 if peer == 'E' else 24))*self.scale*1000), rf_source='simulated'))
        return result

    def route(self, src, dst):
        edges = self.directions()
        queue = collections.deque([[src]])
        while queue:
            path = queue.popleft()
            if path[-1] == dst:
                return path
            for a, b in sorted(edges):
                if a == path[-1] and b not in path and (b, a) in edges:
                    queue.append(path+[b])
        return []

    def send(self, label, body):
        dst = LABELS.get(body['dst'])
        payload = bytes.fromhex(body['payload_hex'])
        if dst is None or dst == label or len(payload) > 160 or not isinstance(body.get('request_id'), str):
            raise ValueError('invalid business request')
        row = self.rows[label]
        request = body['request_id']
        if request in row['requests']:
            return row['requests'][request]
        if len(row['requests']) >= 2048:
            raise ValueError('model request limit reached')
        row['seq'] += 1
        identity = dict(origin=IDS[label], origin_boot=row['boot'], seq=row['seq'], dst=IDS[dst])
        receipt = dict(accepted=True, **identity, delivery_status='destination_unconfirmed', transport_source='host_model', request_id=request)
        row['requests'][request] = receipt
        self.event(label, 'tx_queued', **identity, payload_hex=payload.hex(), packet_kind='DATA')
        path = self.route(label, dst)
        if not path:
            self.event(label, 'route_no_route', **identity, reason='host_model_partition')
            return receipt
        self.event(label, 'route_selected', **identity, path=[IDS[x] for x in path], request_seq=row['seq'])
        for i, hop in enumerate(path[:-1]):
            if i:
                self.event(hop, 'rx_relay', **identity, previous_hop=IDS[path[i-1]], payload_hex=payload.hex(), packet_kind='DATA')
            self.event(hop, 'tx_submit', **identity, next_hop=IDS[path[i+1]], payload_hex=payload.hex(), packet_kind='DATA')
        end = self.event(dst, 'rx_local', **identity, previous_hop=IDS[path[-2]], payload_hex=payload.hex(), packet_kind='DATA')
        target = self.rows[dst]
        target['inbox_cursor'] += 1
        target['inbox'].append(dict(end, inbox_cursor=target['inbox_cursor']))
        self.write('delivery', path=path, identity=identity, payload_hex=payload.hex())
        return receipt


class EdgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, model, label):
        self.model, self.label = model, label
        super().__init__(('127.0.0.1', 0), Handler)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, status, data):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        m, label = self.server.model, self.server.label
        row = m.rows[label]
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path == '/api/edge/events':
            # Bounded long poll; no gateway or telemetry dependency.
            after = int(query.get('after', ['0'])[0])
            end = time.monotonic() + min(.3, max(0, float(query.get('wait', ['0'])[0])))
            while time.monotonic() < end and row['cursor'] <= after:
                time.sleep(.02)
            with m.lock:
                return self.reply(200, dict(events=[x for x in row['events'] if x['edge_cursor'] > after], cursor=row['cursor'], instance_id=row['instance']))
        with m.lock:
            if url.path == '/api/edge/status':
                return self.reply(200, dict(ok=True, node_id=IDS[label], instance_id=row['instance'], info=dict(boot_id=row['boot'], deployment_mode='host_model', radio_enabled=m.active(label)), wireless_mode='host_model', transport_source='host_model', routing_supported=True))
            if url.path == '/api/edge/neighbors':
                return self.reply(200, dict(neighbors=m.neighbors(label), source='host_model', rf_source='simulated'))
            if url.path == '/api/edge/inbox':
                after = int(query.get('after', ['0'])[0])
                return self.reply(200, dict(records=[x for x in row['inbox'] if x['inbox_cursor'] > after], cursor=row['inbox_cursor'], instance_id=row['instance']))
            if url.path == '/api/edge/routes':
                return self.reply(200, dict(routes=[], source='host_model'))
            return self.reply(404, {'error': 'not implemented in host model'})

    def do_POST(self):
        m, label = self.server.model, self.server.label
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 8192:
                raise ValueError('invalid request length')
            body = json.loads(self.rfile.read(size))
            with m.lock:
                if self.path == '/api/edge/send':
                    return self.reply(200, m.send(label, body))
                if self.path == '/api/edge/position':
                    return self.reply(200, dict(ok=True, source='host_model', position_source=body.get('source') if body else None))
                return self.reply(404, {'error': 'not implemented in host model'})
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply(400, {'error': str(exc)})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--time-scale', type=float, default=1)
    p.add_argument('--stop-file', type=Path)
    args = p.parse_args()
    if not .1 <= args.time_scale <= 10:
        p.error('time scale must be .1..10')
    args.output.mkdir(parents=True, exist_ok=False)
    model = Model(args.output, args.time_scale)
    servers = [EdgeServer(model, label) for label in 'ABCDE']
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    threads = []
    try:
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            threads.append(thread)
        meta = dict(status='ready', evidence_kind='host_model_not_RF', serial_opens=0, ports={s.label:s.server_port for s in servers}, ids=IDS, time_scale=args.time_scale, started_ms=int(time.time()*1000))
        (args.output / 'ready.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
        print(json.dumps(meta), flush=True)
        while not stop.wait(.1):
            if args.stop_file and args.stop_file.exists():
                break
            with model.lock:
                topology = sorted(model.directions())
                if topology != model.last_topology:
                    model.write('topology', directions=topology)
                    model.last_topology = topology
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(2)
        model.log.close()


if __name__ == '__main__':
    main()
