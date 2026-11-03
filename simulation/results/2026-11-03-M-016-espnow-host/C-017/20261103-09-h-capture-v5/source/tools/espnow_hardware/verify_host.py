"""One finite synthetic test run with source hashes and preserved output."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from . import hardware_tool as h
from . import analysis_bridge

# Explicit M approval is needed to extend this map. No arbitrary active key is trusted.
AUTHORIZED_RELEASES = {
    "E1_full_v3": "f38bee27cec54b9ea6e5627db4036f6b3a7aff4100b306a94051825450dbd251",
    "E1_lifecycle_v4": "3b028fb77103ad011a92e0fdb7f34d4065a940806240ad570f7f30e21c2d908f"
}


def check_active_release(root):
    """Verify M's active key, the approved release anchor, and every source hash."""
    root = Path(root).resolve()
    registry = h.read_json(root / "coordination/reviews/M-016-verification.json")
    active = registry.get("active_freezes", {}).get("E1")
    if not isinstance(active, str) or active not in AUTHORIZED_RELEASES:
        raise ValueError("unknown or unapproved active E1 version")
    frozen = registry.get("frozen", {}).get(active)
    prefix = "firmware/agent_native/"
    anchor = prefix + "FREEZE.json"
    if not isinstance(frozen, dict) or frozen.get(anchor) != AUTHORIZED_RELEASES[active]:
        raise ValueError("active E1 release anchor is not approved")
    if h.sha(root / anchor) != AUTHORIZED_RELEASES[active]:
        raise ValueError("active E1 FREEZE.json drift")
    release = h.read_json(root / anchor)
    sources = release.get("source_hashes")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("release source hash set missing")
    expected = {prefix + key: value for key, value in sources.items()}
    expected[anchor] = AUTHORIZED_RELEASES[active]
    if frozen != expected:
        raise ValueError("M snapshot differs from approved release source set")
    checked = {}
    base = (root / prefix).resolve()
    for key, value in frozen.items():
        target = (root / key).resolve()
        if not target.is_relative_to(base) or not key.startswith(prefix) or ".." in Path(key).parts:
            raise ValueError("release path escapes firmware directory")
        checked[key] = {"expected": value, "actual": h.sha(target)}
    if any(item["expected"] != item["actual"] for item in checked.values()):
        raise ValueError("active E1 source drift; stop integration")
    return {"active_key": active, "anchor_sha256": AUTHORIZED_RELEASES[active], "checked": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != (h.ROOT / "simulation/outputs/H-001").resolve():
        parser.error("expected new H-001 run directory")
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    manifest = h.read_json(h.ROOT / "coordination/templates/RUN_MANIFEST.json")
    command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tools/espnow_hardware/tests", "-v"]
    manifest.update(template_only=False, task_id="H-001", run_id=out.name, started_at=h.now(),
                    worktree=str(h.ROOT), command=command, python_executable=sys.executable,
                    dirty_files_sha256=h.source_hashes(), evidence_kind="synthetic",
                    budget={"command_timeout_seconds": 120, "cumulative_task_limit_seconds": 600},
                    output_directory=str(out), status="running")
    environment = {"python": sys.version, "tools_in_path": {tool: shutil.which(tool) for tool in
                   ("idf.py", "xtensa-esp32s3-elf-gcc", "cmake", "ninja")},
                   "scope": "PATH only; no installation or target compiler invocation",
                   "target_compilation": "not_verified", "radio_run": False}
    exit_code = 1
    try:
        h.write_json(out / "environment.json", environment)
        # Check before and after tests. Do not silently fall back to an older freeze.
        release = check_active_release(h.ROOT)
        h.write_json(out / "active_release_before.json", release)
        _, analyzer_before = analysis_bridge.load_analyzer(h.ROOT)
        h.write_json(out / "analyzer_release_before.json", analyzer_before)
        result = subprocess.run(command, cwd=h.ROOT, capture_output=True, timeout=120)
        (out / "stdout.txt").write_bytes(result.stdout)
        (out / "stderr.txt").write_bytes(result.stderr)
        after = check_active_release(h.ROOT)
        if after != release:
            raise ValueError("active E1 release changed during verification")
        _, analyzer_after = analysis_bridge.load_analyzer(h.ROOT)
        if analyzer_after != analyzer_before:
            raise ValueError("active E2 analyzer changed during verification")
        h.write_json(out / "analyzer_release_after.json", analyzer_after)
        h.write_json(out / "active_release_after.json", after)
        manifest["git_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=h.ROOT,
                            capture_output=True, text=True, check=True, timeout=2).stdout.strip()
        exit_code = result.returncode
        manifest["status"] = "passed" if exit_code == 0 else "failed"
    except Exception as exc:
        manifest.update(status="verification_failed", error=type(exc).__name__ + ": " + str(exc))
    finally:
        manifest.update(finished_at=h.now(), exit_code=exit_code, elapsed_seconds=time.monotonic() - started,
                        dependency_snapshot=environment,
                        limitations=["Synthetic host tests only", "No ESP target compilation", "No physical serial port opened", "No RF measurements"])
        h.write_json(out / "RUN_MANIFEST.json", manifest)
    print(json.dumps({"status": manifest["status"], "output": str(out), "exit_code": exit_code}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
