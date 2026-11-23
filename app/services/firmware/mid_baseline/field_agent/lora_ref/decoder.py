"""Dependency-free LRN1 codec and USB JSONL envelope decoder; never opens a port."""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import struct
import zlib

HEADER = struct.Struct('<4sBBBB6sIIQIBBII')
ROW = struct.Struct('<6sIBBHHbHB')
MAX_ROWS = 8
MAX_FRAME = 208


def _mac(raw: bytes) -> str:
    if len(raw) != 6 or raw[0] & 1 or not any(raw):
        raise ValueError('unicast nonzero MAC required')
    return ':'.join(f'{b:02x}' for b in raw)


def _bytes_mac(text: str) -> bytes:
    if not isinstance(text, str):
        raise ValueError('MAC text required')
    try:
        raw = bytes.fromhex(text.replace(':', ''))
    except ValueError as exc:
        raise ValueError('invalid MAC') from exc
    if _mac(raw) != text:
        raise ValueError('canonical lower-case MAC required')
    return raw


def decode_frame(data: bytes) -> dict:
    if not isinstance(data, bytes) or not 48 <= len(data) <= MAX_FRAME:
        raise ValueError('LRN1 frame length')
    (magic, hlen, rlen, flags, count, mac, boot, seq, stamp, group,
     total, node_number, period, delay) = HEADER.unpack_from(data)
    # bits 0..4 are defined: truncated, table-full, delay, status block, gps block.
    # Byte 35 used to be reserved and now carries the device number. Requiring zero there
    # made every frame from firmware >= 2026-11-18 invalid on this decode path.
    if magic != b'LRN1' or hlen != 44 or rlen != 20 or flags & ~0x1F:
        raise ValueError('LRN1 header/version/reserved')
    if not boot or not seq or not group or not 1000 <= period <= 3600000:
        raise ValueError('LRN1 identity/period')
    if not count <= total <= MAX_ROWS or bool(flags & 1) != (count < total):
        raise ValueError('LRN1 row/truncation declaration')
    has_status = bool(flags & 8)
    has_gps = bool(flags & 16)
    expect = 48 + ROW.size * count + (24 if has_status else 0) + (20 if has_gps else 0)
    if len(data) != expect:
        raise ValueError('LRN1 exact frame length')
    if struct.unpack_from('<I', data, len(data)-4)[0] != zlib.crc32(data[:-4]):
        raise ValueError('LRN1 CRC32')
    if not flags & 4 and delay:
        raise ValueError('invalid TX delay encoding')
    observer = _mac(mac)
    rows, peers = [], set()
    for i in range(count):
        peer, epoch, state, valid, seen, ack, rssi, age, channel = ROW.unpack_from(data, 44+i*20)
        peer_id = _mac(peer)
        if peer_id == observer or peer_id in peers or not epoch or state > 2 or valid & ~15:
            raise ValueError('LRN1 peer/state/flags')
        if seen > 12000 or ack > 9000 or age > 12000:
            raise ValueError('LRN1 age bounds')
        if (not valid & 1 and ack) or (not valid & 2 and rssi) or (not valid & 4 and age) or (not valid & 8 and channel):
            raise ValueError('noncanonical missing field')
        if (state == 2 and not valid & 1) or (valid & 2 and not valid & 4) or (valid & 8 and (not valid & 4 or not 1 <= channel <= 14)):
            raise ValueError('inconsistent validity flags')
        peers.add(peer_id)
        rows.append(dict(peer_id=peer_id, peer_boot=epoch,
                         state=('lost', 'heard', 'bidirectional')[state], seen_age_ms=seen,
                         ack_age_ms=ack if valid & 1 else None,
                         rssi_dbm=rssi if valid & 2 else None,
                         rf_age_ms=age if valid & 4 else None,
                         channel=channel if valid & 8 else None,
                         rf_source='measured' if valid & 2 else 'unavailable'))
    status = gps = None
    if has_status:
        b = 44 + 20 * count
        status = dict(
            reset_reason=data[b], supply_mv=data[b + 1] | (data[b + 2] << 8),
            die_temp_c=struct.unpack_from('<b', data, b + 3)[0],
            heap_free_kb=data[b + 4], queue_depth=data[b + 5], tx_drops=data[b + 6],
            routes=data[b + 7], lora_tx_power_dbm=struct.unpack_from('<b', data, b + 8)[0],
            lora_sf=data[b + 9], fault_flags=data[b + 10], pi_flags=data[b + 11],
            pi_cpu_temp_c=struct.unpack_from('<b', data, b + 12)[0],
            pi_load_x10=data[b + 13], pi_mem_free_mb=data[b + 14] | (data[b + 15] << 8),
            pi_wifi_rssi=struct.unpack_from('<b', data, b + 16)[0],
            serial_errors=data[b + 17], battery_pct=data[b + 18],
            wifi_channel=data[b + 19] or None)
    if has_gps:
        b = 44 + 20 * count + (24 if has_status else 0)
        gflags = data[b]
        status_gps = dict(
            flags=gflags,
            valid=bool(gflags & 1), fix_3d=bool(gflags & 2), dgnss=bool(gflags & 4),
            lat_e7=struct.unpack_from('<i', data, b + 1)[0],
            lon_e7=struct.unpack_from('<i', data, b + 5)[0],
            alt_m=struct.unpack_from('<h', data, b + 9)[0],
            speed_cms=data[b + 11] | (data[b + 12] << 8),
            heading_cdeg=data[b + 13] | (data[b + 14] << 8),
            sats=data[b + 15], hdop_x10=data[b + 16], vdop_x10=data[b + 17])
        gps = status_gps
    return dict(frame_schema='LRN1', observer_id=observer, observer_boot=boot,
                report_seq=seq, snapshot_at_ms=stamp, wifi_group=group,
                node_number=node_number or None,
                report_period_ms=period, tx_delay_ms=delay if flags & 4 else None,
                total_rows=total, truncated=bool(flags & 1), nd_table_full=bool(flags & 2),
                neighbors=rows, status=status, gps=gps,
                transport_age_ms=None, evidence='state_at_source_snapshot')


