"""Wireless PC terminal: serve, status, send, request, recv and finite watch."""
import argparse
import json
from pathlib import Path
import signal
import threading
import time
import sys
import urllib.error
from .application import Application
from .client import Client
from .offline import OfflineLink
from .server import Server

ROOT = Path(__file__).resolve().parents[2]


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    serve = sub.add_parser('serve')
    serve.add_argument('--state', type=Path, required=True)
    serve.add_argument('--http-port', type=int, default=8791)
    serve.add_argument('--udp-host', default='0.0.0.0')
    serve.add_argument('--udp-port', type=int, default=8793)
    serve.add_argument('--entry', action='append', default=[], help='Optional debug seed IPv4:8792; normal operation discovers entries')
    serve.add_argument('--broadcast', help='Optional hotspot subnet broadcast address for discovery')
    serve.add_argument('--pc-id', type=int, help='Stable nonzero uint32; must match an existing state directory')
    serve.add_argument('--lease-s', type=float, default=10)
    serve.add_argument('--query-timeout', type=float, default=2)
    serve.add_argument('--neighbor-snapshots', action='store_true', help='Enable nonce-bound live neighbor queries; requires matching firmware')
    serve.add_argument('--offline', action='store_true', help='Empty map and PC status without opening a UDP socket')
    serve.add_argument('--static-dir', type=Path, default=ROOT/'research/agent_native_network/mobile_gateway')
    serve.add_argument('--duration', type=float, default=0)
    serve.add_argument('--stop-file', type=Path)
    for name in ('status', 'send', 'request', 'recv', 'watch', 'await-entries'):
        q = sub.add_parser(name)
        q.add_argument('--port', type=int, default=8791)
    sub.choices['send'].add_argument('--dst', required=True)
    payload = sub.choices['send'].add_mutually_exclusive_group(required=True)
    payload.add_argument('--text')
    payload.add_argument('--payload-hex')
    sub.choices['send'].add_argument('--request-id')
    sub.choices['send'].add_argument('--wait', type=float, default=0, help='Finite seconds waiting for destination receipt; never resends')
    sub.choices['request'].add_argument('request_id')
    sub.choices['request'].add_argument('--wait', type=float, default=0)
    sub.choices['recv'].add_argument('--after', type=int, default=0)
    sub.choices['recv'].add_argument('--wait', type=float, default=0)
    sub.choices['watch'].add_argument('--duration', type=float, default=30)
    sub.choices['watch'].add_argument('--interval', type=float, default=.5)
    sub.choices['await-entries'].add_argument('--count', type=int, default=2)
    sub.choices['await-entries'].add_argument('--timeout', type=float, default=30)
    return p


def emit(value):
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)


def wait_request(client, request_id, seconds):
    end = time.monotonic() + seconds
    while True:
        value = client.request(request_id)
        if value['record']['destination_received'] or time.monotonic() >= end:
            return dict(value, observation_timeout=not value['record']['destination_received'])
        time.sleep(min(.1, max(0, end-time.monotonic())))


def run(argv=None):
    p = parser()
    a = p.parse_args(argv)
    if a.command == 'serve':
        if a.duration < 0 or not 1 <= a.lease_s <= 10 or not .05 <= a.query_timeout <= 5:
            p.error('invalid duration/lease/query bound')
        stop = threading.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, lambda *_: stop.set())
        if a.offline:
            link = OfflineLink()
        else:
            from .wireless import WirelessLink
            link = WirelessLink(a.udp_host, a.udp_port, debug_entries=a.entry, broadcast=a.broadcast,
                                lease_s=a.lease_s, query_timeout=a.query_timeout,
                                neighbor_snapshots=a.neighbor_snapshots)
        app = Application(a.state, link, pc_id=a.pc_id)
        try:
            with Server(a.http_port, app, a.static_dir) as server:
                server.timeout = .2
                emit(dict(status='ready', http_port=server.server_port, pc=app.status(),
                          serial_access=False, stop='Ctrl+C/SIGTERM/--duration/--stop-file'))
                until = time.monotonic() + a.duration if a.duration else None
                while not stop.is_set() and (until is None or time.monotonic() < until) and not (a.stop_file and a.stop_file.exists()):
                    server.handle_request()
        finally:
            app.close()
        return
    client = Client(a.port)
    if a.command == 'status':
        return emit(client.status())
    if a.command == 'send':
        raw = a.text.encode('utf-8') if a.text is not None else bytes.fromhex(a.payload_hex)
        result = client.send(a.dst, raw, a.request_id)
        emit(result)
        if a.wait:
            result = wait_request(client, result['record']['request_id'], a.wait)
            emit(result)
            if result['observation_timeout']:
                raise SystemExit(2)
    elif a.command == 'request':
        result = wait_request(client, a.request_id, a.wait)
        emit(result)
        if a.wait and result['observation_timeout']:
            raise SystemExit(2)
    elif a.command == 'recv':
        until = time.monotonic() + a.wait
        while True:
            result = client.inbox(a.after)
            if result['records'] or time.monotonic() >= until:
                emit(dict(result, observation_timeout=not bool(result['records'])))
                if a.wait and not result['records']:
                    raise SystemExit(2)
                return
            time.sleep(.1)
    elif a.command == 'await-entries':
        if not 1 <= a.count <= 5 or not 0 <= a.timeout <= 300:
            p.error('entry count 1..5, timeout 0..300 required')
        until = time.monotonic() + a.timeout
        while True:
            status = client.status()
            count = sum(bool(e['connected']) for e in status['entries'])
            if count >= a.count:
                return emit(dict(status, observation_timeout=False))
            if time.monotonic() >= until:
                emit(dict(status, observation_timeout=True))
                raise SystemExit(2)
            time.sleep(.2)
    else:
        if not 0 < a.duration <= 3600 or not .1 <= a.interval <= 10:
            p.error('finite watch duration 0..3600, interval .1..10 required')
        until, cursor, inbox = time.monotonic() + a.duration, 0, 0
        while time.monotonic() < until:
            status, events, received = client.status(), client.events(cursor), client.inbox(inbox)
            emit(dict(status=status, events=events, inbox=received))
            cursor, inbox = events['cursor'], received['cursor']
            time.sleep(min(a.interval, max(0, until-time.monotonic())))


def main(argv=None):
    try:
        return run(argv)
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read(4096))
        except Exception:
            value = dict(error=str(exc))
        print(json.dumps(dict(http_status=exc.code, **value)), file=sys.stderr)
        raise SystemExit(2)
    except (ValueError, OSError, TimeoutError) as exc:
        print(json.dumps(dict(error=str(exc))), file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()
