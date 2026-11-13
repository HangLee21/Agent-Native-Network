"""PC application client. Local API access never opens a board serial port."""
import json
import urllib.parse
import urllib.request
import uuid


class Client:
    def __init__(self, port=8791):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ValueError('local unprivileged API port required')
        self.base = 'http://127.0.0.1:' + str(port)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, None if body is None else json.dumps(body).encode(),
                                     headers={'Content-Type': 'application/json', 'Origin': self.base})
        with self.opener.open(req, timeout=8) as response:
            return json.load(response)

    def status(self):
        return self.call('/api/pc/status')

    def send(self, dst, payload, request_id=None):
        if not isinstance(payload, bytes):
            raise ValueError('payload must be bytes')
        return self.call('/api/pc/send', dict(request_id=request_id or uuid.uuid4().hex,
                                            dst=dst, payload_hex=payload.hex()))

    def request(self, request_id):
        return self.call('/api/pc/requests/' + urllib.parse.quote(request_id, safe=''))

    def inbox(self, after=0):
        return self.call('/api/pc/inbox?after=' + str(after))

    def events(self, after=0):
        return self.call('/api/pc/events?after=' + str(after))
