"""Finite real UDP/HTTP checks with explicitly synthetic field.ip.v2 entries."""
import argparse
import collections
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
from .application import Application
from .client import Client
from .offline import OfflineLink
from .protocol import SCHEMA, MAX_PAYLOAD
from .server import Server
from .wireless import WirelessLink

A, B, C, D = ['02:00:00:00:00:0' + str(i) for i in range(1, 5)]
OUT = None


def until(test, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        result = test()
        if result:
            return result
        time.sleep(.02)
    raise AssertionError('finite observation timed out')


class Entry:
    """UDP fixture only. Its fixed paths are not a board routing implementation."""
    def __init__(self, node, pc_address, bus, path):
        self.node, self.pc_address, self.bus, self.path = node, pc_address, bus, path
        self.boot = 10 + len(bus)
        self.pc_id = 91
        self.session = 0
        self.lease_until = 0
        self.cursor = 0
        self.commands, self.events, self.payloads = [], [], []
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('127.0.0.1', 0))
        self.socket.settimeout(.02)
        self.address = self.socket.getsockname()
        self.offline = False
        self.stop = threading.Event()
        self.receipt_gate = threading.Event()
        self.receipt_gate.set()
        bus[node] = self
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def emit(self, name, retained=False, **fields):
        value = dict(schema=SCHEMA, event=name, entry_id=self.node, entry_boot=self.boot,
                     pc_id=self.pc_id, pc_session=self.session, **fields)
        if retained:
            self.cursor += 1
            value['event_cursor'] = self.cursor
            self.events.append(value)
            self.events = self.events[-16:]
        if not self.offline:
            self.socket.sendto(json.dumps(value).encode(), self.pc_address)
        return value

    def run(self):
        announce = 0
        pending = []
        while not self.stop.is_set():
            if not self.offline and time.monotonic() >= announce:
                self.emit('register')
                announce = time.monotonic()+.15
            if self.receipt_gate.is_set():
                for message in pending:
                    self.emit('delivery', retained=True, **message)
                pending.clear()
            try:
                raw, address = self.socket.recvfrom(1025)
            except socket.timeout:
                continue
            if self.offline:
                continue
            value = json.loads(raw)
            self.commands.append(value)
            assert value['schema'] == SCHEMA
            op = value['op']
            self.pc_id = value['pc_id']
            if op == 'lease':
                assert value['entry_boot'] == self.boot
                self.session = value['pc_session']
                self.lease_until = time.monotonic()+value['lease_ms']/1000
                if self.node == A:
                    self.emit('status', max_payload_bytes=128, lease_remaining_ms=value['lease_ms'],
                              ip_connected=True, service_live=True)
            elif op == 'hello':
                if self.session and self.lease_until > time.monotonic():
                    self.emit('status', max_payload_bytes=128,
                              lease_remaining_ms=max(1,int((self.lease_until-time.monotonic())*1000)),
                              ip_connected=True,service_live=True,
                              oldest_cursor=self.events[0]['event_cursor'] if self.events else 0)
            elif op == 'route':
                self.emit('route', transaction=value['transaction'], dst=value['dst'],
                          reachable=value['dst'] == C, path=self.path, expires_in_ms=1000)
            elif op == 'send':
                assert len(bytes.fromhex(value['payload_hex'])) <= 128
                assert value['pc_session'] == self.session
                self.payloads.append(value)
                seq = len(self.payloads)
                if value['dst'] == self.node:
                    self.emit('delivery', retained=True, transaction=value['transaction'], origin=self.node,
                              origin_boot=self.boot, seq=seq, payload_hex=value['payload_hex'], transport='wifi_direct')
                    continue
                self.emit('accepted', retained=True, transaction=value['transaction'], origin=self.node,
                          origin_boot=self.boot, seq=seq)
                pending.append(dict(transaction=value['transaction'], origin=self.node,
                                    origin_boot=self.boot, seq=seq, dst=value['dst'], payload_hex=value['payload_hex']))
            elif op == 'poll':
                later = [e for e in self.events if e['event_cursor'] > value['after']]
                if later:
                    self.socket.sendto(json.dumps(later[0]).encode(), address)

    def up(self, transaction, payload=b'Remote to PC', seq=7):
        return self.emit('inbox', retained=True, transaction=transaction, origin=C, origin_boot=33,
                         seq=seq, logical_dst='pc:'+str(self.pc_id), payload_hex=payload.hex())

    def close(self):
        self.stop.set()
        self.thread.join(2)
        self.socket.close()


