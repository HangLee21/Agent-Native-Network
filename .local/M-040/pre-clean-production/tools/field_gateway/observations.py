"""Projection of partial board reports with explicit unknown transport freshness."""
from tools.mobile_gateway.state import State
import copy
import math
import time


class FieldState(State):
    def __init__(self, *args, monotonic=time.monotonic, **kwargs):
        super().__init__(*args, **kwargs)
        self.monotonic = monotonic
        self.direct_samples = {}
        self.direct_tables = {}

    def accept_direct(self, proof):
        """Only WirelessLink's nonce/lease-validated first response enters here."""
        with self.lock:
            observer=proof['observer_id'];listed={row['peer_id'] for row in proof['proofs']}
            self.direct_tables[observer]={key:copy.deepcopy(value) for key,value in proof.items() if key not in ('proofs','raw')}
            for key,old in self.direct_samples.items():
                if key[0]==observer and key[1] not in listed:
                    old['state']='unknown';old['invalidated_reason']='absent_current_complete_table'
            for row in proof['proofs']:
                self.direct_samples[(observer,row['peer_id'])] = copy.deepcopy(row)
            if len(self.direct_samples) > 320:
                self.direct_samples.pop(min(self.direct_samples, key=lambda k:self.direct_samples[k]['received_monotonic']))
            self._event(proof['observer_id'], 'neighbor_snapshot', proof, proof['received_ms'])

    def _direct(self, proof, nodes):
        value = copy.deepcopy(proof)
        elapsed = max(0, math.ceil((self.monotonic()-proof['received_monotonic'])*1000))
        for key in ('seen_age_upper_bound_ms', 'confirmation_age_upper_bound_ms','rf_age_upper_bound_ms',
                    'seen_age_lower_bound_ms','confirmation_age_lower_bound_ms','rf_age_lower_bound_ms'):
            if value[key] is not None:
                value[key] += elapsed
        observer = nodes.get(value['observer_id'])
        peer = nodes.get(value['peer_id'])
        epoch = bool(observer and peer and observer['boot_id']==value['observer_boot'] and peer['boot_id']==value['peer_boot'])
        seen = value['seen_age_upper_bound_ms']
        ack = value['confirmation_age_upper_bound_ms']
        valid = epoch and value['state'] in ('heard','bidirectional') and seen is not None and seen < 12000
        confirmed = valid and value['state']=='bidirectional' and ack is not None and ack < 9000
        value.update(valid=valid, confirmed=confirmed, epoch_verified=epoch,
                     freshness='fresh' if valid else 'unknown' if value['state']=='unknown' else 'stale',
                     seen_limit_ms=12000, confirmation_limit_ms=9000,
                     age_basis='upper_bound_board_age_plus_host_monotonic_rtt')
        value['valid_for_ms'] = max(0,min(12000-seen,9000-ack)) if confirmed else 0
        value.pop('received_monotonic', None)
        return value

    def snapshot(self):
        with self.lock:
            value = super().snapshot()
            nodes = {node['node_id']:node for node in value['nodes']}
            direct = {key:self._direct(proof,nodes) for key,proof in self.direct_samples.items()}
        edges = {(edge['to'],edge['from']):edge for edge in value['edges']}
        for (observer,peer), proof in direct.items():
            if observer not in nodes or peer not in nodes:
                continue
            edge = edges.get((observer,peer))
            if edge is None:
                edge = dict(peer_id=peer, state='unknown', rssi_dbm=None, rf_source='unavailable',
                    sample_age_ms=None, sample_age_lower_bound_ms=None, sample_freshness='unknown',
                    sample_stale=True, observer_boot=nodes[observer]['boot_id'], peer_boot=None,
                    reported_by=observer, **{'from':peer,'to':observer})
                value['edges'].append(edge)
                edges[(observer,peer)] = edge
            reverse = direct.get((peer,observer))
            mutual = bool(proof['confirmed'] and reverse and reverse['confirmed'] and
                proof['observer_boot']==reverse['peer_boot'] and proof['peer_boot']==reverse['observer_boot'])
            edge.update(direct_evidence=proof, direct_freshness=proof['freshness'],
                direct_confirmed=proof['confirmed'], mutual_confirmed=mutual,
                mutual_basis='nonce_neighbor_snapshot' if mutual else None)
            edge['mutual_valid_for_ms'] = min(proof['valid_for_ms'],reverse['valid_for_ms']) if mutual else 0
            # The current ND observation and its RSSI frame have separate ages.
            # Keep the previous partial RF sample traceable before projecting ND.
            edge['previous_rf_observation'] = {key:copy.deepcopy(edge.get(key)) for key in
                ('rssi_dbm','rf_source','sample_age_ms','sample_age_lower_bound_ms','sample_received_ms','sample_report_seq','observer_boot','peer_boot')}
            rf_freshness=('unknown' if proof['rssi_dbm'] is None else
                'fresh' if proof['rf_age_upper_bound_ms'] is not None and proof['rf_age_upper_bound_ms']<12000 else 'stale')
            edge.update(state='confirmed' if proof['state']=='bidirectional' else proof['state'],
                observer_boot=proof['observer_boot'],peer_boot=None,
                rssi_dbm=proof['rssi_dbm'],rf_source='measured' if proof['rssi_dbm'] is not None else 'unavailable',
                rssi_sample_age_upper_bound_ms=proof['rf_age_upper_bound_ms'],
                rssi_sample_age_lower_bound_ms=proof['rf_age_lower_bound_ms'],
                rssi_sample_freshness=rf_freshness,
                sample_kind='rf_frame',sample_age_ms=None,sample_age_lower_bound_ms=proof['rf_age_lower_bound_ms'],
                sample_age_upper_bound_ms=proof['rf_age_upper_bound_ms'],age_is_lower_bound=proof['rf_age_lower_bound_ms'] is not None,
                sample_received_ms=proof['received_ms'],sample_freshness=rf_freshness,
                sample_stale=rf_freshness!='fresh',sample_identity_basis='nonce_bound_rf_age_upper_bound',
                sample_query_id=proof['query_id'],sample_report_seq=None,state_report_seq=None,
                invalidated_reason=proof.get('invalidated_reason') or (None if proof['epoch_verified'] else 'direct_epoch_unverified'),
                confirmation_age_upper_bound_ms=proof['confirmation_age_upper_bound_ms'],
                confirmation_age_lower_bound_ms=proof['confirmation_age_lower_bound_ms'],
                confirmation_limit_ms=9000,seen_limit_ms=12000)
        # If only one side has an active query, legacy sample freshness cannot
        # stand in for the missing opposite current-epoch query.
        for (observer,peer), edge in edges.items():
            if (peer,observer) in direct and (observer,peer) not in direct:
                edge['mutual_confirmed'] = False
        for node in value['nodes']:
            node['neighbors'] = [copy.deepcopy(edge) for edge in value['edges'] if edge['to']==node['node_id']]
        value['direct_neighbor_policy'] = 'nonce_rtt_nd_9s_12s_v1'
        value['neighbor_snapshots'] = [{key:item for key,item in table.items() if key!='received_monotonic'}
                                       for table in self.direct_tables.values()]
        unknown = {node['node_id'] for node in value['nodes'] if node.get('freshness_known') is False}
        for node in value['nodes']:
            if node['node_id'] in unknown:
                node['telemetry_status'] = 'unknown'
                node['report_age_lower_bound_ms'] = node['report_age_ms']
                node['report_age_ms'] = None
        for edge in value['edges']:
            if edge['to'] in unknown:
                edge['telemetry_status']='unknown'
        return value
