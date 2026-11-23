#!/usr/bin/env python3
"""Probe EoRa nodes attached to this host over USB serial.

Speaks the same `mid.serial.v1` line protocol the field firmware emits: one JSON object per
line, request/response matched by `nonce`. Everything is read-only: info/stats/lora_ref_status
never change device state.

Two things this has to get right on Linux that a naive pyserial open does not:

* opening the port asserts DTR/RTS, which are wired to the ESP32 EN/IO0 lines, so the board
  reboots (or drops into the ROM loader) as soon as the port is opened. The port is therefore
  configured before open and the caller waits SETTLE_S afterwards.
* the connection is reused for the whole probe instead of reopened per command, which is both
  what a real client does and what keeps the board out of a reset loop.

    python3 pi_node_probe.py              # one pass over every port
    python3 pi_node_probe.py --rounds 20  # stability pass
"""
import argparse
import json
import os
import secrets
import statistics
import sys
import time

import serial

BAUD = 460800
SETTLE_S = 2.5
NONCE_PREFIX = "probe-"


def candidate_ports():
    """Prefer /dev/serial/by-id so the name survives re-enumeration."""
    base = "/dev/serial/by-id"
    by_id = []
    if os.path.isdir(base):
        by_id = [os.path.join(base, name) for name in sorted(os.listdir(base))]
    if by_id:
        return by_id
    return sorted(
        os.path.join("/dev", name) for name in os.listdir("/dev")
        if name.startswith("ttyUSB") or name.startswith("ttyACM")
    )


class Node:
    def __init__(self, port):
        self.port = port
        self.events = 0
        self.buffer = bytearray()
        self.link = serial.Serial()
        self.link.port = port
        self.link.baudrate = BAUD
        self.link.timeout = 0.05
        self.link.dtr = False
        self.link.rts = False
        self.link.open()
        time.sleep(SETTLE_S)          # the open itself resets the board
        self.link.reset_input_buffer()

    def close(self):
        try:
            self.link.close()
        except Exception:              # noqa: BLE001 - closing must not raise
            pass

    def _pump(self, deadline, want=None):
        """Read lines until `want(nonce)` matches or the deadline passes."""
        while time.monotonic() < deadline:
            chunk = self.link.read(4096)
            if not chunk:
                continue
            self.buffer.extend(chunk)
            while b"\n" in self.buffer:
                line, _, rest = self.buffer.partition(b"\n")
                self.buffer[:] = rest
                line = line.strip()
                if not line:
                    continue
                try:
                    reply = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(reply, dict):
                    continue
                if want is None:
                    self.events += 1
                elif reply.get("nonce") == want:
                    return reply
        return None

    def ask(self, cmd, timeout=4.0, extra=None):
        nonce = NONCE_PREFIX + secrets.token_hex(4)
        request = {"cmd": cmd, "nonce": nonce}
        if extra:
            request.update(extra)
        self.link.write((json.dumps(request) + "\n").encode())
        reply = self._pump(time.monotonic() + timeout, want=nonce)
        if reply is None:
            raise TimeoutError("%s: no reply to %s within %.1fs" % (self.port, cmd, timeout))
        return reply

    def drain(self, seconds):
        """Count unsolicited events for a while."""
        before = self.events
        self._pump(time.monotonic() + seconds)
        return self.events - before


def summarize(reply):
    keys = ("node_id", "device_label", "build_id", "mode", "radio", "channel",
            "uart_baud", "lora_ref_requested_role", "frequency_hz", "sync_word",
            "report_period_ms", "attempted", "tx_done")
    parts = []
    for key in keys:
        if key in reply:
            value = reply[key]
            if key == "build_id":
                value = str(value)[-12:]
            parts.append("%s=%s" % (key, value))
    return " ".join(parts)


def probe_once(port, rounds):
    print("\n=== %s ===" % port)
    node = Node(port)
    try:
        info = node.ask("info")
        print("  info  :", summarize(info))
        stats = node.ask("stats")
        print("  stats :", summarize(stats))
        lora = node.ask("lora_ref_status")
        print("  lora  :", summarize(lora))
        idle_events = node.drain(3.0)
        print("  events: %d unsolicited events in 3 s" % idle_events)

        if rounds <= 0:
            return True

        latencies, failures = [], 0
        started = time.monotonic()
        for _ in range(rounds):
            try:
                begin = time.monotonic()
                node.ask("stats", timeout=3.0)
                latencies.append((time.monotonic() - begin) * 1000)
            except Exception as exc:           # noqa: BLE001 - report, do not abort
                failures += 1
                print("   round failure:", exc)
            time.sleep(0.2)
        elapsed = time.monotonic() - started
        if latencies:
            print("  %d rounds in %.1fs: %d ok, %d failed, median %.1f ms, max %.1f ms"
                  % (rounds, elapsed, len(latencies), failures,
                     statistics.median(latencies), max(latencies)))
        else:
            print("  %d rounds in %.1fs: all failed" % (rounds, elapsed))
        return failures == 0
    finally:
        node.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=0,
                        help="extra stats rounds per port (stability)")
    args = parser.parse_args()

    ports = candidate_ports()
    if not ports:
        print("no serial ports found: is a node plugged into this host?")
        return 1
    print("ports:", ports)
    ok = True
    for port in ports:
        try:
            ok = probe_once(port, args.rounds) and ok
        except Exception as exc:               # noqa: BLE001
            ok = False
            print("  FAILED:", exc)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
