"""Fleet control for the EoRa Raspberry Pis, over Tailscale.

Devices are found by name in the tailnet (`eora-air-*`), never by address, so campus DHCP
churn, WiFi changes and 4G all stop mattering.

    python fleet.py status                      # every device: node, build, uptime, disk, temp
    python fleet.py run "df -h /"               # one command across the fleet
    python fleet.py push <image.bin>            # copy a firmware image to every device
    python fleet.py update <image.bin>          # flash every node, verified + auto rollback
    python fleet.py logs eora-air-02            # tail one device's node events

`update` is the reason this exists: the node hangs off its Pi's USB, so the Pi programs its
own node. Ten devices or forty, it is the same single command instead of a bench session.
"""
import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

TAILSCALE = shutil.which("tailscale") or r"C:\Program Files\Tailscale\tailscale.exe"
KEY = os.path.expanduser(r"~/.ssh/id_ed25519_eora")
KNOWN_HOSTS = os.path.join(os.environ.get("TEMP", "/tmp"), "pi_known_hosts")
SSH_USER = "eora"
NAME_PREFIX = "eora-air-"
SUDO_PASS = os.environ.get("EORA_PASS", "")


def tailscale_devices():
    """Return [(name, ip)] for every online device whose name matches the fleet prefix."""
    out = subprocess.run([TAILSCALE, "status", "--json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit("tailscale status failed: " + (out.stderr or "").strip())
    data = json.loads(out.stdout or "{}")
    found = []
    for peer in (data.get("Peer") or {}).values():
        name = (peer.get("HostName") or "").strip()
        if not name.startswith(NAME_PREFIX):
            continue
        if not peer.get("Online", False):
            found.append((name, None))
            continue
        ips = peer.get("TailscaleIPs") or []
        ip = next((x for x in ips if ":" not in x), ips[0] if ips else None)
        found.append((name, ip))
    return sorted(found)


def tailscale_health():
    """Return (state, self_ips) so a caller can tell "Tailscale is down" from "no devices".

    BackendState drops to NoState and this machine loses its address whenever tailscaled
    cannot reach the coordination server. Reporting that as "no devices online" sends the
    operator to inspect the Pis, which is the wrong place; this has already cost hours.
    """
    out = subprocess.run([TAILSCALE, "status", "--json"], capture_output=True, text=True)
    if out.returncode != 0:
        return "error: " + (out.stderr or out.stdout or "").strip()[:120], []
    try:
        data = json.loads(out.stdout or "{}")
    except ValueError:
        return "unparseable status", []
    return data.get("BackendState") or "unknown", data.get("TailscaleIPs") or []


def require_tailscale():
    """Print an actionable message and return False when this PC is off the tailnet."""
    state, ips = tailscale_health()
    if state == "Running" and ips:
        return True
    print("Tailscale is not connected on this computer (state: %s)." % state)
    print("This is a network-app problem, not a device problem.")
    print("Fix, in an Administrator PowerShell:")
    print("    Restart-Service Tailscale")
    print("then check:")
    print("    tailscale status")
    return False


def ssh_target(name, ip):
    return "%s@%s" % (SSH_USER, ip or name)


def run_ssh(target, command, timeout=60, stdin_text=None):
    args = ["ssh", "-T", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
            "-o", "BatchMode=yes", "-i", KEY, "-o", "ConnectTimeout=15",
            "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4",
            target, command]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                              input=stdin_text)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ss" % timeout


STATUS_CMD = (
    'echo "uptime=$(cut -d. -f1 /proc/uptime)"; '
    'echo "disk=$(df -h / | awk \'NR==2{print $4" free of "$2}\')"; '
    'echo "temp=$(vcgencmd measure_temp 2>/dev/null | cut -d= -f2 | cut -d\\\' -f1)"; '
    'echo "wifi=$(ip -4 -o addr show wlan0 2>/dev/null | awk \'{print $4}\')"; '
    'echo "cable=$(ip -4 -o addr show eth0 2>/dev/null | awk \'{print $4}\')"; '
    'echo "reader=$(systemctl is-active node_reader)"; '
    # `grep -a`: a hard power cut can leave NUL holes in an ext4 file, after which plain grep
    # calls it binary and prints nothing.
    'echo "node=$(grep -a -h \'"session":"open"\' ~/eora/logs/node_events.jsonl 2>/dev/null | tail -1 | grep -a -o \'"node_id":"[^"]*"\' | cut -d\'"\' -f4) '
    '$(grep -a -h \'"session":"open"\' ~/eora/logs/node_events.jsonl 2>/dev/null | tail -1 | grep -a -o \'"build_id":"[^"]*"\' | cut -d\'"\' -f4 | tail -c 13)"'
)


def cmd_status(args):
    if not require_tailscale():
        return 2
    devices = tailscale_devices()
    if not devices:
        print("this computer is on the tailnet, but no %s* device is registered yet." % NAME_PREFIX)
        print("A new card shows up here after its first boot finishes (2-5 minutes).")
        return 1

    def one(item):
        name, ip = item
        if not ip:
            return name, "offline"
        code, out = run_ssh(ssh_target(name, ip), STATUS_CMD, timeout=45)
        if code != 0:
            return name, "unreachable (%s)" % out.strip().splitlines()[-1][:60]
        fields = dict(line.split("=", 1) for line in out.strip().splitlines() if "=" in line)
        return name, fields

    print("%-14s %-6s %-22s %-16s %-16s %s" %
          ("device", "rdr", "node / build / mode", "wifi", "cable", "disk/temp/uptime"))
    print("-" * 110)
    with ThreadPoolExecutor(max_workers=16) as pool:
        for name, info in pool.map(one, devices):
            if isinstance(info, str):
                print("%-14s %s" % (name, info))
                continue
            print("%-14s %-6s %-22s %-16s %-16s %s / %s / %ss" % (
                name, info.get("reader", "?"), info.get("node", "?"),
                info.get("wifi") or "-", info.get("cable") or "-",
                info.get("disk", "?"), info.get("temp", "?"), info.get("uptime", "?")))
    return 0


def cmd_run(args):
    devices = [d for d in tailscale_devices() if d[1]]
    if args.only:
        devices = [d for d in devices if d[0] in args.only]
    if SUDO_PASS:
        prefix = "printf '%s\\n' %s | sudo -S " % ("%s", json.dumps(SUDO_PASS))
    else:
        prefix = ""
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = pool.map(
            lambda d: (d[0], run_ssh(ssh_target(*d), prefix + args.command, timeout=args.timeout)),
            devices)
        for name, (code, out) in results:
            print("=== %s (exit %d) ===" % (name, code))
            print(out.strip() or "(no output)")
    return 0


def cmd_push(args):
    image = os.path.abspath(args.image)
    if not os.path.isfile(image):
        raise SystemExit("image not found: " + image)
    devices = [d for d in tailscale_devices() if d[1]]
    for name, ip in devices:
        target = "%s:%s" % (ssh_target(name, ip), "/home/eora/eora/%s" % os.path.basename(image))
        proc = subprocess.run(["scp", "-o", "StrictHostKeyChecking=no",
                               "-o", "UserKnownHostsFile=" + KNOWN_HOSTS, "-o", "BatchMode=yes",
                               "-i", KEY, image, target], capture_output=True, text=True)
        print("%-14s %s" % (name, "pushed" if proc.returncode == 0 else proc.stderr.strip()[:80]))
    return 0


HELPER_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gateway_probe")


def _ensure_helper(target, name):
    """Copy a helper script to the device when it is not there yet.

    A stock Pi image only has the reader; the flasher and the serial probe are ours. Making
    the update fail on their absence turned a one-command job into a debugging session.
    """
    present = run_ssh(target, "test -f ~/eora/%s && echo yes" % name, timeout=30)
    if "yes" in (present[1] or ""):
        return None
    local = os.path.join(HELPER_DIR, name)
    if not os.path.isfile(local):
        return "missing locally: " + local
    pushed = subprocess.run(
        ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
         "-o", "BatchMode=yes", "-i", KEY, local, "%s:/home/eora/eora/%s" % (target, name)],
        capture_output=True, text=True)
    if pushed.returncode != 0:
        return "push %s failed: %s" % (name, (pushed.stderr or "").strip()[:120])
    return None


