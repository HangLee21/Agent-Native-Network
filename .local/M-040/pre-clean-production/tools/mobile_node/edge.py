"""Loopback access only. This process never opens the serial device."""
import json
import urllib.request
from tools.mid_edge.local_api import LocalClient


class MobileEdge(LocalClient):
    def __init__(self, port=8780, timeout=2):
        super().__init__(port)
        from tools.mid_edge.mobile_position import PositionStream
        self.positions = PositionStream()
        self.timeout = timeout
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _call(self, path, body=None):
        request = urllib.request.Request(
            self.base + path, None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Origin': self.base})
        with self.opener.open(request, timeout=self.timeout) as response:
            return json.load(response)

    def status(self):
        return self._call('/api/edge/status')

    def set_position(self, fix):
        return self._call('/api/edge/position', self.positions.encode(fix))

    def telemetry(self):
        return self._call('/api/edge/telemetry')
