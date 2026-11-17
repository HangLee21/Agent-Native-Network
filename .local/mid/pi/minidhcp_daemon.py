"""Bench DHCP for direct-cable / switch-attached Raspberry Pis.

Replaces the single-MAC whitelist that blocked every device except the first one. The rule
now is the inverse: ignore this host's own MACs (they must never take a lease on the link
they serve) and give every other client a stable address from a small pool.

Stability comes from a lease file, so `ssh eora@169.254.10.23` keeps working across reboots
of both ends, and the lease file doubles as the inventory of everything on the bench:

    python3 minidhcp_daemon.py                 # serve the link
    python3 minidhcp_daemon.py --list          # print the inventory, then exit

No router and no DNS are advertised on purpose: this link exists to reach devices, and
answering with a gateway here used to steal the default route from the real uplink.
"""
import argparse
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = open(HERE / "minidhcp.log", "a", buffering=1, encoding="utf-8")
LEASES = HERE / "leases.json"
EXCLUDE = HERE / "dhcp_exclude.json"
HOSTNAMES = HERE / "hostnames.json"

MASK = "255.255.255.0"
LEASE_S = 3600
POOL_PREFIX = "192.168.137."
POOL_FIRST = 11
POOL_LAST = 250

_SERVER_IP = "192.168.137.10"


