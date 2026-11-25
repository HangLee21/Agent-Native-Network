"""Independent entry leases and board-supplied reachability; no host route planner."""
import copy
import secrets
import threading
import time
from .application import MAC, NoWirelessPath


class Entries:
    def __init__(self, query, *, lease_s=10, evidence_s=3, query_timeout=2,
                 max_payload=None, clock=time.monotonic):
        self.query = query
        self.lease_s, self.evidence_s, self.query_timeout = lease_s, evidence_s, query_timeout
        self.max_payload, self.clock = max_payload, clock
        self.condition = threading.Condition(threading.RLock())
        self.rows, self.retired, self.evidence, self.pending = {}, {}, {}, {}
        self.last_selected = None

    def register(self, node_id, boot_id, address, *, source='wireless_ip', lease_s=None, metadata=None):
        if not isinstance(node_id, str) or not MAC.fullmatch(node_id) or type(boot_id) is not int or not 1 <= boot_id <= 0xffffffff:
            raise ValueError('entry MAC and nonzero board boot required')
        now = self.clock()
        with self.condition:
            if boot_id in self.retired.get(node_id, []):
                raise ValueError('retired entry boot')
            old = self.rows.get(node_id)
            if old and old['boot_id'] != boot_id:
                self.retired[node_id] = (self.retired.get(node_id, []) + [old['boot_id']])[-4:]
                self.evidence = {k:v for k,v in self.evidence.items() if k[0] != node_id}
            if node_id not in self.rows and len(self.rows) >= 5:
                raise ValueError('five-entry capacity reached')
            lifetime = min(self.lease_s, self.lease_s if lease_s is None else lease_s)
            if lifetime <= 0:
                raise ValueError('positive lease lifetime required')
            self.rows[node_id] = dict(node_id=node_id, boot_id=boot_id, address=address,
                                      expires=now+lifetime, registered_at=now, source=source,
                                      status=copy.deepcopy(metadata or {}))
            self.condition.notify_all()

    def revoke(self, node_id, boot_id):
        with self.condition:
            row = self.rows.get(node_id)
            if row and row['boot_id'] == boot_id:
                row['expires'] = self.clock()
                self.condition.notify_all()

    def _active(self):
        now = self.clock()
        return [row for row in self.rows.values() if row['expires'] > now]

    def valid_sender(self, node_id, boot_id, address):
        with self.condition:
            row = self.rows.get(node_id)
            return bool(row and row['boot_id'] == boot_id and tuple(row['address']) == tuple(address)
                        and row['expires'] > self.clock())

    def route_evidence(self, node_id, boot_id, query_id, dst, hops, ttl_ms, *, raw=None):
        with self.condition:
            pending = self.pending.get(query_id)
            row = self.rows.get(node_id)
            if not pending or pending['dst'] != dst or not row or row['boot_id'] != boot_id or row['expires'] <= self.clock():
                return False
            if type(hops) is not int or not 0 <= hops <= 4 or type(ttl_ms) is not int or ttl_ms <= 0:
                return False
            until = min(row['expires'], self.clock() + min(ttl_ms/1000, self.evidence_s))
            self.evidence = {k:v for k,v in self.evidence.items() if v['expires'] > self.clock()}
            if len(self.evidence) >= 256:
                self.evidence.pop(min(self.evidence, key=lambda k:self.evidence[k]['expires']))
            self.evidence[(node_id, boot_id, dst)] = dict(hops=hops, expires=until, raw=raw, query_id=query_id)
            self.condition.notify_all()
            return True

    def _choose(self, dst):
        now = self.clock()
        candidates = []
        for row in self._active():
            evidence = self.evidence.get((row['node_id'], row['boot_id'], dst))
            if row['node_id'] == dst:
                candidates.append((0, row['node_id'], row, None))
            elif evidence and evidence['expires'] > now:
                candidates.append((evidence['hops'], row['node_id'], row, evidence))
        if not candidates:
            return None
        def order(item):
            path = (item[3] or {}).get('raw', {}).get('path', [item[1]])
            return item[0], tuple(bytes.fromhex(m.replace(':','')) for m in path), bytes.fromhex(item[1].replace(':', ''))
        hops, _, row, evidence = min(candidates, key=order)
        return dict(node_id=row['node_id'], boot_id=row['boot_id'], address=list(row['address']),
                    basis='direct_ip_registration' if hops == 0 else 'board_route_evidence',
                    hops=hops, evidence_valid_for_ms=max(0, int(((evidence or row)['expires']-now)*1000)),
                    evidence_expires_at=(evidence or row)['expires'],
                    path=copy.deepcopy(evidence['raw']['path']) if evidence and evidence.get('raw') and 'path' in evidence['raw'] else [row['node_id']],
                    evidence=copy.deepcopy(evidence), transport='wifi_ip' if hops == 0 else 'wifi_ip_then_espnow')

    def select(self, dst):
        with self.condition:
            ready = self._choose(dst)
            if ready:
                self.last_selected = ready
                return copy.deepcopy(ready)
            active = copy.deepcopy(self._active())
            if not active:
                raise NoWirelessPath('no active entry lease; no business submitted')
            if len(self.pending) >= 32:
                raise NoWirelessPath('finite route-query capacity reached; no business submitted')
            query_id = secrets.randbelow(0xffffffff) + 1
            while query_id in self.pending:
                query_id = secrets.randbelow(0xffffffff) + 1
            self.pending[query_id] = dict(dst=dst)
        try:
            for row in active:
                try:
                    self.query(row, dst, query_id)
                except OSError:
                    continue
            deadline = self.clock() + self.query_timeout
            with self.condition:
                # Collect replies within the native proof's remaining lifetime.
                collect_until = None
                while self.clock() < deadline:
                    ready = self._choose(dst)
                    now = self.clock()
                    if ready and collect_until is None:
                        collect_until = min(deadline, now+.2,
                                            now+max(.001,(ready['evidence_expires_at']-now)/2))
                    if collect_until is not None and now >= collect_until:
                        break
                    target = min(deadline, collect_until) if collect_until is not None else deadline
                    self.condition.wait(max(0,target-now))
                result = self._choose(dst)
                if not result:
                    raise NoWirelessPath('no fresh board route evidence from active entries; no business submitted')
                self.last_selected = result
                return copy.deepcopy(result)
        finally:
            with self.condition:
                self.pending.pop(query_id, None)

    def status(self):
        with self.condition:
            now = self.clock()
            rows = [dict(row, connected=row['expires'] > now,
                         lease_remaining_ms=max(0, int((row['expires']-now)*1000)))
                    for row in sorted(self.rows.values(), key=lambda r:r['node_id'])]
            return dict(connected=any(row['connected'] for row in rows), entries=rows,
                        last_selected=copy.deepcopy(self.last_selected), max_payload_bytes=self.max_payload,
                        entry_selection='dynamic_multi_entry', host_planner_used=False,
                        status='entries_available' if self._active() else 'no_wireless_path')
