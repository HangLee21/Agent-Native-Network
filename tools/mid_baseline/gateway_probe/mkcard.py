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
import binascii
import os
import re
import sys
import shutil
import tempfile
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

ROOT = Path(__file__).resolve().parents[3]
HELPERS = Path(__file__).resolve().parent.parent / "gateway_probe"
ENV_FILE = ROOT / ".local" / "mid" / "pi" / "device.env"
# The public key that is baked into every card. Production kits ship this file next to the
# tool, because the person making cards never needs the matching PRIVATE key: only the
# developer who later updates the fleet over SSH needs that.
def _default_public_key():
    here = Path(__file__).resolve().parent
    for candidate in (here / "fleet.pub", here.parent / "fleet.pub",
                      Path.home() / ".ssh" / "id_ed25519_eora.pub"):
        if candidate.is_file():
            return candidate
    return Path.home() / ".ssh" / "id_ed25519_eora.pub"


FLEET_PUBLIC_KEY = _default_public_key()
INSTALLER_NAME = "eora-firstboot.sh"
MARKER = "# >>> eora identity >>>"
RUNCMD_ARGS = "bash, /boot/firmware/" + INSTALLER_NAME
DEPLOY = ("node_reader.py", "node_update.py", "pi_node_probe.py")
SERVICE = "node_reader.service"


def say(msg=""):
    print(msg, flush=True)


_LAST_ENV_FILE = None


def load_env(path=None):
    """Read the operator settings.

    The default is this checkout's .local file, which is a developer convenience. A production
    site must be able to point at ITS OWN file (its Wi-Fi, its tailnet or none), so --env
    overrides the path and nothing site-specific has to live in the repository.
    """
    data = {}
    if path:
        source = Path(path)
    else:
        # Operators keep one file and reuse it for every card. Look for site.env next to the
        # tool and at the kit root before falling back to the developer's .local file.
        # Walk up from this file: the tool lives in gateway_probe/ and the operator keeps
        # one site.env at the package root, which may be 1-4 levels above depending on layout.
        here = Path(__file__).resolve().parent
        source = ENV_FILE
        for depth in range(0, min(5, len(here.parents))):
            candidate = here.parents[depth] / "site.env"
            if candidate.is_file():
                source = candidate
                break
    if source.is_file():
        # utf-8-sig: PowerShell and Notepad write a BOM, which would otherwise become part
        # of the first key and look like a missing setting.
        for line in source.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip()
    global _LAST_ENV_FILE
    _LAST_ENV_FILE = source
    return data


_PUBLIC_KEY_OVERRIDE = None


def _public_key_path():
    return Path(_PUBLIC_KEY_OVERRIDE) if _PUBLIC_KEY_OVERRIDE else FLEET_PUBLIC_KEY


def load_fleet_public_key():
    """Read and validate the single management Ed25519 public key."""
    try:
        raw = _public_key_path().read_text(encoding="utf-8").replace("\r", "")
        keys = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2 or parts[0] != "ssh-ed25519":
                raise ValueError("expected an ssh-ed25519 public key")
            blob = base64.b64decode(parts[1], validate=True)
            if (len(blob) != 51 or blob[:4] != b"\x00\x00\x00\x0b"
                    or blob[4:15] != b"ssh-ed25519" or blob[15:19] != b"\x00\x00\x00\x20"):
                raise ValueError("invalid Ed25519 key data")
            keys.append("ssh-ed25519 " + parts[1])
        if not keys:
            raise ValueError("the public key file is empty")
        return "\n".join(keys)
    except (OSError, UnicodeError, ValueError, binascii.Error) as exc:
        raise ValueError("无法读取有效的机群公钥 %s；请联系管理员恢复该公钥后重试，存储卡未修改。" % _public_key_path()) from exc


