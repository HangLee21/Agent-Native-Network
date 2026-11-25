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
GATEWAY_IP = "192.168.137.11"   # static address configured on the Ebyte E870-L
LAB_IP = "192.168.137.10"       # this PC on the lab subnet


def port_open_on(host, port, timeout=1.5):
    import socket
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def gateway_nic_present():
    """True when this machine holds the lab subnet address the gateway forwards to."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -eq '%s' }).IPAddress" % LAB_IP],
            capture_output=True, text=True, timeout=20)
        return LAB_IP in (out.stdout or "")
    except Exception:
        return False


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


def receiver_worker_status(value):
    if not isinstance(value, dict) or value.get('schema') != 'lora.topology.v1' or value.get('source') != 'gateway_udp_lrn1' or not isinstance(value.get('receiver'), dict):
        return 'unknown'
    state = value['receiver'].get('worker_state')
    return state if state in ('starting', 'running', 'recovering', 'stopped') else 'legacy' if state is None else 'unknown'


def run_netmode_script(script, script_args, *, elevate=True, timeout=180):
    """Run a PowerShell script through Start-Process and return its exit status.

    The command text is fixed. Paths and arguments travel through the environment,
    then Windows command-line quoting is applied once to the child argument string.
    """
    child_args = ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)] + list(script_args)
    env = os.environ.copy()
    env["EORA_CHILD_PS_ARGS"] = subprocess.list2cmdline(child_args)
    env["EORA_CHILD_PS_ELEVATE"] = "1" if elevate else "0"
    command = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    $options = @{FilePath='powershell.exe'; ArgumentList=$env:EORA_CHILD_PS_ARGS;
                 PassThru=$true; Wait=$true; WindowStyle='Hidden'; ErrorAction='Stop'}
    if ($env:EORA_CHILD_PS_ELEVATE -eq '1') { $options.Verb = 'RunAs' }
    $child = Start-Process @options
    exit $child.ExitCode
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 125
}
'''
    return subprocess.run(["powershell.exe", "-NoProfile", "-Command", command],
                          env=env, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout)


def ensure_lab_mode(interactive=True):
    """Put the wired port on the lab subnet, elevating once if needed.

    Switching an interface address needs administrator rights, and the whole point of the
    desktop shortcut is that nobody has to remember that. Returns True when the address is
    present afterwards.
    """
    if gateway_nic_present():
        return True
    script = ROOT / "tools" / "mid_baseline" / "gateway_probe" / "netmode.ps1"
    if not script.is_file():
        print("  netmode.ps1 not found: %s" % script)
        return False
    print("  wired port is not on the lab subnet; switching (you will get one UAC prompt)")
    try:
        result = run_netmode_script(script, ["-Mode", "lab"])
        if result.returncode:
            print("  network setup exited with code %s: %s" %
                  (result.returncode, (result.stderr or result.stdout or "no details").strip()))
            return False
    except Exception as exc:
        print("  could not elevate: %s" % exc)
        return False
    for _ in range(20):
        if gateway_nic_present():
            return True
        time.sleep(1)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--output", default=None, help="Studio output dir (must not exist)")
    parser.add_argument("--skip-lab", action="store_true", help="do not touch the network mode")
    args = parser.parse_args()

    if not args.skip_lab:
        print("== wired port")
        if ensure_lab_mode():
            print("  lab subnet ready (%s)" % LAB_IP)
        else:
            print("  FAILED: %s is still missing." % LAB_IP)
            print("  Run as administrator:  .\\tools\\mid_baseline\\gateway_probe\\netmode.ps1 lab")
            print("  Continuing anyway; the page will show no data until this is fixed.")

    print("\n== checking services")
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
        existing = http_json(TOPOLOGY_PORT, "/api/v1/lora/topology")
        state = receiver_worker_status(existing)
        if state == 'unknown':
            print("  port %d is occupied by an unrecognized service; leaving it untouched" % TOPOLOGY_PORT)
            return 1
        print("  topology_server already up on %d (worker: %s)" % (TOPOLOGY_PORT, state))

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
    worker = receiver_worker_status(topo)
    if worker in ('starting', 'recovering'):
        print("  receiver worker is %s: %s" % (worker, rx.get('worker_error') or 'waiting for UDP socket'))
    elif worker == 'stopped':
        print("  receiver worker stopped; inspect topology.out; no process was terminated")
    elif worker == 'legacy':
        print("  receiver worker health not provided by this older service")
    print("\n== state")
    print("  gateway : %s" % (topo.get("labels", {}).get(rx.get("gateway_id"), rx.get("gateway_id") or "-")))
    print("  frames  : %s   reports: %d" % (rx.get("frames"), len(topo.get("reports") or [])))
    if worker in ('starting', 'recovering', 'stopped', 'unknown'):
        print("  receiver health is not ready; waiting for the local receiver before diagnosing gateway traffic")
    elif rx.get('gateway_observed') is True and rx.get('state') != 'receiving':
        print("  gateway heartbeat is healthy; waiting for new node reports")
    elif rx.get("state") != "receiving":
        # Diagnose instead of just warning: the three usual causes are checked in the order
        # that used to waste the most time.
        gw = port_open_on(GATEWAY_IP, 80)
        nic = gateway_nic_present()
        print("  no frames yet. Checks:")
        print("    %s gateway %s reachable" % ("OK  " if gw else "FAIL", GATEWAY_IP))
        print("    %s wired port configured for the lab subnet (%s)" % ("OK  " if nic else "FAIL", LAB_IP))
        if not nic:
            print("       -> run as administrator:  .\\tools\\mid_baseline\\gateway_probe\\netmode.ps1 lab")
        if nic and not gw:
            print("       -> gateway off, cable out, or still booting (takes ~60 s)")
        if gw and nic:
            print("       -> gateway reachable but silent: check its server_address is %s"
                  " and serv_port_up is %d" % (LAB_IP, UDP_PORT))
        if not (gw or nic):
            pass

    url = "http://127.0.0.1:%d/" % STUDIO_PORT
    print("\n== open %s" % url)
    if not args.no_browser:
        webbrowser.open(url)
    print("  (leave this window open to keep the services running, or close it: they are detached)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
