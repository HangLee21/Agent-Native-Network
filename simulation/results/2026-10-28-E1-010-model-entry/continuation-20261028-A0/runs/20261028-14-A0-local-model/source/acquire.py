"""One bounded acquisition, exact D allowlist and isolated package overlay.

No retries, no entire-repository fetch, no new torch wheel, no shared env edits.
Only run after M's checkpoint and the once-authorized passing resource preflight.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback
import urllib.request
import venv

from .a0 import verify_model_file
from .common import DATA_ROOT, ROOT, complete_run, file_sha, new_run
from .runtime import write_json


def run(output, preflight):
    source_lock = ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json"
    card = ROOT / "coordination/tasks/E1-010.md"
    source = json.loads(source_lock.read_text(encoding="utf-8"))["model"]
    evidence = json.loads(Path(preflight).read_text(encoding="utf-8"))
    if evidence["status"] != "resources_pass_acquisition_not_started" or evidence["source_lock_sha256"] != file_sha(source_lock):
        raise ValueError("passing authorized preflight with matching lock required")
    if "M构建结束后的有界A0续行" not in card.read_text(encoding="utf-8"):
        raise ValueError("M bounded continuation checkpoint absent")
    out, manifest = new_run(output, "bounded_model_and_overlay_acquisition", dict(download_limit_bytes=2500000000, preparation_wall_s=600, model_forwards=0))
    started = time.monotonic()
    task_root = DATA_ROOT.resolve()
    task_root.mkdir(parents=True, exist_ok=True)
    model_dir, wheels, env_dir = task_root / "model", task_root / "downloads", task_root / "env"
    if any(p.exists() for p in (model_dir, wheels, env_dir)):
        raise ValueError("acquisition directories already exist; no retry/overwrite")
    model_dir.mkdir(); wheels.mkdir()
    records, downloaded = [], 0
    ledger = out / "download_ledger.json"
    manifest.update(upstream_commit=source["revision"], source_lock_sha256=file_sha(source_lock),
                    task_card_sha256=file_sha(card), actual_model_forwards=0)
    write_json(out / "manifest.json", manifest)
    (out / "SOURCE_LOCK.json").write_bytes(source_lock.read_bytes())
    (out / "E1-010-checkpoint.md").write_bytes(card.read_bytes())

    def remaining():
        seconds = 600 - (time.monotonic() - started)
        if seconds <= 0:
            raise TimeoutError("10-minute preparation wall budget exhausted")
        return seconds

    def save_ledger():
        write_json(ledger, dict(downloaded_bytes=downloaded, elapsed_s=time.monotonic() - started, files=records))

    def fetch(url, destination, expected_size=None, expected_sha=None, max_size=None):
        nonlocal downloaded
        remaining()
        if expected_size is not None and downloaded + expected_size > 2500000000:
            raise ValueError("download would exceed task byte budget")
        record = dict(url=url, path=str(destination), status="started", downloaded_bytes=0)
        records.append(record); save_ledger()
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=min(25, remaining())) as response, destination.open("xb") as stream:
            while True:
                remaining()
                data = response.read(1024 * 1024)
                if not data:
                    break
                downloaded += len(data)
                record["downloaded_bytes"] += len(data)
                if downloaded > 2500000000 or (max_size and record["downloaded_bytes"] > max_size):
                    save_ledger()
                    raise ValueError("download byte cap exhausted")
                stream.write(data); digest.update(data)
                if record["downloaded_bytes"] % (16 * 1024 * 1024) == 0:
                    save_ledger()
        record.update(status="downloaded", sha256=digest.hexdigest())
        save_ledger()
        if expected_size is not None and record["downloaded_bytes"] != expected_size:
            raise ValueError("download size mismatch")
        if expected_sha is not None and record["sha256"] != expected_sha:
            raise ValueError("download SHA-256 mismatch")
        print(destination.name, record["downloaded_bytes"], "bytes", flush=True)
        return record

    try:
        # Resolve wheels from fixed official PyPI metadata without invoking an
        # unconstrained pip dependency solver or downloading a torch wheel.
        from packaging.tags import sys_tags
        from packaging.utils import parse_wheel_filename
        supported = {tag: i for i, tag in enumerate(sys_tags())}
        packages = dict(line.strip().split("==") for line in Path(__file__).with_name("a0_requirements.txt").read_text(encoding="utf-8").splitlines()
                        if line.strip() and not line.startswith("#"))
        selected = []
        for name, version in packages.items():
            meta_path = out / f"pypi-{name}-{version}.json"
            fetch(f"https://pypi.org/pypi/{name}/{version}/json", meta_path, max_size=2000000)
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            choices = []
            for row in meta["urls"]:
                if row["filename"].endswith(".whl"):
                    tags = parse_wheel_filename(row["filename"])[3]
                    ranks = [supported[tag] for tag in tags if tag in supported]
                    if ranks:
                        choices.append((min(ranks), row))
            choice = min(choices, key=lambda item: item[0])[1] if choices else next(row for row in meta["urls"] if row["packagetype"] == "sdist")
            selected.append(dict(package=name, version=version, requires_dist=meta["info"].get("requires_dist"), **choice))
        write_json(out / "dependency_resolution.json", selected)
        projected = downloaded + sum(r["size"] for r in selected) + source["download_plan"]["conservative_total_bytes"]
        if projected > 2500000000:
            raise ValueError("resolved dependencies and model exceed combined cap")
        for row in selected:
            fetch(row["url"], wheels / row["filename"], row["size"], row["digests"]["sha256"])
        remaining()
        venv.EnvBuilder(system_site_packages=True, with_pip=True).create(env_dir)
        python = env_dir / "Scripts/python.exe"
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PIP_CACHE_DIR=str(task_root / "pip-cache"),
                   TMP=str(task_root / "tmp"), TEMP=str(task_root / "tmp"), PIP_DISABLE_PIP_VERSION_CHECK="1")
        (task_root / "tmp").mkdir()
        commands = [[str(python), "-B", "-m", "pip", "install", "--no-deps", "--no-index", "--no-build-isolation", *[str(wheels / r["filename"]) for r in selected]],
                    [str(python), "-B", "-c", "import torch,transformers,tokenizers; print(torch.__version__,transformers.__version__,tokenizers.__version__); from transformers import AutoProcessor,AutoModelForImageTextToText; print('model API imports ready')"]]
        for i, command in enumerate(commands):
            with (out / f"environment-{i:02d}.txt").open("w", encoding="utf-8") as log:
                p = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, env=env, timeout=remaining())
            if p.returncode:
                raise RuntimeError(f"isolated environment command {i} exited {p.returncode}")
        model_hashes = {}
        for row in source["files"]:
            if row["path"] not in source["download_plan"]["conservative_root_allowlist"]:
                continue
            path = model_dir / row["path"]
            fetch(source["resolve_base_url"] + row["path"], path, row["size_bytes"], row["sha256"])
            verified = verify_model_file(path, row, file_sha(path))
            model_hashes[row["path"]] = verified["sha256"]
            remaining()
        write_json(out / "model_files_verified.json", model_hashes)
        config = dict(repo_id=source["repo_id"], source_revision=source["revision"],
                      source_lock_sha256=file_sha(source_lock), task_card_sha256=file_sha(card),
                      m_checkpoint_excerpt="M授权在本卡原预算内执行有限A0兼容验证。",
                      python=str(python), model_dir=str(model_dir), model_file_sha256=model_hashes,
                      minimum_free_ram_bytes=2147483648,
                      budget=dict(calls=4,max_new_tokens=128,per_call_s=180,total_s=720))
        write_json(task_root / "a0_config.json", config)
        write_json(out / "a0_config.json", config)
        complete_run(out, manifest, "acquired_and_imported", 0, downloaded_bytes=downloaded,
                     preparation_wall_s=time.monotonic() - started, dependency_snapshot="dependency_resolution.json + environment logs")
        save_ledger()
        return 0
    except Exception as exc:
        save_ledger()
        write_json(out / "failure.json", dict(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc(),
                                              downloaded_bytes=downloaded, elapsed_s=time.monotonic()-started))
        complete_run(out, manifest, "acquisition_failed", 1, downloaded_bytes=downloaded,
                     preparation_wall_s=time.monotonic()-started)
        return 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",required=True)
    p.add_argument("--preflight",required=True)
    a=p.parse_args()
    return run(a.output,a.preflight)


if __name__=="__main__":
    raise SystemExit(main())
