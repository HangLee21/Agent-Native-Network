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
import collections
import json
import os
import socket
import struct
import threading
import time
import zlib
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


# ---------------------------------------------------------------- downlink (LRC2 / LRA2)
# The uplink is receiver-only by nature, but the same socket can carry commands back: the
# gateway's address is learned from the datagrams it sends, and a Semtech PULL_RESP (type 3)
# with a `txpk` body makes it transmit. The node answers with an LRA2 receipt over the air,
# which we match back to the command by its 8-byte id.
LRC2 = struct.Struct("<4sBBH6sHIIQIIII")


def build_command(target, target_boot, report_seq, operation, value, ttl_ms, cmd_id):
    """Encode one LRC2 command: it must anchor to a report the node actually sent."""
    op = {"echo": 1, "status": 2}.get(operation)
    if op is None:
        raise ValueError("operation must be echo or status")
    raw = LRC2.pack(b"LRC2", 1, op, 48, bytes.fromhex(target.replace(":", "")), 0,
                    target_boot, report_seq, cmd_id, ttl_ms, value, 0, 0)
    return raw[:-4] + struct.pack("<I", zlib.crc32(raw[:-4]))


def decode_receipt(raw):
    (magic, version, op, length, mac, flags, boot, seq, ident, status, value, uptime,
     crc) = LRC2.unpack(raw)
    if magic != b"LRA2" or version != 1 or length != 48:
        raise ValueError("not an LRA2 receipt")
    if crc != zlib.crc32(raw[:-4]):
        raise ValueError("LRA2 CRC")
    return {
        "target": mac_text(mac), "target_boot": boot, "report_seq": seq,
        "cmd_id": "%016x" % ident, "operation": "echo" if op == 1 else "status",
        "executed": status == 2, "status": status, "value": value,
        "uptime_ms": uptime, "duplicate": bool(flags & 1),
    }


