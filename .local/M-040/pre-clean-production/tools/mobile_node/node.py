"""One mobile node. Every network and position worker has an independent loop."""
import collections
import threading
import time
import uuid
from .providers import aged_position
from .reporting import event_report, neighbor_report


class Node:
    def __init__(self, edge, provider, queue, journal, label='', sample_s=1,
                 report_s=10, max_age_s=15, inject_position=True):
        if not .05 <= sample_s <= 3600 or not .1 <= report_s <= 3600 or not .1 <= max_age_s <= 86400:
            raise ValueError('invalid position/report/expiry interval')
        self.edge, self.provider, self.queue, self.journal = edge, provider, queue, journal
        self.label, self.sample_s, self.report_s = label, sample_s, report_s
        self.max_age_s, self.inject = max_age_s, inject_position
        self.lock = threading.Lock()
        self.fix = None
        self.position_error = None
        self.events = collections.deque(maxlen=512)
        self.events_dropped = 0
        self.cursor = 0
        self.edge_instance = None
        self.session = uuid.uuid4().hex
        self.seq = 0
        self.threads = []
        self.last_status = None
        self.urgent = threading.Event()
        self._last_report = 0

    def positions(self, stop):
        unsupported = False
        while not stop.is_set():
            try:
                fix = self.provider()
                with self.lock:
                    self.fix = fix
                    self.position_error = None
                if self.inject and not unsupported:
                    view = aged_position(fix, self.max_age_s)
                    try:
                        # Unknown/stale fixes clear validity on the board, never invent a fresh fix.
                        self.edge.set_position(view if view and not view['stale'] else None)
                    except Exception as exc:
                        import urllib.error
                        unsupported = isinstance(exc, urllib.error.HTTPError) and exc.code in (404, 422)
                        self.journal.write('position_injection_error', error=str(exc),
                                           disabled_until_restart=unsupported)
            except Exception as exc:
                with self.lock:
                    self.fix, self.position_error = None, str(exc)
                self.journal.write('position_provider_error', error=str(exc))
                if self.inject and not unsupported:
                    try:
                        self.edge.set_position(None)
                    except Exception:
                        pass
            stop.wait(self.sample_s)

    def observations(self, stop):
        while not stop.is_set():
            try:
                response = self.edge.events(self.cursor, wait=.3)
                instance = response.get('instance_id')
                if self.edge_instance is not None and instance != self.edge_instance:
                    self.cursor = 0
                    self.edge_instance = instance
                    self.journal.write('edge_restarted', instance_id=instance)
                    continue
                self.edge_instance = instance
                for event in response.get('events', []):
                    # node_id is the serial logger/observer; origin is the business sender.
                    normalized = event_report(event, event['node_id'])
                    self.cursor = max(self.cursor, event['edge_cursor'])
                    if normalized is None:
                        continue
                    normalized['event_id'] = str(instance) + ':' + str(event['edge_cursor'])
                    self.journal.write('board_event', observation=normalized)
                    with self.lock:
                        if len(self.events) == self.events.maxlen:
                            self.events_dropped += 1
                        self.events.append(normalized)
                    if normalized['kind'] in ('received', 'relayed') or normalized['event'].startswith('neighbor'):
                        self.urgent.set()
                self.cursor = response.get('cursor', self.cursor)
            except Exception as exc:
                import urllib.error
                if isinstance(exc, urllib.error.HTTPError) and exc.code == 503:
                    # An expired retained cursor is surfaced by the owner as 503. Reset only
                    # after recording loss, with duplicates still carrying original identity.
                    self.journal.write('event_gap', cursor=self.cursor, error=str(exc))
                    self.cursor = 0
                else:
                    self.journal.write('event_poll_error', error=str(exc))
                stop.wait(.5)

    def snapshot(self):
        status = self.edge.status()
        try:
            raw_neighbors = self.edge.neighbors()
            try:
                telemetry = self.edge.telemetry()
            except Exception:
                telemetry = None
            neighbors = neighbor_report(raw_neighbors, telemetry)
            neighbor_error = None
        except Exception as exc:
            neighbors, neighbor_error = [], str(exc)
        info = status['info']
        if self.last_status and self.last_status['info'].get('boot_id') != info.get('boot_id'):
            self.journal.write('board_restarted', old_boot=self.last_status['info'].get('boot_id'), new_boot=info.get('boot_id'))
            self.session, self.seq = uuid.uuid4().hex, 0
        with self.lock:
            fix = aged_position(self.fix, self.max_age_s)
            events = list(self.events)[:128]
            position_error = self.position_error
            dropped = self.events_dropped
        self.seq += 1
        report = dict(schema_version=1, node_id=status['node_id'], boot_id=info.get('boot_id'),
                      session_id=self.session, seq=self.seq, label=self.label or status['node_id'],
                      position=fix, neighbors=neighbors, events=events, rf_source='unavailable',
                      generated_at=time.time(), position_error=position_error, neighbor_error=neighbor_error,
                      peer_positions=(telemetry or {}).get('peer_positions', []) if not neighbor_error else [],
                      radio_counters={k:v for k,v in dict(info, **(telemetry or {})).items()
                                      if k.startswith(('control_', 'route_data_', 'route_control_', 'telemetry_'))} if not neighbor_error else {},
                      events_dropped=dropped, edge_instance_id=status['instance_id'], **self.queue.stats())
        self.queue.put(report)
        with self.lock:
            # Producers can append during the transaction. Remove only captured entries.
            captured = {id(e) for e in events}
            self.events = collections.deque((e for e in self.events if id(e) not in captured), maxlen=512)
        self.last_status = status
        self.journal.write('report_queued', seq=self.seq, session_id=self.session,
                           node_id=status['node_id'], position_source=fix['source'] if fix else None,
                           events=len(events), **self.queue.stats())
        return report

    def run(self, stop):
        for name, function in [('position', self.positions), ('observations', self.observations)]:
            thread = threading.Thread(target=function, args=(stop,), name='mobile-' + name)
            thread.start()
            self.threads.append(thread)
        next_report = 0
        try:
            while not stop.is_set():
                now = time.monotonic()
                # Urgent changes are rate limited to one report per second.
                if now >= next_report or self.urgent.is_set() and now >= self._last_report + 1:
                    self.urgent.clear()
                    try:
                        self.snapshot()
                    except Exception as exc:
                        self.journal.write('snapshot_error', error=str(exc))
                    self._last_report = now
                    next_report = now + self.report_s
                stop.wait(.05)
        finally:
            stop.set()
            for thread in self.threads:
                thread.join()
            if hasattr(self.provider, 'close'):
                self.provider.close()