def encode_frame(report: dict) -> bytes:
    rows = report['neighbors']
    total = report.get('total_rows', len(rows))
    status = report.get('status')
    gps = report.get('gps')
    flags = (int(len(rows) < total) | (int(bool(report.get('nd_table_full'))) << 1)
             | (int(report.get('tx_delay_ms') is not None) << 2)
             | (int(status is not None) << 3) | (int(gps is not None) << 4))
    raw = bytearray(HEADER.pack(b'LRN1', 44, 20, flags, len(rows),
                    _bytes_mac(report['observer_id']), report['observer_boot'], report['report_seq'],
                    report['snapshot_at_ms'], report['wifi_group'], total,
                    report.get('node_number') or 0,
                    report['report_period_ms'], report.get('tx_delay_ms') or 0))
    for row in rows:
        fields = [row.get(k) for k in ('ack_age_ms', 'rssi_dbm', 'rf_age_ms', 'channel')]
        valid = sum((int(v is not None) << i) for i, v in enumerate(fields))
        state = ('lost', 'heard', 'bidirectional').index(row['state'])
        raw.extend(ROW.pack(_bytes_mac(row['peer_id']), row['peer_boot'], state, valid,
                            row['seen_age_ms'], *(0 if v is None else v for v in fields)))
    if status is not None:
        # Field order and signedness must match write_status() in lrn1_frame.c exactly:
        # u8 reset, u16 supply, i8 die, u8 heap, u8 queue, u8 drops, u8 routes, i8 tx,
        # u8 sf, u8 fault, u8 pi_flags, i8 pi_temp, u8 pi_load, u16 pi_mem, i8 pi_wifi,
        # u8 serial, u8 battery.
        def _u8(v): return max(0, min(255, int(v or 0)))
        def _i8(v): return max(-128, min(127, int(v or 0)))
        def _u16(v): return max(0, min(65535, int(v or 0)))
        raw.extend(struct.pack('<BHbBBBBbBBBbBHbBBB',
                               _u8(status.get('reset_reason')),
                               _u16(status.get('supply_mv')),
                               _i8(status.get('die_temp_c')),
                               _u8(status.get('heap_free_kb')),
                               _u8(status.get('queue_depth')),
                               _u8(status.get('tx_drops')),
                               _u8(status.get('routes')),
                               _i8(status.get('lora_tx_power_dbm')),
                               _u8(status.get('lora_sf')),
                               _u8(status.get('fault_flags')),
                               _u8(status.get('pi_flags')),
                               _i8(status.get('pi_cpu_temp_c')),
                               _u8(status.get('pi_load_x10')),
                               _u16(status.get('pi_mem_free_mb')),
                               _i8(status.get('pi_wifi_rssi')),
                               _u8(status.get('serial_errors')),
                               _u8(status.get('battery_pct')),
                               _u8(status.get('wifi_channel'))))
        raw.extend(b'\x00' * 4)   # block is 24 bytes; 20 carry data
    if gps is not None:
        raw.extend(struct.pack('<Bii hHHBBB',
                               gps.get('flags', 0) & 0xFF,
                               int(gps.get('lat_e7', 0)),
                               int(gps.get('lon_e7', 0)),
                               int(gps.get('alt_m', 0)),
                               int(gps.get('speed_cms', 0)) & 0xFFFF,
                               int(gps.get('heading_cdeg', 0)) & 0xFFFF,
                               gps.get('sats', 0) & 0xFF,
                               gps.get('hdop_x10', 0) & 0xFF,
                               gps.get('vdop_x10', 0) & 0xFF))
        raw.extend(b'\x00' * 2)   # block is 20 bytes; 18 carry data
    raw.extend(struct.pack('<I', zlib.crc32(raw)))
    result = bytes(raw)
    decode_frame(result)  # Same canonical and bound checks for encoding.
    return result


def decode_serial_line(line: str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON field')
            result[key] = value
        return result
    if not isinstance(line, str) or len(line.encode('utf-8')) > 2048:
        raise ValueError('bounded JSONL required')
    value = json.loads(line, object_pairs_hook=unique,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    if value.get('schema') != 'lora.ref.v1' or value.get('event') != 'lora_ref_rx':
        raise ValueError('LoRa RX envelope required')
    _bytes_mac(value['gateway_id'])
    for field, minimum, maximum in [('gateway_boot', 1, 0xffffffff), ('rx_seq', 1, 0xffffffff), ('received_at_ms', 0, 2**53-1)]:
        v = value[field]
        if type(v) is not int or not minimum <= v <= maximum:
            raise ValueError('invalid RX '+field)
    radio = value['lora']
    if not isinstance(radio, dict):
        raise ValueError('LoRa metadata object required')
    for key in ('rssi_dbm', 'snr_db'):
        v = radio.get(key)
        if v is not None and (type(v) not in (int, float) or not math.isfinite(v)):
            raise ValueError('invalid LoRa packet status')
    raw = bytes.fromhex(value['frame_hex'])
    return dict(value, report=decode_frame(raw))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    args = p.add_mutually_exclusive_group(required=True)
    args.add_argument('--hex-file', type=Path)
    args.add_argument('--serial-file', type=Path)
    a = p.parse_args()
    result = decode_serial_line(a.serial_file.read_text(encoding='utf-8-sig')) if a.serial_file else decode_frame(bytes.fromhex(a.hex_file.read_text(encoding='ascii')))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
