"""Rebuild the display-label table from what the devices themselves report.

The LoRa topology frame (LRN1) carries no name field, so the viewer needs a MAC -> name
table. Keeping that table hand-written means it drifts every time the naming scheme changes
(letters to numbers, re-flashed boards, swapped hardware). This reads each device's own
`device_label` / `node_number` out of its node_reader log and rewrites the table.

    python refresh_labels.py --field device_label     # A, B, C  (what the firmware displays)
    python refresh_labels.py --field node_number      # 1, 2, 3  (factory node number)

Existing entries for devices that were not reachable are preserved, and gateway names from
the served topology are merged back in, so a partial run never loses the other half.
"""
import argparse
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

DEFAULT_OUT = os.path.join(".local", "mid", "pi", "labels.json")
DEFAULT_FLEET = os.path.join("data", "fleet.json")
TOPOLOGY_URL = "http://127.0.0.1:8780/api/v1/lora/topology"


def devices():
    out = subprocess.run([TAILSCALE, "status", "--json"], capture_output=True, text=True)
    data = json.loads(out.stdout or "{}")
    found = []
    for peer in (data.get("Peer") or {}).values():
        name = (peer.get("HostName") or "").strip()
        if not name.startswith(NAME_PREFIX) or not peer.get("Online"):
            continue
        ips = peer.get("TailscaleIPs") or []
        ip = next((x for x in ips if ":" not in x), None)
        if ip:
            found.append((name, ip))
    return sorted(found)


def last_session(ip):
    cmd = ("grep -a -h '\"session\":\"open\"' ~/eora/logs/node_events.jsonl 2>/dev/null | tail -1")
    proc = subprocess.run(
        ["ssh", "-T", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=" + KNOWN_HOSTS,
         "-o", "BatchMode=yes", "-i", KEY, "-o", "ConnectTimeout=12",
         "%s@%s" % (SSH_USER, ip), cmd],
        capture_output=True, text=True, timeout=45)
    line = (proc.stdout or "").strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", choices=("device_label", "node_number"), default="device_label")
    parser.add_argument("--out", default=DEFAULT_OUT)
    # The Studio needs a MAC -> node_id roster. Writing it from the same device reads keeps
    # one source of truth: nothing is declared that was not actually heard.
    parser.add_argument("--fleet", default=DEFAULT_FLEET,
                        help="also write the Studio roster here (empty when nothing is online)")
    args = parser.parse_args()

    labels = {}
    if os.path.exists(args.out):
        try:
            labels = json.load(open(args.out, encoding="utf-8"))
        except ValueError:
            labels = {}

    try:
        import urllib.request
        topo = json.load(urllib.request.urlopen(TOPOLOGY_URL, timeout=5))
        for mac, name in (topo.get("labels") or {}).items():
            labels.setdefault(mac, name)
        gw = (topo.get("receiver") or {}).get("gateway_id")
        if gw:
            labels[gw] = (topo.get("labels") or {}).get(gw, labels.get(gw, gw))
    except Exception:
        pass

    found = devices()
    if not found:
        print("no %s* devices online" % NAME_PREFIX)

    def one(item):
        name, ip = item
        rec = last_session(ip)
        if not rec or not rec.get("node_id"):
            return name, None, None
        value = rec.get(args.field)
        number = rec.get("node_number")
        if value is None:
            return name, None, number
        return rec["node_id"].lower(), str(value), number

    nodes = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for key, value, number in pool.map(one, found):
            if value:
                labels[key] = value
                print("  %-18s -> %s" % (key, value))
            else:
                print("  %-18s -> (no %s in log yet)" % (key, args.field))
            if key and type(number) is int and number > 0:
                nodes.append({"node_id": number, "mac": key})

    tmp = args.out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(labels, fh, indent=2, ensure_ascii=False, sort_keys=True)
    os.replace(tmp, args.out)
    print("\nwrote %d labels to %s" % (len(labels), args.out))

    if args.fleet:
        roster = {"schema_version": 1, "nodes": sorted(nodes, key=lambda n: n["node_id"])}
        os.makedirs(os.path.dirname(args.fleet) or ".", exist_ok=True)
        tmp = args.fleet + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(roster, fh, indent=2)
        os.replace(tmp, args.fleet)
        print("wrote %d node(s) to %s" % (len(nodes), args.fleet))
        if not nodes:
            print("  (empty roster: nothing is declared until a device actually reports)")

    print("\nrestart these to pick the changes up:")
    print("  python -m tools.mid_baseline.gateway_probe.topology_server --udp-port 1680 "
          "--port 8780 --labels %s" % args.out)
    print("  (or just re-run START_STUDIO.cmd)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
