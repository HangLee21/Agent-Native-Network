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
import os
import socket
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LRN1_STATES = ("lost", "heard", "bidirectional")
STALE_AFTER_MS = 30000         # a node silent this long is shown as stale
GATEWAY_OBSERVE_S = 30      # a gateway silent this long is not observed

KNOWN_GATEWAYS = {"b827ebfffe32e2c1": "RHF2S008", "a4f00fe57b830000": "E870L-470"}   # friendly names only; identity comes from the wire


def log(*args):
    print(*args, flush=True)


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
        self.node_numbers = {}     # observer mac -> number learned from header byte 35
        self.frames = 0
        self.resets = 0        # recvfrom OSErrors recovered from
        self.lrn1 = 0
        self.foreign = 0
        self.bad = 0
        self.last_rx = None
        self.last_rx_by = {}     # observer mac -> last frame time
        self.channel = None
        self.freq = None
        # Learned from the PUSH_DATA header of whichever gateway is actually sending, so a
        # replacement gateway needs no code change and the old one keeps working.
        self.gateway_eui = None
        self.last_gateway = None   # any datagram, including PULL_DATA keepalives

    def gateway_name(self, eui=None):
        eui = (eui or self.gateway_eui or "").lower()
        return KNOWN_GATEWAYS.get(eui, "gateway-" + eui[-8:] if eui else "gateway")

    def note_reset(self):
        """Count a socket reset so a flapping link is visible instead of silent."""
        with self.lock:
            self.resets += 1

    def note_gateway(self, eui):
        """Called once per PUSH_DATA with the 8-byte EUI from the packet header."""
        if not eui:
            return
        with self.lock:
            if self.gateway_eui != eui:
                if self.gateway_eui:
                    log("gateway changed %s -> %s" % (self.gateway_eui, eui))
                else:
                    log("gateway %s (%s)" % (eui, self.gateway_name(eui)))
                self.gateway_eui = eui
            self.last_gateway = time.time()

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
            # Age must be per observer: a single global timestamp makes a dead node
            # look as fresh as whichever node transmitted most recently.
            self.last_rx_by[observer] = time.time()
            # Header byte 35 carries the device's own number, so names are learned from the
            # air and no roster file has to be maintained as the fleet grows.
            number = raw[35]
            if 1 <= number <= 255:
                self.node_numbers[observer] = number
            record = {
                "gateway_id": self.gateway_eui or "",
                "gateway_boot": 0,
                "report": {
                    "frame_schema": "LRN1",
                    "observer_id": observer,
                    "node_number": number if 1 <= number <= 255 else None,
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
                    # The viewer compares this field against the strings below, so emitting the raw
                    # byte silently disabled every lost/mutual classification.
                    "state": LRN1_STATES[row[10]] if row[10] < len(LRN1_STATES) else "unknown",
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
            # Learn from the wire, but never override a name a human put in the label file.
            for mac, num in self.node_numbers.items():
                labels.setdefault(mac, str(num))
            if self.gateway_eui:
                labels.setdefault(self.gateway_eui, self.gateway_name())
            now = time.time()
            rows = []
            for observer, rec in self.reports.items():
                item = json.loads(json.dumps(rec))
                seen = self.last_rx_by.get(observer)
                item["pc_receive_age_ms"] = int((now - seen) * 1000) if seen else 0
                rows.append(item)
            return {
                "schema": "lora.topology.v1",
                "source": "gateway_udp_lrn1",
                "labels": labels,
                "receiver": {
                    # A receiver that has not heard anything for the stale window must not keep claiming
                    # "receiving": that made a dead forwarder look healthy for hours.
                    "state": ("idle" if not self.last_rx else
                              "receiving" if (now - self.last_rx) * 1000 <= STALE_AFTER_MS else
                              "stale"),
                    "gateway_id": (self.gateway_eui or "").lower(),
                    # The viewer only uses a source when the gateway is provably talking to
                    # us; without these fields it reports "receiving" but is never selected.
                    "gateway_observed": bool(self.last_gateway
                                              and (now - self.last_gateway) <= GATEWAY_OBSERVE_S),
                    "gateway_last_pull_age_ms": int((now - self.last_gateway) * 1000)
                                                 if self.last_gateway else None,
                    "identity_verified": bool(self.gateway_eui),
                    "recent_threshold_ms": STALE_AFTER_MS,
                    "port": None,
                    "serial_open": False,
                    "last_rx_age_ms": int((now - self.last_rx) * 1000) if self.last_rx else None,
                    "channel": self.channel,
                    "frequency_hz": int(round(float(self.freq) * 1e6)) if self.freq else None,
                    "frames": self.frames,
                    "lrn1_frames": self.lrn1,
                    "foreign_frames": self.foreign,
                    "bad_frames": self.bad,
                    "socket_resets": self.resets,
                },
                "reports": rows,
                "evidence": "decoded from gateway PUSH_DATA; CRC32 verified per frame",
            }


def claim_port(port):
    """Refuse to start when another process already owns the UDP port.

    With SO_REUSEADDR Windows lets a second socket bind the same UDP port, and the two then
    race for incoming datagrams, so half the frames vanish with no error anywhere. Binding
    once without SO_REUSEADDR makes that situation visible at startup instead.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.bind(("0.0.0.0", port))
    except OSError:
        return False
    finally:
        probe.close()
    return True


def udp_loop(topology, port, stop):
    if not claim_port(port):
        log("udp/%d is already in use: another receiver would steal frames. "
            "Stop it first, or pass --udp-port." % port)
        stop.set()
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Windows turns the ICMP port-unreachable produced when a sender closes its socket into
    # a ConnectionResetError on the *next* recvfrom. `socket.SIO_UDP_CONNRESET` does not
    # exist in every Python build, so the constant is spelled out; relying on hasattr()
    # silently disabled this guard and let one reset kill the receive thread for good.
    if os.name == "nt":
        try:
            sock.ioctl(0x9800000C, False)
        except (OSError, ValueError, AttributeError):
            pass
    sock.bind(("0.0.0.0", port))
    sock.settimeout(0.5)
    while not stop.is_set():
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            continue
        except OSError:
            # A single reset must never end reception: the gateway keeps forwarding and we
            # would go deaf while still reporting a healthy "listening" state.
            if stop.is_set():
                break
            topology.note_reset()
            continue
        if len(data) < 4:
            continue
        version, token, mtype = data[0], data[1:3], data[3]
        if mtype == 0:                                   # PUSH_DATA
            sock.sendto(bytes([version]) + token + bytes([1]), addr)
            if len(data) > 12:
                # Bytes 4..12 are the gateway EUI: the Semtech UDP header carries it, so
                # whichever gateway is on the link identifies itself. No hard-coded ID.
                topology.note_gateway(data[4:12].hex())
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
    # A receiver that does not own the UDP port is worse than no receiver: the page stays
    # "empty" while frames are actually arriving somewhere else.
    if not claim_port(a.udp_port):
        print("udp/%d is already in use (another receiver or forwarder?). "
              "Stop it, or pass --udp-port." % a.udp_port, flush=True)
        return 1
    topology = Topology()
    if a.labels:
        topology.labels.update(json.loads(open(a.labels, encoding="utf-8").read()))
    stop = threading.Event()
    threading.Thread(target=udp_loop, args=(topology, a.udp_port, stop), daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), handler_for(topology))
    print(json.dumps({"status": "ready", "http": f"http://127.0.0.1:{a.port}/api/v1/lora/topology",
                      "udp": a.udp_port, "identity": "learned from PUSH_DATA header"}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        stop.set()


if __name__ == "__main__":
    main()
