"""Switch the field nodes between the ESP-NOW and the 2.4 GHz LoRa link layer.

One command does the whole sequence so the radio settings and the persisted
link_mode can never drift apart:

  lora24 : link radio at 2.4 GHz in link role, then link_mode=lora24 + reboot
  espnow : uplink settings back to 470.5 MHz tx, then link_mode=espnow + reboot

Both paths verify afterwards by reading the node back over serial.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

PROFILES = {
    "espnow": {
        "lora": ["--freq", "470500000", "--sf", "7", "--bw", "125000",
                 "--power", "15", "--role", "tx"],
        "expect": {"frequency_hz": 470500000, "role": "tx"},
    },
    "lora24": {
        "lora": ["--freq", "2404000000", "--sf", "7", "--bw", "406000",
                 "--power", "13", "--role", "link"],
        "expect": {"frequency_hz": 2404000000, "role": "link"},
    },
}


def run(args):
    print("  $ python " + " ".join(args))
    r = subprocess.run([sys.executable, "-X", "utf8"] + args, cwd=str(ROOT))
    if r.returncode != 0:
        print("  !! 上一步失败（exit %d）" % r.returncode)
    return r.returncode


def online_devices():
    """Names of nodes currently reachable over Tailscale (offline ones would stall)."""
    try:
        r = subprocess.run([sys.executable, "-X", "utf8",
                            str(HERE / "fleet.py"), "status"],
                           cwd=str(ROOT), capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return []
    names = []
    for line in (r.stdout or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "active" and parts[0].startswith("eora-air-"):
            names.append(parts[0])
    return names


def main():
    ap = argparse.ArgumentParser(description="在 espnow 与 lora24 之间切换节点链路层")
    ap.add_argument("mode", choices=["espnow", "lora24", "toggle", "status"],
                    help="目标链路层；toggle 切到当前模式的另一侧；status 只读不写")
    ap.add_argument("only", nargs="*", help="设备名，省略则作用于全部在线节点")
    ap.add_argument("--no-reboot", action="store_true", help="写入后不重启（下次上电生效）")
    a = ap.parse_args()

    only = []
    targets = a.only or online_devices()
    if not targets:
        print("!! 没有可达的节点；用 SWITCH_LINK.cmd status 先确认在线状态")
        return 1
    print("== 目标节点: " + " ".join(targets))
    for name in targets:
        only += ["--only", name]

    node_config = str(HERE / "node_config.py")
    set_link = str(HERE / "set_link_mode.py")

    if a.mode == "status":
        run([node_config, "read"] + only)
        run([set_link, "--read"] + only)
        return 0

    # toggle: read what is stored now, then aim at the other side.
    if a.mode == "toggle":
        r = subprocess.run([sys.executable, "-X", "utf8", set_link, "--read"] + only,
                           cwd=str(ROOT), capture_output=True, text=True)
        text = (r.stdout or "") + (r.stderr or "")
        current = "lora24" if "stored=lora24" in text else "espnow"
        a.mode = "espnow" if current == "lora24" else "lora24"
        print("== 当前 %s -> 切换到 %s" % (current, a.mode))

    p = PROFILES[a.mode]
    print("== 切换到 %s" % a.mode)
    print("-- 1/3 写入射频参数")
    run([node_config, "lora"] + p["lora"] + only)

    print("-- 2/3 写入 link_mode")
    mode_args = [set_link, "--mode", a.mode] + only
    if not a.no_reboot:
        mode_args.append("--reboot")
    run(mode_args)

    if not a.no_reboot:
        print("-- 3/3 等待重启（35 s）")
        time.sleep(35)
        print("-- 读回校验")
        run([node_config, "read"] + only)

    print("== 完成。期望值：频率 %d、role=%s、link_mode=%s"
          % (p["expect"]["frequency_hz"], p["expect"]["role"], a.mode))
    print("   上行链路请用网关确认：python tools\\mid_baseline\\fleet\\sample_node.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
