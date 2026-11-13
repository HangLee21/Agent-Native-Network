#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Minimal Semtech UDP receiver for the RHF2S008 packet forwarder.

Acknowledges PUSH_DATA and PULL_DATA (without which lora_pkt_fwd auto-quits) and appends
every received frame as one JSON line. Python 2 and 3 compatible; writes nothing else.
"""
import base64
import binascii
import json
import socket
import sys
import time

PORT = 1680
LOG = '/home/rxhf/eora_rx.jsonl'

PY3 = sys.version_info[0] >= 3


def reply(ver, token, kind):
    body = bytearray([ver]) + bytearray(token) + bytearray([kind])
    return bytes(body) if PY3 else str(body)


def to_hex(b64):
    try:
        return binascii.hexlify(base64.b64decode(b64)).decode('ascii')
    except Exception:
        return None


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', PORT))
    log = open(LOG, 'a')
    sys.stderr.write('eora_rx listening on udp/%d -> %s\n' % (PORT, LOG))
    sys.stderr.flush()
    while True:
        try:
            data, addr = sock.recvfrom(65535)
        except OSError:
            continue
        if len(data) < 4:
            continue
        ver = data[0] if PY3 else ord(data[0])
        token = data[1:3]
        mtype = data[3] if PY3 else ord(data[3])
        if mtype == 0:                      # PUSH_DATA
            sock.sendto(reply(ver, token, 1), addr)
            if len(data) <= 12:
                continue
            body = data[12:]
            try:
                payload = json.loads(body.decode('utf-8', 'replace'))
            except Exception:
                continue
            for pkt in payload.get('rxpk') or []:
                record = {
                    'host_t': time.strftime('%Y-%m-%dT%H:%M:%S'),
                    'tmst': pkt.get('tmst'), 'chan': pkt.get('chan'),
                    'freq': pkt.get('freq'), 'stat': pkt.get('stat'),
                    'rssi': pkt.get('rssi'), 'lsnr': pkt.get('lsnr'),
                    'datr': pkt.get('datr'), 'codr': pkt.get('codr'),
                    'size': pkt.get('size'),
                    'b64': pkt.get('data'), 'hex': to_hex(pkt.get('data')),
                }
                log.write(json.dumps(record) + '\n')
                log.flush()
        elif mtype == 2:                    # PULL_DATA
            sock.sendto(reply(ver, token, 4), addr)


if __name__ == '__main__':
    main()
