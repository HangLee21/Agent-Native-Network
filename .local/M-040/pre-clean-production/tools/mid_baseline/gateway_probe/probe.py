"""Discover and interrogate an Ethernet-attached LoRa gateway.

Read-only: sends discovery probes, opens TCP connections, and fetches the web root. It
never writes configuration to the device and never changes host IP settings.

    python -m tools.mid_baseline.gateway_probe.probe discover
    python -m tools.mid_baseline.gateway_probe.probe scan --cidr 169.254.173.0/24
    python -m tools.mid_baseline.gateway_probe.probe http --host 192.168.1.1
"""
import argparse
import json
import re
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor

COMMON_PORTS = [80, 443, 22, 23, 8080, 8443, 1883, 8883, 5000, 8081, 9000,
                1700, 2000, 4001, 4370, 502, 10000, 10001, 4789]


def bind_host():
    """Pick the IPv4 address of the wired adapter, without changing any setting."""
    import subprocess
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-NetIPConfiguration | Where-Object { $_.InterfaceAlias -like '*以太网*' "
                          "-and $_.IPv4Address }).IPv4Address.IPAddress"],
                         capture_output=True, text=True)
    return out.stdout.strip() or None


def discover(host_ip):
    """SSDP, mDNS and a passive DHCP watch. Returns every responder seen."""
    found = []

    def note(kind, addr, detail):
        found.append(dict(kind=kind, from_=addr, detail=detail))

    # SSDP
    try:
        msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\n"
               'MAN: "ssdp:discover"\r\nMX: 2\r\nST: ssdp:all\r\n\r\n').encode()
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(2.5)
        if host_ip:
            s.bind((host_ip, 0))
        s.sendto(msg, ("239.255.255.250", 1900))
        end = time.time() + 2.5
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4096)
                note("ssdp", addr[0], data.decode("latin-1", "replace").split("\r\n")[:5])
            except socket.timeout:
                break
        s.close()
    except OSError as exc:
        note("ssdp-error", "-", str(exc))

    # mDNS service enumeration
    try:
        q = b"".join(bytes([len(p)]) + p for p in
                     [b"_services", b"_dns-sd", b"_udp", b"local"]) + b"\x00"
        pkt = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0) + q + struct.pack(">HH", 12, 1)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                     socket.inet_aton(host_ip) if host_ip else socket.inet_aton("0.0.0.0"))
        s.settimeout(2.5)
        s.sendto(pkt, ("224.0.0.251", 5353))
        end = time.time() + 2.5
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4096)
                note("mdns", addr[0], data[:64].hex())
            except socket.timeout:
                break
        s.close()
    except OSError as exc:
        note("mdns-error", "-", str(exc))

    # Passive DHCP: is the device asking for an address?
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 67))
        s.settimeout(1.0)
        end = time.time() + 12
        seen = {}
        while time.time() < end:
            try:
                data, addr = s.recvfrom(4096)
            except socket.timeout:
                continue
            if len(data) >= 240:
                mac = ":".join(f"{b:02x}" for b in data[28:34])
                seen[mac] = seen.get(mac, 0) + 1
        s.close()
        for mac, count in seen.items():
            note("dhcp-client", mac, f"{count} packet(s)")
    except OSError as exc:
        note("dhcp-watch-unavailable", "-", str(exc))
    return found


def probe_port(host, port, timeout=0.4):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan(cidr, ports):
    base = cidr.split("/")[0].rsplit(".", 1)[0]
    live = []
    hosts = [f"{base}.{i}" for i in range(1, 255)]
    with ThreadPoolExecutor(max_workers=64) as pool:
        def check(h):
            if not probe_port(h, 80, 0.25) and not probe_port(h, 443, 0.25) \
                    and not probe_port(h, 22, 0.25):
                return None
            return h
        for host in pool.map(check, hosts):
            if host:
                live.append(host)
    results = []
    for host in live:
        open_ports = [p for p in ports if probe_port(host, p)]
        results.append(dict(host=host, ports=open_ports))
    return results


def http_probe(host, port=80):
    """Fetch the root page and pull out anything that identifies the product."""
    try:
        with socket.create_connection((host, port), timeout=2) as s:
            s.sendall(f"GET / HTTP/1.0\r\nHost: {host}\r\n\r\n".encode())
            raw = b""
            while len(raw) < 65536:
                chunk = s.recv(8192)
                if not chunk:
                    break
                raw += chunk
    except OSError as exc:
        return dict(host=host, port=port, error=str(exc))
    text = raw.decode("utf-8", "replace")
    head, _, body = text.partition("\r\n\r\n")
    title = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    server = re.search(r"(?im)^server:\s*(.+)$", head)
    return dict(host=host, port=port, status=head.splitlines()[0] if head else "",
                server=server.group(1).strip() if server else None,
                title=(title.group(1).strip()[:120] if title else None),
                bytes=len(raw), first_lines=head.splitlines()[:12])


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    s2 = sub.add_parser("scan")
    s2.add_argument("--cidr", default="169.254.173.0/24")
    s2.add_argument("--ports", type=int, nargs="*", default=COMMON_PORTS)
    h = sub.add_parser("http")
    h.add_argument("--host", required=True)
    h.add_argument("--port", type=int, default=80)
    a = ap.parse_args()
    host_ip = bind_host()
    if a.cmd == "discover":
        print(json.dumps(dict(host_ip=host_ip, responders=discover(host_ip)), indent=1))
    elif a.cmd == "scan":
        print(json.dumps(dict(cidr=a.cidr, live=scan(a.cidr, a.ports)), indent=1))
    else:
        print(json.dumps(http_probe(a.host, a.port), indent=1))


if __name__ == "__main__":
    main()
