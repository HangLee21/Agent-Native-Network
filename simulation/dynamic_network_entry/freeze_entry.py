"""Freeze this task's finite outputs; no compiler/model/simulator execution."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import network_entry as entry
import verify_static


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result_dir = entry.ROOT / "simulation/results/2026-10-28-E2-011-network-entry"
    if result_dir.exists():
        raise ValueError("Refusing to overwrite frozen result archive")
    out = entry.fresh(args.output)
    m = entry.new_manifest(out, "freeze")
    checks = verify_static.collect()
    reservations = sorted(p.name for p in (entry.OUTPUTS / ".reservations").glob("*.json"))
    build = json.loads((entry.DATA / "BUILD_BUDGET.json").read_text())
    actual_runs = []
    for name in ("20261028-13-dynamic0-supplement", "20261028-14-dynamic1-supplement"):
        p = entry.OUTPUTS / name
        verification = json.loads((p / "verification.json").read_text(encoding="utf-8"))
        actual_runs.append({"run_id": name, "passed": verification["passed"],
                            "events_sha256": entry.sha(p / "raw/events.jsonl"),
                            "pcap_files": [x.name for x in (p / "raw").glob("*.pcap")]})
    result = {"status": "bounded_dynamic_micro_scenarios_verified", "static_checks": checks,
              "build_wall_seconds_total": build["wall_seconds"], "build_within_budget": build["wall_seconds"] <= 900,
              "reservation_files": reservations, "started_attempts": len(reservations),
              "completed_simulations": 2, "original_pre_simulation_failures": 3,
              "actual_runs": actual_runs, "runtime_acceptance": "both dynamic checks pass; no scaling or task-performance claim",
              "next_step": "C-013 independent review and M acceptance; no further run budget",
              "no_background_research_process_started_by_freeze": True}
    entry.dump(out / "verification.json", result)
    m.update(status=result["status"], finished_at=entry.now(), exit_code=0,
             upstream_commit=entry.CONFIG["upstream_commit"],
             data_and_weights_sha256={"ns3_source_archive": entry.sha(entry.DATA / "ns-3.46.tar.bz2")},
             result_archive=str(result_dir),
             output_hashes={"verification.json": entry.sha(out / "verification.json")})
    m["budget"].update(simulations=5, additional_dynamic_start_checks=2,
                       authorization="E2-011 M explicit startup-fix supplement; first three failures retained")
    entry.dump(out / "manifest.json", m)
    result_dir.mkdir(parents=True)
    source_files = [(p, Path("code") / p.name) for p in entry.HERE.iterdir() if p.is_file()]
    source_files += [(p, Path("runs") / p.relative_to(entry.OUTPUTS))
                     for p in entry.OUTPUTS.rglob("*") if p.is_file()]
    for name in ("SOURCE.json", "SOURCE-VERIFIED.json", "BUILD.json", "BUILD_BUDGET.json"):
        p = entry.DATA / name
        if p.exists(): source_files.append((p, Path("source") / name))
    source_files.append((entry.DATA / "ns-3.46/LICENSE", Path("source/ns3-LICENSE")))
    manifest = []
    for p, rel in source_files:
        target = result_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        raw = p.read_bytes()
        shutil.copyfile(p, target)
        encoding = "identity"
        manifest.append({"original": str(p.relative_to(entry.ROOT)), "stored": str(target.relative_to(result_dir)),
                         "encoding": encoding, "original_bytes": len(raw), "original_sha256": entry.sha(p),
                         "stored_sha256": entry.sha(target)})
    entry.dump(result_dir / "ARCHIVE_MANIFEST.json", {"task_id": "E2-011", "files": manifest,
               "source_archive_not_duplicated": str(entry.DATA / "ns-3.46.tar.bz2"),
               "source_archive_sha256": entry.sha(entry.DATA / "ns-3.46.tar.bz2"),
               "dynamic_micro_scenarios_verified": 2})
    (result_dir / "README.md").write_text(
        "# E2-011 前置网络入口证据\n\n"
        "ns-3.46源码已取得、原生入口构建通过，累计构建814.531秒。"
        "前三次启动在Simulator::Run前失败；M明确增加两个启动检查名额后，两原动态种子各完成60秒场景并通过日志核验。"
        "12项合成日志fixture单测不是无线模拟。失败、命令、源码和预算名额完整保留。\n\n"
        "[实际报告](../../../research/agent_native_network/preparation_20261028/NETWORK_ENTRY.md)；"
        "[主卡](../../../coordination/tasks/E2-011.md)。"
        "ARCHIVE_MANIFEST逐文件记录原始/存储SHA-256，全部原字节复制，不改原manifest。"
        "源码官方归档保留在本卡data隔离目录，不重复打包整套工具链或构建树。"
        "本归档只支持两个受控B0的路径/分区/恢复与计费核验，不支持规模、容量或Agent任务收益；后续运行需新授权预算。\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "archive_files": len(manifest), "archive": str(result_dir)}))


if __name__ == "__main__":
    main()