KEY_INSTALLER = r'''#!/usr/bin/env python3
import os
import pwd
import shlex
import sys
from pathlib import Path


def install_authorized_key(home, key):
    ssh_dir = Path(home) / ".ssh"
    ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ssh_dir, 0o700)
    authorized = ssh_dir / "authorized_keys"
    existing = authorized.read_text(encoding="utf-8") if authorized.exists() else ""
    key_type, key_data = key.split()
    found = False
    for line in existing.splitlines():
        try:
            fields = shlex.split(line, comments=True)
        except ValueError:
            continue
        if fields[:2] == [key_type, key_data] or fields[1:3] == [key_type, key_data]:
            found = True
            break
    if not found:
        with authorized.open("a", encoding="utf-8") as stream:
            if existing and not existing.endswith("\n"):
                stream.write("\n")
            stream.write(key + "\n")
    os.chmod(authorized, 0o600)


if __name__ == "__main__":
    user = pwd.getpwnam("eora")
    if os.geteuid() != user.pw_uid:
        raise SystemExit("SSH key installation must run as eora")
    # One key per line: two operators must both be able to log in.
    installed = 0
    for line in sys.argv[1].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        install_authorized_key(user.pw_dir, line)
        installed += 1
    if not installed:
        raise SystemExit("no usable public key given")
'''


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



def normalise_card(text):
    """Accept F, f:, F:\ and F:/ alike.

    The prompt asks for "a letter", so people type "F" or "f" and the old code turned that
    into the relative path "F", which never matches a drive and reported "not a mounted
    card" even though the card was sitting right there.
    """
    s = str(text or "").strip().strip('"').strip("'")
    if not s:
        return ""
    s = s.replace("/", "\\").rstrip("\\")
    if len(s) == 1 and s.isalpha():
        s += ":"
    if len(s) == 2 and s[0].isalpha() and s[1] == ":":
        s = s[0].upper() + ":"
    return s


def detect_cards():
    """Every mounted Raspberry Pi boot partition, as (letter, path, already_prepared)."""
    found = []
    for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
        boot = find_boot(letter + ":")
        if boot and (boot / "cmdline.txt").exists():
            found.append((letter + ":", boot, (boot / INSTALLER_NAME).exists()))
    return found


def shq(value):
    return "'" + str(value).replace("'", "'\\''") + "'"


