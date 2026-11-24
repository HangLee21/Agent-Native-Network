"""Causal, direct-neighbour packet transport for field-sampling experiments.

This is an abstract shared-medium model, not a radio, MAC or routing emulator.
"""
from __future__ import annotations

import copy
import heapq
import json
import math
import random
from dataclasses import dataclass, asdict
from typing import Mapping


_REQUIRED = {
    'NODE_STATE': ('node_id', 'position', 'velocity', 'timestamp'),
    'MAP_SUMMARY': ('region_id', 'mean', 'variance', 'sample_count'),
    'TASK_INTENT': ('region_id', 'utility', 'eta'),
    'TASK_UPDATE': ('region_id', 'owner', 'status', 'expires_at'),
    'SAMPLE': ('sample_id', 'node_id', 'step', 'x_m', 'y_m', 'h_m', 't_s', 'value_dbm'),
}


@dataclass(frozen=True)
class NetworkConfig:
    range_m: float = 100.0
    bandwidth_bps: float = 1_000_000.0
    propagation_delay_s: float = 0.0
    loss_probability: float = 0.0
    distance_loss_probability: float = 0.0
    max_queue_delay_s: float | None = None

    def __post_init__(self):
        for key in ('range_m', 'bandwidth_bps'):
            value = getattr(self, key)
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f'{key} must be finite and positive')
        if not math.isfinite(self.propagation_delay_s) or self.propagation_delay_s < 0:
            raise ValueError('propagation_delay_s must be finite and nonnegative')
        for key in ('loss_probability', 'distance_loss_probability'):
            value = getattr(self, key)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'{key} must be in [0,1]')
        if self.max_queue_delay_s is not None and (not math.isfinite(self.max_queue_delay_s) or self.max_queue_delay_s < 0):
            raise ValueError('max_queue_delay_s must be nonnegative or None')


def serialize_message(source, destination, kind, payload, created_at, message_id):
    """Encode one immutable UTF-8 JSON envelope; bytes are exactly len(return)."""
    if kind not in _REQUIRED:
        raise ValueError('unknown message kind')
    if not isinstance(payload, dict) or any(k not in payload for k in _REQUIRED[kind]):
        raise ValueError(f'{kind} payload requires {_REQUIRED[kind]}')
    envelope = {'id': message_id, 'source': source, 'destination': destination,
                'kind': kind, 'created_at': created_at, 'payload': payload}
    try:
        return json.dumps(envelope, sort_keys=True, separators=(',', ':'),
                          ensure_ascii=False, allow_nan=False).encode('utf-8')
    except (TypeError, ValueError) as exc:
        raise ValueError('message must be finite JSON data') from exc


