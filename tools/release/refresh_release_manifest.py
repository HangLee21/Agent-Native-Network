"""Recompute firmware/manifest.json service_files_sha256 for the packaged tree.

The packaged launcher (app/start/launcher.py) freezes every .py/.js/.css/.html/.json file
under app/services in that hash map and refuses to start on any mismatch or any unhashed
file. Replacing the frontend/backend and adding the card/flash tools therefore requires
regenerating the map; everything else in the manifest is left untouched.
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
SERVICES = ROOT / "app" / "services"
MANIFEST = ROOT / "firmware" / "manifest.json"
SUFFIXES = {".py", ".js", ".css", ".html", ".json"}


def collect():
    out = {}
    for path in sorted(SERVICES.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts:
            continue
        if path.suffix.lower() not in SUFFIXES:
            continue
        rel = path.relative_to(SERVICES).as_posix()
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main():
    if not MANIFEST.is_file():
        print("no manifest:", MANIFEST)
        return 2
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    before = data.get("service_files_sha256") or {}
    after = collect()

    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])

    print("entries: %d -> %d" % (len(before), len(after)))
    for label, items in (("added", added), ("removed", removed), ("changed", changed)):
        print("%-8s %d" % (label, len(items)))
        for item in items[:20]:
            print("   ", item)

    if "--dry-run" in sys.argv:
        return 0

    data["service_files_sha256"] = after
    MANIFEST.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("updated", MANIFEST)
    return 0


if __name__ == "__main__":
    sys.exit(main())
