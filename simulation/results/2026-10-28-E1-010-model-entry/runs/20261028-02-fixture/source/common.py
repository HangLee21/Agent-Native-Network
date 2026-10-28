"""Output containment, run provenance and read-only inventory for E1-010."""
from __future__ import annotations

import ctypes
from datetime import datetime, timezone
import importlib.metadata
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

from .runtime import sha, write_json

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT / "simulation/outputs/E1-010"
DATA_ROOT = ROOT / "data/agent_native/E1-010"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def inventory():
    result = dict(python_executable=sys.executable, python_version=sys.version,
                  platform=platform.platform(), logical_cpu=os.cpu_count(),
                  cpu_identifier=os.environ.get("PROCESSOR_IDENTIFIER"), packages={})
    for name in ("torch", "transformers", "Pillow", "huggingface-hub", "safetensors", "numpy"):
        try:
            result["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][name] = None
    if sys.platform == "win32":
        class Memory(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total_physical", "free_physical", "total_page", "free_page", "total_virtual", "free_virtual", "extended")]
        memory = Memory()
        memory.length = ctypes.sizeof(memory)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            result.update(physical_ram_bytes=memory.total_physical, free_ram_bytes=memory.free_physical)
    result["workspace_disk_free_bytes"] = shutil.disk_usage(ROOT).free
    command = ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader"]
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=15, encoding="utf-8", errors="replace")
        result["gpu_query"] = dict(command=command, exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["gpu_query"] = dict(command=command, error=str(exc))
    return result


def new_run(output, kind, budget, config_file=None):
    out = Path(output).resolve()
    if not out.is_relative_to(OUTPUT_ROOT.resolve()) or out == OUTPUT_ROOT.resolve():
        raise ValueError("output must be a new run directory below simulation/outputs/E1-010")
    out.mkdir(parents=True, exist_ok=False)
    manifest = __import__("json").loads((ROOT / "coordination/templates/RUN_MANIFEST.json").read_text(encoding="utf-8-sig"))
    manifest.update(template_only=False, task_id="E1-010", run_id=out.name, started_at=utc_now(),
                    worktree=str(ROOT), command=[sys.executable, *sys.argv],
                    python_executable=sys.executable, config_file=str(config_file) if config_file else None,
                    seeds=[0], budget=budget, output_directory=str(out), process_id=os.getpid(),
                    status="running", entry_kind=kind, source_hashes={},
                    limitations=["P2 preparation only; no physical wireless or autonomous-agent performance claim"])
    try:
        manifest["git_commit"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, timeout=10).strip()
    except (OSError, subprocess.SubprocessError) as exc:
        manifest["git_commit_unavailable"] = str(exc)
    source_dir = out / "source"
    source_dir.mkdir()
    for path in sorted(Path(__file__).parent.iterdir()):
        if path.is_file() and path.suffix in {".py", ".json"}:
            data = path.read_bytes()
            (source_dir / path.name).write_bytes(data)
            manifest["source_hashes"][str(path.relative_to(ROOT))] = sha(data)
    manifest["dirty_files_sha256"] = dict(manifest["source_hashes"])
    manifest["dirty_files_scope"] = "entry source/config only; concurrent management documents excluded"
    if config_file:
        config_bytes = Path(config_file).read_bytes()
        (out / "config.json").write_bytes(config_bytes)
        manifest["config_sha256"] = sha(config_bytes)
    (out / "RUN_MANIFEST.template.json").write_bytes((ROOT / "coordination/templates/RUN_MANIFEST.json").read_bytes())
    write_json(out / "manifest.json", manifest)
    return out, manifest


def complete_run(out, manifest, status, exit_code, **extra):
    manifest.update(status=status, exit_code=exit_code, finished_at=utc_now(), **extra)
    write_json(out / "manifest.json", manifest)
