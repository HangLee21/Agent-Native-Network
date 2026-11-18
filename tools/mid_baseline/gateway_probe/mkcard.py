"""Bake one Raspberry Pi's identity into an SD card's boot partition.

The slow way is: flash the card, plug an Ethernet cable into this PC, run three scripts per
device, then remember which number it got. For forty units that is not a workflow.

This writes an installer into the boot partition and hooks it into **cloud-init's runcmd**,
which is the mechanism this image actually uses (its cmdline carries ``ds=nocloud``). An
earlier version hooked ``systemd.run=`` instead; on this image that silently never executed,
and adding ``systemd.unit=kernel-command-line.target`` additionally diverted the boot away
from multi-user, so the device looked completely dead.

    python mkcard.py --card E: --number 7
    insert the card and power the Pi -> it appears as eora-air-07 in the tailnet

Secrets come from ``.local/mid/pi/device.env`` (git-ignored), never from the repository.
Diagnostics land in the FAT boot partition, so putting the card back in this PC is enough.
"""
import argparse
import base64
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[3]
HELPERS = Path(__file__).resolve().parent.parent / "gateway_probe"
ENV_FILE = ROOT / ".local" / "mid" / "pi" / "device.env"
INSTALLER_NAME = "eora-firstboot.sh"
MARKER = "# >>> eora identity >>>"
RUNCMD_ARGS = "bash, /boot/firmware/" + INSTALLER_NAME
DEPLOY = ("node_reader.py", "node_update.py", "pi_node_probe.py")
SERVICE = "node_reader.service"


def say(msg=""):
    print(msg, flush=True)


def load_env():
    data = {}
    if ENV_FILE.is_file():
        # utf-8-sig: PowerShell and Notepad write a BOM, which would otherwise become part
        # of the first key and look like a missing setting.
        for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    return data


def find_boot(card):
    for suffix in (os.sep, ""):
        candidate = Path(str(card) + suffix)
        if candidate.is_dir() and (candidate / "cmdline.txt").exists():
            return candidate
    for suffix in (os.sep, ""):
        candidate = Path(str(card) + suffix)
        if candidate.is_dir():
            return candidate
    return None


