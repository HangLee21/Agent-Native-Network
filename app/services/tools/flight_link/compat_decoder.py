"""LRN1 decoder for Python 3.4; generated from the delivery decoder."""
import struct,zlib
HEADER=struct.Struct('<4sBBBB6sIIQIBBII')
ROW=struct.Struct('<6sIBBHHbHB')
MAX_ROWS=8
MAX_FRAME=208
def _mac(raw):
 if len(raw)!=6 or raw[0]&1 or not any(raw):raise ValueError('unicast nonzero MAC required')
 return ':'.join('{:02x}'.format(b) for b in raw)

def decode_frame(data):
    if not isinstance(data, bytes) or not 48 <= len(data) <= MAX_FRAME:
        raise ValueError('LRN1 frame length')
    magic, hlen, rlen, flags, count, mac, boot, seq, stamp, group, total, reserved, period, delay = HEADER.unpack_from(data)
    if magic != b'LRN1' or hlen != 44 or rlen != 20 or flags & ~7 or reserved:
        raise ValueError('LRN1 header/version/reserved')
    if not boot or not seq or (not group) or (not 1000 <= period <= 3600000):
        raise ValueError('LRN1 identity/period')
    if not count <= total <= MAX_ROWS or bool(flags & 1) != (count < total):
        raise ValueError('LRN1 row/truncation declaration')
    if len(data) != 48 + ROW.size * count:
        raise ValueError('LRN1 exact frame length')
    if struct.unpack_from('<I', data, len(data) - 4)[0] != zlib.crc32(data[:-4]):
        raise ValueError('LRN1 CRC32')
    if not flags & 4 and delay:
        raise ValueError('invalid TX delay encoding')
    observer = _mac(mac)
    rows, peers = ([], set())
    for i in range(count):
        peer, epoch, state, valid, seen, ack, rssi, age, channel = ROW.unpack_from(data, 44 + i * 20)
        peer_id = _mac(peer)
        if peer_id == observer or peer_id in peers or (not epoch) or (state > 2) or valid & ~15:
            raise ValueError('LRN1 peer/state/flags')
        if seen > 12000 or ack > 9000 or age > 12000:
            raise ValueError('LRN1 age bounds')
        if not valid & 1 and ack or (not valid & 2 and rssi) or (not valid & 4 and age) or (not valid & 8 and channel):
            raise ValueError('noncanonical missing field')
        if state == 2 and (not valid & 1) or (valid & 2 and (not valid & 4)) or (valid & 8 and (not valid & 4 or not 1 <= channel <= 14)):
            raise ValueError('inconsistent validity flags')
        peers.add(peer_id)
        rows.append(dict(peer_id=peer_id, peer_boot=epoch, state=('lost', 'heard', 'bidirectional')[state], seen_age_ms=seen, ack_age_ms=ack if valid & 1 else None, rssi_dbm=rssi if valid & 2 else None, rf_age_ms=age if valid & 4 else None, channel=channel if valid & 8 else None, rf_source='measured' if valid & 2 else 'unavailable'))
    return dict(frame_schema='LRN1', observer_id=observer, observer_boot=boot, report_seq=seq, snapshot_at_ms=stamp, wifi_group=group, report_period_ms=period, tx_delay_ms=delay if flags & 4 else None, total_rows=total, truncated=bool(flags & 1), nd_table_full=bool(flags & 2), neighbors=rows, transport_age_ms=None, evidence='state_at_source_snapshot')
