"""Standard-library HTTP observation service. Run with python -m tools.mobile_gateway."""
import argparse
import json
import mimetypes
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .state import State

ROOT = Path(__file__).resolve().parents[2]


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, address, state, static_dir):
        self.state, self.static_dir = state, Path(static_dir).resolve()
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(8)

    def reply(self, code, value, mime='application/json; charset=utf-8'):
        data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/health':
            return self.reply(200, dict(status='ok', role='observation_only', gateway_instance=self.server.state.instance))
        if url.path == '/api/v1/state':
            return self.reply(200, self.server.state.snapshot())
        if url.path == '/api/v1/timeline':
            try:
                after = int(parse_qs(url.query).get('after', ['0'])[0])
                if after < 0:
                    raise ValueError()
            except ValueError:
                return self.reply(400, {'error': 'invalid after cursor'})
            return self.reply(200, self.server.state.history(after))
        path = unquote(url.path)
        pieces = path.lstrip('/').split('/')
        if '\\' in path or any(x.startswith('.') for x in pieces if x) or ':' in path:
            return self.reply(404, {'error': 'not found'})
        if path == '/':
            pieces = ['index.html']
        target = self.server.static_dir.joinpath(*pieces).resolve()
        if not target.is_relative_to(self.server.static_dir) or not target.is_file():
            if path in ('/', '/index.html'):
                return self.reply(200, b'<!doctype html><meta charset="utf-8"><title>Mobile gateway</title><h1>Observation gateway</h1><p>Map assets are not installed yet.</p><p><a href="/api/v1/state">Current state</a> | <a href="/api/v1/timeline">Timeline</a></p>', 'text/html; charset=utf-8')
            return self.reply(404, {'error': 'not found'})
        mime = mimetypes.guess_type(target.name)[0] or 'application/octet-stream'
        if target.suffix in ('.html', '.js', '.css', '.svg'):
            mime += '; charset=utf-8'
        return self.reply(200, target.read_bytes(), mime)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/v1/reports':
            self.close_connection = True
            return self.reply(404, {'error': 'observation gateway has no business/control endpoint'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 262144 or self.headers.get('Transfer-Encoding'):
                self.close_connection = True
                return self.reply(413, {'error': 'report limit is 262144 bytes; Content-Length required'})
            data = self.rfile.read(size)
            if len(data) != size:
                raise ValueError('incomplete report')
            report = json.loads(data, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
            return self.reply(200, self.server.state.accept(report))
        except (ValueError, TypeError, UnicodeError) as exc:
            return self.reply(400, {'error': str(exc)})
        except OSError:
            return self.reply(503, {'error': 'report journal unavailable'})


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8790)
    p.add_argument('--static-dir', type=Path, default=ROOT / 'assets/mobile_gateway')
    p.add_argument('--output', required=True, type=Path, help='new capture directory')
    p.add_argument('--resume', action='store_true', help='resume only this gateway capture; never truncate it')
    p.add_argument('--offline-ms', type=int, default=30000)
    p.add_argument('--stale-ms', type=int, default=30000)
    p.add_argument('--stop-file', type=Path, help='optional local lifecycle file, not an HTTP control endpoint')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.offline_ms < 100 or args.stale_ms < 100:
        raise SystemExit('age thresholds must be at least 100 ms')
    out = args.output.resolve()
    if args.resume:
        if not (out / 'reports.jsonl').is_file() or not (out / 'gateway.json').is_file():
            raise SystemExit('resume requires a gateway capture')
    else:
        out.mkdir(parents=True, exist_ok=False)
    journal_lock = threading.Lock()
    with (out / 'reports.jsonl').open('a' if args.resume else 'x', encoding='utf-8') as log:
        def journal(row):
            with journal_lock:
                log.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
                log.flush()
        state = State(offline_ms=args.offline_ms, stale_ms=args.stale_ms, journal=journal)
        if args.resume:
            with (out / 'reports.jsonl').open(encoding='utf-8') as previous:
                for line in previous:
                    row = json.loads(line)
                    state.accept(row['report'], row['received_ms'], replay=True)
        # Binding failure must never stop or replace an existing service.
        with Gateway((args.host, args.port), state, args.static_dir) as server:
            meta = dict(schema_version=1, gateway_instance=state.instance, host=args.host, port=server.server_port, static_dir=str(args.static_dir.resolve()), output=str(out), serial_access=False, business_forwarding=False)
            (out / ('gateway-' + state.instance + '.json')).write_text(json.dumps(meta, indent=2), encoding='utf-8')
            if not args.resume:
                (out / 'gateway.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
            print(json.dumps(dict(status='ready', **meta)), flush=True)
            watcher_done = threading.Event()
            def watch():
                while not watcher_done.wait(.1):
                    if args.stop_file and args.stop_file.exists():
                        server.shutdown()
                        return
            watcher = threading.Thread(target=watch, daemon=True)
            watcher.start()
            try:
                server.serve_forever(poll_interval=.2)
            except KeyboardInterrupt:
                pass
            finally:
                watcher_done.set()
                watcher.join(2)
                (out / ('final-' + state.instance + '.json')).write_text(json.dumps(state.snapshot(), ensure_ascii=False, indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
