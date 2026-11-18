"""Bake one Raspberry Pi's identity into an SD card's boot partition.

The slow way is: flash the card, plug an Ethernet cable into this PC, run three scripts per
device, then remember which number it got. For forty units that is not a workflow, it is a
weekend. Instead each card carries its own identity and configures itself on first boot:

    write image with Raspberry Pi Imager (user eora, SSH on, your public key)
    python mkcard.py --card E: --number 7
    insert the card and power the Pi -> it appears as eora-air-07 in the tailnet

Nothing has to be plugged into this PC, and no step depends on knowing an IP address.

Secrets are never stored in the repository: they come from a local env file
(``.local/mid/pi/device.env``, git-ignored) with WIFI_SSID / WIFI_IDENTITY / WIFI_PASSWORD
and TAILSCALE_AUTHKEY.
"""
import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HELPERS = Path(__file__).resolve().parent.parent / "gateway_probe"
ENV_FILE = ROOT / ".local" / "mid" / "pi" / "device.env"
MARKER_BEGIN = "# >>> eora identity >>>"
MARKER_END = "# <<< eora identity <<<"

# Helpers pushed to the device at first boot so nothing has to be copied by hand later.
DEPLOY = ("node_reader.py", "node_update.py", "pi_node_probe.py")


def say(msg=""):
    print(msg, flush=True)


def load_env():
    data = {}
    if ENV_FILE.is_file():
        # utf-8-sig: PowerShell and Notepad write a BOM, which would otherwise become
        # part of the first key name and silently look like a missing setting.
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def find_boot(card):
    """Return the boot-partition path for a drive letter such as ``E:``."""
    for candidate in (Path(card + os.sep), Path(card)):
        if candidate.is_dir() and (candidate / "firstrun.sh").exists():
            return candidate
    for candidate in (Path(card + os.sep), Path(card)):
        if candidate.is_dir():
            return candidate
    return None


def read_text_keep_newline(path):
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def compose_identity(number, env, helpers):
    host = "eora-air-%02d" % number
    ssid = env.get("WIFI_SSID", "")
    identity = env.get("WIFI_IDENTITY", "")
    password = env.get("WIFI_PASSWORD", "")
    authkey = env.get("TAILSCALE_AUTHKEY", "")

    blobs = []
    for name, content in helpers.items():
        blobs.append("printf '%%s' '%s' | base64 -d > /usr/local/lib/eora/%s"
                     % (base64.b64encode(content.encode("utf-8")).decode(), name))

    lines = [
        MARKER_BEGIN,
        "# Identity for this card. Written by mkcard.py; re-running replaces this block.",
        "EORA_HOST=%s" % host,
        "EORA_NUMBER=%d" % number,
        "EORA_SSID=%s" % shlex_quote(ssid),
        "EORA_IDENTITY=%s" % shlex_quote(identity),
        "EORA_WIFI_PASS=%s" % shlex_quote(password),
        "EORA_AUTHKEY=%s" % shlex_quote(authkey),
        "mkdir -p /usr/local/lib/eora",
        *blobs,
        'cat > /usr/local/sbin/eora-firstboot.sh <<\'EORA_FB\'',
        FIRSTBOOT_TEMPLATE.strip(),
        "EORA_FB",
        "chmod +x /usr/local/sbin/eora-firstboot.sh",
        'cat > /etc/systemd/system/eora-firstboot.service <<\'EORA_UNIT\'',
        "[Unit]",
        "Description=EoRa first-boot identity (hostname, Wi-Fi, tailnet, node reader)",
        "After=network-online.target cloud-init.service cloud-final.service",
        "Wants=network-online.target",
        "ConditionPathExists=/usr/local/sbin/eora-firstboot.sh",
        "",
        "[Service]",
        "Type=oneshot",
        "ExecStart=/usr/local/sbin/eora-firstboot.sh",
        "RemainAfterExit=yes",
        "TimeoutStartSec=15min",
        "",
        "[Install]",
        "WantedBy=multi-user.target",
        "EORA_UNIT",
        "systemctl enable eora-firstboot.service",
        # One shot only. Leaving the hook in place would make every boot enter
        # kernel-command-line.target and reboot again: an endless loop. Raspberry Pi's own
        # firstrun removes its hook for exactly this reason.
        "if [ -f /boot/firmware/cmdline.txt ]; then",
        "  cp /boot/firmware/cmdline.txt /boot/firmware/cmdline.txt.eora-backup",
        "  sed -i 's/ *systemd\\.run=[^ ]*//g;"
        " s/ *systemd\\.run_success_action=[^ ]*//g;"
        " s/ *systemd\\.unit=kernel-command-line\\.target//g'"
        " /boot/firmware/cmdline.txt",
        "fi",
        'echo "cmdline hook removed; eora-firstboot.service will run on the next boot"',
        MARKER_END,
    ]
    return "\n".join(lines) + "\n"