class Rig:
    def __init__(self, path):
        self.link = WirelessLink('127.0.0.1', 0, lease_s=1, query_timeout=.12)
        self.app = Application(path, self.link, pc_id=91)
        self.server = Server(0, self.app, Path(__file__).resolve().parents[2]/'research/agent_native_network/mobile_gateway')
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval':.05})
        self.thread.start()
        self.client = Client(self.server.server_port)
        self.bus = {}
        pc = self.link.socket.getsockname()
        self.a = Entry(A, pc, self.bus, [A, D, C])
        self.b = Entry(B, pc, self.bus, [B, C])
        until(lambda: len(self.client.status()['entries']) == 2)

    def close(self):
        for entry in self.bus.values():
            entry.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.close()


class Checks(unittest.TestCase):
    def test_01_empty_ui_and_no_wireless_side_effect(self):
        app = Application(OUT/'offline', OfflineLink(), pc_id=8)
        server = Server(0, app, Path(__file__).resolve().parents[2]/'research/agent_native_network/mobile_gateway')
        worker = threading.Thread(target=server.serve_forever, kwargs={'poll_interval':.05})
        worker.start()
        client = Client(server.server_port)
        try:
            status = client.status()
            self.assertFalse(status['connected'])
            self.assertEqual(status['entries'], [])
            self.assertFalse(status['serial_access'])
            self.assertEqual(client.call('/api/v1/state')['nodes'], [])
            with self.assertRaises(urllib.error.HTTPError) as exc:
                client.send(C, b'No link', 'offline-message-01')
            self.assertEqual(exc.exception.code, 503)
            self.assertIsNone(app.store.get('offline-message-01'))
            self.assertEqual(client.inbox()['records'], [])
        finally:
            server.shutdown();server.server_close();worker.join();app.close()

    def test_02_bidirectional_dynamic_failover(self):
        rig = Rig(OUT/'dynamic')
        try:
            rig.b.receipt_gate.clear()
            receipt = rig.client.send(C, bytes(range(128)), 'first-downlink-01')['record']
            self.assertEqual(receipt['entry']['node_id'], B)
            self.assertEqual(receipt['entry']['basis'], 'board_route_evidence')
            until(lambda: rig.client.request('first-downlink-01')['record']['entry_accepted'])
            self.assertFalse(rig.client.request('first-downlink-01')['record']['destination_received'])
            rig.b.emit('delivery', retained=True, transaction=receipt['transaction_id'], origin=B,
                       origin_boot=rig.b.boot, seq=1, dst=C, payload_hex='00')
            until(lambda: any(e['kind']=='payload_mismatch_receipt' for e in rig.client.events()['events']))
            self.assertFalse(rig.client.request('first-downlink-01')['record']['destination_received'])
            self.assertEqual(rig.client.inbox()['records'], [])
            # A repeated UI action must not transmit this original transaction again.
            rig.client.send(C, bytes(range(128)), 'first-downlink-01')
            self.assertEqual(len(rig.b.payloads), 1)
            rig.b.receipt_gate.set()
            until(lambda: rig.client.request('first-downlink-01')['record']['destination_received'])
            self.assertEqual(rig.client.inbox()['records'], [])
            rig.a.up(501)
            until(lambda: len(rig.client.inbox()['records']) == 1)
            rig.b.up(501, seq=9)
            until(lambda: rig.client.status()['counters']['inbox_duplicates'] == 1)
            self.assertEqual(len(rig.client.inbox()['records']), 1)
            self.assertEqual(rig.client.inbox()['records'][0]['payload_hex'], b'Remote to PC'.hex())
            before = time.monotonic()
            rig.b.offline = True
            until(lambda: [e['node_id'] for e in rig.client.status()['entries'] if e['connected']] == [A])
            second = rig.client.send(C, b'New packet after loss', 'second-downlink-02')['record']
            self.assertEqual(second['entry']['node_id'], A)
            until(lambda: rig.client.request('second-downlink-02')['record']['destination_received'])
            rig.a.up(502, b'New reverse packet', seq=10)
            until(lambda: len(rig.client.inbox()['records']) == 2)
            self.assertEqual(len(rig.b.payloads), 1)
            # Direct-IP destination uses only its own current registration, no RF path guess.
            direct = rig.client.send(A, b'Direct IP', 'direct-downlink-03')['record']
            self.assertEqual(direct['entry']['basis'], 'direct_ip_registration')
            self.assertEqual(direct['entry']['hops'], 0)
            until(lambda: rig.client.request('direct-downlink-03')['record']['destination_received'])
            # Retained event poll can replay receipts without a second business send.
            rig.a.socket.sendto(json.dumps(rig.a.events[0]).encode(), rig.a.pc_address)
            until(lambda: rig.client.status()['wireless']['counters'].get('event_duplicates', 0) > 0)
            rig.a.offline = True
            until(lambda: not rig.client.status()['connected'])
            with self.assertRaises(urllib.error.HTTPError) as exc:
                rig.client.send(C, b'No entries', 'no-entry-downlink-04')
            self.assertEqual(exc.exception.code, 503)
            # A surviving entry can register again without erasing other history.
            rig.b.offline = False
            until(lambda: any(e['node_id'] == B and e['connected'] for e in rig.client.status()['entries']))
            with self.assertRaises(urllib.error.HTTPError):
                rig.client.send(C, bytes(129), 'too-long-downlink-05')
            with self.assertRaises(urllib.error.HTTPError):
                rig.client.send(C, b'Changed', 'first-downlink-01')
            self.assertEqual(len(rig.b.payloads), 1)
            result = dict(status=rig.client.status(), inbox=rig.client.inbox(),
                          events=rig.client.events(), elapsed_since_failure_s=time.monotonic()-before,
                          requests=[rig.client.request(key) for key in ['first-downlink-01','second-downlink-02','direct-downlink-03']],
                          udp_commands={m:e.commands for m,e in rig.bus.items()}, physical_RF=False)
            (OUT/'dynamic/checks.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        finally:
            rig.close()

    def test_03_durable_identity_and_unknown_no_replay(self):
        path = OUT/'durable'
        app = Application(path, OfflineLink(), pc_id=15)
        request = dict(dst=C, payload_hex='4869')
        record, _ = app.store.reserve('saved-unknown-001', request, dict(node_id=A, boot_id=11, address=['127.0.0.1', 1]))
        app.close()
        app = Application(path, OfflineLink(), pc_id=15)
        try:
            result = app.send(dict(request_id='saved-unknown-001', **request))
            self.assertEqual(record['transaction_id'], result['transaction_id'])
            self.assertEqual(result['state'], 'outcome_unknown')
            self.assertNotEqual(app.store.pc_boot, result['pc_boot'])
        finally:
            app.close()

    def test_04_public_cli_and_report_freshness(self):
        rig = Rig(OUT/'cli')
        try:
            commands = []
            for args in [
                ['await-entries','--count','2','--timeout','2'],
                ['send','--dst',C,'--text','CLI wireless bytes','--request-id','cli-downlink-001','--wait','2'],
                ['recv','--wait','.1'],
                ['watch','--duration','.3','--interval','.1']]:
                command = [sys.executable,'-X','utf8','-m','tools.field_gateway',*args,'--port',str(rig.server.server_port)]
                result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2 if args[0] == 'recv' else 0, result.stderr)
                commands.append(dict(argv=command, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
            # A partial report with unknown transport age must not invent live nodes/edges.
            rig.a.emit('report', retained=True, observer_id=C, observer_boot=33, report_seq=1,
                       transport_age_ms=None, segment=1, counts={'received':3},
                       rf_neighbors=[dict(peer_id=B,state='bidirectional',rssi_dbm=-60,
                                          sample_age_ms=1000,rf_source='simulated')])
            until(lambda: len(rig.client.call('/api/v1/state')['nodes']) == 1)
            snapshot = rig.client.call('/api/v1/state')
            self.assertIsNone(snapshot['nodes'][0]['position'])
            self.assertEqual(snapshot['nodes'][0]['telemetry_status'], 'unknown')
            self.assertFalse(snapshot['edges'][0]['mutual_confirmed'])
            self.assertIsNone(snapshot['edges'][0]['sample_age_ms'])
            (OUT/'cli/checks.json').write_text(json.dumps(dict(commands=commands,map=snapshot),indent=2), encoding='utf-8')
        finally:
            rig.close()

    def test_05_native_ttl_and_capture(self):
        rig = Rig(OUT/'native-ttl')
        try:
            rig.link.registry.query_timeout = 2
            started = time.monotonic()
            record = rig.client.send(C,b'Native 1000ms proof','native-ttl-packet-01')['record']
            self.assertLess(time.monotonic()-started, 1)
            self.assertEqual(record['entry']['node_id'], B)
            until(lambda: rig.client.request('native-ttl-packet-01')['record']['destination_received'])
            command = [sys.executable,'-X','utf8','-m','tools.field_gateway.capture',
                       '--port',str(rig.server.server_port),'--output',str(OUT/'native-ttl/capture'),
                       '--duration','.3','--interval','.1']
            result = subprocess.run(command,capture_output=True,text=True,timeout=5)
            self.assertEqual(result.returncode,0,result.stderr)
            summary = json.loads((OUT/'native-ttl/capture/summary.json').read_text())
            self.assertEqual(summary['max_simultaneous_entries'],2)
            self.assertEqual(summary['business_sends_by_capture'],0)
            (OUT/'native-ttl/checks.json').write_text(json.dumps(dict(command=command,stdout=result.stdout,
                exit_code=result.returncode,record=record),indent=2),encoding='utf-8')
        finally:
            rig.close()

    def test_06_public_serve_process(self):
        command = [sys.executable,'-X','utf8','-m','tools.field_gateway','serve',
                   '--state',str(OUT/'serve-process'),'--pc-id','91','--http-port','0',
                   '--udp-host','127.0.0.1','--udp-port','0','--duration','.2']
        result = subprocess.run(command,capture_output=True,text=True,timeout=5)
        self.assertEqual(result.returncode,0,result.stderr)
        ready = json.loads(result.stdout.splitlines()[0])
        self.assertFalse(ready['pc']['connected'])
        self.assertFalse(ready['serial_access'])
        (OUT/'serve-process/command.json').write_text(json.dumps(dict(argv=command,stdout=result.stdout,
             stderr=result.stderr,exit_code=result.returncode),indent=2),encoding='utf-8')


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    OUT = args.output
    OUT.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[2]
    files = list((root/'tools/field_gateway').glob('*')) + list((root/'deploy/field_gateway').glob('*'))
    files += [root/'tools/mobile_gateway/state.py',root/'tools/mobile_gateway/server.py']
    files += [root/'firmware/mid_baseline/field_agent'/p for p in ['GATEWAY.md','bridge.h','bridge.c',
               'field_ip.h','field_ip.c','idf/main/field_runtime.inc']]
    hashes = {}
    for path in files:
        if path.is_file():
            relative = path.relative_to(root)
            raw = path.read_bytes()
            target = OUT/'source'/relative
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            hashes[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    manifest = dict(task_id='E2-029',run_id=OUT.name,started_at=datetime.now(timezone.utc).isoformat(),
        timezone='Asia/Shanghai',worktree=str(root),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty_files_sha256=hashes,command=getattr(sys,'orig_argv',sys.argv),python_executable=sys.executable,
        dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=[],
        budget=dict(finite=True),output_directory=str(OUT.resolve()),process_id=__import__('os').getpid(),
        finished_at=None,exit_code=None,status='running',review_reference=None,
        limitations=['Actual localhost UDP/HTTP with synthetic board endpoints; not real Wi-Fi/ESP-NOW or zeroUSB field evidence.',
                     'Fixed fixture paths do not validate firmware route/service discovery.'])
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with (OUT/'unittest.txt').open('x',encoding='utf-8') as log:
        class Tee:
            def write(self,value):sys.stderr.write(value);log.write(value)
            def flush(self):sys.stderr.flush();log.flush()
        result = unittest.TextTestRunner(stream=Tee(),verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),exit_code=0 if result.wasSuccessful() else 1,
                    status='passed' if result.wasSuccessful() else 'failed')
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'summary.json').write_text(json.dumps(dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),success=result.wasSuccessful()),indent=2),encoding='utf-8')
    raise SystemExit(manifest['exit_code'])


if __name__ == '__main__':main()
