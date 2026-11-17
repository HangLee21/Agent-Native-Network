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


def ssh_target(name, ip):
    return "%s@%s" % (SSH_USER, ip or name)


def run_ssh(target, command, timeout=60, stdin_text=None):
    args = ["ssh", "-T", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
            "-o", "BatchMode=yes", "-i", KEY, "-o", "ConnectTimeout=15", target, command]
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
    'echo "node=$(tail -1 ~/eora/logs/node_events.jsonl 2>/dev/null | python3 -c '
    '"import sys,json;'
    'd=json.loads(sys.stdin.read() or \'{}\');'
    'print(d.get(\'node_id\',\'?\')+\' \'+(d.get(\'build_id\') or \'\')[-12:]+\' \'+d.get(\'mode\',\'?\'))" '
    '2>/dev/null)"'
)


def cmd_status(args):
    devices = tailscale_devices()
    if not devices:
        print("no %s* devices in the tailnet" % NAME_PREFIX)
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


def cmd_update(args):
    image = os.path.abspath(args.image)
    if not os.path.isfile(image):
        raise SystemExit("image not found: " + image)
    if not SUDO_PASS:
        raise SystemExit("set EORA_PASS to the device sudo password for unattended updates")
    devices = [d for d in tailscale_devices() if d[1]]
    if args.only:
        devices = [d for d in devices if d[0] in args.only]
    base = os.path.basename(image)
    remote = "/home/eora/eora/%s" % base

    def one(item):
        name, ip = item
        target = ssh_target(name, ip)
        pushed = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
             "-o", "BatchMode=yes", "-i", KEY, image, "%s:%s" % (target, remote)],
            capture_output=True, text=True)
        if pushed.returncode != 0:
            return name, 1, "push failed: " + pushed.stderr.strip()[:100]
        code, out = run_ssh(target,
                            "EORA_SUDO_PASS=%s python3 ~/eora/node_update.py %s"
                            % (json.dumps(SUDO_PASS), remote), timeout=args.timeout)
        tail = [line for line in out.strip().splitlines() if "VERIFIED" in line
                or "MISMATCH" in line or "FAILED" in line or "rollback" in line.lower()]
        return name, code, (tail[-1] if tail else out.strip().splitlines()[-1][:100])

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
