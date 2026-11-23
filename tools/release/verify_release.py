"""Reproduce app/start/launcher.py's release validation against the current tree.

If this passes, START_STUDIO.cmd will accept the package. It mirrors release() exactly:
schema/status/release_id, service entry modules hashed, per-file SHA256 match, and no
unhashed runtime file under app/services.
"""
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICES = ROOT / "app" / "services"
MANIFEST = ROOT / "firmware" / "manifest.json"
MODULE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+")
SUFFIXES = {".py", ".json", ".html", ".js", ".css"}


def fail(msg):
    print("  FAIL:", msg)
    return 1


def main():
    m = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    if m.get("schema_version") != 1:
        return fail("schema_version != 1")
    if m.get("status") not in ("candidate", "validated"):
        return fail("status invalid: %r" % m.get("status"))
    if not isinstance(m.get("release_id"), str) or not m["release_id"]:
        return fail("release_id missing")

    svc = m.get("services", {})
    hashes = m.get("service_files_sha256")
    if not isinstance(hashes, dict) or not hashes:
        return fail("service_files_sha256 missing")

    for key in ("gateway_module", "studio_module"):
        name = svc.get(key)
        if not isinstance(name, str) or not MODULE.fullmatch(name):
            return fail("%s invalid: %r" % (key, name))
        rel = name.replace(".", "/") + ".py"
        if rel not in hashes:
            return fail("entry module not hashed: " + rel)

    for rel, expected in hashes.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            return fail("bad sha format: " + rel)
        path = SERVICES / rel
        if not path.is_file():
            return fail("hashed file missing: " + rel)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            return fail("hash mismatch: " + rel)

    for path in SERVICES.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path == MANIFEST:
            continue
        if path.suffix.lower() not in SUFFIXES:
            continue
        rel = path.relative_to(SERVICES).as_posix()
        if rel not in hashes:
            return fail("unhashed runtime file: " + rel)

    for key in ("gateway_args", "studio_args"):
        value = svc.get(key)
        if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
            return fail("%s invalid" % key)

    print("  PASS: release manifest matches the tree")
    print("    release_id   :", m["release_id"])
    print("    status       :", m["status"])
    print("    gateway      :", svc.get("gateway_module"))
    print("    studio       :", svc.get("studio_module"))
    print("    hashed files :", len(hashes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
