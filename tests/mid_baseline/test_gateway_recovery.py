"""Loopback-only regression for gateway UDP failure recovery.

Run from any working directory: python -m unittest discover -s tests/mid_baseline
No physical gateway, serial device, or production port is used.
"""
import base64
import json
import socket
import sys
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
from tools.mid_baseline.gateway_probe import topology_server as mod


class InjectedSocket:
    def __init__(self, shared):
        self.raw = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.shared = shared
        self.closed = False
        shared['sockets'].append(self)

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def recvfrom(self, size):
        if self.shared['fail_recv'].is_set():
            self.shared['fail_recv'].clear()
            raise OSError(10051, 'injected receive failure')
        if self.shared['terminate'].is_set():
            self.shared['terminate'].clear()
            raise SystemExit('injected unexpected worker termination')
        return self.raw.recvfrom(size)

    def sendto(self, data, addr):
        if data[3] in self.shared['fail_ack']:
            self.shared['fail_ack'].remove(data[3])
            raise OSError(10051, 'injected ACK failure')
        return self.raw.sendto(data, addr)

    def close(self):
        self.closed = True
        self.raw.close()


def push(seq, token):
    report = dict(observer_id='02:00:00:00:00:02', observer_boot=1,
                  report_seq=seq, snapshot_at_ms=seq * 10, wifi_group=1,
                  report_period_ms=10000, neighbors=[])
    packet = {'data': base64.b64encode(encode_frame(report)).decode('ascii'), 'freq': 470.5}
    return bytes([2]) + token + bytes([0]) + bytes.fromhex('b827ebfffe32e2c1') + json.dumps({'rxpk': [packet]}).encode()


class RecoveryTests(unittest.TestCase):
    def test_ack_failure_receive_rebuild_and_worker_exit(self):
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
        probe.close()
        shared = {'sockets': [], 'fail_ack': {1, 4}, 'fail_recv': threading.Event(),
                  'terminate': threading.Event()}
        topology = mod.Topology()
        stop = threading.Event()

        def worker(top, udp_port, event):
            mod.udp_loop(top, udp_port, event, socket_factory=lambda *_: InjectedSocket(shared))

        supervisor = threading.Thread(target=mod.supervise_udp, args=(topology, port, stop),
                                      kwargs={'worker_fn': worker})
        server = ThreadingHTTPServer(('127.0.0.1', 0), mod.handler_for(topology))
        http = threading.Thread(target=server.serve_forever, daemon=True)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender.settimeout(2)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        url = 'http://127.0.0.1:%d/api/v1/lora/topology' % server.server_port
        supervisor.start()
        http.start()

        def wait_for(predicate):
            deadline = time.monotonic() + 6
            while time.monotonic() < deadline:
                with opener.open(url, timeout=2) as response:
                    value = json.load(response)
                if predicate(value):
                    return value
                time.sleep(.03)
            self.fail('receiver condition not reached: %r' % value['receiver'])

        try:
            wait_for(lambda v: v['receiver']['worker_state'] == 'running')
            sender.sendto(push(1, b'\x12\x34'), ('127.0.0.1', port))
            first = wait_for(lambda v: len(v['reports']) == 1)
            self.assertEqual(first['receiver']['ack_errors'], 1)
            pull = bytes.fromhex('02567802b827ebfffe32e2c1')
            sender.sendto(pull, ('127.0.0.1', port))
            wait_for(lambda v: v['receiver']['ack_errors'] == 2)
            sender.sendto(push(2, b'\x11\x11'), ('127.0.0.1', port))
            self.assertEqual(sender.recv(16).hex(), '02111101')
            wait_for(lambda v: v['reports'][0]['report']['report_seq'] == 2)

            shared['fail_recv'].set()
            recovered = wait_for(lambda v: v['receiver']['worker_restarts'] >= 1 and
                                 v['receiver']['worker_state'] == 'running')
            self.assertFalse(recovered['receiver']['gateway_observed'])
            self.assertIn('10051', recovered['receiver']['last_worker_error'])
            sender.sendto(pull, ('127.0.0.1', port))
            self.assertEqual(sender.recv(16).hex(), '02567804')
            wait_for(lambda v: v['receiver']['gateway_observed'])

            shared['terminate'].set()
            recovered = wait_for(lambda v: v['receiver']['worker_restarts'] >= 2 and
                                 v['receiver']['worker_state'] == 'running')
            self.assertFalse(recovered['receiver']['gateway_observed'])
            self.assertIn('exited unexpectedly', recovered['receiver']['last_worker_error'])
            self.assertTrue(shared['sockets'][-2].closed)
            sender.sendto(pull, ('127.0.0.1', port))
            self.assertEqual(sender.recv(16).hex(), '02567804')
            wait_for(lambda v: v['receiver']['gateway_observed'])
            count = topology.worker_restarts
            time.sleep(.8)
            self.assertEqual(topology.worker_restarts, count)
        finally:
            stop.set()
            supervisor.join(5)
            server.shutdown()
            server.server_close()
            sender.close()
            http.join(2)
        self.assertFalse(supervisor.is_alive())
        self.assertTrue(all(s.closed for s in shared['sockets']))
        self.assertEqual(topology.worker_state, 'stopped')


if __name__ == '__main__':
    unittest.main(verbosity=2)
