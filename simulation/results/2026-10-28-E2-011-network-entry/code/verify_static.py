"""Offline contract checks; never launches ns-3, a model, or a compiler."""
import ast
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def collect():
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    for path in HERE.glob("*.py"):
        ast.parse(path.read_text(encoding="utf-8"))
    tree = ROOT / "data/agent_native/E2-011/ns-3.46"
    raw = ROOT / "simulation/outputs/E2-011/EXAMPLE-NOT-EXECUTED/raw"
    relative = os.path.relpath(raw, tree)
    checks = {
        "python_syntax": True,
        "config_ns3_3_46": config["ns3_version"] == "3.46",
        "count_and_time": 5 + .5 * (config["application"]["count"] - 1) == 59.5,
        "relative_output_has_no_whitespace": not any(c.isspace() for c in relative),
        "relative_output_resolves_correctly": (tree / relative).resolve() == raw.resolve(),
    }
    if tree.exists():
        header = (tree / "src/core/model/command-line.h").read_text(encoding="utf-8")
        checks["upstream_string_stream_extraction_confirmed"] = "iss >> dest;" in header
    return {"scope": "offline static checks only; native runtime evidence is stored in separate authorized run directories",
            "checks": checks, "passed": all(checks.values()), "example_relative_output": relative,
            "source_hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir() if p.is_file()}}


if __name__ == "__main__":
    print(json.dumps(collect(), indent=2))
