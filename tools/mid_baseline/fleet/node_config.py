"""Read and set per-node radio parameters from the Pi, without reflashing.

Everything here is stored on the node (NVS for link mode, lr_ref blob for the LoRa
uplink), so a board is flashed once and then tuned from this script.

    python tools\\mid_baseline\\fleet\\node_config.py read
    python tools\\mid_baseline\\fleet\\node_config.py read --only eora-air-01

    python tools\\mid_baseline\\fleet\\node_config.py link --mode lora24 [--reboot]
    python tools\\mid_baseline\\fleet\\node_config.py lora --sf 8 --bw 125000 --power 14
    python tools\\mid_baseline\\fleet\\node_config.py lora --freq 470500000 --period 10000 --role tx

Options for `lora` (only what you pass is changed):
    --freq HZ        frequency_hz,   410000000..493000000 (sub-GHz) or 2400000000..2500000000 (2.4G)
    --sf N           7..12
    --bw HZ          125000|250000|500000 (sub-GHz) or 203000|406000|812000 (2.4G)
    --cr N           5..8   (coding rate 4/N)
    --power DBM      -17..22 sub-GHz, -18..13 at 2.4G
    --role R         off|rx|tx
    --period MS      report period, must stay above time-on-air + 100 ms + jitter
    --jitter MS
    --preamble N     8..64
    --sync N         18 (private) | 52 (public)

The node validates the combination and replies with `why` when it refuses, so an
out-of-range change fails loudly instead of silently applying.
"""
import base64
import json
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\tools\mid_baseline\fleet")
import fleet  # noqa: E402

HELPER = '''
import json, sys, time
from pi_node_probe import Node, candidate_ports
ports = candidate_ports()
if not ports:
    print("NO_PORT"); raise SystemExit(1)
jobs = json.loads(sys.argv[1])          # [{"cmd": "...", "args": {...}}, ...]
n = Node(ports[0])
out = []
try:
    time.sleep(5)
    for job in jobs:
        reply = n.ask(job["cmd"], timeout=8, extra=job.get("args") or {})
        out.append({"cmd": job["cmd"], "ok": reply.get("ok"), "why": reply.get("why")})
    info = n.ask("info", timeout=8)
    st = n.ask("lora_ref_status", timeout=8)
finally:
    n.close()
print(json.dumps({"replies": out, "info": info, "lora": st}, ensure_ascii=False))
'''

LORA_KEYS = [
    ("frequency_hz", "--freq", int),
    ("sf", "--sf", int),
    ("bandwidth_hz", "--bw", int),
    ("coding_rate", "--cr", int),
    ("tx_power_dbm", "--power", int),
    ("report_period_ms", "--period", int),
    ("jitter_ms", "--jitter", int),
    ("preamble_symbols", "--preamble", int),
    ("sync_word", "--sync", int),
    ("role", "--role", str),
]
INFO_KEYS = ["node_number", "link_mode", "link_mode_active", "link_mode_pending"]
STATUS_KEYS = ["frequency_hz", "sf", "bandwidth_hz", "coding_rate", "tx_power_dbm",
               "report_period_ms", "lora_ref_requested_role", "lora_ref_worker_state",
               "max_frame_toa_ms", "rx_rssi", "rx_snr"]


def parse(argv):
    if not argv:
        raise SystemExit(__doc__)
    action, rest = argv[0], argv[1:]
    opts = {}
    hosts = []
    reboot = False
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--only":
            i += 1
            while i < len(rest) and not rest[i].startswith("--"):
                hosts.append(rest[i]); i += 1
        elif a == "--reboot":
            reboot = True; i += 1
        elif a in ("--mode",) + tuple(k for _, k, _ in LORA_KEYS):
            opts[a] = rest[i + 1]; i += 2
        else:
            raise SystemExit("unknown argument: " + a)
    return action, opts, hosts, reboot


def build_jobs(action, opts):
    if action == "read":
        return []
    if action == "link":
        mode = opts.get("--mode")
        if mode not in ("espnow", "lora24"):
            raise SystemExit("--mode must be espnow or lora24")
        return [{"cmd": "link_mode", "args": {"mode": mode}}]
    if action == "lora":
        args = {}
        for field, flag, cast in LORA_KEYS:
            if flag in opts:
                args[field] = opts[flag] if cast is str else cast(opts[flag])
        if not args:
            raise SystemExit("nothing to set; pass at least one --sf/--bw/--freq/...")
        return [{"cmd": "lora_ref_config", "args": args}]
    raise SystemExit("unknown action: " + action)


def show(host, data, action):
    reps = data.get("replies") or []
    info = data.get("info") or {}
    lora = data.get("lora") or {}
    for r in reps:
        if not r.get("ok"):
            print("  %-13s %-16s REFUSED why=%s" % (host, r.get("cmd"), r.get("why")))
            return
    if action == "link":
        print("  %-13s stored=%-7s active=%-7s pending=%s"
              % (host, info.get("link_mode"), info.get("link_mode_active"), info.get("link_mode_pending")))
        return
    print("  %-13s #%s  link=%s(%s)  %s Hz SF%s BW%s CR4/%s %sdBm role=%s  period=%sms  ToA=%sms  rx=%s/%s"
          % (host, info.get("node_number"), info.get("link_mode"), info.get("link_mode_active"),
             lora.get("frequency_hz"), lora.get("sf"), lora.get("bandwidth_hz"),
             lora.get("coding_rate"), lora.get("tx_power_dbm"),
             lora.get("lora_ref_requested_role"), lora.get("report_period_ms"), lora.get("max_frame_toa_ms"),
             lora.get("rx_rssi"), lora.get("rx_snr")))


def main():
    action, opts, hosts, reboot = parse(sys.argv[1:])
    if not hosts:
        hosts = ["eora-air-01", "eora-air-02", "eora-air-03", "eora-air-04", "eora-air-05"]
    jobs = build_jobs(action, opts)

    pw = fleet.sudo_password()
    if not pw:
        raise SystemExit("no cached sudo password (.local/mid/pi/sudo_pass.txt)")
    q = json.dumps(pw)
    b64 = base64.b64encode(HELPER.encode("utf-8")).decode()

    for host in hosts:
        target = fleet.ssh_target(host, None)
        remote = "/tmp/eora-node-config.py"
        fleet.run_ssh(target, "echo '%s' | base64 -d > %s" % (b64, remote), timeout=60)
        fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S systemctl stop node_reader" % q, timeout=60)
        try:
            code, out = fleet.run_ssh(
                target,
                "cd ~/eora && PYTHONPATH=$HOME/eora python3 %s '%s'"
                % (remote, json.dumps(jobs).replace("'", "'\\''")),
                timeout=120)
        finally:
            fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S systemctl start node_reader" % q, timeout=60)
        line = next((l for l in (out or "").splitlines() if l.startswith("{")), "")
        if not line:
            print("  %-13s FAILED: %s" % (host, (out or "").strip()[:100]))
            continue
        show(host, json.loads(line), action)
        if reboot and action != "read":
            fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S reboot" % q, timeout=30)
            print("  %-13s reboot requested" % host)


if __name__ == "__main__":
    main()
