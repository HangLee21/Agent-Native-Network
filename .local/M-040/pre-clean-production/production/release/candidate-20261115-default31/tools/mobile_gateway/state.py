"""Bounded v1 report validation, session ordering and observation projections."""
import collections
import copy
import hashlib
import json
import math
import re
import threading
import time
import uuid

MAC = re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')


def millis():
    return int(time.time() * 1000)


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError('invalid ' + name)
    return value


def validate(report):
    r = copy.deepcopy(report)
    if not isinstance(r, dict) or type(r.get('schema_version')) is not int or r.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    if not isinstance(r.get('node_id'), str) or not MAC.fullmatch(r['node_id']):
        raise ValueError('node_id must be a canonical lowercase MAC')
    if not isinstance(r.get('session_id'), str) or not 1 <= len(r['session_id']) <= 128:
        raise ValueError('invalid session_id')
    if type(r.get('boot_id')) is not int or not 1 <= r['boot_id'] <= 0xffffffff:
        raise ValueError('boot_id must be an unsigned nonzero board boot ID')
    if type(r.get('seq')) is not int or not 1 <= r['seq'] <= 2**53 - 1:
        raise ValueError('invalid report seq')
    if not isinstance(r.get('label'), str) or len(r['label']) > 64:
        raise ValueError('invalid label')
    number(r.get('report_age_ms', 0), 'cached report age_ms', 0, 10**12)
    if 'neighbors_partial' in r and type(r['neighbors_partial']) is not bool:
        raise ValueError('neighbors_partial must be boolean')
    p = r.get('position')
    if p is not None:
        if not isinstance(p, dict) or not isinstance(p.get('source'), str) or len(p['source']) > 64:
            raise ValueError('invalid position source')
        number(p.get('lat'), 'latitude', -90, 90)
        number(p.get('lon'), 'longitude', -180, 180)
        number(p.get('age_ms'), 'position age_ms', 0, 10**12)
        if p.get('accuracy_m') is not None:
            number(p['accuracy_m'], 'accuracy_m', 0, 10**8)
    if not isinstance(r.get('neighbors'), list) or len(r['neighbors']) > 64:
        raise ValueError('neighbors must be a list of at most 64')
    seen = set()
    for n in r['neighbors']:
        if not isinstance(n, dict) or not isinstance(n.get('peer_id'), str) or not MAC.fullmatch(n['peer_id']) or n['peer_id'] == r['node_id'] or n['peer_id'] in seen:
            raise ValueError('invalid or repeated neighbor')
        seen.add(n['peer_id'])
        if n.get('state') not in ('heard', 'confirmed', 'lost', 'unknown'):
            raise ValueError('invalid neighbor state')
        if n.get('rf_source') not in ('measured', 'simulated', 'unavailable'):
            raise ValueError('neighbor rf_source required')
        if n.get('rssi_dbm') is not None:
            number(n['rssi_dbm'], 'RSSI', -200, 20)
            if n['rf_source'] == 'unavailable':
                raise ValueError('unavailable RSSI must be null')
        if n.get('sample_age_ms') is not None:
            number(n['sample_age_ms'], 'sample_age_ms', 0, 10**12)
        for key in ('sample_age_lower_bound_ms', 'sample_at_ms'):
            if n.get(key) is not None:
                number(n[key], key, 0, 10**12 if key.endswith('bound_ms') else 2**53-1)
        if 'age_is_lower_bound' in n and type(n['age_is_lower_bound']) is not bool:
            raise ValueError('age_is_lower_bound must be boolean')
        if n.get('peer_boot') is not None and (type(n['peer_boot']) is not int or not 1 <= n['peer_boot'] <= 0xffffffff):
            raise ValueError('invalid neighbor peer_boot')
    if not isinstance(r.get('events'), list) or len(r['events']) > 128:
        raise ValueError('events must be a list of at most 128')
    for event in r['events']:
        if not isinstance(event, dict) or not isinstance(event.get('event', event.get('type')), str):
            raise ValueError('event needs event or type')
        for field in ('origin', 'dst'):
            if field in event and (not isinstance(event[field], str) or not MAC.fullmatch(event[field])):
                raise ValueError('invalid event ' + field)
        for field in ('origin_boot', 'boot', 'seq'):
            if field in event and (type(event[field]) is not int or not 1 <= event[field] <= 0xffffffff):
                raise ValueError('invalid event ' + field)
        if 'payload_hex' in event:
            try:
                if not isinstance(event['payload_hex'], str) or len(bytes.fromhex(event['payload_hex'])) > 160:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError('invalid payload_hex') from None
    return r