# Runs on the Pi once the target system is up. Idempotent; disables itself when everything
# succeeded so a normal boot costs nothing.
LOGIC = r"""#!/bin/bash
set -euo pipefail
LOG=/boot/firmware/eora-firstboot.log
[ -d /boot/firmware ] && touch "$LOG" 2>/dev/null || LOG=/var/log/eora-firstboot.log
exec >>"$LOG" 2>&1
STATUS=/boot/firmware/eora-status.txt
mark(){ echo "== $*"; echo "$(date -Is) $*" > "$STATUS" 2>/dev/null || true; }
trap 'mark "FAILED: firstboot line $LINENO"' ERR

mark "1/6 firstboot starting"
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
runuser -u eora -- python3 /usr/local/lib/eora/install_fleet_key.py "$(cat /etc/eora/fleet.pub)" || { mark "FAILED: SSH public key installation"; exit 1; }
getent group dialout >/dev/null || { mark "FAILED: dialout group missing"; exit 1; }
usermod -a -G dialout eora

# Password login is opt-in: the second operator may not want to carry a key at all.
allow_pass=0
if [ -n "$EORA_SSH_PASS" ]; then
  printf 'eora:%s\n' "$EORA_SSH_PASS" | chpasswd || { mark "FAILED: set eora password"; exit 1; }
  allow_pass=1
  mark "2b/6 eora password set"
fi
[ "$EORA_SSH_ALLOW_PASS" = "yes" ] && allow_pass=1
if [ "$allow_pass" = "1" ]; then
  install -d -m 755 /etc/ssh/sshd_config.d
  printf 'PasswordAuthentication yes\nKbdInteractiveAuthentication yes\n' \
    > /etc/ssh/sshd_config.d/20-eora-password.conf
  systemctl reload ssh 2>/dev/null || systemctl restart ssh || { mark "FAILED: ssh reload"; exit 1; }
  mark "2c/6 ssh password login enabled"
fi

grep -q '^precedence ::ffff:0:0/96' /etc/gai.conf 2>/dev/null || \
  echo 'precedence ::ffff:0:0/96  100' >> /etc/gai.conf

if [ -n "$EORA_SSID" ] && [ -n "$EORA_WIFI_PASS" ]; then
  # Raspberry Pi Imager writes a plain-password profile even for an 802.1X network, where it
  # can never authenticate. Two profiles for one SSID then fight over the radio.
  for name in $(nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '$2=="802-11-wireless"{print $1}'); do
    [ "$name" = "wifi-$EORA_SSID" ] && continue
    [ "$(nmcli -g 802-11-wireless.ssid connection show "$name" 2>/dev/null)" = "$EORA_SSID" ] && \
      nmcli connection delete "$name" >/dev/null 2>&1 && echo "removed plain profile: $name"
  done
  if [ "$EORA_WIFI_AUTH" = "psk" ]; then
    # Plain WPA2/WPA3-PSK (office, home router, phone hotspot). No identity, no 802.1X.
    nmcli --terse --fields NAME connection show 2>/dev/null | grep -qx "wifi-$EORA_SSID" || {
      nmcli connection add type wifi con-name "wifi-$EORA_SSID" ifname wlan0 ssid "$EORA_SSID" \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$EORA_WIFI_PASS" \
        ipv4.method auto ipv4.route-metric 100 \
        connection.autoconnect yes connection.autoconnect-priority 20 2>/dev/null
    }
  else
    [ -n "$EORA_IDENTITY" ] || { mark "FAILED: 802.1X needs EORA_IDENTITY"; exit 1; }
    nmcli --terse --fields NAME connection show 2>/dev/null | grep -qx "wifi-$EORA_SSID" || {
      nmcli connection add type wifi con-name "wifi-$EORA_SSID" ifname wlan0 ssid "$EORA_SSID" \
        wifi-sec.key-mgmt wpa-eap 802-1x.eap peap 802-1x.phase2-auth mschapv2 \
        802-1x.identity "$EORA_IDENTITY" 802-1x.password "$EORA_WIFI_PASS" \
        ipv4.method auto ipv4.route-metric 100 \
        connection.autoconnect yes connection.autoconnect-priority 20 2>/dev/null
    }
  fi
  if ! wifi_error=$(nmcli connection up "wifi-$EORA_SSID" 2>&1); then
    wifi_error=${wifi_error//"$EORA_WIFI_PASS"/[redacted]}
    wifi_error=${wifi_error//"$EORA_IDENTITY"/[redacted]}
    printf 'nmcli connection up: %s\n' "$wifi_error"
    mark "FAILED: wifi connection"
    exit 1
  fi
fi
mark "3/6 wifi configured"

for i in $(seq 1 90); do ip -4 route get 1.1.1.1 >/dev/null 2>&1 && break; sleep 5; done
ip -4 route get 1.1.1.1 >/dev/null 2>&1 || mark "WARN: no default route yet"
wlan_ip=$(ip -4 -o addr show wlan0 2>/dev/null | awk '{print $4}' || true)
[ -n "$wlan_ip" ] || { mark "FAILED: wlan0 has no IPv4 address"; exit 1; }
mark "4/6 network up: $wlan_ip"

# A Pi has no RTC: until NTP catches up its clock can lag the repositories' signing time, and
# apt then rejects every signature with "Not live until ...". That is exactly what happened on
# card 05: the Tailscale install failed with an unsigned-repository error even though the Wi-Fi
# was fine. Wait for a synced clock before touching any repository.
mark "4a/6 waiting for a synchronised clock"
timedatectl set-ntp true >/dev/null 2>&1 || true
for i in $(seq 1 60); do
  [ "$(timedatectl show -p NTPSynchronized --value 2>/dev/null)" = "yes" ] && break
  sleep 5
done
mark "4a/6 clock: $(date -Is) synced=$(timedatectl show -p NTPSynchronized --value 2>/dev/null)"

# Tailscale is the management overlay, not a hard requirement. A production site may run its
# own tailnet (key supplied in device.env), or no overlay at all and reach the Pis over the
# local network. With an empty key we install nothing and the card still completes.
if [ -n "$EORA_AUTHKEY" ]; then
  if ! command -v tailscale >/dev/null 2>&1; then
    # Retry: even after the clock wait, a lagging signature window can still bite once.
    for attempt in 1 2 3; do
      curl -fsSL https://tailscale.com/install.sh | sh && break
      mark "WARN: tailscale install attempt $attempt failed"
      sleep 15
      timedatectl set-ntp true >/dev/null 2>&1 || true
    done
    command -v tailscale >/dev/null 2>&1 || { mark "FAILED: tailscale installation"; exit 1; }
  fi
  tailscale up --auth-key="$EORA_AUTHKEY" --hostname="$EORA_HOST" --accept-dns=false || { mark "FAILED: tailscale connection"; exit 1; }
  mark "5/6 tailscale: $(tailscale ip -4 2>/dev/null | head -1)"
else
  mark "5/6 tailscale: skipped (no EORA_AUTHKEY; management over the local network)"
fi

if ! python3 -m pip --version >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip || { mark "FAILED: python3-pip installation"; exit 1; }
fi
PIP_SYSTEM_FLAG=()
if python3 -m pip help install > /tmp/eora-pip-help.txt && grep -q -- '--break-system-packages' /tmp/eora-pip-help.txt; then PIP_SYSTEM_FLAG=(--break-system-packages); fi
rm -f /tmp/eora-pip-help.txt
python3 -m pip install "${PIP_SYSTEM_FLAG[@]}" --quiet pyserial==3.5 esptool==5.6.0 || { mark "FAILED: Python dependencies"; exit 1; }
runuser -u eora -- python3 -c "import serial, esptool" || { mark "FAILED: service Python imports"; exit 1; }
install -d -o eora -g eora /home/eora/eora /home/eora/eora/logs
for f in node_reader.py node_update.py pi_node_probe.py; do
  [ -f "/usr/local/lib/eora/$f" ] || { mark "FAILED: missing helper $f"; exit 1; }
  install -o eora -g eora "/usr/local/lib/eora/$f" "/home/eora/eora/$f"
done
[ -f "/usr/local/lib/eora/eora-node-reader.service" ] || { mark "FAILED: missing service"; exit 1; }
install -m 644 /usr/local/lib/eora/eora-node-reader.service /etc/systemd/system/node_reader.service
systemctl daemon-reload
systemctl enable --now node_reader.service || { mark "FAILED: node_reader start"; exit 1; }

overlay_ok=1
[ -n "$EORA_AUTHKEY" ] && { tailscale ip -4 >/dev/null 2>&1 || overlay_ok=0; }
if [ "$overlay_ok" = "1" ] && systemctl is-active --quiet node_reader; then
  systemctl disable eora-firstboot.service >/dev/null 2>&1
  mark "6/6 DONE host=$EORA_HOST overlay=$(tailscale ip -4 2>/dev/null | head -1 || echo none) ip=$(hostname -I | awk '{print $1}')"
else
  mark "6/6 INCOMPLETE overlay=$(tailscale ip -4 2>/dev/null | head -1 || echo none) reader=$(systemctl is-active node_reader)"
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


def compose_installer(number, env, helpers, fleet_public_key):
    """The script cloud-init runs: drop the payload, install the unit, start it once."""
    host = "eora-air-%02d" % number
    lines = [
        "#!/bin/bash",
        "# generated by mkcard.py -- identity for " + host,
        "# Installs the first-boot logic and runs it. Later boots retry through",
        "# eora-firstboot.service until everything succeeded.",
        "set -eu",
        "exec >>/boot/firmware/eora-install.log 2>&1",
        "trap 'echo FAILED: installer line $LINENO' ERR",
        "echo \"== $(date -Is) installer start for " + host + "\"",
        "mkdir -p /usr/local/lib/eora /etc/eora",
        "",
        "cat > /etc/eora/identity.env <<'EORA_ID'",
        "EORA_HOST=%s" % shq(host),
        "EORA_NUMBER=%d" % number,
        "EORA_SSID=%s" % shq(env.get("WIFI_SSID", "")),
        # Authentication scheme travels with the card: enterprise 802.1X (campus) needs an
        # identity, a plain WPA2-PSK network (office/hotspot) must not send one at all.
        "EORA_WIFI_AUTH=%s" % shq((env.get("WIFI_AUTH") or "eap").strip().lower()),
        "EORA_IDENTITY=%s" % shq(env.get("WIFI_IDENTITY", "")),
        "EORA_WIFI_PASS=%s" % shq(env.get("WIFI_PASSWORD", "")),
        "EORA_AUTHKEY=%s" % shq(env.get("TAILSCALE_AUTHKEY", "")),
        # Two operators must both be able to log in, and the second one may prefer a
        # password over carrying a private key. Empty means key-only.
        "EORA_SSH_PASS=%s" % shq(env.get("SSH_PASSWORD", "")),
        "EORA_SSH_ALLOW_PASS=%s" % shq(env.get("SSH_ALLOW_PASSWORD", "")),
        "EORA_ID",
        "chmod 600 /etc/eora/identity.env",
        "printf '%s\\n' " + shq(fleet_public_key) + " > /etc/eora/fleet.pub",
        "printf '%s' " + shq(base64.b64encode(KEY_INSTALLER.encode('utf-8')).decode()) + " | base64 -d > /usr/local/lib/eora/install_fleet_key.py",
        "chmod 755 /usr/local/lib/eora",
        "chmod 644 /usr/local/lib/eora/install_fleet_key.py",
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
        "runuser -u eora -- python3 /usr/local/lib/eora/install_fleet_key.py \"$(cat /etc/eora/fleet.pub)\"",
        "systemctl start --no-block eora-firstboot.service",
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
    text = " ".join(text.lstrip("\ufeff").split())
    if text != original:
        cmdline.write_text(text.rstrip() + "\n", encoding="utf-8")
        return True
    return False


def install_cloud_init_hook(user_data, installer_name, env=None):
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
        if not isinstance(data, dict):
            raise SystemExit("user-data must be a mapping")
        cmds = data.get("runcmd")
        if cmds is None:
            cmds = []
        if not isinstance(cmds, list):
            raise SystemExit("user-data runcmd is not a list")
        cmds = [c for c in cmds if c != entry and c != "bash /boot/firmware/" + installer_name]
        cmds.append(entry)
        data["hostname"] = "eora-air-%02d" % _ACTIVE_NUMBER
        data["preserve_hostname"] = False
        # Raspberry Pi Imager writes ssh_pwauth: false when the operator picks "key only".
        # If this card is meant to allow a password, override that decision here.
        if str((env or {}).get("SSH_PASSWORD") or "").strip():
            data["ssh_pwauth"] = True
        data["runcmd"] = cmds
        dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True,
                                default_flow_style=None)
        new = header + MARKER + "\n" + dumped + MARKER + "\n"
    else:
        raise SystemExit("需要 PyYAML；未修改存储卡")
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
    auth = (env.get("WIFI_AUTH") or "eap").strip().lower()
    if auth not in ("eap", "psk"):
        auth = "eap"
    if not (ssid and password):
        return False
    if auth == "eap" and not identity:
        return False
    if not isinstance(data, dict):
        return False
    network = data.get("network", data)
    if not isinstance(network, dict):
        return False
    wifis = network.setdefault("wifis", {})
    wlan = wifis.setdefault("wlan0", {})
    wlan["dhcp4"] = True
    wlan.setdefault("regulatory-domain", "CN")
    wlan["optional"] = True
    aps = wlan.setdefault("access-points", {})
    ap = aps.setdefault(ssid, {})
    if not isinstance(ap, dict):
        return False
    ap.pop("auth", None)
    if auth == "psk":
        # Office / home router / phone hotspot: netplan expresses this as a plain password.
        ap["password"] = password
    else:
        ap.pop("password", None)
        ap["auth"] = {
            "key-management": "eap",
            "method": "peap",
            "identity": identity,
            "password": password,
            "phase2-auth": "mschapv2",
        }
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
    new_id = "eora-air-%02d-%s" % (number, uuid.uuid4().hex)
    if yaml is None: raise SystemExit("需要 PyYAML；未修改存储卡")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict): raise SystemExit("meta-data 格式错误")
    data["instance-id"] = new_id
    data["local-hostname"] = "eora-air-%02d" % number
    meta.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    cmd = boot / "cmdline.txt"
    words = cmd.read_text(encoding="utf-8-sig").split()
    seen = 0
    for i, word in enumerate(words):
        match = re.fullmatch(r"ds=(nocloud(?:-net)?)(?:;(.*))?", word)
        if match:
            seen += 1
            fields = (match.group(2) or "").split(";")
            fields = [field for field in fields if field and not re.match(r"^(?:i|instance-id)=", field)]
            words[i] = "ds=" + match.group(1) + ";" + ";".join(fields + ["i=" + new_id])
    if seen != 1: raise SystemExit("不支持的镜像：cmdline 中需要且只能有一个 ds=nocloud 或 ds=nocloud-net；未修改存储卡")
    cmd.write_text(" ".join(words)+"\n",encoding="utf-8")
    return new_id


def wait_for_card(previous=None, timeout_s=900):
    """Wait until a mounted, unprepared card appears (and is not the one we just wrote)."""
    import time as _time
    deadline = _time.time() + timeout_s
    while _time.time() < deadline:
        cards = detect_cards()
        fresh = [c for c in cards if not c[2]]
        if fresh:
            boot = fresh[0][1]
            if previous is None or boot.resolve() != previous.resolve():
                return boot
        _time.sleep(2)
    return None



def write_card(boot, number, env, helpers, fleet_public_key):
    """Prepare one mounted card: stage, verify, back up, then replace atomically.

    Shared by the single-card path and --batch, so the two can never drift apart.
    """
    global _ACTIVE_NUMBER
    _ACTIVE_NUMBER = number
    names = ["cmdline.txt", "user-data", "meta-data", "network-config", INSTALLER_NAME]
    with tempfile.TemporaryDirectory(prefix="eora-card-") as td:
        stage = Path(td)
        for name in names:
            source = boot / name
            if source.exists(): shutil.copy2(source, stage / name)
        strip_cmdline_hook(stage / "cmdline.txt")
        install_cloud_init_hook(stage / "user-data", INSTALLER_NAME, env)
        new_id = bump_instance_id(stage, number)
        if (stage / "network-config").exists() and not fix_network_config(stage, env):
            raise SystemExit("无法检查或更新 Wi-Fi 配置；未修改存储卡")
        (stage / INSTALLER_NAME).write_text(compose_installer(number, env, helpers, fleet_public_key),encoding="utf-8",newline="\n")
        # Preserve originals on the card before any change; failures restore from these bytes.
        backup = boot / ("eora-backup-" + uuid.uuid4().hex)
        backup.mkdir()
        originals = {}
        for name in names:
            f=boot/name
            originals[name]=f.read_bytes() if f.exists() else None
            if originals[name] is not None:(backup/name).write_bytes(originals[name])
        try:
            for name in names:
                src=stage/name
                if not src.exists():continue
                dst=boot/name;tmp=boot/(name+".eora-tmp")
                with tmp.open("wb") as stream:stream.write(src.read_bytes());stream.flush();os.fsync(stream.fileno())
                os.replace(tmp,dst)
        except Exception:
            for name,data in originals.items():
                dst=boot/name
                if data is None:
                    if dst.exists():dst.unlink()
                else:dst.write_bytes(data)
            raise
    say("已准备节点 %d；实例号已同步。" % number)
    say("原文件保存在卡内 " + backup.name + "；启动后查看 eora-install.log 和 eora-firstboot.log。")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--card", help="boot-partition drive letter, e.g. E:")
    parser.add_argument("--number", type=int, help="node number for this card")
    parser.add_argument("--auto", action="store_true",
                        help="pick the only mounted card instead of naming a letter")
    parser.add_argument("--env", help="operator settings file (default: .local/mid/pi/device.env)")
    parser.add_argument("--public-key", help="management public key to bake into the card")
    parser.add_argument("--i-know-this-is-the-dev-key", action="store_true",
                        help="allow the developer key that lives inside this checkout")
    parser.add_argument("--batch", action="store_true",
                        help="keep going: wait for each new card, number it, ask for the next")
    parser.add_argument("--from", dest="first", type=int,
                        help="first node number for --batch (default: one more than --number)")
    parser.add_argument("--count", type=int, default=1, help="how many cards to prepare in --batch")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    global _PUBLIC_KEY_OVERRIDE
    if args.public_key:
        _PUBLIC_KEY_OVERRIDE = args.public_key

    env = load_env(args.env)

    # Never bake THIS checkout's Tailscale key into a card that leaves the lab: that key
    # belongs to a personal tailnet, and a production card carrying it would hand the whole
    # fleet to that account. Production must pass --env with the site's own file.
    env_path = Path(_LAST_ENV_FILE).resolve() if _LAST_ENV_FILE else ENV_FILE.resolve()
    inside_checkout = (ROOT / ".local").resolve() in env_path.parents
    if env.get("TAILSCALE_AUTHKEY") and inside_checkout and not args.i_know_this_is_the_dev_key:
        raise SystemExit(
            "拒绝写入：这份 Tailscale 授权来自仓库内的开发配置，会泄露开发者个人账号。\n"
            "  正确的做法：  --env D:\\ops\\site.env   （里面放现场自己的 TAILSCALE_AUTHKEY）\n"
            "  仅当这是自用的调试卡时，才加 --i-know-this-is-the-dev-key")
    # Tailscale is optional: a production site may use its own tailnet, a plain LAN, or no
    # overlay at all. Requiring a key here forced the operator's personal account into every
    # card, which is exactly what a customer deployment cannot accept.
    auth = (env.get("WIFI_AUTH") or "eap").strip().lower()
    required = ["WIFI_SSID", "WIFI_PASSWORD"]
    if auth != "psk":
        required.append("WIFI_IDENTITY")
    missing = [k for k in required if not env.get(k)]
    if not env.get("TAILSCALE_AUTHKEY"):
        say("   NOTE: 没有 TAILSCALE_AUTHKEY —— 卡片将不装 Tailscale（走局域网/mDNS）")
    say("== secrets file: %s" % (_LAST_ENV_FILE or ENV_FILE))
    if inside_checkout:
        say("   WARNING: 这是仓库内的开发配置，不要用于生产卡")
    if missing:
        say("   MISSING: %s" % ", ".join(missing))
    else:
        say("   required keys present (auth=%s, tailscale=%s)"
            % ((env.get("WIFI_AUTH") or "eap").strip().lower(),
               "on" if env.get("TAILSCALE_AUTHKEY") else "off"))
    if args.check:
        try:
            load_fleet_public_key()
        except ValueError as exc:
            say(str(exc))
            return 2
        say("   fleet public key valid")
        return 0 if not missing else 2

    if args.list:
        seen = 0
        for letter in "DEFGHIJKLMNOPQRSTUVWXYZ":
            boot = find_boot(letter + ":")
            if not boot or not (boot / "cmdline.txt").exists():
                continue
            seen += 1
            if (boot / INSTALLER_NAME).exists():
                text = (boot / INSTALLER_NAME).read_text(encoding="utf-8", errors="replace")
                m = re.search(r"EORA_HOST='(eora-air-\d+)'", text)
                say("  %s: %s" % (letter + ":", m.group(1) if m else "(prepared)"))
            else:
                say("  %s: (empty card, ready to prepare)" % (letter + ":"))
        if not seen:
            # Printing nothing looked identical to the tool being broken.
            say("  没有检测到存储卡：读卡器里没有卡，或卡还没被系统挂载出来。")
            say("  插卡后等两三秒再跑；或者用 `--auto` 让工具自己找。")
        return 0

    if (not args.card and not args.auto) or args.number is None:
        parser.error("--card/--auto and --number are required unless --list/--check")
    if missing:
        return 2
    if not (1 <= args.number <= 255):
        parser.error("--number must be 1..255 (it travels in one frame byte)")

    try:
        fleet_public_key = load_fleet_public_key()
    except ValueError as exc:
        say(str(exc))
        return 2

    if args.batch:
        first = args.first if args.first is not None else (args.number or 1)
        last = first + max(1, args.count) - 1
        try:
            fleet_public_key = load_fleet_public_key()
        except ValueError as exc:
            say(str(exc))
            return 2
        if yaml is None:
            say("需要 PyYAML；未修改存储卡")
            return 2
        helpers = {}
        for name in DEPLOY + (SERVICE,):
            helper_path = HELPERS / name
            if not helper_path.is_file():
                raise SystemExit("缺少必要文件：" + name)
            helpers["eora-node-reader.service" if name == SERVICE else name] = \
                helper_path.read_text(encoding="utf-8")
        done = 0
        for number in range(first, last + 1):
            say("\n== waiting for card #%d (of %d..%d) ..." % (number, first, last))
            boot = wait_for_card()
            if boot is None:
                say("   no card appeared within 15 minutes; stopping at #%d" % number)
                break
            previous = boot
            write_card(boot, number, env, helpers, fleet_public_key)
            done += 1
            say("== #%d done on %s. 拔卡，换下一张。" % (number, boot))
            while detect_cards() and any(c[1].resolve() == boot.resolve() for c in detect_cards()):
                import time as _time
                _time.sleep(2)
        say("\n== batch finished: %d card(s) prepared" % done)
        return 0

    boot = None
    if args.card:
        boot = find_boot(normalise_card(args.card))
        if not boot:
            say("   %s is not a mounted card" % args.card)
    if not boot:
        cards = detect_cards()
        fresh = [c for c in cards if not c[2]]
        if len(fresh) == 1:
            boot = fresh[0][1]
            say("   自动选中未准备的卡 %s" % fresh[0][0])
        elif len(cards) == 1:
            boot = cards[0][1]
            say("   自动选中 %s（已准备过，将改写身份）" % cards[0][0])
        elif not cards:
            say("   FAILED: 没检测到任何树莓派启动分区。请确认卡已插入，"
                "或先别急着拔卡——读卡器刚插入时盘符可能还在枚举。")
            return 2
        else:
            say("   FAILED: 检测到多张卡，请显式指定盘符：")
            for letter, _path, prepared in cards:
                say("      %s  %s" % (letter, "已准备" if prepared else "未准备"))
            return 2
    say("   目标卡：%s" % boot)
    cmdline = boot / "cmdline.txt"
    if not cmdline.exists():
        say("   FAILED: %s has no cmdline.txt (is this the boot partition?)" % boot)
        return 2

    # A card that already booted tells us why it failed; surface that before overwriting it,
    # otherwise the evidence is lost and the next attempt starts blind.
    previous = boot / "eora-status.txt"
    if previous.is_file():
        text = previous.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            say("== previous boot on this card said:")
            for line in text.splitlines()[-3:]:
                say("   " + line)
            say("   (card will be re-prepared; that history is overwritten)")

    if yaml is None:
        say("需要 PyYAML；未修改存储卡")
        return 2
    helpers = {}
    for name in DEPLOY + (SERVICE,):
        path = HELPERS / name
        if not path.is_file(): raise SystemExit("缺少必要文件：" + name)
        helpers["eora-node-reader.service" if name == SERVICE else name] = path.read_text(encoding="utf-8")
    return write_card(boot, args.number, env, helpers, fleet_public_key)

if __name__ == "__main__":
    sys.exit(main())
