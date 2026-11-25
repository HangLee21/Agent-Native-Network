"""Serve the LoRa topology of our EoRa nodes from the RHF2S008 packet forwarder.

Listens to the Semtech UDP protocol the gateway speaks (PUSH_DATA on 1680), decodes the
LRN1 frames our firmware emits, and exposes the same `lora.topology.v1` JSON the Studio
already consumes. Non-LRN1 traffic on the same channel (other vendors' nodes) is counted
and ignored instead of being shown as ours.

    python -m tools.mid_baseline.gateway_probe.topology_server --port 8780
    # then point the Studio's "网关地址" at http://127.0.0.1:8780
"""
import argparse
import base64
import binascii
import json
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GATEWAY_EUI = "b827ebFFFE32e2c1"
GATEWAY_NAME = "RHF2S008"


def crc32(data):
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return crc ^ 0xFFFFFFFF


def mac_text(raw):
    return ":".join("%02x" % b for b in raw)


class Topology:
    def __init__(self):
        self.lock = threading.Lock()
        self.reports = {}          # observer mac -> decoded record
        self.labels = {}
        self.frames = 0
        self.lrn1 = 0
        self.foreign = 0
        self.bad = 0
        self.last_rx = None
        self.channel = None
        self.freq = None

    def ingest(self, pkt):
        """One rxpk dict from the gateway."""
        try:
            raw = base64.b64decode(pkt.get("data", ""))
        except (binascii.Error, ValueError):
            with self.lock:
                self.bad += 1
            return
        with self.lock:
            self.frames += 1
            self.last_rx = time.time()
            self.channel = pkt.get("chan")
            self.freq = pkt.get("freq")
            if len(raw) < 48 or raw[:4] != b"LRN1" or raw[4] != 44 or raw[5] != 20:
                self.foreign += 1        # not our firmware: another node on this channel
                return
            rows = raw[7]
            if len(raw) != 48 + 20 * rows:
                self.bad += 1
                return
            if crc32(raw[:-4]) != struct.unpack("<I", raw[-4:])[0]:
                self.bad += 1
                return
            observer = mac_text(raw[8:14])
            record = {
                "gateway_id": GATEWAY_EUI,
                "gateway_boot": 0,
                "report": {
                    "frame_schema": "LRN1",
                    "observer_id": observer,
                    "observer_boot": struct.unpack("<I", raw[14:18])[0],
                    "report_seq": struct.unpack("<I", raw[18:22])[0],
                    "snapshot_at_ms": struct.unpack("<Q", raw[22:30])[0],
                    "wifi_group": struct.unpack("<I", raw[30:34])[0],
                    "total_rows": raw[34],
                    "report_period_ms": struct.unpack("<I", raw[36:40])[0],
                    "tx_delay_ms": struct.unpack("<I", raw[40:44])[0],
                    "truncated": raw[34] > rows,
                    "neighbors": [],
                },
                "lora": {
                    "rssi_dbm": pkt.get("rssi"),
                    "snr_db": pkt.get("lsnr"),
                    "frequency_hz": int(round(float(pkt.get("freq", 0)) * 1e6)),
                    "channel": pkt.get("chan"),
                    "datarate": pkt.get("datr"),
                },
                "pc_receive_age_ms": 0,
            }
            for i in range(rows):
                row = raw[44 + 20 * i:44 + 20 * (i + 1)]
                record["report"]["neighbors"].append({
                    "peer_id": mac_text(row[0:6]),
                    "peer_boot": struct.unpack("<I", row[6:10])[0],
                    "state": row[10],
                    "valid": row[11],
                    "seen_age_ms": struct.unpack("<H", row[12:14])[0],
                    "ack_age_ms": struct.unpack("<H", row[14:16])[0],
                    "wifi_rssi_dbm": struct.unpack("b", row[16:17])[0] if row[11] & 0x02 else None,
                    "rssi_dbm": struct.unpack("b", row[16:17])[0] if row[11] & 0x02 else None,
                    "rf_age_ms": struct.unpack("<H", row[17:19])[0],
                    "wifi_channel": row[19],
                })
            self.reports[observer] = record
            self.lrn1 += 1

    def snapshot(self):
        with self.lock:
            labels = dict(self.labels)
            labels.setdefault(GATEWAY_EUI.lower(), GATEWAY_NAME)
            now = time.time()
            rows = []
            for observer, rec in self.reports.items():
                item = json.loads(json.dumps(rec))
                item["pc_receive_age_ms"] = int((now - self.last_rx) * 1000) if self.last_rx else 0
                rows.append(item)
            return {
                "schema": "lora.topology.v1",
                "source": "gateway_udp_lrn1",
                "labels": labels,
                "receiver": {
                    "state": "receiving" if self.last_rx else "idle",
                    "gateway_id": GATEWAY_EUI.lower(),
                    "port": None,
                    "serial_open": False,
                    "last_rx_age_ms": int((now - self.last_rx) * 1000) if self.last_rx else None,
                    "channel": self.channel,
                    "frequency_hz": int(round(float(self.freq) * 1e6)) if self.freq else None,
                    "frames": self.frames,
                    "lrn1_frames": self.lrn1,
                    "foreign_frames": self.foreign,
                    "bad_frames": self.bad,
                },
                "reports": rows,
                "evidence": "decoded from gateway PUSH_DATA; CRC32 verified per frame",
            }


def udp_loop(topology, port, stop):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        if len(data) < 4:
            continue
        version, token, mtype = data[0], data[1:3], data[3]
        if mtype == 0:                                   # PUSH_DATA
            sock.sendto(bytes([version]) + token + bytes([1]), addr)
            if len(data) > 12:
                try:
                    payload = json.loads(data[12:].decode("utf-8", "replace"))
                except ValueError:
                    continue
                for pkt in payload.get("rxpk") or []:
                    topology.ingest(pkt)
        elif mtype == 2:                                 # PULL_DATA
            sock.sendto(bytes([version]) + token + bytes([4]), addr)
    sock.close()


def handler_for(topology):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802 - stdlib naming
            if self.path.split("?")[0] in ("/api/v1/lora/topology", "/"):
                body = json.dumps(topology.snapshot(), ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):                    # keep the console quiet
            pass

    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--udp-port", type=int, default=1680)
    ap.add_argument("--port", type=int, default=8780)
    ap.add_argument("--labels", help="JSON file mapping MAC to a display name")
    a = ap.parse_args()
    topology = Topology()
    if a.labels:
        topology.labels.update(json.loads(open(a.labels, encoding="utf-8").read()))
    stop = threading.Event()
    threading.Thread(target=udp_loop, args=(topology, a.udp_port, stop), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler_for(topology))
    print(json.dumps({"status": "ready", "http": f"http://127.0.0.1:{a.port}/api/v1/lora/topology",
                      "udp": a.udp_port, "gateway": GATEWAY_EUI}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
