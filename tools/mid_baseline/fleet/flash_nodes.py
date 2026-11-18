"""One-click node flashing: pick an image, make sure the fleet is reachable, flash everyone.

    python tools/mid_baseline/fleet/flash_nodes.py                # newest BUILD-*/images/mid_edge.bin
    python tools/mid_baseline/fleet/flash_nodes.py <image.bin>
    python tools/mid_baseline/fleet/flash_nodes.py --list

The point of this file is that a failure must explain itself. Every precondition is checked
and printed before anything is touched: tailscale reachable, devices online, image readable,
sudo password available. The actual flashing is delegated to `fleet.py update`, which also
self-heals a device that is missing esptool or the flasher script.
"""
import argparse
import getpass
import glob
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FLEET = Path(__file__).resolve().parent / "fleet.py"
PASS_FILE = ROOT / ".local" / "mid" / "pi" / "sudo_pass.txt"
TAILSCALE = r"C:\Program Files\Tailscale\tailscale.exe"


def say(msg=""):
    print(msg, flush=True)


def tailscale_online():
    """Return the list of eora-air-* devices that tailscale currently sees as up."""
    exe = TAILSCALE if os.path.isfile(TAILSCALE) else "tailscale"
    try:
        proc = subprocess.run([exe, "status"], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        return None, "tailscale not found"
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout).strip()[:200]
    names = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].startswith("eora-air-") and "offline" not in line:
            names.append(parts[1])
    return names, None


def newest_image():
    candidates = sorted(
        glob.glob(str(ROOT / "BUILD-*" / "images" / "mid_edge.bin")),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    return candidates[0] if candidates else None


def read_password():
    env = os.environ.get("EORA_PASS")
    if env:
        return env, "environment"
    if PASS_FILE.is_file():
        value = PASS_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value, str(PASS_FILE)
    say("Device sudo password (stored in %s for next time):" % PASS_FILE)
    value = getpass.getpass("  password: ").strip()
    if value:
        PASS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PASS_FILE.write_text(value + "\n", encoding="utf-8")
        try:
            os.chmod(PASS_FILE, 0o600)
        except OSError:
            pass
    return value, "prompt"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?", help="firmware .bin (default: newest BUILD-*)")
    parser.add_argument("--list", action="store_true", help="show available images and exit")
    parser.add_argument("--only", action="append", default=[], help="flash only this device")
    args = parser.parse_args()

    if args.list:
        for p in sorted(glob.glob(str(ROOT / "BUILD-*" / "images" / "mid_edge.bin"))):
            say("  %s  %d bytes" % (p, os.path.getsize(p)))
        return 0

    say("== 1/4 fleet reachability")
    devices, err = tailscale_online()
    if devices is None:
        say("   FAILED: %s" % err)
        say("   Fix: open Tailscale and make sure it says Connected, or run")
        say("        Restart-Service Tailscale   (as administrator)")
        return 2
    if not devices:
        say("   FAILED: no eora-air-* device is online")
        say("   Fix: power the Raspberry Pi(s) and make sure they have network")
        return 2
    say("   online: %s" % ", ".join(devices))

    say("== 2/4 image")
    image = args.image or newest_image()
    if not image or not os.path.isfile(image):
        say("   FAILED: no image found (looked for BUILD-*/images/mid_edge.bin)")
        return 2
    say("   %s (%d bytes)" % (image, os.path.getsize(image)))

    say("== 3/4 credential")
    password, source = read_password()
    if not password:
        say("   FAILED: no sudo password")
        return 2
    say("   using %s" % source)

    say("== 4/4 flashing (each device: stop reader, esptool, verify build id, restart)")
    env = dict(os.environ)
    env["EORA_PASS"] = password
    cmd = [sys.executable, "-X", "utf8", str(FLEET), "update", image]
    for name in args.only:
        cmd += ["--only", name]
    proc = subprocess.run(cmd, env=env, text=True)
    say()
    if proc.returncode == 0:
        say("== done. `python tools\\mid_baseline\\fleet\\fleet.py status` to confirm.")
    else:
        say("== fleet update exited with %d" % proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
