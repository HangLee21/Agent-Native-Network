"""C-017 frozen E1 host/core checks. No ESP target, serial, RF or author output writes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
SRC = ROOT / "firmware/agent_native"
assert OUT.parent == ROOT / "simulation/outputs/C-017"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def main():
    began = time.monotonic()
    expected = json.loads((ROOT / "coordination/reviews/M-016-verification.json").read_text("utf-8-sig"))["frozen"]["E1_lifecycle_v4"]
    if any(sha(ROOT / path) != value for path, value in expected.items()):
        raise RuntimeError("E1 full freeze mismatch; no compilation")
    manifest = json.loads((ROOT / "coordination/templates/RUN_MANIFEST.json").read_text("utf-8-sig"))
    manifest.update(template_only=False, task_id="C-017", run_id=OUT.name,
                    started_at=datetime.now(timezone.utc).isoformat(), worktree=str(ROOT),
                    git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, timeout=2, text=True).strip(),
                    command=[sys.executable, "-B", str(Path(__file__).resolve())],
                    python_executable=sys.executable, output_directory=str(OUT), evidence_kind="synthetic_host",
                    dirty_files_sha256=expected | {str(p.relative_to(ROOT)): sha(p) for p in (Path(__file__), OUT / "audit_cases.c")},
                    budget={"per_child_seconds": 60, "run_seconds": 90, "task_seconds": 600, "bytes": 104857600},
                    dependency_snapshot={"python": sys.version, "gcc": shutil.which("gcc")},
                    status="running", review_reference="coordination/reviews/C-017.md",
                    limitations=["Host compilation only, no ESP-IDF target build", "No serial, RF, model or old simulation",
                                 "Prepopulated local route fixture is not an online global-topology oracle"])
    save("RUN_MANIFEST.started.json", manifest)
    steps = []
    error = None

    def run(label, args, accepted=(0,), stdin=None):
        if time.monotonic() - began >= 90:
            raise RuntimeError("C run budget exhausted")
        start = time.monotonic()
        with (OUT / (label + ".txt")).open("x", encoding="utf-8") as log:
            result = subprocess.run([str(item) for item in args], cwd=ROOT, input=stdin, text=True,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    timeout=min(60, 90 - (time.monotonic() - began)))
        steps.append({"label": label, "command": [str(item) for item in args], "exit_code": result.returncode,
                      "wall_seconds": time.monotonic() - start})
        if result.returncode not in accepted:
            raise RuntimeError(label + " unexpected exit " + str(result.returncode))
        return result.returncode

    try:
        gcc = shutil.which("gcc")
        if not gcc:
            raise RuntimeError("existing host compiler absent; no installation")
        options = [gcc, "-std=c99", "-Wall", "-Wextra", "-Wpedantic", "-Werror", "-I", SRC / "include", "-I", SRC / "src"]
        run("build_host", options + [SRC / "src/ann.c", SRC / "src/ann_console.c", SRC / "src/ann_log.c", SRC / "host/main.c", "-o", OUT / "ann_host.exe"])
        run("build_cases", options + [SRC / "src/ann.c", OUT / "audit_cases.c", "-o", OUT / "audit_cases.exe"])
        run("build_lifecycle", options + [SRC / "src/ann.c", SRC / "host/lifecycle_regressions.c", "-o", OUT / "lifecycle.exe"])
        run("lifecycle", [OUT / "lifecycle.exe"])
        run("author_scenarios", [OUT / "ann_host.exe", "--scenario", "all"])
        records = [json.loads(line) for line in (OUT / "author_scenarios.txt").read_text("utf-8").splitlines()]
        cases = [row for row in records if row.get("schema") == "ann.test.v1" and "scenario" in row]
        assert len(cases) == 12 and all(row["passed"] for row in cases) and records[-1]["failures"] == 0
        stdin = '{"cmd":"info","nonce":"probe123"}\n{"cmd":"stats","nonce":"s"}\n' + '{"cmd":"info","nonce":"bad"}\x00tail\n' + 'x' * 1023 + '{"cmd":"info","nonce":"tail"}\n' + '{"cmd":"info","nonce":"after"}\r\n'
        run("console", [OUT / "ann_host.exe", "--console"], stdin=stdin)
        console = [json.loads(line) for line in (OUT / "console.txt").read_text("utf-8").splitlines()]
        assert len(console) == 5 and console[0]["chip"] == "host-synthetic" and console[0]["mode"] == "idle"
        assert console[2]["event"] == console[3]["event"] == "error" and console[4]["nonce"] == "after"
        run("independent_cases", [OUT / "audit_cases.exe"], accepted=(0, 1))
        independent = [json.loads(line) for line in (OUT / "independent_cases.txt").read_text("utf-8").splitlines()]
        assert len(independent) == 3
        provenance = json.loads((SRC / "golden/provenance.json").read_text("utf-8"))
        original = ROOT / provenance["source"]
        golden = SRC / "golden/serial-v1.jsonl"
        assert sha(original) == provenance["source_sha256"] and sha(golden) == provenance["golden_sha256"]
        original_lines = original.read_bytes().splitlines()
        golden_lines = golden.read_bytes().splitlines()
        assert len(golden_lines) == len(provenance["events"]) == 12
        assert all(line == original_lines[event["source_line"] - 1] for line, event in zip(golden_lines, provenance["events"]))
        summary = {"schema": "C-017.E1-v4-audit/1", "author_scenarios": len(cases), "author_summary": records[-1],
                   "console_framing_passed": True, "golden_verbatim_lines": len(golden_lines),
                   "independent_cases": independent, "target_compilation": "not_performed", "hardware_runs": 0}
        lifecycle = json.loads((OUT / "lifecycle.txt").read_text("utf-8").splitlines()[-1])
        assert lifecycle["checks"] == 164 and lifecycle["failures"] == 0
        summary["lifecycle"] = lifecycle
        save("summary.json", summary)
        code = 0 if all(case["passed"] for case in independent) else 1
    except Exception as exc:
        error = repr(exc)
        code = 1
        save("failure.json", {"error": error})
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(), exit_code=code,
                    status="passed" if code == 0 else ("findings_reproduced" if error is None else "failed"),
                    elapsed_seconds=time.monotonic() - began, steps=steps, error=error,
                    frozen_unchanged_after=all(sha(ROOT / path) == value for path, value in expected.items()))
    save("RUN_MANIFEST.json", manifest)
    size = sum(path.stat().st_size for path in OUT.rglob("*") if path.is_file())
    if size > 104857600:
        raise RuntimeError("output cap exceeded; stop")
    print(json.dumps({"status": manifest["status"], "elapsed_seconds": manifest["elapsed_seconds"], "output_bytes": size,
                      "frozen_unchanged_after": manifest["frozen_unchanged_after"], "error": error}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
