"""Bounded ns-3.46 B0 runner. Only stdlib; no simulator replacement or installer."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUTPUTS = ROOT / "simulation/outputs/E2-011"
DATA = ROOT / "data/agent_native/E2-011"
CONFIG = json.loads((HERE / "config.json").read_text(encoding="utf-8"))


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inside(path, parent):
    p, base = Path(path).resolve(), Path(parent).resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Path outside task scope: {p}")
    return p


def fresh(path):
    p = inside(path, OUTPUTS)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.mkdir(exist_ok=False)
    return p


def new_manifest(out, action):
    m = json.loads((ROOT / "coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8"))
    tracked = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout.splitlines()
    # Record existing dirty files without treating other windows' work as our output.
    dirty = {}
    for row in tracked:
        rel = row[3:].strip('"')
        path = ROOT / rel
        if path.is_file():
            dirty[rel] = sha(path)
    m.update(template_only=False, task_id="E2-011", run_id=out.name, started_at=now(),
             worktree=str(ROOT), git_commit=subprocess.check_output(
                 ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
             dirty_files_sha256=dirty, command=sys.argv, python_executable=sys.executable,
             dependency_snapshot={"platform": platform.platform(), "python": sys.version},
             upstream_commit=None, config_file=str(HERE / "config.json"),
             seeds=[], budget={"simulations": 3, "dynamic": 2, "smoke": 1,
                               "simulation_seconds_each": 60, "build_wall_seconds": 900},
             output_directory=str(out), process_id=os.getpid(), status="running",
             action=action, source_hashes={p.name: sha(p) for p in HERE.iterdir() if p.is_file()},
             limitations=list(CONFIG["limitations"]))
    dump(out / "manifest.json", m)
    return m


def command(cmd, cwd, log_prefix, timeout):
    start = time.monotonic()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["CCACHE_DIR"] = str(DATA / "ccache")
    env["TMP"] = str(DATA / "tmp")
    env["TEMP"] = env["TMP"]
    Path(env["TMP"]).mkdir(parents=True, exist_ok=True)
    # Avoid an unrelated Anaconda/GCC runtime winning DLL lookup. Only this
    # child process gets the toolchain/runtime prefix; never change global PATH.
    compiler = shutil.which("g++")
    prefix = [str(DATA / "ns-3.46/build/lib")]
    if compiler:
        prefix.append(str(Path(compiler).parent))
    env["PATH"] = os.pathsep.join(prefix + [env.get("PATH", "")])
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    with Path(str(log_prefix) + ".stdout.txt").open("w", encoding="utf-8") as so, \
            Path(str(log_prefix) + ".stderr.txt").open("w", encoding="utf-8") as se:
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=so, stderr=se, **options)
        dump(Path(str(log_prefix) + ".started.json"), {"command": cmd, "process_id": p.pid, "started_at": now(), "child_path_prefix": prefix})
        timed_out = False
        try:
            code = p.wait(timeout=max(0.1, timeout))
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                os.killpg(p.pid, signal.SIGKILL)
            code = p.wait()
    record = {"command": cmd, "cwd": str(cwd), "process_id": p.pid,
              "exit_code": code, "timed_out": timed_out, "wall_seconds": time.monotonic() - start}
    dump(Path(str(log_prefix) + ".command.json"), record)
    return record


def source_root(value):
    p = inside(value, DATA)
    if (p / "VERSION").read_text(encoding="utf-8").strip() != CONFIG["ns3_version"]:
        raise ValueError("Expected exact VERSION 3.46, not a rolling or patch version")
    return p


def preflight(out):
    info = {"platform": platform.platform(), "python": sys.executable,
            "tools": {x: shutil.which(x) for x in ("cmake", "ninja", "g++", "mingw32-make", "wsl")},
            "global_environment_modified": False, "simulations_run": 0}
    for tool in ("cmake", "ninja", "g++"):
        if info["tools"][tool]:
            command([tool, "--version"], ROOT, out / tool, 15)
    if os.name == "nt":
        # Inventory only. Never call `wsl -d`, launch Docker, or install a distro.
        r = subprocess.run(["wsl.exe", "--list", "--verbose"], capture_output=True, timeout=20)
        def decode(b):
            return b.decode("utf-16-le" if b.count(b"\0") > len(b) // 8 else "utf-8", errors="replace")
        info["wsl_inventory"] = {"exit_code": r.returncode, "stdout": decode(r.stdout), "stderr": decode(r.stderr)}
        info["windows_build_candidate"] = all(info["tools"][x] for x in ("cmake", "ninja", "g++"))
    dump(out / "environment.json", info)
    return {"status": "environment_recorded", "environment": info}


def acquire(out):
    DATA.mkdir(parents=True, exist_ok=True)
    archive = DATA / "ns-3.46.tar.bz2"
    if archive.exists() or (DATA / "ns-3.46").exists():
        raise ValueError("Source acquisition refuses existing archive/tree; preserve and inspect it")
    received = 0
    request = urllib.request.Request(CONFIG["source_archive_url"], headers={"User-Agent": "E2-011-source-freeze"})
    with urllib.request.urlopen(request, timeout=30) as response, archive.open("xb") as f:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            received += len(block)
            if received > CONFIG["source_archive_max_bytes"]:
                raise ValueError("Source exceeds 100 MiB budget; partial archive retained")
            f.write(block)
    dump(out / "download.json", {"url": CONFIG["source_archive_url"], "bytes": received, "sha256": sha(archive)})
    return extract_source(out)


def extract_source(out):
    archive = DATA / "ns-3.46.tar.bz2"
    if archive.stat().st_size > CONFIG["source_archive_max_bytes"]:
        raise ValueError("Source archive exceeds budget")
    if (DATA / "ns-3.46").exists():
        raise ValueError("Refusing to overwrite an existing source tree")
    skipped = []
    with tarfile.open(archive, "r:bz2") as tar:
        members = []
        for member in tar.getmembers():
            inside(DATA / member.name, DATA)
            if member.issym() and member.name in (
                    "ns-3.46/doc/tutorial/source/figures", "ns-3.46/doc/manual/source/figures"):
                # Documentation-only convenience symlinks cannot be created by
                # unprivileged Windows tar extraction. They are not build inputs.
                skipped.append({"name": member.name, "target": member.linkname})
                continue
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("Unexpected archive link/device")
            members.append(member)
        tar.extractall(DATA, members=members)
    source = source_root(DATA / "ns-3.46")
    record = {"url": CONFIG["source_archive_url"], "bytes": archive.stat().st_size, "sha256": sha(archive),
              "archive": str(archive), "tree": str(source), "version": "3.46", "tag": "ns-3.46",
              "acquired_at": now(), "skipped_documentation_symlinks": skipped,
              "verification": "official HTTPS archive, exact VERSION, local SHA-256; no independently published digest compared",
              "files": {name: sha(source / name) for name in ("VERSION", "RELEASE_NOTES.md", "ns3")}}
    dump(out / "source.json", record)
    dump(DATA / "SOURCE.json", record)
    return {"status": "source_acquired", "source": record}


def build(out, tree):
    tree = source_root(tree)
    budget_file = DATA / "BUILD_BUDGET.json"
    used = json.loads(budget_file.read_text()).get("wall_seconds", 0) if budget_file.exists() else 0
    if used >= 900:
        raise ValueError("15-minute cumulative build budget exhausted")
    target = tree / "scratch/b0-aodv.cc"
    if target.exists() and sha(target) != sha(HERE / "b0-aodv.cc"):
        # This file is our exclusive staging copy, not upstream code. Preserve old bytes.
        shutil.copyfile(target, out / "previous-staged-b0-aodv.cc")
    shutil.copyfile(HERE / "b0-aodv.cc", target)
    start = time.monotonic()
    records = []
    try:
        cmds = [[sys.executable, "ns3", "configure", "--enable-modules=" + ";".join(CONFIG["modules"]),
                 "--disable-examples", "--disable-tests", "-G", "Ninja", "--", "-DCMAKE_CXX_COMPILER=g++",
                 "-DNS3_CCACHE=OFF", "-DPython3_EXECUTABLE=" + sys.executable,
                 "-DCMAKE_CXX_FLAGS=-include algorithm"],
                [sys.executable, "ns3", "build", "b0-aodv", "-j", "4"]]
        for i, cmd in enumerate(cmds):
            left = 900 - used - (time.monotonic() - start)
            if left <= 0:
                raise TimeoutError("Cumulative build deadline reached")
            result = command(cmd, tree, out / f"build-{i}", left)
            records.append(result)
            if result["exit_code"]:
                raise RuntimeError(f"Build command {i} failed; logs preserved")
        freeze = {"tree": str(tree), "ns3_version": "3.46", "entry_sha256": sha(target),
                  "config_sha256": sha(HERE / "config.json"), "built_at": now(),
                  "upstream_archive_sha256": sha(DATA / "ns-3.46.tar.bz2") if (DATA / "ns-3.46.tar.bz2").exists() else None}
        dump(DATA / "BUILD.json", freeze)
        return {"status": "built", "freeze": freeze, "commands": records}
    finally:
        dump(budget_file, {"wall_seconds": used + time.monotonic() - start, "last_output": str(out)})


def reserve(mode, seed, supplement=False):
    allowed = CONFIG["allowed_dynamic_seeds"] if mode == "dynamic" else CONFIG["allowed_smoke_seeds"]
    if seed not in allowed:
        raise ValueError("Seed outside finite micro-scenario budget")
    directory = OUTPUTS / ".reservations"
    directory.mkdir(parents=True, exist_ok=True)
    if supplement and mode != "dynamic":
        raise ValueError("M supplement allows only original dynamic seeds, no smoke retry")
    record = directory / f"{mode}-{seed}{'-M-supplement' if supplement else ''}.json"
    with record.open("x", encoding="utf-8") as f:
        json.dump({"mode": mode, "seed": seed, "reserved_at": now(), "attempt_counts_even_if_failed": True,
                   "M_supplement": supplement, "authorization": "coordination/tasks/E2-011.md: M extra two startup checks, total five" if supplement else "original three-start budget"}, f)


def analyze_events(events, mode):
    """No simulator calls. Invariants and partition/recovery checks from real logs."""
    errors = []
    generated, results, received, delivered = {}, {}, {}, {}
    forwards = defaultdict(list)
    frames, intervals = [], []
    ends = []
    for e in events:
        t = e.get("t_s", 0)
        if not math.isfinite(t) or t < 0 or t > 60.000001:
            errors.append("invalid_event_time")
        k = e["kind"]
        if k == "app_generated":
            if e["seq"] in generated: errors.append("duplicate_generated")
            generated[e["seq"]] = e
        elif k == "socket_result":
            if e["seq"] in results: errors.append("duplicate_socket_result")
            results[e["seq"]] = e
        elif k == "app_rx":
            if e["seq"] in received: errors.append("duplicate_app_rx")
            received[e["seq"]] = e
        elif k == "ip_deliver":
            if e["seq"] in delivered: errors.append("duplicate_ip_deliver")
            delivered[e["seq"]] = e
        elif k == "ip_forward": forwards[e["seq"]].append(e)
        elif k == "phy_tx": frames.append(e)
        elif k == "phy_tx_interval": intervals.append(e)
        elif k == "simulation_end": ends.append(e)
    expected = set(range(CONFIG["application"]["count"]))
    if set(generated) != expected: errors.append("generated_sequence_not_complete_110")
    if set(results) != set(generated): errors.append("socket_results_not_conserved")
    for seq, g in generated.items():
        if abs(g["t_s"] - (5 + seq * .5)) > 1e-7 or g["bytes"] != 512:
            errors.append("source_schedule_or_size_mismatch")
    accepted = {s for s, e in results.items() if e["return_bytes"] == 512}
    rejected = set(results) - accepted
    for seq, e in received.items():
        if seq not in accepted or seq not in delivered:
            errors.append("receive_without_accepted_source_and_ip_delivery")
            continue
        if e["bytes"] != 512 or abs(e["generated_s"] - generated[seq]["t_s"]) > 1e-7 or e["t_s"] < e["generated_s"]:
            errors.append("receive_payload_or_causality_mismatch")
        hops = 65 - delivered[seq]["ttl"]
        if mode == "dynamic" and (hops != 2 or not any(f["node"] == 1 and f["t_s"] <= e["t_s"] for f in forwards[seq])):
            errors.append("missing_actual_two_hop_relay_evidence")
        if mode == "smoke" and hops != 1: errors.append("smoke_not_one_hop")
    if set(delivered) != set(received): errors.append("ip_application_delivery_mismatch")
    partition_rx = [e for e in received.values() if 22 <= e["t_s"] <= 38]
    if mode == "dynamic" and partition_rx: errors.append("delivery_during_physical_partition")
    pre = [e for e in received.values() if e["t_s"] < 19]
    post = [e for e in received.values() if e["t_s"] >= 42 and e["generated_s"] >= 42]
    if not pre: errors.append("no_initial_delivery")
    if mode == "dynamic" and len(post) < 3: errors.append("no_three_fresh_recovery_deliveries")
    if len(ends) != 1 or abs(ends[0]["t_s"] - 60) > 1e-7: errors.append("missing_clean_simulation_end")
    # A frame is joined with the TX-state interval at the same node/start timestamp.
    # 802.11a has no aggregation/MU here; never infer time from a nominal bitrate.
    joined = []
    partial_attempts = 0
    for f in frames:
        match = [x for x in intervals if x["node"] == f["node"] and abs(x["start_s"] - f["t_s"]) < 1e-8]
        if len(match) != 1: errors.append("unmatched_phy_transmission_interval")
        else:
            duration = match[0]["duration_s"]
            if not math.isfinite(duration) or duration <= 0:
                errors.append("invalid_phy_duration")
                continue
            elapsed = max(0., min(duration, 60 - match[0]["start_s"]))
            partial_attempts += elapsed < duration - 1e-12
            joined.append({**f, "airtime_s": elapsed})
    if len(joined) != len(intervals): errors.append("unmatched_phy_state_interval")
    categories = {}
    for category in sorted({x["category"] for x in joined}):
        xs = [x for x in joined if x["category"] == category]
        categories[category] = {"attempts": len(xs), "frame_bytes": sum(x["frame_bytes"] for x in xs),
                                "airtime_s": sum(x["airtime_s"] for x in xs)}
    if not categories.get("aodv", {}).get("attempts"): errors.append("missing_actual_aodv_control_cost")
    if not categories.get("application", {}).get("attempts"): errors.append("missing_actual_application_tx")
    not_received = accepted - set(received)
    if len(generated) != len(rejected) + len(received) + len(not_received): errors.append("application_conservation_failed")
    terminals = []
    for seq in sorted(generated):
        rx = received.get(seq)
        status = "socket_rejected" if seq in rejected else "not_received_by_stop"
        if rx:
            status = "delivered_on_time" if rx["t_s"] <= generated[seq]["t_s"] + 2 else "delivered_late"
        terminals.append({"seq": seq, "status": status, "generated_s": generated[seq]["t_s"],
                          "deadline_s": generated[seq]["t_s"] + 2, "received_s": rx["t_s"] if rx else None})
    return {"passed": not errors, "errors": sorted(set(errors)), "mode": mode,
            "generated": len(generated), "socket_accepted": len(accepted), "socket_rejected": len(rejected),
            "received_unique": len(received), "not_received_by_stop": len(not_received),
            "initial_deliveries": len(pre), "partition_deliveries": len(partition_rx),
            "fresh_recovery_deliveries": len(post),
            "first_fresh_delivery_after_42_s": min((e["t_s"] for e in post), default=None),
            "hop_histogram_received": dict(Counter(65 - delivered[s]["ttl"] for s in received if s in delivered)),
            "actual_phy_cost_by_category": categories, "request_terminals": terminals,
            "tx_attempts_truncated_by_stop": partial_attempts,
            "frame_byte_scope": "full MPDU sizes of started attempts; airtime clipped to observed 60 s; partial attempts separately counted",
            "scope": "engineering UDP probe accounting; no Agent inference/consumption or performance benchmark"}


def analyze(out, raw, mode):
    raw = inside(raw, OUTPUTS)
    with (raw / "events.jsonl").open(encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    result = analyze_events(events, mode)
    result["input_events_sha256"] = sha(raw / "events.jsonl")
    dump(out / "verification.json", result)
    return {"status": "verified" if result["passed"] else "verification_failed", "verification": result}


def run(out, tree, mode, seed, supplement=False):
    tree = source_root(tree)
    freeze = json.loads((DATA / "BUILD.json").read_text(encoding="utf-8"))
    if freeze["entry_sha256"] != sha(HERE / "b0-aodv.cc") or freeze["entry_sha256"] != sha(tree / "scratch/b0-aodv.cc"):
        raise ValueError("Entry differs from successful build freeze; rebuild before spending run budget")
    if freeze["config_sha256"] != sha(HERE / "config.json"):
        raise ValueError("Configuration differs from successful build freeze")
    reserve(mode, seed, supplement)
    raw = out / "raw"
    # Execute the already-built native binary as an argv list, without a shell.
    # ns-3.46 CommandLine UserItemParse<std::string> uses `iss >> dest`, so even
    # a correctly quoted absolute path is truncated at whitespace. A relative
    # path removes the common workspace component containing a space.
    executable = tree / "build/scratch" / ("ns3.46-b0-aodv-default.exe" if os.name == "nt" else "ns3.46-b0-aodv-default")
    if not executable.is_file():
        raise ValueError("Expected exact-version, default-profile B0 binary is missing")
    dump(out / "binary.json", {"path": str(executable), "sha256": sha(executable),
                              "built_from_entry_sha256": freeze["entry_sha256"]})
    relative_raw = os.path.relpath(raw, tree)
    if any(c.isspace() for c in relative_raw):
        raise ValueError("B0 output argument must have no whitespace after relative-path conversion")
    if (tree / relative_raw).resolve() != raw.resolve():
        raise ValueError("Relative output did not resolve to the fresh task output")
    cmd = [str(executable), f"--output={relative_raw}", f"--mode={mode}", f"--seed={seed}"]
    r = command(cmd, tree, out / "simulation", CONFIG["run_wall_seconds"])
    if r["exit_code"]:
        raise RuntimeError("Simulation failed; attempt and output retained")
    return analyze(out, raw, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["preflight", "acquire", "extract", "build", "check", "run", "analyze"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ns3-root", type=Path, default=DATA / "ns-3.46")
    parser.add_argument("--mode", choices=["dynamic", "smoke"], default="dynamic")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--M-supplement", action="store_true", help="Only the task-card-approved extra dynamic startup checks")
    args = parser.parse_args()
    out = fresh(args.output)
    m = new_manifest(out, args.action)
    code = 0
    try:
        if args.action == "preflight": result = preflight(out)
        elif args.action == "acquire": result = acquire(out)
        elif args.action == "extract": result = extract_source(out)
        elif args.action == "build": result = build(out, args.ns3_root)
        elif args.action == "check":
            r = command([sys.executable, "-B", "-m", "unittest", "discover", "-s", str(HERE),
                         "-p", "test_*.py", "-v"], ROOT, out / "unit-checks", 30)
            if r["exit_code"]: raise RuntimeError("Checker unit tests failed; logs preserved")
            result = {"status": "checker_unit_tests_passed", "scope": "synthetic log fixtures, not wireless simulation", "command": r}
        elif args.action == "run":
            m["seeds"] = [args.seed]
            if args.M_supplement:
                m["budget"].update(simulations=5, additional_dynamic_start_checks=2,
                                   authorization="M explicit E2-011 task-card supplement; original failures retained")
            dump(out / "manifest.json", m)
            result = run(out, args.ns3_root, args.mode, args.seed, args.M_supplement)
        else:
            if not args.raw: raise ValueError("--raw is required")
            result = analyze(out, args.raw, args.mode)
        if result["status"] == "verification_failed": code = 1
        m["status"] = result["status"]
        dump(out / "result.json", result)
    except Exception as exc:
        code = 1
        m["status"] = "failed"
        dump(out / "failure.json", {"type": type(exc).__name__, "message": str(exc)})
    finally:
        m.update(finished_at=now(), exit_code=code)
        source = DATA / "SOURCE.json"
        if source.exists():
            record = json.loads(source.read_text(encoding="utf-8"))
            m["upstream_commit"] = CONFIG["upstream_commit"]
            m["upstream_tag"] = record["tag"]
            m["data_and_weights_sha256"] = {"ns3_source_archive": record["sha256"]}
        m["output_hashes"] = {str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file() and p.name != "manifest.json"}
        dump(out / "manifest.json", m)
    print(json.dumps({"output": str(out), "status": m["status"], "exit_code": code}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
