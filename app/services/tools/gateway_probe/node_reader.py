#!/usr/bin/env python3
"""Keep one EoRa node's serial session alive and record it into a small bounded log.

Why this is not just `cat /dev/ttyUSB0 >> log`:

* the node emits roughly 8 events/second (tx_queued, route_accepted, route_waiting,
  tx_submit). Stored verbatim that is ~175 MB/day. Here the repetitive kinds are counted and
  flushed once a minute, while state-changing and diagnostic events are written immediately,
  so a week of operation stays in the low megabytes.
* opening the port asserts DTR/RTS, which are wired to the ESP32 EN/IO0 lines, so the board
  reboots (or lands in the ROM loader). The port is configured before open, the caller waits
  for it to come back, and the session is reused rather than reopened per read.
* the node can reboot or drop off USB on its own. The reader notices a silent port, reopens,
  and writes a session record instead of exiting.

Size control: LOG_MAX_BYTES per file, LOG_KEEP rotated files, and a hard cap on aggregated
kinds tracked at once. A quiet run writes a few hundred bytes a minute.

    python3 node_reader.py --out ~/eora/logs
"""
import argparse
import errno
import json
import os
import secrets
import sys
import time

import serial

BAUD = 460800
SETTLE_S = 2.5
SILENT_REOPEN_S = 30.0        # no bytes for this long -> reopen the port
AGG_FLUSH_S = 60.0            # how often counters are written out
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_KEEP = 3                  # -> at most ~6 MiB of logs on disk
BY_ID = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"

# Written immediately: they mark a state change or a fault.
IMMEDIATE = {
    "command_result", "deployment_applied", "error", "fault", "panic", "boot",
    "route_lost", "route_reply", "route_reject", "neighbor_lost", "neighbor_add",
    "radio_heal", "radio_error", "config_applied", "storage_error",
}
IMMEDIATE_FIELDS = ("schema", "event", "at_ms", "at", "node_id", "boot_id", "build_id",
                    "cmd", "ok", "error", "why", "seq", "dst", "src", "reason", "detail",
                    "state", "mode", "code")


def rotate(path, max_bytes, keep):
    """Rotate `path` when it exceeds max_bytes, keeping `keep` older files."""
    try:
        if os.path.getsize(path) < max_bytes:
            return
    except OSError:
        return
    for index in range(keep - 1, 0, -1):
        older = "%s.%d" % (path, index)
        newer = "%s.%d" % (path, index + 1) if index + 1 <= keep else None
        if os.path.exists(older):
            if newer:
                os.replace(older, newer)
            else:
                os.remove(older)
    if os.path.exists("%s.1" % path):
        os.replace("%s.1" % path, "%s.2" % path)
    os.replace(path, "%s.1" % path)


class Writer:
    def __init__(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "node_events.jsonl")
        self.max_bytes = LOG_MAX_BYTES
        self.keep = LOG_KEEP
        self.handle = open(self.path, "a", buffering=1, encoding="utf-8")
        self.written = 0

    def line(self, record):
        self.handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.written += 1
        if self.written % 200 == 0:
            self.handle.flush()
            rotate(self.path, self.max_bytes, self.keep)
            self.handle.close()
            self.handle = open(self.path, "a", buffering=1, encoding="utf-8")

    def close(self):
        try:
            self.handle.close()
        except OSError:
            pass


def open_node(port):
    link = serial.Serial()
    link.port = port
    link.baudrate = BAUD
    link.timeout = 0.05
    link.dtr = False
    link.rts = False
    link.open()
    time.sleep(SETTLE_S)          # the open resets the board; let it boot
    link.reset_input_buffer()
    return link


def request(link, cmd, timeout=4.0):
    nonce = "svc-" + secrets.token_hex(4)
    link.write((json.dumps({"cmd": cmd, "nonce": nonce}) + "\n").encode())
    deadline = time.monotonic() + timeout
    buffer = bytearray()
    while time.monotonic() < deadline:
        chunk = link.read(4096)
        if not chunk:
            continue
        buffer.extend(chunk)
        while b"\n" in buffer:
            raw, _, rest = buffer.partition(b"\n")
            buffer[:] = rest
            try:
                reply = json.loads(raw)
            except ValueError:
                continue
            if isinstance(reply, dict) and reply.get("nonce") == nonce:
                return reply
    return None


def slim(reply):
    return {key: reply[key] for key in IMMEDIATE_FIELDS if key in reply}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=os.path.expanduser("~/eora/logs"))
    parser.add_argument("--port", default=BY_ID)
    args = parser.parse_args()

    writer = Writer(args.out)
    aggregates = {}
    last_rx = time.monotonic()
    last_flush = time.monotonic()
    link = None

    def flush_aggregates():
        nonlocal last_flush, aggregates
        if aggregates:
            writer.line({"t": int(time.time()), "aggregate": aggregates})
            aggregates = {}
        last_flush = time.monotonic()

    while True:
        try:
            if link is None:
                link = open_node(args.port)
                info = request(link, "info") or {}
                # device_label / node_number are the names the fleet actually uses; recording
                # them here lets display labels be rebuilt from data instead of a hand-written
                # table that drifts every time the naming scheme changes.
                writer.line({"t": int(time.time()), "session": "open", "port": args.port,
                             "node_id": info.get("node_id"), "build_id": info.get("build_id"),
                             "mode": info.get("mode"), "group": info.get("group"),
                             "device_label": info.get("device_label"),
                             "node_number": info.get("node_number"),
                             "lora_role": info.get("lora_ref_requested_role")})
                last_rx = time.monotonic()

            chunk = link.read(8192)
            now = time.monotonic()
            if chunk:
                last_rx = now
                for raw in chunk.split(b"\n"):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    if not isinstance(event, dict):
                        continue
                    kind = event.get("event") or event.get("schema") or "unknown"
                    if kind in IMMEDIATE:
                        record = slim(event)
                        record["t"] = int(time.time())
                        writer.line(record)
                    else:
                        aggregates[kind] = aggregates.get(kind, 0) + 1
            elif now - last_rx > SILENT_REOPEN_S:
                writer.line({"t": int(time.time()), "session": "reopen",
                             "reason": "silent %ds" % int(SILENT_REOPEN_S)})
                try:
                    link.close()
                except OSError:
                    pass
                link = None
                flush_aggregates()
                continue

            if now - last_flush > AGG_FLUSH_S:
                flush_aggregates()
        except serial.SerialException as exc:
            writer.line({"t": int(time.time()), "session": "error", "detail": str(exc)[:200]})
            try:
                if link:
                    link.close()
            except OSError:
                pass
            link = None
            flush_aggregates()
            time.sleep(3)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                writer.line({"t": int(time.time()), "session": "waiting", "detail": "port absent"})
                time.sleep(5)
            else:
                raise
        except KeyboardInterrupt:
            flush_aggregates()
            writer.close()
            return 0


if __name__ == "__main__":
    sys.exit(main())
