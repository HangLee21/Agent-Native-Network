"""Create one common offline path table, for deployment separately on each local board."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

LABELS = {
    "A": "90:da:72:48:a4:f8", "B": "90:da:72:48:a5:cc", "C": "90:da:72:48:a4:e0",
    "D": "90:da:72:48:a5:20", "E": "90:da:72:48:a6:98",
}

def make(path: list[str], reverse: bool, profile_id: str, autostart: bool = True) -> dict:
    nodes = [LABELS.get(p.upper(), p.lower()) for p in path]
    macs = [bytes.fromhex(n.replace(":", "")) for n in nodes]
    if not 2 <= len(nodes) <= 5 or len(set(macs)) != len(macs):
        raise ValueError("path must contain 2..5 distinct nodes")
    if any(len(m) != 6 or m[0] & 1 or not any(m) for m in macs):
        raise ValueError("all MACs must be nonzero unicast addresses")
    if not 1 <= len(profile_id) <= 64 or any(not 32 <= ord(c) <= 126 for c in profile_id):
        raise ValueError("profile_id must be 1..64 printable ASCII characters")
    n, k = len(nodes), 2 if reverse else 1
    pairs = [(0, n-1)] + ([(n-1, 0)] if reverse else [])
    table = bytearray([n, k]) + b"".join(macs) + bytes(v for pair in pairs for v in pair)
    for f in range(k):
        for i in range(n):
            for j in range(n):
                edge = j == i+1 if f == 0 else j == i-1
                table += struct.pack("<H", 65535 if edge else 0)
    return dict(cmd="deploy", nonce="deploy-" + hashlib.sha256(table).hexdigest()[:12],
                profile_id=profile_id, table_hex=table.hex(), autostart=autostart)

def main() -> None:
    started=dt.datetime.now(dt.timezone.utc).isoformat()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--path", nargs="+", required=True, help="ordered board labels A..E or MAC addresses")
    p.add_argument("--reverse", action="store_true", help="add a second flow along the reverse path")
    p.add_argument("--profile-id", required=True)
    p.add_argument("--no-autostart", action="store_true")
    p.add_argument("--output", type=Path, required=True, help="new output directory; must not exist")
    a = p.parse_args()
    command = make(a.path, a.reverse, a.profile_id, not a.no_autostart)
    a.output.mkdir(parents=True, exist_ok=False)
    (a.output / "deploy.json").write_text(json.dumps(command, indent=2) + "\n", encoding="utf-8")
    (a.output / "deploy.jsonl").write_text(json.dumps(command, separators=(",", ":")) + "\n", encoding="utf-8")
    (a.output / "profile.json").write_text(json.dumps(dict(
        schema="mid.edge.profile.v1", path=a.path, macs=[LABELS.get(n.upper(), n.lower()) for n in a.path],
        reverse=a.reverse, deployment_mode="offline_table", publisher_boot_required=False,
        table_sha256=hashlib.sha256(bytes.fromhex(command["table_hex"])).hexdigest(),
        command_file="deploy.json", limitation="Explicit static paths; no online planner, ACK or delivery guarantee."
    ), indent=2) + "\n", encoding="utf-8")
    root=Path(__file__).resolve().parents[3]
    manifest=json.loads((root/"coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
    manifest.update(template_only=False,task_id="E1-023",run_id=a.output.name,started_at=started,
        finished_at=dt.datetime.now(dt.timezone.utc).isoformat(),worktree=str(root),
        git_commit=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip(),
        command=sys.argv,python_executable=sys.executable,output_directory=str(a.output.resolve()),
        status="passed",exit_code=0,budget=dict(downloads=0,device_access=0),
        dirty_files_sha256={str(Path(__file__).resolve().relative_to(root)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        limitations=["Offline explicit table bytes only; no device, NVS, radio or measured link validation."])
    (a.output/"RUN_MANIFEST.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(a.output.resolve())

if __name__ == "__main__":
    main()
