"""Enable account+password SSH login on nodes we can currently reach only with the key.

The five boards made before password support existed have sshd in "key only" mode. The
developer holds the private key, so this is the one step only the developer can perform.

    python tools\\mid_baseline\\fleet\\enable_ssh_password.py --only eora-air-01 eora-air-05
    python tools\\mid_baseline\\fleet\\enable_ssh_password.py --all --allow-only

Needs:
  * the management private key (known-hosts/password come from the usual fleet settings)
  * EORA_PASS or .local/mid/pi/sudo_pass.txt for sudo on the Pi
  * EORA_NEW_PASSWORD (or --password) when actually setting a password

It is idempotent: running it twice changes nothing.
"""
import argparse
import json
import os
import shlex
import sys
from concurrent.futures import ThreadPoolExecutor

import fleet


def build_remote(sudo_pass, new_password, allow_only):
    """One shell command that sets the password (optional) and opens the sshd switch."""
    inner = [
        "set -e",
        "id eora >/dev/null 2>&1 || { echo NO_EORA_USER; exit 3; }",
    ]
    if new_password:
        # chpasswd reads user:password pairs on stdin; never put the secret on the cmdline.
        inner.append("printf 'eora:%s\\n' %s | chpasswd"
                     % ("%s", shlex.quote(new_password)))
    inner += [
        "install -d -m 755 /etc/ssh/sshd_config.d",
        "printf 'PasswordAuthentication yes\\nKbdInteractiveAuthentication yes\\n'"
        " > /etc/ssh/sshd_config.d/20-eora-password.conf",
        "systemctl reload ssh 2>/dev/null || systemctl restart ssh",
        "sshd -T 2>/dev/null | grep -i '^passwordauthentication' || echo NO_SSHD_T_FIELD",
        "passwd -S eora 2>/dev/null || true",
    ]
    script = "; ".join(inner)
    # sudo -S reads the password from the same pipe, so feed both lines in order.
    return "printf '%s\\n' %s | sudo -S bash -c %s" % (
        "%s", shlex.quote(sudo_pass), shlex.quote(script))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="device names")
    ap.add_argument("--all", action="store_true", help="every reachable device")
    ap.add_argument("--group", type=int)
    ap.add_argument("--password", help="new password for user eora (default: EORA_NEW_PASSWORD)")
    ap.add_argument("--allow-only", action="store_true",
                    help="only open the sshd switch, do not change any password")
    args = ap.parse_args()

    if not fleet.require_tailscale():
        return 2

    new_password = args.password or os.environ.get("EORA_NEW_PASSWORD", "")
    if not new_password and not args.allow_only:
        print("需要 --password 或 EORA_NEW_PASSWORD；只想开开关请加 --allow-only")
        return 2
    if new_password and len(new_password) < 8:
        print("密码太短（至少 8 位）")
        return 2

    devices = [d for d in fleet.devices_all() if d[1]]
    if not args.all:
        devices = fleet.pick(args, devices)
    if not devices:
        print("没有选中设备")
        return 1

    sudo_pass = fleet.sudo_password()
    if not sudo_pass:
        print("缺少 sudo 密码：设置 EORA_PASS 或写入 .local/mid/pi/sudo_pass.txt")
        return 2

    remote = build_remote(sudo_pass, new_password, args.allow_only)

    def one(item):
        name, ip = item
        code, out = fleet.run_ssh(fleet.ssh_target(name, ip), remote, timeout=90)
        lines = [l.strip() for l in out.strip().splitlines() if l.strip()]
        tail = " | ".join(lines[-3:])[:150] if lines else "(no output)"
        return name, ("OK " if code == 0 else "FAIL(%d) " % code) + tail

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(one, devices))

    failed = 0
    for name, result in results:
        print("%-14s %s" % (name, result))
        if not result.startswith("OK"):
            failed += 1
    print("\n%d/%d 成功" % (len(results) - failed, len(results)))
    if new_password and not failed:
        print("已设置密码并开启密码登录；对方现在可以 ssh eora@<地址> 用密码登录。")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
