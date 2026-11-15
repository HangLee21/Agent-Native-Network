"""Nonce-bound live neighbor queries; all elapsed times use the host monotonic clock."""
import math
import time
from . import protocol as p


class DirectQueries:
    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.pending = {}
        self.sequences = {}
        self.last_sent = {}

    def requests(self, entries):
        now = self.clock()
        self.pending = {key: row for key, row in self.pending.items() if now-row['sent'] <= 1}
        active = [row for row in entries if row['connected'] and row.get('status',{}).get('neighbors_api')==1]
        requests = []
        for observer in active:
            key = observer['node_id'], observer['boot_id']
            if now-self.last_sent.get(key,float('-inf')) < 2:
                continue
            nonce = self.sequences.get(key,0)+1
            if nonce > 0xffffffff:
                continue # Never wrap an ID within the PC session.
            self.sequences[key]=nonce;self.last_sent[key]=now
            self.pending[(key[0],key[1],nonce)] = dict(node=key[0], boot=key[1],
                address=tuple(observer['address']), sent=now)
            requests.append((observer['address'], dict(entry_boot=key[1], query_id=nonce)))
        return requests

    def receive(self, value, address, pc_session):
        nonce = p.uint32(value.get('query_id'), 'neighbor query_id')
        key=value['entry_id'],value['entry_boot'],nonce
        pending = self.pending.get(key)
        if (not pending or value.get('pc_session') != pc_session or
            tuple(address) != pending['address']):
            raise ValueError('unmatched current neighbor request')
        now = self.clock()
        rtt = now-pending['sent']
        if not 0 <= rtt <= 1:
            self.pending.pop(key, None)
            raise ValueError('neighbor reply exceeded one second bound')
        stamp = value.get('snapshot_at_ms')
        if type(stamp) is not int or not 0 <= stamp <= 2**53-1:
            raise ValueError('invalid neighbor snapshot clock')
        if value.get('ok') is not True or value.get('encoding')!='nd.rf.v1' or value.get('confirm_ms')!=9000 or value.get('lost_ms')!=12000:
            raise ValueError('unsupported live neighbor snapshot contract')
        rows=value.get('rows')
        if not isinstance(rows,list) or len(rows)>8:
            raise ValueError('bounded complete neighbor table required')
        full=value.get('nd_full')
        if type(full) is not int or full<0:
            raise ValueError('ND capacity counter required')
        margin=math.ceil(rtt*1000)
        base=dict(observer_id=pending['node'],observer_boot=pending['boot'],query_id=nonce,
            pc_session=pc_session,received_monotonic=now,received_ms=int(time.time()*1000),
            rtt_upper_bound_ms=margin,snapshot_at_ms=stamp,source='nonce_neighbor_snapshot',nd_full=full)
        proofs=[];seen=set()
        for row in rows:
            if not isinstance(row,list) or len(row)!=8:
                raise ValueError('eight column ND row required')
            peer,boot,state,age,ack,rssi,rfage,channel=row
            p.mac(peer);p.uint32(boot,'neighbor peer boot')
            if peer==pending['node'] or peer in seen or type(state) is not int or state not in (0,1,2):
                raise ValueError('invalid or repeated ND peer')
            seen.add(peer)
            for number,limit in ((age,12000),(ack,9000),(rfage,12000)):
                if number is not None and (type(number) is not int or not 0<=number<=limit):
                    raise ValueError('invalid clamped board age')
            if age is None or state==2 and ack is None:
                raise ValueError('ND state requires seen/ACK age')
            if rssi is not None and (type(rssi) is not int or not -200<=rssi<=20 or rfage is None):
                raise ValueError('RSSI needs measured value and age')
            if channel is not None and (type(channel) is not int or not 1<=channel<=14):
                raise ValueError('invalid ND RF channel')
            proofs.append(dict(base,peer_id=peer,peer_boot=boot,state=('lost','heard','bidirectional')[state],
                seen_age_upper_bound_ms=age+margin if age<12000 else None,
                seen_age_lower_bound_ms=12000 if age==12000 else None,
                confirmation_age_upper_bound_ms=ack+margin if ack is not None and ack<9000 else None,
                confirmation_age_lower_bound_ms=9000 if ack==9000 else None,
                rssi_dbm=rssi,rf_age_upper_bound_ms=rfage+margin if rfage is not None and rfage<12000 else None,
                rf_age_lower_bound_ms=12000 if rfage==12000 else None,
                channel=channel,age_clamped=age==12000,ack_clamped=ack==9000,rf_age_clamped=rfage==12000))
        self.pending.pop(key)
        return dict(base,proofs=proofs,full_table=True,nd_full=value.get('nd_full'),raw=value)
