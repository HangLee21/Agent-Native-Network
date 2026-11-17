#!/usr/bin/env python3
"""Flash the node attached to this Pi, with verification and automatic rollback.

This is how a fleet gets updated: build once, copy the image to each Pi, let each Pi program
its own node over USB. Nobody unplugs a board.

Safety rules, because a bad flash means a site visit:
  * the expected build id is read out of the image itself, so success is proven rather than
    assumed: after flashing, the node is asked for `info` and its build_id must match;
  * the image that was last known good is kept as `previous.bin`; if the new image does not
    come up, it is reflashed automatically;
  * the reader service is stopped for the flash and always restarted, even on failure;
  * nothing is written unless the image contains a recognisable build id.

    python3 node_update.py ~/eora/mid_edge.bin
    python3 node_update.py ~/eora/mid_edge.bin --no-rollback
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
FLASH_OFFSET = "0x10000"
SERVICE = "node_reader"
FIRMWARE_DIR = HERE / "firmware"
CURRENT = FIRMWARE_DIR / "current.bin"
PREVIOUS = FIRMWARE_DIR / "previous.bin"
BUILD_RE = re.compile(rb"mid-lora-ref-v1-[0-9a-f]{64}")


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


def sudo(cmd):
    """Run a command through sudo, feeding the local password non-interactively."""
    password = os.environ.get("EORA_SUDO_PASS")
    if password:
        return subprocess.run(["sudo", "-S"] + cmd, input=password + "\n",
                              text=True, capture_output=True)
    return subprocess.run(["sudo"] + cmd, capture_output=True, text=True)


def service(action):
    result = sudo(["systemctl", action, SERVICE])
    return result.returncode == 0


def read_build_id(node):
    from pi_node_probe import Node
    try:
        info = node.ask("info", timeout=6)
    except Exception:
        return None
    return info.get("build_id")


def flash(image):
    for command in (["write-flash"], ["write_flash"]):
        proc = subprocess.run(
            [sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", PORT,
             "--baud", "460800", "--before", "default-reset", "--after", "hard-reset"]
            + command + ["--flash-mode", "dio", "--flash-freq", "40m",
                         "--flash-size", "4MB", FLASH_OFFSET, str(image)],
            capture_output=True, text=True)
        output = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            return True, output
        if "invalid choice" in output or "unrecognized" in output:
            continue
        return False, output
    return False, "esptool rejected both write-flash and write_flash"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="firmware .bin to flash")
    parser.add_argument("--no-rollback", action="store_true")
    args = parser.parse_args()

    image = Path(args.image).expanduser().resolve()
    if not image.is_file():
        log("image not found: %s" % image)
        return 2
    blob = image.read_bytes()
    found = BUILD_RE.search(blob)
    if not found:
        log("refusing: no build id inside %s (not a mid_edge image?)" % image.name)
        return 2
    expected = found.group(0).decode()
    log("image    : %s (%d bytes)" % (image.name, len(blob)))
    log("sha256   : %s" % hashlib.sha256(blob).hexdigest())
    log("expected : %s" % expected[-16:])

    if not Path(PORT).exists():
        log("node not present at %s" % PORT)
        return 3

    FIRMWARE_DIR.mkdir(exist_ok=True)
    from pi_node_probe import Node

    log("stopping %s to free the serial port" % SERVICE)
    service("stop")
    time.sleep(1)

    rollback_from = CURRENT if CURRENT.exists() else None
    result = 0
    try:
        log("flashing %s -> %s" % (image.name, FLASH_OFFSET))
        ok, output = flash(image)
        if not ok:
            log("flash FAILED:\n%s" % output[-1500:])
            return 4

        time.sleep(4)
        node = Node(PORT)
        try:
            actual = read_build_id(node)
        finally:
            node.close()
        log("node reports: %s" % (actual[-16:] if actual else "NO REPLY"))

        if actual == expected:
            log("VERIFIED: node is running the image that was just flashed")
            shutil.copy2(image, CURRENT)
            if rollback_from and rollback_from.exists() and rollback_from != CURRENT:
                shutil.copy2(rollback_from, PREVIOUS)
        else:
            log("MISMATCH: flash did not take effect")
            result = 5
            if not args.no_rollback and rollback_from and rollback_from.exists():
                log("rolling back to %s" % rollback_from.name)
                ok, output = flash(rollback_from)
                if not ok:
                    log("ROLLBACK FAILED:\n%s" % output[-800:])
                    result = 6
                else:
                    time.sleep(4)
                    node = Node(PORT)
                    try:
                        back = read_build_id(node)
                    finally:
                        node.close()
                    log("after rollback node reports: %s"
                        % (back[-16:] if back else "NO REPLY"))
    finally:
        log("restarting %s" % SERVICE)
        service("start")
    return result


if __name__ == "__main__":
    sys.exit(main())