def log(*args, **kwargs):
    kwargs.pop("flush", None)
    print(time.strftime("%H:%M:%S"), *args, file=LOG, flush=True, **kwargs)


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save_leases(leases):
    tmp = LEASES.with_suffix(".tmp")
    tmp.write_text(json.dumps(leases, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, LEASES)


def mac_of(data):
    return ":".join("%02x" % b for b in data[28:34])


def parse_options(data):
    options, index = {}, 240
    while index < len(data):
        code = data[index]
        if code == 255:
            break
        if code == 0:
            index += 1
            continue
        if index + 1 >= len(data):
            break
        length = data[index + 1]
        options[code] = data[index + 2:index + 2 + length]
        index += 2 + length
    return options


def build_reply(request, message_type, offer_ip):
    xid = struct.unpack("!I", request[4:8])[0]
    flags = struct.unpack("!H", request[10:12])[0]
    client_mac = request[28:44]
    packet = struct.pack("!BBBBIHH", 2, 1, request[2], 0, xid, 0, flags)
    packet += socket.inet_aton("0.0.0.0")
    packet += socket.inet_aton(offer_ip)
    packet += socket.inet_aton("0.0.0.0")
    packet += socket.inet_aton("0.0.0.0")
    packet += client_mac + b"\x00" * (16 - len(client_mac))
    packet += b"\x00" * 64 + b"\x00" * 128
    packet += b"\x63\x82\x53\x63"
    packet += bytes([53, 1, message_type])
    packet += bytes([54, 4]) + socket.inet_aton(_SERVER_IP)
    packet += bytes([51, 4]) + struct.pack("!I", LEASE_S)
    packet += bytes([1, 4]) + socket.inet_aton(MASK)
    # Router 0.0.0.0 is the RFC-defined way to say "no default gateway": the client is
    # satisfied, and nothing on this link can steal the real uplink's default route.
    packet += bytes([3, 4]) + socket.inet_aton(_SERVER_IP)
    packet += b"\xff"
    return packet


def build_nak(request):
    xid = struct.unpack("!I", request[4:8])[0]
    flags = struct.unpack("!H", request[10:12])[0]
    client_mac = request[28:44]
    packet = struct.pack("!BBBBIHH", 2, 1, request[2], 0, xid, 0, flags)
    packet += socket.inet_aton("0.0.0.0") * 4
    packet += client_mac + b"\x00" * (16 - len(client_mac))
    packet += b"\x00" * 64 + b"\x00" * 128
    packet += b"\x63\x82\x53\x63"
    packet += bytes([53, 1, 6])
    packet += bytes([54, 4]) + socket.inet_aton(_SERVER_IP)
    packet += b"\xff"
    return packet


def send_client(sock, packet):
    """Send to both broadcast addresses.

    On a multi-homed Windows host `255.255.255.255` follows the default route and can leave
    through the WiFi adapter, so the client on the wired link never sees the reply. The
    subnet broadcast of the served link is routed to that link explicitly, and sending both
    costs nothing.
    """
    for destination in ("255.255.255.255", "169.254.255.255"):
        try:
            sock.sendto(packet, (destination, 68))
        except OSError:
            pass


def pick_address(leases, mac):
    """Stable address per MAC: reuse the record, else take the next free slot."""
    if mac in leases:
        return leases[mac]
    used = set(leases.values())
    for last in range(POOL_FIRST, POOL_LAST + 1):
        candidate = POOL_PREFIX + str(last)
        if candidate not in used:
            leases[mac] = candidate
            save_leases(leases)
            return candidate
    return POOL_PREFIX + str(POOL_FIRST)


def main():
    global _SERVER_IP
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="print the lease inventory and exit")
    # Answer only this device. On a bench host the port is also the uplink, and a DHCP
    # server that answers everything can hand a bogus lease (and default route) to the
    # campus network or to this machine itself.
    parser.add_argument("--only-mac", action="append", default=[],
                        help="serve only this MAC (repeatable); default: serve everyone")
    args = parser.parse_args()

    leases = load_json(LEASES, {})
    # Drop leases that belong to a pool we no longer serve (the link moved subnets, for
    # example when the gateway joined 192.168.137.0/24). Otherwise a device keeps being
    # offered its old, now-unreachable address.
    stale = [mac for mac, ip in leases.items() if not str(ip).startswith(POOL_PREFIX)]
    if stale:
        for mac in stale:
            leases.pop(mac, None)
        save_leases(leases)
        log("dropped %d stale leases outside %s" % (len(stale), POOL_PREFIX))
    if args.list:
        if not leases:
            print("no leases yet")
        names = load_json(HOSTNAMES, {})
        for mac, ip in sorted(leases.items(), key=lambda kv: kv[1]):
            print("%-16s %-18s %s" % (ip, mac, names.get(mac, "")))
        return 0

    config = load_json(EXCLUDE, {})
    excluded = {m.lower() for m in config.get("exclude_macs", [])}
    host_ips = config.get("host_ips", [])
    if host_ips:
        _SERVER_IP = host_ips[0]
    names = load_json(HOSTNAMES, {})

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        sock.bind(("0.0.0.0", 67))
    except OSError as exc:
        log("bind udp/67 failed:", exc)
        return 1
    sock.settimeout(1.0)
    log("listening on udp/67, pool %s%d-%d, %d known leases, excluding %s"
        % (POOL_PREFIX, POOL_FIRST, POOL_LAST, len(leases), ",".join(sorted(excluded)) or "none"))

    while True:
        try:
            data, addr = sock.recvfrom(2048)
        except socket.timeout:
            continue
        except OSError:
            continue
        if len(data) < 240 or data[236:240] != b"\x63\x82\x53\x63":
            continue
        options = parse_options(data)
        message_type = options.get(53, b"\x00")[0]
        mac = mac_of(data)
        if mac in excluded:
            continue
        _allowed = {m.strip().lower() for m in getattr(args, "only_mac", [])}
        if _allowed and mac.lower() not in _allowed:
            # Not our device: stay silent rather than answer on a network we do not own.
            continue
        name = {1: "DISCOVER", 3: "REQUEST", 4: "DECLINE",
                7: "RELEASE", 8: "INFORM"}.get(message_type, str(message_type))
        host = options.get(12, b"").decode("utf-8", "replace")
        if host:
            names[mac] = host
            (HERE / "hostnames.json").write_text(json.dumps(names, indent=2, sort_keys=True), encoding="utf-8")
        offer = pick_address(leases, mac)
        log("<-", name, "from", addr[0], "mac=" + mac, "->", offer)
        if message_type == 1:
            send_client(sock, build_reply(data, 2, offer))
        elif message_type == 3:
            requested = options.get(50)
            requested_ip = (socket.inet_ntoa(requested)
                            if requested and len(requested) == 4 else None)
            if requested_ip and requested_ip != offer:
                send_client(sock, build_nak(data))
                log("-> NAK requested", requested_ip, "instead of", offer)
            else:
                send_client(sock, build_reply(data, 5, offer))


if __name__ == "__main__":
    sys.exit(main())