def shq(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


# Runs on the Pi once the target system is up. Idempotent; disables itself when everything
# succeeded so a normal boot costs nothing.
LOGIC = r"""#!/bin/bash
set -u
LOG=/boot/firmware/eora-firstboot.log
[ -d /boot/firmware ] && touch "$LOG" 2>/dev/null || LOG=/var/log/eora-firstboot.log
exec >>"$LOG" 2>&1
STATUS=/boot/firmware/eora-status.txt
mark(){ echo "== $*"; echo "$(date -Is) $*" > "$STATUS" 2>/dev/null || true; }

. /etc/eora/identity.env
mark "1/6 start host=$EORA_HOST"

if [ "$(hostname)" != "$EORA_HOST" ]; then
  hostnamectl set-hostname "$EORA_HOST"
  sed -i "/^127\.0\.1\.1/d" /etc/hosts
  echo "127.0.1.1	$EORA_HOST" >>/etc/hosts
fi
mark "2/6 hostname=$EORA_HOST"

for i in $(seq 1 120); do id eora >/dev/null 2>&1 && break; sleep 5; done
id eora >/dev/null 2>&1 || { mark "FAILED: user eora missing"; exit 1; }

grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null || \
  echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

if [ -n "$EORA_SSID" ] && [ -n "$EORA_IDENTITY" ] && [ -n "$EORA_WIFI_PASS" ]; then
  # Raspberry Pi Imager writes a plain-password profile even for an 802.1X network, where it
  # can never authenticate. Two profiles for one SSID then fight over the radio.
  for name in $(nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '$2=="802-11-wireless"{print $1}'); do
    [ "$name" = "wifi-$EORA_SSID" ] && continue
    [ "$(nmcli -g 802-11-wireless.ssid connection show "$name" 2>/dev/null)" = "$EORA_SSID" ] && \
      nmcli connection delete "$name" >/dev/null 2>&1 && echo "removed plain profile: $name"
  done
  nmcli --terse --fields NAME connection show 2>/dev/null | grep -qx "wifi-$EORA_SSID" || {
    nmcli connection add type wifi con-name "wifi-$EORA_SSID" ifname wlan0 ssid "$EORA_SSID" \
      wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
      802-1x.identity "$EORA_IDENTITY" 802-1x.password "$EORA_WIFI_PASS" \
      ipv4.method auto ipv4.route-metric 100 \
      connection.autoconnect yes connection.autoconnect-priority 20 2>/dev/null
  }
  nmcli connection up "wifi-$EORA_SSID" >/dev/null 2>&1
fi
mark "3/6 wifi configured"

for i in $(seq 1 90); do ip -4 route get 1.1.1.1 >/dev/null 2>&1 && break; sleep 5; done
ip -4 route get 1.1.1.1 >/dev/null 2>&1 || mark "WARN: no default route yet"
mark "4/6 network up: $(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}')"

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh || true
fi
if command -v tailscale >/dev/null 2>&1 && [ -n "$EORA_AUTHKEY" ]; then
  tailscale up --auth-key="$EORA_AUTHKEY" --hostname="$EORA_HOST" --accept-dns=false || true
fi
mark "5/6 tailscale: $(tailscale ip -4 2>/dev/null | head -1)"

python3 -m pip install --user --break-system-packages --quiet pyserial esptool 2>/dev/null || true
install -d -o eora -g eora /home/eora/eora /home/eora/eora/logs
for f in node_reader.py node_update.py pi_node_probe.py; do
  [ -f "/usr/local/lib/eora/$f" ] && install -o eora -g eora "/usr/local/lib/eora/$f" "/home/eora/eora/$f"
done
[ -f "/usr/local/lib/eora/eora-node-reader.service" ] && \
  install -m 644 /usr/local/lib/eora/eora-node-reader.service /etc/systemd/system/node_reader.service
systemctl daemon-reload
systemctl enable --now node_reader.service 2>/dev/null || true

if tailscale ip -4 >/dev/null 2>&1 && systemctl is-active --quiet node_reader; then
  systemctl disable eora-firstboot.service >/dev/null 2>&1
  mark "6/6 DONE host=$EORA_HOST tailnet=$(tailscale ip -4 2>/dev/null | head -1)"
else
  mark "6/6 INCOMPLETE tailscale=$(tailscale ip -4 2>/dev/null | head -1) reader=$(systemctl is-active node_reader)"
fi
"""

UNIT = """[Unit]
Description=EoRa first-boot identity (hostname, Wi-Fi, tailnet, node reader)
After=network-online.target cloud-init.service cloud-final.service
Wants=network-online.target
ConditionPathExists=/usr/local/sbin/eora-firstboot-logic.sh

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/eora-firstboot-logic.sh
RemainAfterExit=yes
TimeoutStartSec=20min

[Install]
WantedBy=multi-user.target
"""


def compose_installer(number, env, helpers):
    """The script cloud-init runs: drop the payload, install the unit, start it once."""
    host = "eora-air-%02d" % number
    lines = [
        "#!/bin/bash",
        "# generated by mkcard.py -- identity for " + host,
        "# Installs the first-boot logic and runs it. Later boots retry through",
        "# eora-firstboot.service until everything succeeded.",
        "set -u",
        "exec >>/boot/firmware/eora-install.log 2>&1",
        "echo \"== $(date -Is) installer start for " + host + "\"",
        "mkdir -p /usr/local/lib/eora /etc/eora",
        "",
        "cat > /etc/eora/identity.env <<'EORA_ID'",
        "EORA_HOST=%s" % shq(host),
        "EORA_NUMBER=%d" % number,
        "EORA_SSID=%s" % shq(env.get("WIFI_SSID", "")),
        "EORA_IDENTITY=%s" % shq(env.get("WIFI_IDENTITY", "")),
        "EORA_WIFI_PASS=%s" % shq(env.get("WIFI_PASSWORD", "")),
        "EORA_AUTHKEY=%s" % shq(env.get("TAILSCALE_AUTHKEY", "")),
        "EORA_ID",
        "chmod 600 /etc/eora/identity.env",
        "",
        "# The logic is base64 on purpose: no nested quotes or heredocs to get wrong.",
    ]
    b64 = base64.b64encode(LOGIC.encode("utf-8")).decode()
    lines.append(": > /tmp/eora-logic.b64")
    for chunk in (b64[i:i + 100] for i in range(0, len(b64), 100)):
        lines.append("printf '%%s' '%s' >> /tmp/eora-logic.b64" % chunk)
    lines += [
        "base64 -d /tmp/eora-logic.b64 > /usr/local/sbin/eora-firstboot-logic.sh",
        "rm -f /tmp/eora-logic.b64",
        "chmod 755 /usr/local/sbin/eora-firstboot-logic.sh",
        "",
        "# helpers",
    ]
    for name, content in helpers.items():
        blob = base64.b64encode(content.encode("utf-8")).decode()
        lines.append("printf '%%s' '%s' | base64 -d > /usr/local/lib/eora/%s" % (blob, name))
    lines += [
        "",
        "cat > /etc/systemd/system/eora-firstboot.service <<'EORA_UNIT'",
        UNIT.strip(),
        "EORA_UNIT",
        "systemctl daemon-reload",
        "systemctl enable eora-firstboot.service",
        "systemctl start eora-firstboot.service || true",
        "echo \"== $(date -Is) installer done for " + host + "\"",
    ]
    return "\n".join(lines) + "\n"


def strip_cmdline_hook(cmdline):
    """Undo the old systemd.run hook, which stopped this image from booting normally."""
    text = cmdline.read_text(encoding="utf-8-sig", errors="replace")
    original = text
    text = re.sub(r"\s*systemd\.run=\S+", "", text)
    text = re.sub(r"\s*systemd\.run_success_action=\S+", "", text)
    text = re.sub(r"\s*systemd\.unit=kernel-command-line(?:\.target)?", "", text)
    text = text.lstrip("\ufeff").strip("\n")
    if text != original:
        cmdline.write_text(text.rstrip() + "\n", encoding="utf-8")
        return True
    return False


def install_cloud_init_hook(user_data, installer_name):
    """Make cloud-init run our installer on first boot."""
    header = "#cloud-config\n"
    text = user_data.read_text(encoding="utf-8-sig") if user_data.exists() else header
    body = text[len(header):] if text.startswith(header) else text
    entry = ["bash", "/boot/firmware/" + installer_name]
    if yaml is not None:
        try:
            data = yaml.safe_load(body) or {}
        except Exception as exc:
            raise SystemExit("user-data is not valid YAML: %s" % exc)
        cmds = data.get("runcmd")
        if cmds is None:
            cmds = []
        if not isinstance(cmds, list):
            raise SystemExit("user-data runcmd is not a list")
        cmds = [c for c in cmds if c != entry]
        cmds.append(entry)
        data["runcmd"] = cmds
        dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                                default_flow_style=None)
        new = header + MARKER + "\n" + dumped + MARKER + "\n"
    else:
        new = (header + body.rstrip("\n") + "\n" + MARKER + "\n"
               + "  # appended by mkcard.py; runcmd must stay last\n"
               + "  - [ " + RUNCMD_ARGS + " ]\n" + MARKER + "\n")
    user_data.write_text(new, encoding="utf-8")
    return new




