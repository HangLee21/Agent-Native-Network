"""Select the node link-layer radio at runtime and persist it on the node.

The board is flashed once; this script chooses which link backend it should use next
boot. The choice is stored in the node's NVS, so it survives reboots and does not need
a reflash.

    python tools\\mid_baseline\\fleet\\set_link_mode.py --read
    python tools\\mid_baseline\\fleet\\set_link_mode.py --mode lora24
    python tools\\mid_baseline\\fleet\\set_link_mode.py --mode espnow --only eora-air-01

Modes:
    espnow  ESP32 Wi-Fi / ESP-NOW for the mesh (current default, implemented)
    lora24  LR1121 2.4 GHz LoRa for the mesh (stored now, backend not implemented; the
            node reports link_mode_pending until it is)

Node access goes over SSH to the Pi, which owns the serial port; node_reader is stopped
for the command and restarted afterwards so the service keeps working.
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
payload = json.loads(sys.argv[1])
n = Node(ports[0])
try:
    time.sleep(5)
    reply = n.ask("link_mode", timeout=8, extra=payload)
    info = n.ask("info", timeout=8)
finally:
    n.close()
print(json.dumps({"reply": reply, "info": {k: info.get(k) for k in
      ("link_mode","link_mode_active","link_mode_pending","node_number")}}, ensure_ascii=False))
'''


def parse_args(argv):
    mode, read, hosts, reboot = None, False, [], False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode":
            mode = argv[i + 1]; i += 2
        elif a == "--read":
            read = True; i += 1
        elif a == "--reboot":
            reboot = True; i += 1
        elif a == "--only":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                hosts.append(argv[i]); i += 1
        else:
            raise SystemExit("unknown argument: " + a)
    return mode, read, hosts, reboot


def main():
    mode, read, hosts, reboot = parse_args(sys.argv[1:])
    if not read and mode not in ("espnow", "lora24"):
        raise SystemExit("--mode must be espnow or lora24 (or use --read)")
    if not hosts:
        hosts = ["eora-air-01", "eora-air-02", "eora-air-03", "eora-air-04", "eora-air-05"]

    payload = {} if read else {"mode": mode}
    pw = fleet.sudo_password()
    if not pw:
        raise SystemExit("no cached sudo password (.local/mid/pi/sudo_pass.txt)")
    q = json.dumps(pw)
    b64 = base64.b64encode(HELPER.encode("utf-8")).decode()

    print("targets:", ", ".join(hosts))
    for host in hosts:
        target = fleet.ssh_target(host, None)
        remote = "/tmp/eora-link-mode.py"
        fleet.run_ssh(target, "echo '%s' | base64 -d > %s" % (b64, remote), timeout=60)
        fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S systemctl stop node_reader" % q, timeout=60)
        try:
            code, out = fleet.run_ssh(
                target,
                "cd ~/eora && PYTHONPATH=$HOME/eora python3 %s '%s'"
                % (remote, json.dumps(payload).replace("'", "'\\''")),
                timeout=90)
        finally:
            fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S systemctl start node_reader" % q, timeout=60)
        line = next((l for l in (out or "").splitlines() if l.startswith("{")), "")
        if not line:
            print("  %-13s FAILED: %s" % (host, (out or "").strip()[:100]))
            continue
        d = json.loads(line)
        rep, info = d.get("reply") or {}, d.get("info") or {}
        print("  %-13s ok=%s why=%s  stored=%s active=%s pending=%s"
              % (host, rep.get("ok"), rep.get("why"), info.get("link_mode"),
                 info.get("link_mode_active"), info.get("link_mode_pending")))
        if reboot and not read:
            fleet.run_ssh(target, "printf '%%s\\n' %s | sudo -S reboot" % q, timeout=30)
            print("  %-13s reboot requested" % host)

    if not read and mode == "lora24":
        print("\n注意：本固件只实现 espnow 后端。lora24 已写入 NVS 并标记 pending，")
        print("      实际仍以 espnow 运行；等 lora24 后端完成后同一设置会自动生效。")


if __name__ == "__main__":
    main()
