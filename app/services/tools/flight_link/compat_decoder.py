"""LRN1 decoder for Python 3.4; accepts both the original and the extended frame.

The delivery firmware emits the original 44-byte-header frame; newer firmware keeps the same
header but uses byte 35 for the node number and may append a 24-byte status block (flags bit
3) and a 20-byte GPS block (flags bit 4). Both must decode, because a site may run either
firmware and the operator should not have to swap decoders to match.

Original frames stay byte-for-byte validated exactly as before; the extended fields are only
read when their flag is set, so an old frame produces exactly the old report plus
node_number=0.
"""
import struct,zlib
# node_number: 0 means the original firmware did not fill the field, so it is
# reported as None to match the host decoder.
HEADER=struct.Struct('<4sBBBB6sIIQIBBII')
ROW=struct.Struct('<6sIBBHHbHB')
STATUS=struct.Struct('<BHbBBBBbBBBbBHbBBB')
GPS=struct.Struct('<BiiHHhBBB2s')
MAX_ROWS=8
MAX_FRAME=208
STATUS_BYTES=24
GPS_BYTES=20

def _mac(raw):
 if len(raw)!=6 or raw[0]&1 or not any(raw):raise ValueError('unicast nonzero MAC required')
 return ':'.join('{:02x}'.format(b) for b in raw)

def _status(block):
 v=STATUS.unpack_from(block)
 return dict(reset_reason=v[0],supply_mv=v[1],die_temp_c=v[2],heap_free_kb=v[3],
  queue_depth=v[4],tx_drops=v[5],routes=v[6],lora_tx_power_dbm=v[7],lora_sf=v[8],
  fault_flags=v[9],pi_flags=v[10],pi_cpu_temp_c=v[11],pi_load_x10=v[12],
  pi_mem_free_mb=v[13],pi_wifi_rssi=v[14],serial_errors=v[15],battery_pct=v[16],
  wifi_channel=v[17])

def _gps(block):
 v=GPS.unpack_from(block)
 flags=v[0]
 return dict(flags=flags,
  lat_e7=v[1] if flags&1 else None,
  lon_e7=v[2] if flags&1 else None,
  alt_m=v[3] if flags&2 else None,
  speed_cms=v[4] if flags&2 else None,
  heading_cdeg=v[5] if flags&2 else None,
  sats=v[6],hdop=v[7],vdop=v[8])

def decode_frame(data):
 if not isinstance(data, bytes) or not 48 <= len(data) <= MAX_FRAME:
  raise ValueError('LRN1 frame length')
 magic,hlen,rlen,flags,count,mac,boot,seq,stamp,group,total,node_number,period,delay = HEADER.unpack_from(data)
 # Byte 35 is the node number in current firmware and zero in the original one; both valid.
 if magic != b'LRN1' or hlen != 44 or rlen != 20 or flags & ~0x1F:
  raise ValueError('LRN1 header/version/flags')
 if not boot or not seq or (not group) or not 1000 <= period <= 3600000:
  raise ValueError('LRN1 identity/period')
 if not count <= total <= MAX_ROWS or bool(flags & 1) != (count < total):
  raise ValueError('LRN1 row/truncation declaration')
 extra=(STATUS_BYTES if flags & 8 else 0)+(GPS_BYTES if flags & 16 else 0)
 if len(data) != 48 + ROW.size * count + extra:
  raise ValueError('LRN1 exact frame length')
 if struct.unpack_from('<I', data, len(data) - 4)[0] != zlib.crc32(data[:-4]):
  raise ValueError('LRN1 CRC32')
 if not flags & 4 and delay:
  raise ValueError('invalid TX delay encoding')
 observer = _mac(mac)
 rows, peers = ([], set())
 for i in range(count):
  peer,epoch,state,valid,seen,ack,rssi,age,channel = ROW.unpack_from(data, 44 + i * 20)
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
 body=44+ROW.size*count
 status=_status(data[body:body+STATUS_BYTES]) if flags & 8 else None
 gps=_gps(data[body+(STATUS_BYTES if flags & 8 else 0):body+(STATUS_BYTES if flags & 8 else 0)+GPS_BYTES]) if flags & 16 else None
 return dict(frame_schema='LRN1', observer_id=observer, observer_boot=boot, report_seq=seq, snapshot_at_ms=stamp, wifi_group=group, node_number=node_number or None, report_period_ms=period, tx_delay_ms=delay if flags & 4 else None, total_rows=total, truncated=bool(flags & 1), nd_table_full=bool(flags & 2), neighbors=rows, status=status, gps=gps, transport_age_ms=None, evidence='state_at_source_snapshot')
