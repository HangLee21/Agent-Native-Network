"""Loopback UI/API for PC sends and destination-only PC receives."""
from http.server import ThreadingHTTPServer
import json
import re
from urllib.parse import parse_qs, urlsplit
from tools.mobile_gateway.server import Handler as MapHandler
from .application import NoWirelessPath


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, port, app, static_dir):
        self.app, self.state, self.static_dir = app, app.map, static_dir.resolve()
        super().__init__(('127.0.0.1', port), Handler)


class Handler(MapHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        path = url.path
        app = self.server.app
        try:
            query = parse_qs(url.query)
            if path == '/api/pc/status':
                return self.reply(200, app.status())
            if path == '/api/pc/inbox':
                return self.reply(200, dict(ok=True, **app.store.inbox(int(query.get('after', ['0'])[0]))))
            if path == '/api/pc/events':
                return self.reply(200, dict(ok=True, **app.history(int(query.get('after', ['0'])[0]))))
            if path.startswith('/api/pc/requests/'):
                key = path[len('/api/pc/requests/'):]
                if not re.fullmatch(r'[a-zA-Z0-9_-]{8,64}', key):
                    raise ValueError('invalid request_id')
                record = app.store.get(key)
                return self.reply(200 if record else 404, dict(ok=bool(record), record=record))
            if path == '/health':
                return self.reply(200, dict(status='ok', role='pc_wireless_endpoint', serial_access=False))
            return super().do_GET()
        except (ValueError, TypeError) as exc:
            return self.reply(400, dict(ok=False, error=str(exc)))

    def do_POST(self):
        if urlsplit(self.path).path != '/api/pc/send':
            self.close_connection = True
            return self.reply(404, dict(error='unsupported local operation'))
        port = self.server.server_port
        host = self.headers.get('Host')
        if self.headers.get_all('Host') != [host] or host not in (f'127.0.0.1:{port}', f'localhost:{port}') or self.headers.get_all('Origin') != ['http://' + host]:
            self.close_connection = True
            return self.reply(403, dict(error='loopback same-origin request required'))
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if not 0 < size <= 2048 or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                self.close_connection = True
                raise ValueError('bounded application/json body required')
            value = json.loads(self.rfile.read(size), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
            return self.reply(200, dict(ok=True, record=self.server.app.send(value)))
        except (ValueError, TypeError, KeyError) as exc:
            return self.reply(400, dict(ok=False, error=str(exc)))
        except NoWirelessPath as exc:
            return self.reply(503, dict(ok=False, error=str(exc), business_submitted=False))
