"""Run paired seeds, retain all results, and report uncertainty without significance claims."""

import argparse
import csv
from dataclasses import asdict
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from simulation.prospecting import Config, LINKS, load_world, run_episode, synthetic_world


def interval(values):
    values = np.array(values, dtype=float)
    rng = np.random.default_rng(942)
    means = rng.choice(values, size=(2000, len(values)), replace=True).mean(axis=1)
    return float(values.mean()), *np.quantile(means, [0.025, 0.975]).tolist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=24)
    parser.add_argument("--output", type=Path, default=Path("simulation/outputs/pilot"))
    parser.add_argument("--data", type=Path, help="NPZ cube with provenance; omitted = SYNTHETIC.")
    args = parser.parse_args()
    if args.seeds < 2:
        parser.error("--seeds must be at least 2 for descriptive uncertainty.")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output folder is not empty; choose a new folder to preserve prior runs.")
    args.output.mkdir(parents=True, exist_ok=True)
    configurations = {
        "strong_prior": Config(prior_block=1, prior_noise_std=0.01),
        "coarse_prior": Config(prior_block=3, prior_noise_std=0.02),
    }
    conditions = [
        ("static", None), ("local", None),
        *[("shared", LINKS[name]) for name in LINKS],
    ]
    records, traces = [], {}
    for prior_name, cfg in configurations.items():
        for seed in range(args.seeds):
            world = load_world(args.data, cfg, seed) if args.data else synthetic_world(seed, cfg)
            for mode, link in conditions:
                result, trace = run_episode(world, mode, link, trace=seed == 0)
                result["prior"] = prior_name
                result["condition"] = link.name if link else mode
                records.append(result)
                if seed == 0:
                    traces[f"{prior_name}_{result['condition']}"] = trace
        print(f"Completed {prior_name}: {args.seeds} paired seeds.", flush=True)
    (args.output / "episodes.json").write_text(
        json.dumps(records, indent=2, allow_nan=False), encoding="utf-8")
    for name, trace in traces.items():
        (args.output / f"trace_{name}.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in trace), encoding="utf-8")
    fields = [key for key in records[0] if key not in
              ("paths", "decisions", "config", "provenance")]
    with (args.output / "metrics.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    summary, paired = [], []
    for prior in configurations:
        groups = {}
        for row in records:
            if row["prior"] == prior:
                groups.setdefault(row["condition"], []).append(row)
        groups["prior_only"] = [
            {**row, "heldout_rmse": row["prior_rmse"], "samples": 0, "delivered_messages": 0}
            for row in groups["local"]
        ]
        for condition, rows in groups.items():
            mean, low, high = interval([r["heldout_rmse"] for r in rows])
            summary.append({
                "prior": prior, "condition": condition, "rmse_mean": mean,
                "bootstrap_low": low, "bootstrap_high": high,
                "samples_mean": float(np.mean([r["samples"] for r in rows])),
                "delivered_mean": float(np.mean([r["delivered_messages"] for r in rows])),
            })
        for a, b in [("ideal", "static"), ("ideal", "local"), ("good", "ideal"),
                     ("intermittent", "ideal"), ("stress", "ideal"),
                     ("disconnected", "local"), ("static", "prior_only"),
                     ("local", "prior_only"), ("ideal", "prior_only")]:
            by_seed_a = {r["seed"]: r for r in groups[a]}
            by_seed_b = {r["seed"]: r for r in groups[b]}
            deltas = [by_seed_a[s]["heldout_rmse"] - by_seed_b[s]["heldout_rmse"]
                      for s in sorted(by_seed_a)]
            mean, low, high = interval(deltas)
            paired.append({
                "prior": prior, "comparison": f"{a} minus {b}",
                "mean_rmse_delta": mean, "bootstrap_low": low, "bootstrap_high": high,
            })
    for name, rows in [("summary", summary), ("paired", paired)]:
        with (args.output / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    git = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
    metadata = {
        "data_kind": records[0]["provenance"]["kind"],
        "data_provenance": records[0]["provenance"],
        "python": platform.python_version(),
        "packages": {n: importlib.metadata.version(n) for n in ("numpy", "simpy", "matplotlib")},
        "git_head_at_run": git.stdout.strip(),
        "git_dirty_at_run": bool(dirty.stdout.strip()),
        "source_sha256": {
            str(path).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(Path("simulation").glob("*.py"))
        },
        "seeds": list(range(args.seeds)),
        "configs": {key: asdict(value) for key, value in configurations.items()},
        "links": {key: {k: ("infinity" if isinstance(v, float) and np.isinf(v) else v)
                        for k, v in asdict(value).items()} for key, value in LINKS.items()},
        "decision": "Exploratory only; no practical-effect threshold yet justified.",
        "ci_scope": "Paired seed bootstrap, not independent real sites; no multiplicity correction.",
        "metric": "Held-out fine-spectrum residual-interpolation RMSE, reflectance in [0,1].",
        "limitations": [
            "Synthetic mixtures by default; no measured ground observations.",
            "No terrain, return-to-base cost, sensor calibration, MAC, routing or LLM.",
            "Policy and estimator are fixed heuristics, not reproduced P31/MOCHA/ACHORD.",
        ],
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    plot_results(summary, records, args.output, metadata["data_kind"])
    lines = [
        "# 首轮任务级仿真自动摘要", "",
        f"数据类别：**{metadata['data_kind']}**；{args.seeds} 个配对随机种子；"
        f"{len(records)} 次运行。所有策略均终局汇总观测。", "",
        "指标为固定留出位置的光谱预测 RMSE，越小越好；不是矿物识别或找矿成功率。",
        "区间是种子自举的描述性 95% 区间，不表示实地总体置信度。", "",
        "| 先验 | 条件 | 平均 RMSE | 平均采样数 |",
        "|---|---|---:|---:|",
    ]
    lines.extend(f"| {r['prior']} | {r['condition']} | {r['rmse_mean']:.6f} | "
                 f"{r['samples_mean']:.2f} |" for r in summary)
    lines += ["", "配对差值按前者减后者；负值表示前者误差较小。", "",
              "| 先验 | 对照 | 平均差值 | 描述性区间 |", "|---|---|---:|---|"]
    lines.extend(f"| {r['prior']} | {r['comparison']} | {r['mean_rmse_delta']:.6f} | "
                 f"[{r['bootstrap_low']:.6f}, {r['bootstrap_high']:.6f}] |" for r in paired)
    lines += ["", "尚无应用依据支持实质收益阈值；本轮不作问题存在或算法优越性的判定。",
              "完整参数见 metadata.json；全部运行见 metrics.csv；种子 0 时序见 trace_*.jsonl。"]
    (args.output / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(paired, indent=2))


def plot_results(summary, records, output, kind):
    fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
    for ax, prior in zip(axes, ("strong_prior", "coarse_prior")):
        rows = [r for r in summary if r["prior"] == prior and r["condition"] != "prior_only"]
        means = np.array([r["rmse_mean"] for r in rows])
        errors = np.array([[r["rmse_mean"] - r["bootstrap_low"] for r in rows],
                           [r["bootstrap_high"] - r["rmse_mean"] for r in rows]])
        ax.errorbar(range(len(rows)), means, yerr=np.maximum(errors, 0), fmt="o", capsize=4)
        baseline = np.mean([r["prior_rmse"] for r in records if r["prior"] == prior])
        ax.axhline(baseline, color="gray", ls="--", label="Prior only")
        ax.set_xticks(range(len(rows)), [r["condition"] for r in rows], rotation=30)
        ax.set_title(prior)
        ax.set_ylabel("Held-out spectral RMSE (lower is better)")
        ax.legend()
        ax.grid(alpha=0.2)
    fig.suptitle(f"{kind.upper()} pilot | descriptive seed bootstrap 95% intervals")
    fig.savefig(output / "rmse.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    main()
