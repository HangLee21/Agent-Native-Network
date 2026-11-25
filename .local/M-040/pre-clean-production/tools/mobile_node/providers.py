"""Replaceable position providers. Coordinates are WGS84 decimal degrees."""
import importlib
import json
import math
import random
import socket
import time


def position(value, now=None):
    """Validate a provider fix; a missing/invalid fix stays unknown."""
    if value is None or value.get('valid', True) is False:
        return None
    now = time.time() if now is None else now
    lat, lon = float(value['lat']), float(value['lon'])
    sampled_at = float(value['sampled_at'])
    accuracy = value.get('accuracy_m')
    source = value['source']
    if not all(math.isfinite(v) for v in (lat, lon, sampled_at)):
        raise ValueError('finite coordinates and sample time required')
    if not -90 <= lat <= 90 or not -180 <= lon <= 180 or sampled_at > now + 2:
        raise ValueError('invalid WGS84 coordinate or future sample')
    if source not in ('simulated', 'gpsd', 'external'):
        raise ValueError('position source must be simulated/gpsd/external')
    if accuracy is not None and (not math.isfinite(float(accuracy)) or float(accuracy) < 0):
        raise ValueError('nonnegative accuracy required')
    return dict(lat=lat, lon=lon, source=source, sampled_at=sampled_at,
                accuracy_m=accuracy, valid=True)


def aged_position(fix, max_age_s=15, now=None):
    if fix is None:
        return None
    now = time.time() if now is None else now
    age = max(0, int((now - fix['sampled_at']) * 1000))
    stale = age > max_age_s * 1000
    return dict(fix, age_ms=age, stale=stale, valid=fix.get('valid', True) and not stale)


def _reflect(distance, size):
    offset = distance % (2 * size)
    return offset if offset <= size else 2 * size - offset


class FakeGPS:
    """Seeded constant-speed path reflected at rectangular campus boundaries."""
    def __init__(self, seed=1, center_lat=30.0, center_lon=120.0,
                 width_m=600, height_m=400, speed_mps=1.4, clock=time.monotonic,
                 wall=time.time):
        if not all(math.isfinite(v) for v in (center_lat, center_lon, width_m, height_m, speed_mps)):
            raise ValueError('finite campus parameters required')
        if not -80 <= center_lat <= 80 or not -179 <= center_lon <= 179:
            raise ValueError('campus center outside supported WGS84 region')
        if not 1 <= width_m <= 100000 or not 1 <= height_m <= 100000 or not 0 <= speed_mps <= 100:
            raise ValueError('invalid campus size or speed')
        self.clock, self.wall = clock, wall
        self.start = clock()
        self.lat, self.lon = center_lat, center_lon
        self.width, self.height = width_m, height_m
        rng = random.Random(seed)
        self.x, self.y = rng.uniform(0, width_m), rng.uniform(0, height_m)
        angle = rng.uniform(0, 2 * math.pi)
        self.vx, self.vy = speed_mps * math.cos(angle), speed_mps * math.sin(angle)

    def __call__(self):
        elapsed = max(0, self.clock() - self.start)
        x = _reflect(self.x + self.vx * elapsed, self.width) - self.width / 2
        y = _reflect(self.y + self.vy * elapsed, self.height) - self.height / 2
        return position(dict(lat=self.lat + y / 111320,
                             lon=self.lon + x / (111320 * math.cos(math.radians(self.lat))),
                             sampled_at=self.wall(), source='simulated', accuracy_m=None))


def fake_GPS_function(**kwargs):
    """Return a stateful, callable fake GPS provider; call it once per sample."""
    return FakeGPS(**kwargs)


class ExternalGPS:
    def __init__(self, spec):
        module, name = spec.split(':', 1)
        self.function = getattr(importlib.import_module(module), name)

    def __call__(self):
        value = self.function()
        if value is None:
            return None
        return position(dict(value, source='external'))


class GPSD:
    """gpsd JSON WATCH reader. Call on the position worker, never the radio loop."""
    def __init__(self, host='127.0.0.1', port=2947, timeout=.5):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None
        self.buffer = bytearray()
        self.fix = None

    def close(self):
        if self.sock:
            self.sock.close()
        self.sock = None
        self.buffer.clear()

    def __call__(self):
        try:
            if self.sock is None:
                self.sock = socket.create_connection((self.host, self.port), self.timeout)
                self.sock.settimeout(self.timeout)
                self.sock.sendall(b'?WATCH={"enable":true,"json":true};\n')
            deadline = time.monotonic() + self.timeout
            while time.monotonic() < deadline:
                try:
                    chunk = self.sock.recv(8192)
                except socket.timeout:
                    break
                if not chunk:
                    self.close()
                    break
                self.buffer.extend(chunk)
                if len(self.buffer) > 65536:
                    raise ValueError('gpsd line buffer exceeded')
                while b'\n' in self.buffer:
                    line, _, tail = self.buffer.partition(b'\n')
                    self.buffer[:] = tail
                    data = json.loads(line)
                    if data.get('class') != 'TPV':
                        continue
                    if data.get('mode', 0) < 2 or 'lat' not in data or 'lon' not in data or 'time' not in data:
                        self.fix = None
                    else:
                        from datetime import datetime
                        stamp = datetime.fromisoformat(data['time'].replace('Z', '+00:00')).timestamp()
                        self.fix = position(dict(lat=data['lat'], lon=data['lon'], source='gpsd',
                                                 sampled_at=stamp, accuracy_m=data.get('eph')))
            return self.fix
        except Exception:
            self.close()
            raise