def shlex_quote(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


# Runs on the Pi. Idempotent, and disables itself once everything succeeded so a normal boot
# costs nothing.
FIRSTBOOT_TEMPLATE = r"""
#!/bin/bash
# Configure this device once, from what the card already knows.
set -u
HOST="$EORA_HOST"; NUMBER="$EORA_NUMBER"
SSID="$EORA_SSID"; IDENTITY="$EORA_IDENTITY"; PASS="$EORA_WIFI_PASS"; AUTHKEY="$EORA_AUTHKEY"
# Log to the FAT boot partition: putting the card back in the PC is then enough to read
# what happened, which matters when forty devices have to be diagnosed without cables.
LOG=/boot/firmware/eora-firstboot.log
[ -d /boot/firmware ] && touch "$LOG" 2>/dev/null || LOG=/var/log/eora-firstboot.log

exec >>"$LOG" 2>&1
echo "== $(date -Is) firstboot start for $HOST"
STATUS=/boot/firmware/eora-status.txt
mark(){ echo "== $*" >> "$LOG"; echo "$(date -Is) $*" > "$STATUS" 2>/dev/null; }
mark "1/5 start host=$HOST"

if [ "$(hostname)" != "$HOST" ]; then
  hostnamectl set-hostname "$HOST"
  sed -i "/^127\.0\.1\.1/d" /etc/hosts
  echo "127.0.1.1	$HOST" >>/etc/hosts
fi

# Campus IPv6 is often unrouted while DNS still prefers AAAA: prefer IPv4 explicitly.
grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null || \
  echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

# 802.1X cannot be expressed by Raspberry Pi Imager, so it is created here.
# cloud-init creates the user; on a cold card this can still be in progress.
for i in $(seq 1 120); do id eora >/dev/null 2>&1 && break; sleep 5; done
if ! id eora >/dev/null 2>&1; then
  mark "FAILED: user eora missing after 10 min"
  exit 1
fi

if [ -n "$SSID" ] && [ -n "$IDENTITY" ] && [ -n "$PASS" ]; then
  # Raspberry Pi Imager writes a plain-password profile even for an 802.1X network, where
  # it can never authenticate. Two profiles for the same SSID then fight over the radio.
  for name in $(nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '"$2=="802-11-wireless"{print $1}"'); do
    [ "$name" = "wifi-$SSID" ] && continue
    [ "$(nmcli -g 802-11-wireless.ssid connection show "$name" 2>/dev/null)" = "$SSID" ] && \
      nmcli connection delete "$name" >/dev/null 2>&1 && echo "removed plain profile: $name"
  done
  nmcli --terse --fields NAME connection show 2>/dev/null | grep -qx "wifi-$SSID" || {
    nmcli connection add type wifi con-name "wifi-$SSID" ifname wlan0 ssid "$SSID" \
      wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
      802-1x.identity "$IDENTITY" 802-1x.password "$PASS" \
      ipv4.method auto ipv4.route-metric 100 \
      connection.autoconnect yes connection.autoconnect-priority 20 2>/dev/null
  }
  nmcli connection up "wifi-$SSID" >/dev/null 2>&1
fi

# Wait for a usable address before anything that needs the network.
for i in $(seq 1 60); do
  if ip -4 route get 1.1.1.1 >/dev/null 2>&1; then break; fi
  sleep 5
done

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh || true
fi
if command -v tailscale >/dev/null 2>&1 && [ -n "$AUTHKEY" ]; then
  tailscale up --auth-key="$AUTHKEY" --hostname="$HOST" --accept-dns=false || true
fi

python3 -m pip install --user --break-system-packages --quiet pyserial esptool 2>/dev/null || true

install -d -o eora -g eora /home/eora/eora /home/eora/eora/logs
for f in node_reader.py node_update.py pi_node_probe.py; do
  [ -f "/usr/local/lib/eora/$f" ] && install -o eora -g eora "/usr/local/lib/eora/$f" "/home/eora/eora/$f"
done
[ -f /usr/local/lib/eora/eora-node-reader.service ] && \
  install -m 644 /usr/local/lib/eora/eora-node-reader.service /etc/systemd/system/node_reader.service
systemctl daemon-reload
systemctl enable --now node_reader.service 2>/dev/null || true

# Success criteria: we have a tailnet address and the reader is running.
if tailscale ip -4 >/dev/null 2>&1 && systemctl is-active --quiet node_reader; then
  systemctl disable eora-firstboot.service >/dev/null 2>&1
  mark "5/5 done, firstboot disabled"
else
  mark "5/5 INCOMPLETE, will retry on next boot"
fi
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", help="boot-partition drive letter, e.g. E:")
    parser.add_argument("--number", type=int, help="node number for this card")
    parser.add_argument("--list", action="store_true", help="show which cards look prepared")
    parser.add_argument("--check", action="store_true", help="only verify environment")
    args = parser.parse_args()

    env = load_env()
    missing = [k for k in ("WIFI_SSID", "WIFI_IDENTITY", "WIFI_PASSWORD", "TAILSCALE_AUTHKEY")
               if not env.get(k)]
    say("== secrets file: %s" % ENV_FILE)
    if missing:
        say("   MISSING: %s" % ", ".join(missing))
        say("   Create it with those keys (it is git-ignored):")
        say("     WIFI_SSID=Tsinghua-Secure")
        say("     WIFI_IDENTITY=<account>")
        say("     WIFI_PASSWORD=<password>")
        say("     TAILSCALE_AUTHKEY=tskey-auth-...")
        if args.check:
            return 2
    else:
        say("   all four keys present")

    if args.list:
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            boot = find_boot(letter + ":")
            if boot and (boot / "firstrun.sh").exists():
                text = read_text_keep_newline(boot / "firstrun.sh")
                m = re.search(r"EORA_HOST=(\S+)", text)
                say("  %s: %s" % (letter + ":", m.group(1) if m else "(not prepared)"))
        return 0

    if args.check:
        return 0 if not missing else 2
    if not args.card or args.number is None:
        parser.error("--card and --number are required unless --list/--check")
    if missing:
        return 2
    if not (1 <= args.number <= 255):
        parser.error("--number must be 1..255 (it travels in one frame byte)")

    boot = find_boot(args.card)
    if not boot:
        say("   FAILED: %s is not a mounted card" % args.card)
        return 2
    firstrun = boot / "firstrun.sh"
    if firstrun.exists():
        say("== appending to existing firstrun.sh (Raspberry Pi Imager's own setup stays intact)")
    else:
        say("== no firstrun.sh found; creating one")

    # The cmdline hook is checked on every run, not only when firstrun.sh was missing:
    # a card that already has the script (for example from an earlier attempt) must still
    # get the hook, otherwise the script is never executed and the card looks inert.
    cmdline = boot / "cmdline.txt"
    if not cmdline.exists():
        say("   FAILED: %s has no cmdline.txt (is this the boot partition?)" % boot)
        return 2
    # systemd only acts on systemd.run= when kernel-command-line.target is also pulled in.
    # Without the third parameter the script silently never executes.
    hook = (" systemd.run=/boot/firmware/firstrun.sh"
            " systemd.run_success_action=reboot"
            " systemd.unit=kernel-command-line.target")
    line = cmdline.read_text(encoding="utf-8-sig", errors="replace").strip()
    line = line.lstrip("\ufeff")   # a BOM here becomes garbage in the kernel cmdline
    if "systemd.run=" not in line:
        cmdline.write_text(line + hook + "\n", encoding="utf-8")
        say("   cmdline.txt: systemd.run hook added")
    elif "kernel-command-line.target" not in line:
        cmdline.write_text(line + " systemd.unit=kernel-command-line.target\n", encoding="utf-8")
        say("   cmdline.txt: added missing kernel-command-line.target")
    else:
        say("   cmdline.txt: hook already complete")

    helpers = {}
    for name in DEPLOY:
        path = HELPERS / name
        if path.is_file():
            helpers[name] = path.read_text(encoding="utf-8")
    service = HELPERS / "node_reader.service"
    if service.is_file():
        helpers["eora-node-reader.service"] = service.read_text(encoding="utf-8")

    block = compose_identity(args.number, env, helpers)
    current = read_text_keep_newline(firstrun)
    current = re.sub(re.escape(MARKER_BEGIN) + r".*?" + re.escape(MARKER_END) + r"\n?",
                     "", current, flags=re.S)
    new = current.rstrip("\n") + "\n\n" + block
    # The boot partition is read by Linux: CRLF would break the shebang.
    firstrun.write_bytes(new.replace("\r\n", "\n").encode("utf-8"))

    say("== wrote identity")
    say("   card     : %s" % boot)
    say("   hostname : eora-air-%02d" % args.number)
    say("   number   : %d" % args.number)
    say("   helpers  : %s" % ", ".join(sorted(helpers)))
    say("   size     : %d bytes" % firstrun.stat().st_size)
    say("")
    say("Next: insert the card into the Pi and power it on. It configures itself and")
    say("appears in the tailnet as eora-air-%02d. No cable to this PC needed." % args.number)
    return 0


if __name__ == "__main__":
    sys.exit(main())