class Topology:
    def __init__(self):
        self.lock = threading.Lock()
        self.reports = {}          # observer mac -> decoded record
        self.retired_boots = {}    # observer mac -> previously observed boots
        self.uplink_samples = {}   # bounded accepted sequence and receive-time samples
        self.labels = {}
        self.node_numbers = {}     # observer mac -> number learned from header byte 35
        self.frames = 0
        self.resets = 0        # recvfrom OSErrors recovered from
        # Downlink: where the gateway last spoke to us, plus the commands we sent and the
        # receipts that came back.
        self.gateway_addr = None
        self.sock = None
        self.commands = []
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

    def note_addr(self, addr):
        """Remember where the gateway is so a command can be sent back on this socket."""
        self.gateway_addr = addr

    def note_command(self, entry):
        self.commands.append(entry)
        del self.commands[:-64]

    def claim_receipt(self, receipt):
        """Match an LRA2 to the command that produced it."""
        for entry in reversed(self.commands):
            if entry["cmd_id"] == receipt["cmd_id"]:
                entry["receipt"] = receipt
                entry["state"] = "executed" if receipt["executed"] else "rejected"
                return entry
        return None


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
                    # Reports and reception timestamps belong to the old gateway.
                    # PULL_DATA alone can announce a replacement before it forwards
                    # its first frame, so clear observations at identity change.
                    self.reports.clear()
                    self.retired_boots.clear()
                    self.uplink_samples.clear()
                    self.last_rx_by.clear()
                    self.node_numbers.clear()
                    self.last_rx = None
                    self.channel = None
                    self.freq = None
                    self.frames = self.lrn1 = self.foreign = self.bad = 0
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
            if raw[:4] == b"LRA2" and len(raw) == 48:
                # A command receipt travels over the same radio path as the reports.
                try:
                    receipt = decode_receipt(raw)
                except ValueError:
                    self.bad += 1
                    return
                self.claim_receipt(receipt)
                return
            if len(raw) < 48 or raw[:4] != b"LRN1" or raw[4] != 44 or raw[5] != 20:
                self.foreign += 1        # not our firmware: another node on this channel
                return
            rows = raw[7]
            flags = raw[6]
            has_status = bool(flags & 0x08)
            has_gps = bool(flags & 0x10)
            expect = 48 + 20 * rows + (24 if has_status else 0) + (20 if has_gps else 0)
            if len(raw) != expect:
                self.bad += 1
                return
            if crc32(raw[:-4]) != struct.unpack("<I", raw[-4:])[0]:
                self.bad += 1
                return
            observer = mac_text(raw[8:14])
            boot = struct.unpack("<I", raw[14:18])[0]
            seq = struct.unpack("<I", raw[18:22])[0]
            snapshot_ms = struct.unpack("<Q", raw[22:30])[0]
            if not boot or not seq:
                self.bad += 1
                return
            previous = self.reports.get(observer)
            retired = self.retired_boots.get(observer, set())
            if boot in retired:
                return
            if previous:
                old = previous['report']
                if boot == old['observer_boot']:
                    if not 0 < ((seq - old['report_seq']) % 0xffffffff) < 0x80000000 or snapshot_ms < old['snapshot_at_ms']:
                        return
                else:
                    if len(retired) >= 256:
                        return
                    self.retired_boots.setdefault(observer, set()).add(old['observer_boot'])
                    self.uplink_samples.pop(observer, None)
            self.last_rx = time.time()
            self.channel = pkt.get("chan")
            self.freq = pkt.get("freq")
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
                    "coding_rate": pkt.get("codr"),
                    "rf_chain": pkt.get("rfch"),
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
                    "ack_age_ms": struct.unpack("<H", row[14:16])[0] if row[11] & 0x01 else None,
                    "wifi_rssi_dbm": struct.unpack("b", row[16:17])[0] if row[11] & 0x02 else None,
                    "rssi_dbm": struct.unpack("b", row[16:17])[0] if row[11] & 0x02 else None,
                    "rf_age_ms": struct.unpack("<H", row[17:19])[0] if row[11] & 0x04 else None,
                    "wifi_channel": row[19] if row[11] & 0x08 else None,
                })
            offset = 44 + 20 * rows
            if has_status:
                b = offset
                record["status"] = {
                    "reset_reason": raw[b],
                    "supply_mv": raw[b + 1] | (raw[b + 2] << 8),
                    "die_temp_c": struct.unpack("<b", raw[b + 3:b + 4])[0],
                    "heap_free_kb": raw[b + 4],
                    "queue_depth": raw[b + 5],
                    "tx_drops": raw[b + 6],
                    "routes": raw[b + 7],
                    "lora_tx_power_dbm": struct.unpack("<b", raw[b + 8:b + 9])[0],
                    "lora_sf": raw[b + 9],
                    "fault_flags": raw[b + 10],
                    "pi_flags": raw[b + 11],
                    "pi_cpu_temp_c": struct.unpack("<b", raw[b + 12:b + 13])[0],
                    "pi_load_x10": raw[b + 13],
                    "pi_mem_free_mb": raw[b + 14] | (raw[b + 15] << 8),
                    "pi_wifi_rssi": struct.unpack("<b", raw[b + 16:b + 17])[0],
                    "serial_errors": raw[b + 17],
                    "battery_pct": raw[b + 18],
                    "wifi_channel": raw[b + 19] or None,
                }
                record["report"]["status"] = record["status"]
                offset += 24
            if has_gps:
                b = offset
                gflags = raw[b]
                record["gps"] = {
                    "flags": gflags,
                    "valid": bool(gflags & 0x01),
                    "fix_3d": bool(gflags & 0x02),
                    "lat_e7": struct.unpack("<i", raw[b + 1:b + 5])[0],
                    "lon_e7": struct.unpack("<i", raw[b + 5:b + 9])[0],
                    "alt_m": struct.unpack("<h", raw[b + 9:b + 11])[0],
                    "speed_cms": raw[b + 11] | (raw[b + 12] << 8),
                    "heading_cdeg": raw[b + 13] | (raw[b + 14] << 8),
                    "sats": raw[b + 15],
                    "hdop_x10": raw[b + 16],
                    "vdop_x10": raw[b + 17],
                }
                record["report"]["gps"] = record["gps"]
            previous = self.reports.get(observer)
            same_boot = previous and previous['report']['observer_boot'] == record['report']['observer_boot']
            for block, present in (('status', has_status), ('gps', has_gps)):
                stamp = block + '_received_at_ms'
                if present:
                    record[stamp] = int(self.last_rx_by[observer] * 1000)
                elif same_boot and block in previous:
                    record[block] = previous[block]
                    record['report'][block] = previous[block]
                    record[stamp] = previous[stamp]
                else:
                    record['report'][block] = None
                    record[stamp] = None
            self.reports[observer] = record
            self.uplink_samples.setdefault(observer, collections.deque(maxlen=20)).append((seq, time.monotonic()))
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
                for block in ('status', 'gps'):
                    stamp = item.get(block + '_received_at_ms')
                    item[block + '_age_ms'] = max(0, int(now * 1000) - stamp) if stamp is not None else None
                samples = self.uplink_samples.get(observer, ())
                quality = {'samples': len(samples), 'sequence_span': 1 if len(samples) == 1 else None, 'observed_fraction': None,
                           'last_interval_ms': None, 'max_interval_ms': None}
                if len(samples) >= 2:
                    steps = [(samples[i][0] - samples[i-1][0]) % 0xffffffff for i in range(1, len(samples))]
                    intervals = [max(0, int((samples[i][1] - samples[i-1][1]) * 1000)) for i in range(1, len(samples))]
                    span = 1 + sum(steps)
                    quality.update(sequence_span=span, observed_fraction=len(samples)/span,
                                   last_interval_ms=intervals[-1], max_interval_ms=max(intervals))
                item['uplink_quality'] = quality
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
    # The HTTP thread needs this same socket: replying on the address the gateway used is the
    # only option, because the gateway only accepts downlink from the server it talks to.
    topology.sock = sock
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
            topology.note_addr(addr)
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
            topology.note_addr(addr)
            sock.sendto(bytes([version]) + token + bytes([4]), addr)
            if len(data) >= 12:
                topology.note_gateway(data[4:12].hex())
    sock.close()


