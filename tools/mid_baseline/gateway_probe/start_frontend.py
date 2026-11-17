"""Bring the whole LoRa frontend up with one command.

Starts the two services the page needs, waits until they actually answer, then opens the
browser. Safe to run when they are already running: it reuses them instead of fighting for
the ports (two receivers on udp/1680 would silently split the frames).

    python tools/mid_baseline/gateway_probe/start_frontend.py
    python tools/mid_baseline/gateway_probe/start_frontend.py --no-browser
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PY = sys.executable
TOPOLOGY_PORT = 8780
STUDIO_PORT = 8794
UDP_PORT = 1680
LABELS = ROOT / ".local" / "mid" / "pi" / "labels.json"
FLEET = ROOT / "data" / "fleet.json"


def http_json(port, path, timeout=4):
    try:
        with urllib.request.urlopen("http://127.0.0.1:%d%s" % (port, path), timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def port_open(port):
    import socket
    s = socket.socket()
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def start_module(args, log_name):
    log_dir = ROOT / ".local" / "mid" / "pi"
    log_dir.mkdir(parents=True, exist_ok=True)
    out = open(log_dir / log_name, "w", encoding="utf-8")
    creation = 0x00000008 if os.name == "nt" else 0        # DETACHED_PROCESS
    return subprocess.Popen([PY, "-X", "utf8"] + args, cwd=str(ROOT),
                            stdout=out, stderr=subprocess.STDOUT,
                            creationflags=creation)


def wait_for(port, path, seconds=25):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if http_json(port, path, timeout=2) is not None:
            return True
        time.sleep(0.7)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--output", default=None, help="Studio output dir (must not exist)")
    args = parser.parse_args()

    print("== checking services")
    started = []

    if not port_open(TOPOLOGY_PORT):
        cmd = ["-m", "tools.mid_baseline.gateway_probe.topology_server",
               "--udp-port", str(UDP_PORT), "--port", str(TOPOLOGY_PORT)]
        if LABELS.is_file():
            cmd += ["--labels", str(LABELS)]
        print("  starting topology_server (udp/%d -> http/%d)" % (UDP_PORT, TOPOLOGY_PORT))
        started.append(start_module(cmd, "topology.out"))
        if not wait_for(TOPOLOGY_PORT, "/api/v1/lora/topology"):
            print("  topology_server did not come up; see .local/mid/pi/topology.out")
            return 1
    else:
        print("  topology_server already up on %d" % TOPOLOGY_PORT)

    if not port_open(STUDIO_PORT):
        stamp = time.strftime("%Y%m%d-%H%M%S") + "-frontend"
        output = args.output or str(ROOT / "simulation" / "outputs" / "H-019" / stamp)
        print("  starting Studio on %d (output %s)" % (STUDIO_PORT, output))
        studio_cmd = ["-m", "tools.mobile_gateway.studio",
                      "--port", str(STUDIO_PORT), "--pc-port", "8791",
                      "--output", output,
                      # The merged Studio polls the local receiver's HTTP view instead of
                      # opening the serial port, so the two never fight over hardware.
                      "--gateway-mode", "legacy_local",
                      "--topology-port", str(TOPOLOGY_PORT)]
        if FLEET.is_file():
            studio_cmd += ["--fleet", str(FLEET)]
        started.append(start_module(studio_cmd, "studio.out"))
        if not wait_for(STUDIO_PORT, "/api/v1/lora/topology"):
            print("  Studio did not come up; see .local/mid/pi/studio.out")
            return 1
    else:
        print("  Studio already up on %d" % STUDIO_PORT)

    topo = http_json(TOPOLOGY_PORT, "/api/v1/lora/topology") or {}
    rx = topo.get("receiver") or {}
    print("\n== state")
    print("  gateway : %s" % (topo.get("labels", {}).get(rx.get("gateway_id"), rx.get("gateway_id") or "-")))
    print("  frames  : %s   reports: %d" % (rx.get("frames"), len(topo.get("reports") or [])))
    if rx.get("state") != "receiving":
        print("  WARNING: no frames yet - is the gateway forwarding to this PC on udp/%d?" % UDP_PORT)

    url = "http://127.0.0.1:%d/" % STUDIO_PORT
    print("\n== open %s" % url)
    if not args.no_browser:
        webbrowser.open(url)
    print("  (leave this window open to keep the services running, or close it: they are detached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
