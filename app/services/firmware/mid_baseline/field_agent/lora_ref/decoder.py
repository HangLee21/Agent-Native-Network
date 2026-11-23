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
     total, reserved, period, delay) = HEADER.unpack_from(data)
    if magic != b'LRN1' or hlen != 44 or rlen != 20 or flags & ~7 or reserved:
        raise ValueError('LRN1 header/version/reserved')
    if not boot or not seq or not group or not 1000 <= period <= 3600000:
        raise ValueError('LRN1 identity/period')
    if not count <= total <= MAX_ROWS or bool(flags & 1) != (count < total):
        raise ValueError('LRN1 row/truncation declaration')
    if len(data) != 48 + ROW.size * count:
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
    return dict(frame_schema='LRN1', observer_id=observer, observer_boot=boot,
                report_seq=seq, snapshot_at_ms=stamp, wifi_group=group,
                report_period_ms=period, tx_delay_ms=delay if flags & 4 else None,
                total_rows=total, truncated=bool(flags & 1), nd_table_full=bool(flags & 2),
                neighbors=rows, transport_age_ms=None, evidence='state_at_source_snapshot')


def encode_frame(report: dict) -> bytes:
    rows = report['neighbors']
    total = report.get('total_rows', len(rows))
    flags = (int(len(rows) < total) | (int(bool(report.get('nd_table_full'))) << 1)
             | (int(report.get('tx_delay_ms') is not None) << 2))
    raw = bytearray(HEADER.pack(b'LRN1', 44, 20, flags, len(rows),
                    _bytes_mac(report['observer_id']), report['observer_boot'], report['report_seq'],
                    report['snapshot_at_ms'], report['wifi_group'], total, 0,
                    report['report_period_ms'], report.get('tx_delay_ms') or 0))
    for row in rows:
        fields = [row.get(k) for k in ('ack_age_ms', 'rssi_dbm', 'rf_age_ms', 'channel')]
        valid = sum((int(v is not None) << i) for i, v in enumerate(fields))
        state = ('lost', 'heard', 'bidirectional').index(row['state'])
        raw.extend(ROW.pack(_bytes_mac(row['peer_id']), row['peer_boot'], state, valid,
                            row['seen_age_ms'], *(0 if v is None else v for v in fields)))
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