class State:
    def __init__(self, *, offline_ms=30000, stale_ms=30000, max_nodes=64, clock=millis, journal=None):
        self.instance = str(uuid.uuid4())
        self.offline_ms, self.stale_ms, self.max_nodes = offline_ms, stale_ms, max_nodes
        self.clock, self.journal = clock, journal
        self.lock = threading.RLock()
        self.nodes, self.retired = {}, {}
        self.neighbor_samples, self.retired_boots, self.boot_barriers = {}, {}, {}
        self.timeline = collections.deque(maxlen=8192)
        self.dedup = collections.OrderedDict()
        self.cursor = 0
        self.counts = collections.Counter()
        self._event(None, 'gateway_started', {'instance': self.instance}, self.clock())

    def _event(self, node, kind, data, received):
        self.cursor += 1
        self.timeline.append(dict(cursor=self.cursor, received_ms=received, node_id=node, type=kind, data=copy.deepcopy(data)))

    def accept(self, report, received=None, *, replay=False):
        r = validate(report)
        now = self.clock() if received is None else received
        with self.lock:
            node, session = r['node_id'], r['session_id']
            old = self.nodes.get(node)
            outcome = 'accepted'
            if r['boot_id'] in self.retired_boots.get(node, set()):
                outcome = 'retired_boot'
            elif old and session == old['report']['session_id']:
                if r['boot_id'] != old['report']['boot_id']:
                    raise ValueError('boot_id changed within a report session')
                if r['seq'] <= old['report']['seq']:
                    outcome = 'duplicate' if r['seq'] == old['report']['seq'] else 'out_of_order'
            elif session in self.retired.get(node, set()):
                outcome = 'retired_session'
            if outcome != 'accepted':
                self.counts[outcome] += 1
                return dict(status=outcome, current_seq=old['report']['seq'], cursor=self.cursor)
            if node not in self.nodes and len(self.nodes) >= self.max_nodes:
                raise ValueError('node capacity reached')
            if old and session != old['report']['session_id'] and len(self.retired.get(node, set())) >= 256:
                raise ValueError('session history capacity reached; start a new capture')
            # Persist before changing memory so an I/O failure cannot acknowledge an unrecorded report.
            if self.journal and not replay:
                self.journal(dict(received_ms=now, report=r))
            if old and session != old['report']['session_id']:
                self.retired.setdefault(node, set()).add(old['report']['session_id'])
                self._event(node, 'session_changed', dict(previous_session=old['report']['session_id'], previous_boot=old['report']['boot_id'], session_id=session, boot_id=r['boot_id']), now)
            if old and old['report']['boot_id'] != r['boot_id']:
                self.retired_boots.setdefault(node,set()).add(old['report']['boot_id'])
                self.boot_barriers[node] = now
                self.neighbor_samples.pop(node,None)
                for samples in self.neighbor_samples.values():
                    samples.pop(node,None)
                self.counts['neighbor_epoch_invalidations'] += 1
            if old and now - old['received_ms'] > self.offline_ms:
                self._event(node, 'telemetry_rejoined', {'gap_ms': now - old['received_ms']}, now)
            self.nodes[node] = dict(report=r, received_ms=now)
            self._merge_neighbors(r,now)
            self.counts['accepted'] += 1
            self._event(node, 'report', dict(session_id=session, seq=r['seq'], boot_id=r['boot_id']), now)
            for event in r['events']:
                # Identical retransmitted observations do not become extra deliveries.
                stable_event = event.get('raw', event)
                identity = (node, r['boot_id'], hashlib.sha256(json.dumps(stable_event, sort_keys=True, separators=(',', ':')).encode()).digest())
                if identity in self.dedup:
                    self.counts['duplicate_events'] += 1
                    continue
                self.dedup[identity] = True
                if len(self.dedup) > 16384:
                    self.dedup.popitem(last=False)
                self._event(node, event.get('event', event.get('type')), event, now)
            return dict(status='accepted', cursor=self.cursor)

    def _merge_neighbors(self, report, received):
        node,boot = report['node_id'],report['boot_id']
        partial = (report.get('neighbors_partial') is True or
                   'neighbors_partial' not in report and report.get('report_scope') == 'partial_rotating_rows')
        samples = self.neighbor_samples.setdefault(node,{})
        if not partial:
            listed = {n['peer_id'] for n in report['neighbors']}
            samples = self.neighbor_samples[node] = {peer:sample for peer,sample in samples.items() if peer in listed}
        for neighbor in report['neighbors']:
            peer = neighbor['peer_id']
            exact = neighbor.get('sample_age_ms')
            age = report.get('report_age_ms',0)
            known = exact is not None and neighbor.get('age_is_lower_bound') is not True and report.get('freshness_known') is not False
            lower = neighbor.get('sample_age_lower_bound_ms', exact)
            lower = (lower if lower is not None else 0)+age
            stamp = neighbor.get('sample_at_ms')
            identity = (neighbor.get('rf_source'),neighbor.get('rssi_dbm'))
            candidate = dict(value=copy.deepcopy(neighbor),observer_boot=boot,received_ms=received,
                exact_age=exact+age if known else None,lower_age=lower,stamp=stamp,identity=identity,
                sample_report_seq=report['seq'],state_report_seq=report['seq'])
            previous = samples.get(peer)
            replace = previous is None
            if previous is not None:
                if stamp is not None and previous['stamp'] is not None:
                    replace = stamp > previous['stamp']
                elif candidate['exact_age'] is not None:
                    replace = (previous['exact_age'] is None or
                        received-candidate['exact_age'] > previous['received_ms']-previous['exact_age'])
                else:
                    before_boot=previous['value'].get('peer_boot');next_boot=neighbor.get('peer_boot')
                    replace = identity != previous['identity'] or (before_boot is not None and next_boot is not None and before_boot!=next_boot)
            if replace:
                samples[peer] = candidate
            else:
                # A new report/state is not automatically a new RF sample.
                previous['value']['state'] = neighbor['state']
                previous['state_report_seq'] = report['seq']
                # First learning a timestamp/peer epoch does not prove that this
                # is a different sample from the untagged one already retained.
                if previous['stamp'] is None and stamp is not None:
                    previous['stamp']=stamp;previous['value']['sample_at_ms']=stamp
                if previous['value'].get('peer_boot') is None and neighbor.get('peer_boot') is not None:
                    previous['value']['peer_boot']=neighbor['peer_boot']
                if previous['exact_age'] is None:
                    previous['lower_age'] = max(previous['lower_age'],lower-max(0,received-previous['received_ms']))
                self.counts['neighbor_samples_not_refreshed'] += 1
            if len(samples) > 64:
                samples.pop(min(samples,key=lambda key:samples[key]['received_ms']))
                self.counts['neighbor_samples_evicted'] += 1

    def _neighbor(self,node,peer,sample,now):
        value = copy.deepcopy(sample['value'])
        elapsed = max(0,now-sample['received_ms'])
        exact = sample['exact_age']+elapsed if sample['exact_age'] is not None else None
        lower = max(sample['lower_age']+elapsed,exact if exact is not None else 0)
        invalid = None
        current = self.nodes.get(peer)
        explicit_boot = value.get('peer_boot')
        if current and explicit_boot is not None and explicit_boot != current['report']['boot_id']:
            invalid = 'peer_boot_mismatch'
        barrier = self.boot_barriers.get(peer)
        if barrier is not None and explicit_boot is None:
            if exact is None or now-exact <= barrier:
                invalid = 'peer_restart_sample_epoch_unverified'
        if sample['observer_boot'] != self.nodes[node]['report']['boot_id']:
            invalid = 'observer_boot_mismatch'
        freshness = ('stale' if value['state']=='lost' or lower>self.stale_ms else
                     'fresh' if exact is not None and exact<=self.stale_ms and invalid is None else 'unknown')
        value.update(sample_age_ms=exact,sample_age_lower_bound_ms=lower,
            sample_freshness=freshness,sample_stale=freshness!='fresh',
            sample_identity_basis='observer_sample_stamp' if sample['stamp'] is not None else 'exact_age_anchor' if sample['exact_age'] is not None else 'measurement_values_conservative',
            sample_received_ms=sample['received_ms'],sample_report_seq=sample['sample_report_seq'],
            state_report_seq=sample['state_report_seq'],observer_boot=sample['observer_boot'],
            peer_boot=explicit_boot,peer_current_boot=current['report']['boot_id'] if current else None,
            invalidated_reason=invalid,age_is_lower_bound=exact is None)
        return value

    def snapshot(self):
        now = self.clock()
        with self.lock:
            nodes, edges = [], []
            for node, row in self.nodes.items():
                r = copy.deepcopy(row['report'])
                age = max(0, now - row['received_ms']) + r.get('report_age_ms', 0)
                status = 'offline' if age > self.offline_ms else 'online'
                r.update(received_ms=row['received_ms'], report_age_ms=age, telemetry_status=status)
                if r.get('position') is not None:
                    p = r['position']
                    p['age_ms'] += age
                    p['stale'] = p['age_ms'] > self.stale_ms or p.get('fix') is False or p.get('valid') is False
                r['neighbors'] = [self._neighbor(node,peer,sample,now)
                                  for peer,sample in self.neighbor_samples.get(node,{}).items()]
                for n in r['neighbors']:
                    peer = self.nodes.get(n['peer_id'])
                    reverse_sample = self.neighbor_samples.get(n['peer_id'],{}).get(node)
                    reverse = self._neighbor(n['peer_id'],node,reverse_sample,now) if peer and reverse_sample else None
                    fresh = n['sample_freshness']=='fresh'
                    peer_age = max(0, now - peer['received_ms']) + peer['report'].get('report_age_ms', 0) if peer else 0
                    mutual = bool(status == 'online' and fresh and n['state'] == 'confirmed' and peer and peer_age <= self.offline_ms and reverse and reverse['state'] == 'confirmed' and reverse['sample_freshness']=='fresh' and n['invalidated_reason'] is None and reverse['invalidated_reason'] is None)
                    edges.append(dict(n, **{'from': n['peer_id'], 'to': node, 'telemetry_status': status, 'sample_stale': not fresh, 'mutual_confirmed': mutual, 'reported_by': node}))
                nodes.append(r)
            return dict(schema_version=1, gateway_instance=self.instance, now_ms=now, nodes=nodes, edges=edges, cursor=self.cursor, counters=dict(self.counts), offline_after_ms=self.offline_ms, stale_after_ms=self.stale_ms, role='observation_only',neighbor_merge_policy='per_observer_peer_v1')

    def history(self, after=0):
        with self.lock:
            oldest = self.timeline[0]['cursor'] if self.timeline else self.cursor + 1
            return dict(schema_version=1, gateway_instance=self.instance, events=copy.deepcopy([x for x in self.timeline if x['cursor'] > after]), cursor=self.cursor, oldest_cursor=oldest, truncated=after > 0 and after < oldest - 1)
