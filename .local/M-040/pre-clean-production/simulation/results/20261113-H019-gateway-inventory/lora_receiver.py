
#!/usr/bin/env python2
# -*- coding: utf-8 -*-

import socket
import json
import base64
import time

HOST = '127.0.0.1'
PORT = 1680

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print("=== LoRa UDP Receiver ===")
print("Listening on %s:%d" % (HOST, PORT))
print("Waiting for gateway packets...")

while True:
    data, addr = sock.recvfrom(65535)

    if len(data) < 4:
        continue

    version = ord(data[0])
    token = data[1:3]
    msg_type = ord(data[3])

    # Semtech UDP protocol:
    # 0 = PUSH_DATA
    # 1 = PUSH_ACK
    # 2 = PULL_DATA
    # 4 = PULL_ACK

    if msg_type == 0:
        # Acknowledge PUSH_DATA
        sock.sendto(chr(version) + token + chr(1), addr)

        # PUSH_DATA header: 4 bytes + 8-byte gateway EUI
        if len(data) > 12:
            try:
                payload = json.loads(data[12:])

                if 'rxpk' in payload:
                    for pkt in payload['rxpk']:
                        print("\n========== LoRa RX ==========")
                        print("Time: %s" % time.strftime(
                            "%Y-%m-%d %H:%M:%S"))
                        print("Frequency: %s MHz" %
                              pkt.get('freq', '?'))
                        print("RSSI: %s dBm" %
                              pkt.get('rssi', '?'))
                        print("SNR: %s dB" %
                              pkt.get('lsnr', '?'))
                        print("CRC status: %s" %
                              pkt.get('stat', '?'))
                        print("Data rate: %s" %
                              pkt.get('datr', '?'))

                        encoded = pkt.get('data', '')
                        raw = base64.b64decode(encoded)

                        print("Payload HEX: %s" %
                              raw.encode('hex'))
                        print("Payload TEXT: %r" % raw)
                        print("=============================")

            except Exception as e:
                print("Parse error: %s" % e)

    elif msg_type == 2:
        # Acknowledge PULL_DATA
        sock.sendto(chr(version) + token + chr(4), addr)
