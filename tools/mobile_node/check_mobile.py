"""Finite integration checks. Synthetic boards, real loopback HTTP, optional Linux PTYs.

Every output goes beneath the required new --output directory. No physical serial.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import random
import platform
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import unittest
from http.server import ThreadingHTTPServer
from tools.mid_edge import Edge
from tools.mid_edge.mobile_position import PositionStream, validate_position
from tools.mid_sim_console.local_edge import Handler, LocalEdge
from tools.mobile_node.edge import MobileEdge
from tools.mobile_node.node import Node
from tools.mobile_node.providers import ExternalGPS, GPSD, aged_position, fake_GPS_function
from tools.mobile_node.reporting import GatewayReporter, ReportQueue, event_report, neighbor_report
from tools.mobile_node.traffic import Agent, Journal, destinations, fake_agent_function, generate_payload
from tools.mobile_gateway.server import Gateway
from tools.mobile_gateway.state import State, validate

A, B, C = '02:00:00:00:00:01', '02:00:00:00:00:02', '02:00:00:00:00:03'
OUTPUT = None
PTY = False


def eventually(predicate, timeout=8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise AssertionError('condition did not become true before deadline')


class Board:
    """Explicit model fixture: fixed A-B-C transfer, no route algorithm validation."""
    def __init__(self, mac, bus, pty=False):
        self.mac, self.bus = mac, bus
        bus[mac] = self
        self.boot, self.seq = 10 + len(bus), 0
        self.commands, self.deliveries = [], []
        self.input = bytearray()
        self.output = queue.Queue()
        self.closed = False
        self.pty = pty
        self.position = None
        self.mobile_supported = True
        self.last_epoch, self.last_position_seq = None, 0
        if pty:
            self.master, self.slave = os.openpty()
            self.device = os.ttyname(self.slave)
            self.thread = threading.Thread(target=self.pty_loop)
            self.thread.start()

    def emit(self, **fields):
        data = (json.dumps(dict(schema='mid.serial.v1', node_id=self.mac, boot_id=self.boot,
                                rf_source='simulated', **fields)) + '\n').encode()
        if self.pty:
            os.write(self.master, data)
        else:
            self.output.put(data)

    def command(self, q):
        self.commands.append(q)
        fields = {}
        cmd = q['cmd']
        if cmd in ('telemetry', 'position_set') and not self.mobile_supported:
            self.emit(event='command_result', nonce=q['nonce'], cmd=cmd, ok=False, error='unknown_command')
            return
        if cmd == 'info':
            fields = dict(firmware='mid-espnow', chip='esp32s3', deployment_mode='autonomous', discovery_saved=True)
        elif cmd == 'neighbors':
            fields = dict(neighbors=[dict(node_id=m, state='bidirectional', age_ms=20) for m in self.bus if m != self.mac])
        elif cmd == 'telemetry':
            fields = dict(rf_neighbors=[dict(peer_id=m, receiver_id=self.mac, state='bidirectional',
                                             rf_source='simulated', rssi_dbm=-55, sample_age_ms=25)
                                        for m in self.bus if m != self.mac], peer_positions=[])
        elif cmd == 'position_set':
            validate_position({k: q[k] for k in ('position_boot', 'position_seq', 'source', 'fix', 'age_ms', 'lat', 'lon', 'accuracy_m')})
            if q['position_boot'] == self.last_epoch:
                assert q['position_seq'] > self.last_position_seq
            self.last_epoch, self.last_position_seq = q['position_boot'], q['position_seq']
            self.position = q
        elif cmd == 'send':
            self.seq += 1
            identity = dict(origin=self.mac, origin_boot=self.boot, seq=self.seq, dst=q['dst'])
            self.emit(event='tx_queued', **identity)
            self.emit(event='tx_submit', next_hop=B, **identity)
            self.emit(event='tx_link_ok', next_hop=B, **identity)
            fields = dict(origin=self.mac, origin_boot=self.boot, packet_seq=self.seq, dst=q['dst'])
            if q['dst'] in self.bus and q['dst'] != self.mac:
                if B in self.bus and B not in (self.mac, q['dst']):
                    self.bus[B].emit(event='rx_relay', **identity)
                dest = self.bus[q['dst']]
                dest.deliveries.append(dict(identity, payload_hex=q['payload_hex'], at=time.monotonic()))
                dest.emit(event='rx_local', payload_hex=q['payload_hex'], **identity)
        self.emit(event='command_result', nonce=q['nonce'], cmd=cmd, ok=True, **fields)

    def write(self, data):
        self.input.extend(data)
        while b'\n' in self.input:
            line, _, tail = self.input.partition(b'\n')
            self.input[:] = tail
            self.command(json.loads(line))
        return len(data)

    def read(self, size):
        try:
            return self.output.get(timeout=.05)
        except queue.Empty:
            return b''

    def pty_loop(self):
        import select
        while not self.closed:
            if select.select([self.master], [], [], .05)[0]:
                try:
                    self.write(os.read(self.master, 4096))
                except OSError:
                    if not self.closed:
                        time.sleep(.01)

    def close(self):
        self.closed = True
        if self.pty:
            self.thread.join(1)
            os.close(self.master)
            os.close(self.slave)


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class Rig:
    def __init__(self, out):
        self.out = out
        self.bus, self.owners, self.apps, self.servers, self.threads = {}, [], [], [], []
        for name, address in [('A', A), ('B', B), ('C', C)]:
            board = Board(address, self.bus, PTY)
            edge = Edge(board.device if PTY else 'synthetic', address, 460800,
                        transport=None if PTY else board, log=str(out / (name + '-serial.jsonl')))
            self.owners.append(edge)
            app = LocalEdge(edge, out / (name + '-requests.json'))
            server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
            server.app = app
            thread = threading.Thread(target=server.serve_forever, kwargs=dict(poll_interval=.05))
            thread.start()
            self.apps.append(app)
            self.servers.append(server)
            self.threads.append(thread)
        self.clients = [MobileEdge(server.server_port, timeout=3) for server in self.servers]

    def close(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()
        for thread in self.threads:
            thread.join()
        for app in self.apps:
            app.stopping = True
            app.thread.join(1)
        for edge in self.owners:
            edge.close()
        # Queue transports are closed by Edge; PTYs need their model-side FD cleanup.
        if PTY:
            for board in self.bus.values():
                board.close()


class Checks(unittest.TestCase):
    def test_01_providers_and_lengths(self):
        current = [0.0]
        p = fake_GPS_function(seed=7, clock=lambda: current[0], wall=lambda: 1000 + current[0])
        q = fake_GPS_function(seed=7, clock=lambda: current[0], wall=lambda: 1000 + current[0])
        previous = None
        for i in range(200):
            current[0] = i * .5
            fix = p()
            self.assertEqual(fix, q())
            x = (fix['lon'] - 120) * 111320 * math.cos(math.radians(30))
            y = (fix['lat'] - 30) * 111320
            self.assertLessEqual(abs(x), 300.0001)
            self.assertLessEqual(abs(y), 200.0001)
            if previous:
                self.assertLessEqual(math.hypot(x - previous[0], y - previous[1]), .7001)
            previous = (x, y)
        self.assertTrue(aged_position(p(), max_age_s=1, now=1200)['stale'])
        stale = aged_position(p(), max_age_s=1, now=1200)
        self.assertFalse(stale['valid'])
        gateway_state = State(clock=lambda: 1200000)
        gateway_state.accept(dict(schema_version=1, node_id=A, boot_id=1, session_id='expiry-check',
                                 seq=1, label='A', position=stale, neighbors=[], events=[]))
        self.assertTrue(gateway_state.snapshot()['nodes'][0]['position']['stale'])
        external = ExternalGPS('tools.mobile_node.check_mobile:external_fix')
        self.assertEqual(external()['source'], 'external')
        lengths = set()
        rng = random.Random(29)
        for _ in range(3000):
            payload = generate_payload(rng, 0, 160)
            lengths.add(len(payload))
            self.assertTrue(all(32 <= b < 127 for b in payload))
        self.assertEqual(lengths, set(range(161)))
        self.assertEqual(len(generate_payload(rng, 160, 160)), 160)
        self.assertEqual(generate_payload(rng, 0, 0), b'')
        with self.assertRaises(ValueError):
            generate_payload(rng, 0, 161)
        self.assertIsNone(event_report(dict(event='command_result'), A))
        choice = event_report(dict(event='route_selected', origin=A, origin_boot=11, seq=7, dst=C, request=7), A)
        self.assertIsNone(choice['packet'])
        self.assertEqual(choice['sequence_scope'], 'route_request')
        control = event_report(dict(event='tx_submit', origin=A, origin_boot=11, seq=1, dst=C, packet_kind='RREQ'), A)
        self.assertEqual(control['kind'], 'control')
        self.assertIsNone(control['packet'])
        self.assertEqual(neighbor_report(dict(neighbors=[dict(node_id=B, state='bidirectional', age_ms=30)]))[0],
                         dict(peer_id=B, state='confirmed', rssi_dbm=None, sample_age_ms=30,
                              rf_source='unavailable', direction='peer_to_reporter',
                              raw=dict(node_id=B, state='bidirectional', age_ms=30)))

    def test_02_gpsd_no_fix(self):
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen()
        release, finish = threading.Event(), threading.Event()
        commands = []
        def producer():
            conn, _ = server.accept()
            with conn:
                commands.append(conn.recv(1024).decode())
                from datetime import datetime, timezone
                row = dict(class_='unused')
                row = {'class': 'TPV', 'mode': 3, 'lat': 30.1, 'lon': 120.2,
                       'time': datetime.now(timezone.utc).isoformat(), 'eph': 2.5}
                wire = (json.dumps(row) + '\r\n').encode()
                conn.sendall(wire[:12])
                conn.sendall(wire[12:])
                release.wait(3)
                conn.sendall(b'{"class":"TPV","mode":1}\r\n')
                finish.wait(3)
        thread = threading.Thread(target=producer)
        thread.start()
        gps = GPSD(port=server.getsockname()[1], timeout=.1)
        try:
            fix = gps()
            self.assertEqual(fix['source'], 'gpsd')
            self.assertEqual(fix['accuracy_m'], 2.5)
            release.set()
            self.assertIsNone(gps())
            self.assertIn('?WATCH=', commands[0])
        finally:
            release.set()
            finish.set()
            gps.close()
            thread.join(4)
            server.close()

    def test_03_queue_reopen_and_overflow(self):
        path = OUTPUT / 'bounded.sqlite3'
        q = ReportQueue(path, 2)
        for seq in range(1, 6):
            q.put(dict(seq=seq))
        self.assertEqual(q.stats()['dropped_reports'], 3)
        q.close()
        q = ReportQueue(path, 2)
        self.assertEqual(q.peek()[1]['seq'], 4)
        q.ack(q.peek()[0])
        self.assertEqual(q.peek()[1]['seq'], 5)
        q.close()

    def test_03b_continuous_api_stop_and_seed(self):
        class MemoryLog:
            def __init__(self):
                self.rows = []
            def write(self, kind, **fields):
                self.rows.append(dict(kind=kind, **fields))
        class FakeAPI:
            def __init__(self, own=A):
                self.own, self.empty_rounds, self.sends, self.received = own, 0, [], False
            def status(self):
                return dict(node_id=self.own)
            def neighbors(self):
                self.empty_rounds += 1
                return dict(neighbors=[] if self.empty_rounds <= 2 else [dict(node_id=C), dict(node_id=self.own)])
            def send(self, dst, payload, request_id):
                self.sends.append(dict(dst=dst, payload_hex=payload.hex(), request_id=request_id))
                if len(self.sends) == 1:
                    raise TimeoutError('synthetic unknown outcome; never resend')
                return dict(state='locally_accepted', board_terminal='route_no_route', delivery_status='destination_unconfirmed')
            def events(self, cursor, wait):
                time.sleep(.01)
                if self.sends and not self.received:
                    self.received = True
                    return dict(cursor=1, instance_id='fake-api', events=[dict(event='rx_local', node_id=self.own,
                                origin=C, origin_boot=33, seq=9, dst=self.own, payload_hex='48656c6c6f')])
                return dict(cursor=cursor, instance_id='fake-api', events=[])
        traces = []
        for own in (A, A, B):
            api, log, stop = FakeAPI(own), MemoryLog(), threading.Event()
            thread = threading.Thread(target=fake_agent_function, args=(api, log),
                kwargs=dict(stop=stop, seed=87, interval_min=.05, interval_max=.06,
                            min_bytes=0, max_bytes=160))
            thread.start()
            eventually(lambda: len(api.sends) >= 4 and any(r['kind'] == 'received' for r in log.rows))
            stop.set()
            thread.join(1)
            self.assertFalse(thread.is_alive())
            count = len(api.sends)
            time.sleep(.07)
            self.assertEqual(len(api.sends), count)
            self.assertEqual(len(set(r['request_id'] for r in api.sends)), count)
            self.assertTrue(all(r['dst'] != own for r in api.sends))
            self.assertTrue(any(r['kind'] == 'agent_idle' for r in log.rows))
            self.assertTrue(any(r['kind'] == 'send_outcome_unknown' for r in log.rows))
            self.assertGreaterEqual(sum(r['kind'] == 'send_receipt' for r in log.rows), 3)
            traces.append(dict(own=own, sends=api.sends, log=log.rows, stopped=True))
        project = lambda t: [(r['dst'], r['payload_hex']) for r in t['sends'][:4]]
        self.assertEqual(project(traces[0]), project(traces[1]))
        self.assertNotEqual(project(traces[0]), project(traces[2]))
        (OUTPUT / 'continuous-api.json').write_text(json.dumps(traces, indent=2))

    def test_04_offline_business_reconnect_cli(self):
        out = OUTPUT / 'integration'
        out.mkdir()
        rig = Rig(out)
        state = State()
        Gateway.allow_reuse_address = True
        gateway = Gateway(('127.0.0.1', 0), state, out)
        gateway_port = gateway.server_port
        gateway_thread = threading.Thread(target=gateway.serve_forever, kwargs=dict(poll_interval=.05))
        gateway_thread.start()
        stop = threading.Event()
        journals, queues, threads, nodes = [], [], [], []
        try:
            for index, label in [(0, 'A'), (2, 'C')]:
                journal = Journal(out / (label + '-node.jsonl'))
                q = ReportQueue(out / (label + '-reports.sqlite3'), 3)
                node = Node(MobileEdge(rig.servers[index].server_port),
                            fake_GPS_function(seed=index + 9), q, journal, label,
                            sample_s=.1, report_s=.25)
                reporter = GatewayReporter('http://127.0.0.1:' + str(gateway_port), q, journal,
                                           timeout=.2, retry_s=.1)
                agent = Agent(MobileEdge(rig.servers[index].server_port), journal, seed=index + 19,
                              interval_min=.1, interval_max=.2, min_bytes=0, max_bytes=160,
                              dest=[A, C])
                for target in (node.run, reporter.run, agent.run):
                    thread = threading.Thread(target=target, args=(stop,))
                    thread.start()
                    threads.append(thread)
                journals.append(journal)
                queues.append(q)
                nodes.append(node)
            eventually(lambda: len(state.snapshot()['nodes']) == 2)
            eventually(lambda: len(rig.bus[C].deliveries) >= 2 and len(rig.bus[A].deliveries) >= 2)
            initial = state.snapshot()
            gateway.shutdown()
            gateway.server_close()
            gateway_thread.join()
            gateway = None
            before = len(rig.bus[C].deliveries) + len(rig.bus[A].deliveries)
            eventually(lambda: all(q.stats()['dropped_reports'] >= 1 for q in queues), timeout=10)
            offline = len(rig.bus[C].deliveries) + len(rig.bus[A].deliveries)
            self.assertGreater(offline, before)
            retained = [q.stats() for q in queues]
            self.assertTrue(all(v['pending_reports'] <= 3 for v in retained))
            # Reconnect the actual H gateway implementation, at the same address.
            Gateway.allow_reuse_address = True
            gateway = Gateway(('127.0.0.1', gateway_port), state, out)
            gateway_thread = threading.Thread(target=gateway.serve_forever, kwargs=dict(poll_interval=.05))
            gateway_thread.start()
            eventually(lambda: any(n['seq'] > 5 for n in state.snapshot()['nodes']))
            eventually(lambda: any(e['type'] == 'rx_local' for e in state.history()['events']))
            self.assertTrue(all(n['position']['source'] == 'simulated' for n in state.snapshot()['nodes']))
            self.assertTrue(all(e['rf_source'] == 'simulated' for e in state.snapshot()['edges']))
            for node in nodes:
                validate(node.snapshot())
            # Board restart uses a new report session; original packet boot IDs remain intact.
            old_session = nodes[0].session
            rig.bus[A].boot += 100
            eventually(lambda: nodes[0].session != old_session)
            eventually(lambda: next(n for n in state.snapshot()['nodes'] if n['node_id'] == A)['boot_id'] == rig.bus[A].boot)
            # Run the public node and standalone agent entry points as finite processes.
            commands = []
            for args in [
                ['node', '--gps', 'none', '--report-s', '.25', '--sample-s', '.1',
                 '--gateway', 'http://127.0.0.1:' + str(gateway_port)],
                ['agent', '--interval-min', '.1', '--interval-max', '.2', '--min-bytes', '160', '--max-bytes', '160', '--dest', C]]:
                cmd = [sys.executable, '-X', 'utf8', '-m', 'tools.mobile_node'] + args + [
                    '--edge-port', str(rig.servers[1].server_port), '--state', str(out / ('cli-' + args[0])), '--duration', '1.5']
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                commands.append(dict(argv=cmd, returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
                self.assertEqual(result.returncode, 0, result.stderr)
            # HTTP validation rejects path injection and out-of-range payloads before serial.
            before_position = len([c for c in rig.bus[B].commands if c['cmd'] == 'position_set'])
            valid = PositionStream().encode(None)
            with self.assertRaises(urllib.error.HTTPError) as err:
                rig.clients[1]._call('/api/edge/position', dict(valid, path=[A, B, C]))
            self.assertEqual(err.exception.code, 400)
            self.assertEqual(before_position, len([c for c in rig.bus[B].commands if c['cmd'] == 'position_set']))
            rig.bus[B].mobile_supported = False
            with self.assertRaises(urllib.error.HTTPError) as err:
                rig.clients[1].telemetry()
            self.assertEqual(err.exception.code, 422)
            legacy_log = Journal(out / 'B-legacy.jsonl')
            legacy = Node(rig.clients[1], fake_GPS_function(seed=3), None, legacy_log, sample_s=.05)
            legacy_stop = threading.Event()
            legacy_worker = threading.Thread(target=legacy.positions, args=(legacy_stop,))
            legacy_worker.start()
            try:
                eventually(lambda: len([c for c in rig.bus[B].commands if c['cmd'] == 'position_set']) > before_position)
                time.sleep(.3)
            finally:
                legacy_stop.set()
                legacy_worker.join(4)
                legacy_log.close()
            self.assertFalse(legacy_worker.is_alive())
            self.assertEqual(len([c for c in rig.bus[B].commands if c['cmd'] == 'position_set']), before_position + 1)
            for board in rig.bus.values():
                for command in board.commands:
                    self.assertNotIn(command['cmd'], ['deploy', 'link_filter', 'route_config'])
                    if command['cmd'] == 'send':
                        self.assertNotEqual(command['dst'], board.mac)
                        self.assertLessEqual(len(bytes.fromhex(command['payload_hex'])), 160)
                        self.assertEqual(set(command), {'schema', 'cmd', 'nonce', 'dst', 'payload_hex'})
            final = state.snapshot()
            timeline = state.history()
            self.assertTrue(any(e['data'].get('boot') and e['data'].get('dst') for e in timeline['events'] if e['type'] == 'rx_local'))
            for row in timeline['events']:
                if row['type'] != 'rx_local':
                    continue
                event = row['data']
                original = next(d for d in rig.bus[event['dst']].deliveries
                                if (d['origin'], d['origin_boot'], d['seq'], d['dst']) ==
                                (event['origin'], event['boot'], event['seq'], event['dst']))
                self.assertEqual(original['payload_hex'], event['payload_hex'])
            self.assertTrue(any(e['data'].get('report_age_ms', 0) > 0 for e in timeline['events']) or any(n['report_age_ms'] > 0 for n in final['nodes']))
            (out / 'checks.json').write_text(json.dumps(dict(initial=initial, final=final,
                timeline=timeline, offline_deliveries=offline-before, retained_during_outage=retained,
                cli_commands=commands, delivery_records={m: b.deliveries for m, b in rig.bus.items()},
                commands={m: b.commands for m, b in rig.bus.items()}, physical_RF=False, linux_PTY=PTY), indent=2))
        finally:
            stop.set()
            for thread in threads:
                thread.join(6)
                self.assertFalse(thread.is_alive())
            if gateway:
                gateway.shutdown()
                gateway.server_close()
                gateway_thread.join()
            rig.close()
            for q in queues:
                q.close()
            for journal in journals:
                journal.close()


def external_fix():
    return dict(lat=30, lon=120, sampled_at=time.time(), accuracy_m=None)


def main():
    global OUTPUT, PTY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--pty', action='store_true', help='Linux PTYs using actual pyserial exclusive owners')
    args = parser.parse_args()
    OUTPUT, PTY = args.output, args.pty
    OUTPUT.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    paths = list((root / 'tools/mobile_node').glob('*.py')) + list((root / 'deploy/mobile_node').glob('*'))
    paths += [root / p for p in ['tools/mid_edge/client.py', 'tools/mid_edge/local_api.py',
        'tools/mid_edge/mobile_position.py', 'tools/mid_sim_console/local_edge.py',
        'tools/mobile_gateway/state.py', 'tools/mobile_gateway/server.py',
        'firmware/mid_baseline/mobile_telemetry/TELEMETRY.md',
        'firmware/mid_baseline/mobile_telemetry/idf/main/app_main.c']]
    hashes = {}
    for path in paths:
        if path.is_file():
            raw = path.read_bytes()
            relative = path.relative_to(root)
            target = OUTPUT / 'source' / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            hashes[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, timeout=5).strip()
    except Exception:
        commit = None
    manifest = dict(task_id='E2-028', run_id=OUTPUT.name,
        started_at=datetime.now(timezone.utc).isoformat(), timezone='Asia/Shanghai', worktree=str(root),
        git_commit=commit, dirty_files_sha256=hashes, command=getattr(sys, 'orig_argv', sys.argv),
        python_executable=sys.executable, dependency_snapshot=dict(python=sys.version, platform=platform.platform()),
        upstream_commit=None, data_and_weights_sha256={}, config_file=None, seeds=[1,3,7,9,11,19,21,29,87],
        budget=dict(finite_suite=True, per_condition_timeout_s=8), output_directory=str(OUTPUT.resolve()),
        process_id=os.getpid(), finished_at=None, exit_code=None, status='running', review_reference=None,
        limitations=['Synthetic board events and fixed model transfer; no board routing/RF validation.',
                    'Loopback HTTP; no physical Pi, USB, GNSS or multiple hosts.',
                    'GPSD tested against a local protocol fixture.',
                    'Linux PTY uses actual pyserial only when --pty is set.'])
    (OUTPUT / 'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    with (OUTPUT / 'unittest.txt').open('x', encoding='utf-8') as transcript:
        class Tee:
            def write(self, text):
                sys.stderr.write(text)
                transcript.write(text)
            def flush(self):
                sys.stderr.flush()
                transcript.flush()
        result = unittest.TextTestRunner(verbosity=2, stream=Tee()).run(suite)
    (OUTPUT / 'summary.json').write_text(json.dumps(dict(tests=result.testsRun, errors=len(result.errors),
        failures=len(result.failures), success=result.wasSuccessful(), physical_RF=False, linux_PTY=PTY), indent=2))
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=0 if result.wasSuccessful() else 1,
                    status='passed' if result.wasSuccessful() else 'failed')
    (OUTPUT / 'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__ == '__main__':
    main()