class Network:
    """Discrete event transport. All methods use monotone simulated seconds.

    `update` is a zero-order hold: positions and node online state apply until
    the next update. Events strictly before an update use the old topology;
    events exactly at the update use the new topology.
    """
    def __init__(self, config=None, seed=0):
        self.config = config if isinstance(config, NetworkConfig) else NetworkConfig(**(config or {}))
        self._rng = random.Random(seed)
        self._time = 0.0
        self._initialised = False
        self._start = None
        self._positions = {}
        self._online = {}
        self._nodes = ()
        self._events = []
        self._event_counter = 0
        self._next_free = 0.0
        self._next_id = 0
        self._mail = {}
        self._frames = []
        self._inflight = {}
        self._rejected = []
        self._outcomes = []
        self._drain_cursor = 0
        self._connected_time = 0.0
        self._partition_time = 0.0
        self._degree_integral = 0.0
        self._node_degree_integral = {}
        self._node_offline_time = {}

    def _schedule(self, when, kind, data):
        self._event_counter += 1
        heapq.heappush(self._events, (when, self._event_counter, kind, data))

    def _edges(self):
        nodes = self._nodes
        return {(a, b) for i, a in enumerate(nodes) for b in nodes[i+1:]
                if self._linked(a, b)}

    def _linked(self, a, b):
        return (a != b and self._online.get(a, False) and self._online.get(b, False)
                and math.dist(self._positions[a], self._positions[b]) <= self.config.range_m)

    def _graph_values(self):
        edges = self._edges()
        degree = {n: 0 for n in self._nodes}
        adj = {n: set() for n in self._nodes}
        for a, b in edges:
            degree[a] += 1; degree[b] += 1
            adj[a].add(b); adj[b].add(a)
        seen = set()
        if self._nodes:
            todo = [self._nodes[0]]
            while todo:
                n = todo.pop()
                if n in seen:
                    continue
                seen.add(n); todo.extend(adj[n] - seen)
        connected = bool(self._nodes) and len(seen) == len(self._nodes) and all(self._online.values())
        return edges, degree, connected

    def _integrate(self, until):
        delta = until - self._time
        if delta > 0 and self._initialised:
            _, degree, connected = self._graph_values()
            self._connected_time += delta if connected else 0.0
            self._partition_time += 0.0 if connected else delta
            self._degree_integral += delta * sum(degree.values()) / len(self._nodes)
            for node in self._nodes:
                self._node_degree_integral[node] += delta * degree[node]
                if not self._online[node]:
                    self._node_offline_time[node] += delta
        self._time = until

    def _advance(self, t, include_equal=True):
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < self._time:
            raise ValueError('time must be finite, monotone simulated seconds')
        while self._events and (self._events[0][0] < t or include_equal and self._events[0][0] <= t):
            when, _, kind, data = heapq.heappop(self._events)
            self._integrate(when)
            if kind == 'start':
                frame = data
                if not self._online[frame['source']]:
                    frame['state'] = 'source_offline'
                    for recipient in frame['recipients']:
                        self._finish(frame, recipient, when, 'source_offline')
                    continue
                frame['state'] = 'transmitted'
                for recipient in frame['recipients']:
                    if not self._linked(frame['source'], recipient):
                        self._finish(frame, recipient, when, 'link_unavailable_at_start')
                        continue
                    distance = math.dist(self._positions[frame['source']], self._positions[recipient])
                    p = min(1.0, self.config.loss_probability +
                            self.config.distance_loss_probability * distance / self.config.range_m)
                    if self._rng.random() < p:
                        self._finish(frame, recipient, when, 'random_loss')
                    else:
                        frame['inflight'].add(recipient)
                        self._inflight[frame['id']] = frame
                        self._schedule(frame['finish'] + self.config.propagation_delay_s,
                                       'arrival', (frame, recipient))
            else:
                frame, recipient = data
                frame['inflight'].discard(recipient)
                if not frame['inflight']:
                    self._inflight.pop(frame['id'], None)
                self._finish(frame, recipient, when, None if recipient not in frame['disrupted'] and self._linked(frame['source'], recipient)
                             else 'link_unavailable_at_arrival')
        self._integrate(t)

    def _finish(self, frame, recipient, when, reason):
        result = {'message_id': frame['id'], 'source': frame['source'], 'destination': recipient,
                  'kind': frame['kind'], 'broadcast': frame['broadcast'],
                  'created_at': frame['created_at'], 'completed_at': when,
                  'latency_s': when - frame['created_at'] if reason is None else None,
                  'bytes': frame['bytes'], 'status': 'delivered' if reason is None else 'dropped',
                  'reason': reason}
        self._outcomes.append(result)
        if reason is None:
            msg = copy.deepcopy(result)
            msg['payload'] = copy.deepcopy(frame['payload'])
            self._mail[recipient].append(msg)

    def update(self, t, positions: Mapping, online=None):
        """Replace complete {node_id: (x,y,z)} and optional online states."""
        if not isinstance(positions, Mapping) or not positions:
            raise ValueError('positions must be a non-empty mapping')
        clean = {}
        for node, pos in positions.items():
            if isinstance(node, bool) or not isinstance(node, (int, str)) or isinstance(node, str) and not node:
                raise ValueError('node ids must be non-empty strings or integers')
            if not isinstance(pos, (tuple, list)) or len(pos) != 3 or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in pos):
                raise ValueError('each position must contain three finite numbers')
            clean[node] = tuple(pos)
        nodes = tuple(sorted(clean, key=lambda n: (type(n).__name__, str(n))))
        if self._initialised and set(nodes) != set(self._nodes):
            raise ValueError('node set is fixed; mark missing nodes offline')
        if online is None:
            enabled = {n: True for n in nodes}
        elif not isinstance(online, Mapping) or set(online) != set(nodes) or any(type(v) is not bool for v in online.values()):
            raise ValueError('online must map every node to a bool')
        else:
            enabled = dict(online)
        self._advance(t, include_equal=False)
        if not self._initialised:
            self._initialised = True; self._start = t; self._nodes = nodes
            self._mail = {n: [] for n in nodes}
            self._node_degree_integral = {n: 0.0 for n in nodes}
            self._node_offline_time = {n: 0.0 for n in nodes}
        self._positions = clean; self._online = enabled
        for frame in self._inflight.values():
            for recipient in frame['inflight']:
                if not self._linked(frame['source'], recipient):
                    frame['disrupted'].add(recipient)
        self._advance(t)
        return self.topology()

    def send(self, t, source, kind, payload, destination=None):
        """Enqueue one frame. None destination = snapshot of direct neighbours.

        Returns frame id or None if explicitly rejected by max_queue_delay_s.
        Counts broadcast as one TX frame but one receive opportunity per intended
        neighbour captured at enqueue time. No automatic forwarding or retries.
        """
        self._advance(t)
        if not self._initialised or source not in self._positions:
            raise ValueError('initialise network and use a registered source')
        if destination is not None and (destination not in self._positions or destination == source):
            raise ValueError('destination must be another registered node')
        recipients = ([destination] if destination is not None else
                      [n for n in self._nodes if self._linked(source, n)])
        message_id = self._next_id
        wire = serialize_message(source, destination, kind, payload, t, message_id)
        start = max(float(t), self._next_free)
        if self.config.max_queue_delay_s is not None and start - t > self.config.max_queue_delay_s:
            self._rejected.append({'source': source, 'broadcast': destination is None,
                                   'recipients': tuple(recipients), 'bytes': len(wire)})
            return None
        self._next_id += 1
        finish = start + len(wire) * 8 / self.config.bandwidth_bps
        self._next_free = finish
        frame = {'id': message_id, 'source': source, 'kind': kind, 'payload': copy.deepcopy(payload),
                 'created_at': float(t), 'start': start, 'finish': finish, 'bytes': len(wire),
                 'broadcast': destination is None, 'recipients': tuple(recipients), 'state': 'queued',
                 'inflight': set(), 'disrupted': set()}
        self._frames.append(frame)
        self._schedule(start, 'start', frame)
        return message_id

    def drain(self, t):
        """Advance and return newly completed per-recipient outcomes, not inboxes."""
        self._advance(t)
        result = copy.deepcopy(self._outcomes[self._drain_cursor:])
        self._drain_cursor = len(self._outcomes)
        return result

    def poll(self, node, t):
        """Return and consume only messages actually delivered to this node."""
        self._advance(t)
        if node not in self._mail:
            raise ValueError('unknown node')
        result = self._mail[node]
        self._mail[node] = []
        return copy.deepcopy(result)

    def topology(self):
        """Snapshot to draw a graph, without modifying time or exposing messages."""
        edges, degree, connected = self._graph_values() if self._initialised else (set(), {}, False)
        return {'time': self._time, 'positions': copy.deepcopy(self._positions),
                'online': dict(self._online), 'edges': sorted(edges, key=repr),
                'degree': degree, 'connected': connected}

    def metrics(self, t):
        """Advance and return structural time averages and recipient-based metrics."""
        self._advance(t)
        duration = self._time - self._start if self._initialised else 0.0
        rows = self._outcomes
        def summarize(frames, outcomes, rejected):
            sent = sum(len(x['recipients']) for x in frames)
            delivered = sum(r['status'] == 'delivered' for r in outcomes)
            dropped = sum(r['status'] == 'dropped' for r in outcomes)
            delays = [r['latency_s'] for r in outcomes if r['status'] == 'delivered']
            transmitted = [f for f in frames if f['state'] == 'transmitted']
            return {'enqueued_frames': len(frames), 'enqueued_bytes': sum(f['bytes'] for f in frames),
                    'tx_frames': len(transmitted), 'tx_bytes': sum(f['bytes'] for f in transmitted),
                    'rejected_frames': len(rejected),
                    'rejected_receive_opportunities': sum(len(x['recipients']) for x in rejected),
                    'receive_opportunities': sent, 'delivered': delivered, 'dropped': dropped,
                    'pending': sent - delivered - dropped,
                    'pdr': delivered / (delivered + dropped) if delivered + dropped else None,
                    'mean_latency_s': sum(delays) / len(delays) if delays else None,
                    'rx_bytes': sum(r['bytes'] for r in outcomes if r['status'] == 'delivered')}
        by_node = {}
        for node in self._nodes:
            src = [f for f in self._frames if f['source'] == node]
            src_rows = [r for r in rows if r['source'] == node]
            rec_rows = [r for r in rows if r['destination'] == node and r['status'] == 'delivered']
            by_node[node] = {**summarize(src, src_rows, [f for f in self._rejected if f['source'] == node]), 'received_messages': len(rec_rows),
                             'received_bytes': sum(r['bytes'] for r in rec_rows),
                             'average_degree': self._node_degree_integral[node] / duration if duration else None,
                             'offline_time_s': self._node_offline_time[node]}
        classes = {}
        for name, broadcast in (('unicast', False), ('broadcast', True)):
            classes[name] = summarize([f for f in self._frames if f['broadcast'] == broadcast],
                                      [r for r in rows if r['broadcast'] == broadcast],
                                      [f for f in self._rejected if f['broadcast'] == broadcast])
        return {'time': self._time, 'observation_duration_s': duration,
                'config': asdict(self.config), 'total': summarize(self._frames, rows, self._rejected),
                'by_class': classes, 'by_node': by_node,
                'connectivity_ratio': self._connected_time / duration if duration else None,
                'partition_duration_s': self._partition_time,
                'average_node_degree': self._degree_integral / duration if duration else None}
