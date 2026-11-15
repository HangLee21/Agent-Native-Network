"""Reproducible random business traffic, independent of the observation gateway."""
import json
import random
import re
import threading
import time
import uuid
from pathlib import Path


def mac(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', value):
        raise ValueError('canonical MAC address required')
    return value.lower()


class Journal:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.file = open(path, 'x', encoding='utf-8')
        self.lock = threading.Lock()

    def write(self, kind, **fields):
        with self.lock:
            self.file.write(json.dumps(dict(kind=kind, recorded_at=time.time(), **fields)) + '\n')
            self.file.flush()

    def close(self):
        self.file.close()


def generate_payload(rng, min_bytes=32, max_bytes=120):
    """ASCII English, exact random byte length in the inclusive range 0..160."""
    if not 0 <= min_bytes <= max_bytes <= 160:
        raise ValueError('payload range must be within 0..160 bytes')
    size = rng.randint(min_bytes, max_bytes)
    # Even very short payloads stay printable; larger messages contain full words.
    text = rng.choice(['Hello friend. ', 'The rover is moving. ', 'A quiet day on campus. '])
    words = ['hello', 'road', 'tree', 'map', 'green', 'car', 'walk', 'home', 'clear', 'sky']
    while len(text) < size:
        text += rng.choice(words) + ' '
    return text[:size].encode('ascii')


def destinations(edge, own_id, configured=()):
    candidates = set(mac(v) for v in configured)
    if not configured:
        # Observed IDs may be unreachable. The local board alone decides routes.
        for peer in edge.neighbors().get('neighbors', []):
            value = peer.get('peer_id', peer.get('node_id'))
            if value:
                candidates.add(mac(value))
    candidates.discard(mac(own_id))
    return sorted(candidates)


class Agent:
    def __init__(self, edge, journal, seed=1, interval_min=2, interval_max=5,
                 min_bytes=32, max_bytes=120, dest=()):
        if not 0.05 <= interval_min <= interval_max <= 86400:
            raise ValueError('traffic interval must be 0.05..86400 seconds')
        if not 0 <= min_bytes <= max_bytes <= 160:
            raise ValueError('payload range must be 0..160 bytes')
        self.edge, self.journal = edge, journal
        self.rng = random.Random(seed)
        self.seed = seed
        self.minimum, self.maximum = interval_min, interval_max
        self.low, self.high = min_bytes, max_bytes
        self.dest = tuple(mac(v) for v in dest)
        self.session = uuid.uuid4().hex
        self.count = 0

    def run(self, stop):
        seeded = False
        while not stop.is_set():
            try:
                own = mac(self.edge.status()['node_id'])
                if not seeded:
                    # Distinct node IDs have independent, repeatable traffic streams.
                    self.rng.seed(str(self.seed) + ':' + own)
                    seeded = True
                interval = self.rng.uniform(self.minimum, self.maximum)
                self.journal.write('agent_wait', interval_s=interval)
                if stop.wait(interval):
                    break
                own = mac(self.edge.status()['node_id'])
                candidates = destinations(self.edge, own, self.dest)
                if not candidates:
                    self.journal.write('agent_idle', reason='no_other_destination')
                    continue
                dst = self.rng.choice(candidates)
                payload = generate_payload(self.rng, self.low, self.high)
                self.count += 1
                request_id = self.session + '-' + str(self.count)
                # The request is journalled before HTTP. Unknown outcome is never retried.
                self.journal.write('send_attempt', request_id=request_id, dst=dst,
                                   payload_hex=payload.hex(), bytes=len(payload))
                try:
                    receipt = self.edge.send(dst, payload, request_id=request_id)
                except Exception as exc:
                    self.journal.write('send_outcome_unknown', request_id=request_id, error=str(exc))
                    continue
                self.journal.write('send_receipt', request_id=request_id, receipt=receipt,
                                   delivery_status='destination_unconfirmed')
            except Exception as exc:
                self.journal.write('agent_error', error=str(exc))
                stop.wait(self.minimum)


def receive_business(edge, journal, stop):
    """An independent event cursor; reading never consumes another app's inbox."""
    cursor, instance = 0, None
    while not stop.is_set():
        try:
            response = edge.events(cursor, wait=.3)
            current = response.get('instance_id')
            if instance is not None and current != instance:
                journal.write('edge_restarted', instance_id=current)
                cursor, instance = 0, current
                continue
            instance = current
            for event in response.get('events', []):
                if event.get('event') == 'rx_local':
                    journal.write('received', observer_id=event['node_id'],
                                   packet=dict(origin=event['origin'], boot=event['origin_boot'],
                                               seq=event['seq'], dst=event['dst']),
                                   payload_hex=event['payload_hex'], raw=event,
                                   delivery_status='destination_received')
            cursor = response.get('cursor', cursor)
        except Exception as exc:
            import urllib.error
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 503:
                journal.write('receive_gap', cursor=cursor, error=str(exc))
                cursor = 0
            else:
                journal.write('receive_error', error=str(exc))
            stop.wait(.5)


def fake_agent_function(edge, journal, *, stop=None, seed=1, interval_min=2,
                        interval_max=5, min_bytes=32, max_bytes=120, dest=(),
                        receive=True):
    """Run random business traffic until stop is set or Ctrl+C, with parallel receive.

    Each round draws a new interval, other-node destination, ASCII content and byte
    length. No candidate, no route and an unknown send outcome do not end the loop.
    An unknown business packet is never resubmitted. Returns the stopped Agent.
    """
    stop = threading.Event() if stop is None else stop
    agent = Agent(edge, journal, seed, interval_min, interval_max, min_bytes, max_bytes, dest)
    receiver = None
    if receive:
        receiver = threading.Thread(target=receive_business, args=(edge, journal, stop),
                                    name='business-receiver')
        receiver.start()
    try:
        agent.run(stop)
    except KeyboardInterrupt:
        stop.set()
    finally:
        stop.set()
        if receiver:
            receiver.join()
    return agent
