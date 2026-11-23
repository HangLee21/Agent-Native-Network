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
import pathlib
import subprocess
import sys

def _detect_root(start):
    """Find the checkout root from any packaging layout.

    These tools live at tools/mid_baseline/fleet in the development tree and at
    app/services/tools/fleet in the deploy packaging, so counting parent directories
    is unreliable; look for something that only exists at the root instead.
    """
    start = pathlib.Path(start)
    for candidate in [start] + list(start.parents):
        if (candidate / ".git").exists() or (candidate / "START_STUDIO.cmd").exists():
            return str(candidate)
    return str(start)

from pathlib import Path

ROOT = Path(_detect_root(Path(__file__).resolve().parent))
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
    """Newest build record, else the single image the delivery package ships."""
    packaged = ROOT / "firmware" / "mid_edge.bin"
    candidates = sorted(
        glob.glob(str(ROOT / "BUILD-*" / "images" / "mid_edge.bin")),
        key=os.path.getmtime, reverse=True)
    if candidates:
        return candidates[0]
    if packaged.is_file():
        return str(packaged)
    return None

def read_password():
    env = os.environ.get("EORA_PASS")
    if env:
        return env, "environment"
    if PASS_FILE.is_file():
        value = PASS_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value, str(PASS_FILE)
    # Never block on a prompt when there is no terminal: a redirected or backgrounded run
    # used to hang here forever with no output, which looks exactly like a stuck flash.
    if not sys.stdin.isatty():
        raise SystemExit(
            "\n没有终端可输入 sudo 密码。二选一：\n"
            "  1) 设置环境变量 EORA_PASS 后重跑\n"
            "  2) 直接在终端里运行一次，密码会缓存到 %s" % PASS_FILE)
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
    parser.add_argument("image", nargs="?", help="firmware .bin (default: newest BUILD-*, else firmware/mid_edge.bin)")
    parser.add_argument("--list", action="store_true", help="show available images and exit")
    parser.add_argument("--only", action="append", default=[], help="flash only this device")
    parser.add_argument("--group", type=int, help="flash only devices in this mesh group")
    args = parser.parse_args()

    if args.list:
        for p in sorted(glob.glob(str(ROOT / "BUILD-*" / "images" / "mid_edge.bin"))):
            say("  %s  %d bytes" % (p, os.path.getsize(p)))
        return 0

    say("== 1/4 fleet reachability")
    devices, err = tailscale_online()
    if devices is None:
        say("   FAILED: Tailscale is not connected on this computer")
        say("   state  : %s" % err)
        say("   This is a network-app problem, not a device problem.")
        say("   Fix, in an Administrator PowerShell:  Restart-Service Tailscale")
        return 2
    if not devices:
        say("   FAILED: tailnet reachable, but no eora-air-* device is online")
        say("   Fix: power the Raspberry Pi(s); a fresh card needs 2-5 minutes")
        return 2
    say("   online: %s" % ", ".join(devices))

    say("== 2/4 image")
    image = args.image or newest_image()
    if not image or not os.path.isfile(image):
        say("   FAILED: no image found (looked for BUILD-*/images/mid_edge.bin or firmware/mid_edge.bin)")
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
    if args.group is not None:
        cmd += ["--group", str(args.group)]
    # fleet.py takes --only as a single nargs="*" list; repeating the flag lets the last
    # occurrence win, which silently flashed just one device out of several.
    if args.only:
        cmd += ["--only"] + list(args.only)
    proc = subprocess.run(cmd, env=env, text=True)
    say()
    if proc.returncode == 0:
        say("== done. `python tools\\mid_baseline\\fleet\\fleet.py status` to confirm.")
    else:
        say("== fleet update exited with %d" % proc.returncode)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
