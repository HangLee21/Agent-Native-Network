"""Read-only resource/source preflight after M checkpoint; never downloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .common import ROOT, complete_run, file_sha, inventory, new_run
from .runtime import write_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-lock-sha256", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    card = ROOT / "coordination/tasks/E1-010.md"
    lock = ROOT / "research/agent_native_network/preparation_20261028/SOURCE_LOCK.json"
    checkpoint = "M授权在本卡原预算内执行有限A0兼容验证。"
    if checkpoint not in card.read_text(encoding="utf-8-sig"):
        raise ValueError("M A0 checkpoint absent")
    if file_sha(lock) != args.source_lock_sha256:
        raise ValueError("D source lock hash changed")
    source = json.loads(lock.read_text(encoding="utf-8-sig"))["model"]
    plan = source["download_plan"]
    allowed = plan["conservative_root_allowlist"]
    selected = [row for row in source["files"] if row["path"] in allowed]
    if len(selected) != 13 or len(allowed) != 13 or any("/" in row["path"] for row in selected):
        raise ValueError("expected exact 13 root-file allowlist")
    total_bytes = sum(row["size_bytes"] for row in selected)
    if total_bytes != plan["conservative_total_bytes"]:
        raise ValueError("source file total mismatch")
    out, manifest = new_run(args.output, "A0_read_only_preflight", dict(model_forwards=0, downloads_bytes=0))
    (out / "SOURCE_LOCK.json").write_bytes(lock.read_bytes())
    (out / "E1-010-checkpoint.md").write_bytes(card.read_bytes())
    observed = inventory()
    write_json(out / "inventory.json", observed)
    requirements = Path(__file__).with_name("a0_requirements.txt").read_text(encoding="utf-8")
    versions = dict(re.findall(r"^([\w-]+)==([^\s#]+)$", requirements, re.M))
    write_json(out / "dependency_plan.json", dict(
        proposed_isolated_overlay=versions, installed_metadata=observed["packages"],
        reuse_readonly=["torch", "torchvision", "accelerate", "numpy", "Pillow"],
        model_allowlist_bytes=total_bytes, combined_limit_bytes=2500000000,
        remaining_download_bytes_for_dependencies=2500000000 - total_bytes,
        wheel_resolution_performed=False, dependency_downloaded_bytes=0,
        reason="check resources before any acquisition; overlay compatibility not yet tested"))
    free_ram = observed.get("free_ram_bytes")
    gpu_stdout = observed.get("gpu_query", {}).get("stdout", "")
    rows = [line.split(",") for line in gpu_stdout.strip().splitlines()]
    gpu_free = int(rows[0][2].strip().split()[0]) * 1024 * 1024 if rows and len(rows[0]) == 4 else None
    reasons = []
    if free_ram is None or free_ram < 2147483648:
        reasons.append("free_RAM_below_declared_2GiB_floor")
    if gpu_free is None or gpu_free < 2684354560:
        reasons.append("free_VRAM_below_declared_2.5GiB_floor")
    record = dict(status="blocked_resource_preflight" if reasons else "resources_pass_acquisition_not_started",
                  source_revision=source["revision"], source_lock_sha256=file_sha(lock),
                  m_checkpoint_present=True, free_ram_bytes=free_ram, minimum_free_ram_bytes=2147483648,
                  free_vram_bytes=gpu_free, minimum_free_vram_bytes=2684354560,
                  blockers=reasons, actual_model_forwards=0, model_downloaded_bytes=0,
                  dependencies_downloaded_bytes=0, shared_environment_modified=False,
                  limitations=["Resource floors are conservative execution gates, not measured peak model requirements",
                               "No process was terminated and no automatic retry is scheduled"])
    write_json(out / "preflight.json", record)
    if reasons:
        write_json(out / "failure.json", record)
    complete_run(out, manifest, record["status"], 2 if reasons else 0,
                 upstream_commit=source["revision"], source_lock_sha256=file_sha(lock),
                 task_card_sha256=file_sha(card), dependency_snapshot="inventory.json + dependency_plan.json",
                 actual_model_forwards=0, model_downloaded_bytes=0, dependencies_downloaded_bytes=0)
    print(json.dumps(record, ensure_ascii=False))
    return 2 if reasons else 0


if __name__ == "__main__":
    raise SystemExit(main())