def _ensure_esptool(target):
    """Install esptool on the device when it is absent, and say so only if that fails."""
    probe = run_ssh(target, "python3 -c 'import esptool' 2>/dev/null && echo yes", timeout=40)
    if "yes" in (probe[1] or ""):
        return None
    print("  %-14s installing esptool (one time, ~30 s)" % target.split("@")[0])
    run_ssh(target, "python3 -m pip install --user --break-system-packages --quiet esptool 2>&1 | tail -n 3",
            timeout=600)
    again = run_ssh(target, "python3 -c 'import esptool;print(esptool.__version__)'", timeout=40)
    if again[0] != 0:
        return "esptool install failed: " + (again[1] or "").strip()[:150]
    return None


def cmd_update(args):
    image = os.path.abspath(args.image)
    if not os.path.isfile(image):
        raise SystemExit("image not found: " + image)
    if not SUDO_PASS:
        raise SystemExit("set EORA_PASS to the device sudo password for unattended updates")
    devices = [d for d in tailscale_devices() if d[1]]
    if args.only:
        devices = [d for d in devices if d[0] in args.only]
    if not devices:
        raise SystemExit("no eora-air-* devices online; check `tailscale status`")
    base = os.path.basename(image)
    remote = "/home/eora/eora/%s" % base

    def one(item):
        name, ip = item
        target = ssh_target(name, ip)
        # Self-heal first: a missing helper or a missing esptool used to surface as an empty
        # "flash FAILED:" and cost an afternoon.
        for helper in ("node_update.py", "pi_node_probe.py"):
            err = _ensure_helper(target, helper)
            if err:
                return name, 1, err
        err = _ensure_esptool(target)
        if err:
            return name, 1, err
        pushed = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
             "-o", "BatchMode=yes", "-i", KEY, image, "%s:%s" % (target, remote)],
            capture_output=True, text=True)
        if pushed.returncode != 0:
            return name, 1, "push failed: " + (pushed.stderr or "").strip()[:100]
        code, out = run_ssh(target,
                            "EORA_SUDO_PASS=%s python3 ~/eora/node_update.py %s"
                            % (json.dumps(SUDO_PASS), remote), timeout=args.timeout)
        lines = [line for line in (out or "").strip().splitlines() if line.strip()]
        # VERIFIED is the authority: the flash already happened and was proven by reading the
        # node's build id. A dropped ssh session after that is not a failed update.
        if any("VERIFIED" in line for line in lines):
            code = 0
        if code == 0:
            note = next((l for l in lines if "VERIFIED" in l or "MISMATCH" in l),
                        lines[-1][:120] if lines else "ok")
            return name, code, note
        # On failure the useful part is the block after the headline, not the headline.
        detail = " | ".join(lines[-6:]) if lines else "no output"
        return name, code, detail

    with ThreadPoolExecutor(max_workers=8) as pool:
        for name, code, note in pool.map(one, devices):
            print("%-14s %-3s %s" % (name, "OK" if code == 0 else "ERR", note))
    return 0


def cmd_logs(args):
    devices = dict(tailscale_devices())
    ip = devices.get(args.device)
    if not ip:
        raise SystemExit("unknown or offline device: " + args.device)
    code, out = run_ssh(ssh_target(args.device, ip),
                        "tail -%d ~/eora/logs/node_events.jsonl" % args.lines)
    print(out)
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="fleet overview").set_defaults(func=cmd_status)

    p_run = sub.add_parser("run", help="run a command on every device")
    p_run.add_argument("command")
    p_run.add_argument("--only", nargs="*")
    p_run.add_argument("--timeout", type=int, default=120)
    p_run.set_defaults(func=cmd_run)

    p_push = sub.add_parser("push", help="copy a firmware image to every device")
    p_push.add_argument("image")
    p_push.set_defaults(func=cmd_push)

    p_upd = sub.add_parser("update", help="flash every node from an image")
    p_upd.add_argument("image")
    p_upd.add_argument("--only", nargs="*")
    p_upd.add_argument("--timeout", type=int, default=300)
    p_upd.set_defaults(func=cmd_update)

    p_logs = sub.add_parser("logs", help="tail one device's node events")
    p_logs.add_argument("device")
    p_logs.add_argument("--lines", type=int, default=20)
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
