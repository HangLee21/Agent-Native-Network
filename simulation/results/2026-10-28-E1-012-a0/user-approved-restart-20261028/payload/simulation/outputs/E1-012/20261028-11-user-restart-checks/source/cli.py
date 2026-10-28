"""Offline commands only. A0 model invocation is a separate gated entry."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import traceback
import zlib

from .common import complete_run, inventory, new_run
from .runtime import BudgetStop, FixtureBackend, Runtime, encode, sha, synthetic_png, write_json


def run_fixture(config_path, output):
    config = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    if config["backend"] != FixtureBackend.label:
        raise ValueError("fixture entry cannot invoke a model")
    out, manifest = new_run(output, "offline_fixture", config["budget"], config_path)
    manifest.update(backend=FixtureBackend.label, deployment="P2_fixture_only", actual_model_forwards=0,
                    clock_mode="fixture_logical_complete_packets_not_wireless")
    runtime = None
    try:
        write_json(out / "inventory.json", inventory())
        manifest["dependency_snapshot"] = "inventory.json"
        nodes = config["nodes"]
        inputs = out / "inputs"
        inputs.mkdir()
        image_records = []
        for node, color in (("n0", (255, 0, 0)), ("n1", (0, 0, 255))):
            raw = synthetic_png(color)
            (inputs / (node + ".png")).write_bytes(raw)
            # PNG fixture loading without third-party imports: decode IDAT.
            offset, compressed = 8, bytearray()
            while offset < len(raw):
                length = struct.unpack(">I", raw[offset:offset + 4])[0]
                kind = raw[offset + 4:offset + 8]
                data = raw[offset + 8:offset + 8 + length]
                if kind == b"IDAT":
                    compressed.extend(data)
                offset += length + 12
            decoded = zlib.decompress(compressed)
            if len(decoded) != 64 * (64 * 3 + 1):
                raise ValueError("generated PNG decode size mismatch")
            ref = node + ":image"
            nodes[node][ref] = dict(kind="private_image", sha256=sha(raw), encoded_bytes=len(raw),
                                    path=str(inputs / (node + ".png")), width=64, height=64,
                                    provenance="generated_solid_color_compatibility_fixture")
            image_records.append(dict(node_id=node, evidence_id=ref, **nodes[node][ref]))
        write_json(out / "input_manifest.json", image_records)
        manifest["data_and_weights_sha256"] = {r["path"]: r["sha256"] for r in image_records}
        with (out / "events.jsonl").open("wb") as stream:
            def sink(event):
                stream.write(encode(event) + b"\n")
                stream.flush()
            runtime = Runtime(nodes, FixtureBackend(config["actions"]), run_id=out.name,
                              latency_s=config["fixture_latency_s"], event_sink=sink, **config["budget"])
            for op, arg in config["schedule"]:
                if op == "call":
                    runtime.call(arg)
                elif op == "deliver":
                    runtime.deliver_until(arg)
                else:
                    raise ValueError("unknown fixture schedule operation")
            runtime.status = "fixture_completed"
        result = runtime.summary()
        write_json(out / "result.json", result)
        complete_run(out, manifest, result["status"], 0)
        return 0
    except Exception as exc:
        write_json(out / "failure.json", dict(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc()))
        if runtime is not None:
            write_json(out / "result.json", runtime.summary())
        complete_run(out, manifest, "budget_stopped" if isinstance(exc, BudgetStop) else "failed", 1)
        return 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path, default=Path(__file__).with_name("fixture_config.json"))
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    return run_fixture(args.config, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