def send_command(topology, target, target_boot, report_seq, operation, value=0,
                 ttl_ms=10000, freq_hz=470500000, datr="SF7BW125"):
    """Transmit one LRC2 command through the gateway.

    Returns a dict describing what was sent. The gateway must have spoken to us at least once
    so its address is known; otherwise there is nowhere to send the PULL_RESP.
    """
    if topology.gateway_addr is None or topology.sock is None:
        raise RuntimeError("网关还没联系过本机：先等它发来一帧/PULL_DATA，再下发命令")
    cmd_id = int.from_bytes(os.urandom(8), "big") or 1
    frame = build_command(target, target_boot, report_seq, operation, value, ttl_ms, cmd_id)
    txpk = {
        "imme": True, "freq": freq_hz / 1e6, "powe": 14, "modu": "LORA",
        "datr": datr, "codr": "4/5", "size": len(frame),
        "data": base64.b64encode(frame).decode("ascii"),
    }
    body = json.dumps({"txpk": txpk}, separators=(",", ":")).encode("ascii")
    packet = bytes([2]) + b"\x00\x00" + bytes([3]) + body     # PULL_RESP
    topology.sock.sendto(packet, topology.gateway_addr)
    entry = {
        "cmd_id": "%016x" % cmd_id, "target": target, "target_boot": target_boot,
        "report_seq": report_seq, "operation": operation, "value": value,
        "ttl_ms": ttl_ms, "frame_hex": frame.hex(), "sent_at_ms": int(time.time() * 1000),
        "gateway": topology.gateway_addr[0], "state": "sent", "receipt": None,
    }
    topology.note_command(entry)
    return entry


def _read_json(handler):
    length = int(handler.headers.get("Content-Length") or 0)
    if not length:
        return {}
    return json.loads(handler.rfile.read(length).decode("utf-8"))



def handler_for(topology):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):                                # noqa: N802 - stdlib naming
            if self.path.split("?")[0] == "/api/v1/lora/commands":
                body = json.dumps({
                    "schema": "lora.commands.v1",
                    "gateway_addr": ("%s:%d" % topology.gateway_addr)
                                    if topology.gateway_addr else None,
                    "commands": list(reversed(topology.commands))[:20],
                }, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
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

        def do_POST(self):                               # noqa: N802 - stdlib naming
            if self.path.split("?")[0] != "/api/v1/lora/command":
                self.send_response(404)
                self.end_headers()
                return
            try:
                body = _read_json(self)
                entry = send_command(
                    topology,
                    target=body["target"],
                    target_boot=int(body["target_boot"]),
                    report_seq=int(body["report_seq"]),
                    operation=body.get("operation", "echo"),
                    value=int(body.get("value", 0)),
                    ttl_ms=int(body.get("ttl_ms", 10000)),
                )
                payload = json.dumps({"ok": True, "command": entry}, ensure_ascii=False).encode("utf-8")
                code = 200
            except Exception as exc:
                payload = json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False).encode("utf-8")
                code = 400
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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