def fix_network_config(boot, env):
    """Rewrite the Wi-Fi entry as 802.1X.

    Raspberry Pi Imager can only express a plain password, so its profile for an 802.1X
    network (PEAP/MSCHAPv2 with an account name) can never authenticate. Writing the correct
    auth block here means the device may get online even if our installer never runs.
    """
    path = boot / "network-config"
    if not path.exists():
        return False
    try:
        import yaml as _yaml
    except ImportError:
        return False
    try:
        data = _yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except Exception:
        return False
    ssid = env.get("WIFI_SSID")
    identity = env.get("WIFI_IDENTITY")
    password = env.get("WIFI_PASSWORD")
    if not (ssid and identity and password):
        return False
    wifis = data.setdefault("network", {}).setdefault("wifis", {})
    wlan = wifis.setdefault("wlan0", {})
    wlan["dhcp4"] = True
    wlan.setdefault("regulatory-domain", "CN")
    wlan["optional"] = True
    wlan["access-points"] = {ssid: {"auth": {
        "key-management": "eap",
        "method": "peap",
        "identity": identity,
        "password": password,
        "phase2-auth": "mschapv2",
    }}}
    path.write_text(_yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return True

def bump_instance_id(boot, number):
    """Give the card a new cloud-init instance id.

    cloud-init runs its modules once per instance-id. A card that was booted before keeps
    its old id, so an edited user-data (our runcmd entry) would never be executed: the device
    boots, ignores the change and looks dead. Changing the id forces a fresh first boot.
    """
    meta = boot / "meta-data"
    text = meta.read_text(encoding="utf-8-sig") if meta.exists() else ""
    new_id = "eora-air-%02d-%d" % (number, int(__import__("time").time() * 1000))
    if "instance-id:" in text:
        lines = []
        for line in text.splitlines():
            if line.strip().startswith("instance-id:"):
                lines.append("instance-id: " + new_id)
            else:
                lines.append(line)
        text = "\n".join(lines) + "\n"
    else:
        text = (text.rstrip("\n") + "\n" if text else "") + "instance-id: " + new_id + "\n"
    meta.write_text(text, encoding="utf-8")
    return new_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", help="boot-partition drive letter, e.g. E:")
    parser.add_argument("--number", type=int, help="node number for this card")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    env = load_env()
    missing = [k for k in ("WIFI_SSID", "WIFI_IDENTITY", "WIFI_PASSWORD", "TAILSCALE_AUTHKEY")
               if not env.get(k)]
    say("== secrets file: %s" % ENV_FILE)
    if missing:
        say("   MISSING: %s" % ", ".join(missing))
    else:
        say("   all four keys present")
    if args.check:
        return 0 if not missing else 2

    if args.list:
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            boot = find_boot(letter + ":")
            if boot and (boot / INSTALLER_NAME).exists():
                text = (boot / INSTALLER_NAME).read_text(encoding="utf-8", errors="replace")
                m = re.search(r"EORA_HOST='(eora-air-\d+)'", text)
                say("  %s: %s" % (letter + ":", m.group(1) if m else "(prepared)"))
        return 0

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
    cmdline = boot / "cmdline.txt"
    if not cmdline.exists():
        say("   FAILED: %s has no cmdline.txt (is this the boot partition?)" % boot)
        return 2

    if strip_cmdline_hook(cmdline):
        say("== removed the old systemd.run hook (it broke normal boot on this image)")

    user_data = boot / "user-data"
    new_ud = install_cloud_init_hook(user_data, INSTALLER_NAME)
    # A brand-new instance id, otherwise cloud-init treats the card as already provisioned
    # and silently skips the runcmd we just added.
    new_id = bump_instance_id(boot, args.number)
    say("== meta-data: instance-id -> %s (forces cloud-init to run again)" % new_id)
    if fix_network_config(boot, env):
        say("== network-config: Wi-Fi rewritten as 802.1X (PEAP/MSCHAPv2)")
    say("== user-data: runcmd entry installed (%d bytes)" % len(new_ud))

    helpers = {}
    for name in DEPLOY + (SERVICE,):
        path = HELPERS / name
        if path.is_file():
            helpers["eora-node-reader.service" if name == SERVICE else name] = \
                path.read_text(encoding="utf-8")

    installer = compose_installer(args.number, env, helpers)
    (boot / INSTALLER_NAME).write_bytes(installer.replace("\r\n", "\n").encode("utf-8"))
    say("== wrote %s (%d bytes)" % (INSTALLER_NAME, (boot / INSTALLER_NAME).stat().st_size))
    say("   hostname : eora-air-%02d" % args.number)
    say("   helpers  : %s" % ", ".join(sorted(helpers)))
    say("")
    say("Next: insert the card and power the Pi. It shows up as eora-air-%02d." % args.number)
    say("To see what happened, put the card back here and read")
    say("  eora-status.txt  and  eora-firstboot.log  in the boot partition.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
