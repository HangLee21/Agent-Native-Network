"""Replay a frozen message catalogue through MessageService; no task policy runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import sys
import time

from message_service import MessageService


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def load_catalogue(path):
    path = Path(path)
    if path.suffix == ".jsonl":
        raw = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    else:
        raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        raw = raw["messages"]
    messages = []
    previous = 0.0
    for index, row in enumerate(raw):
        generated = float(row["generated_at"])
        if not math.isfinite(generated) or generated < previous:
            raise ValueError(f"catalogue times must be finite, nonnegative, ordered: row {index}")
        previous = generated
        if "payload_hex" in row:
            payload = bytes.fromhex(row["payload_hex"])
        else:
            payload = row["payload_utf8"].encode("utf-8")
        if "payload_sha256" in row and row["payload_sha256"] != hashlib.sha256(payload).hexdigest():
            raise ValueError(f"payload hash mismatch: row {index}")
        if "bytes" in row and row["bytes"] != len(payload):
            raise ValueError(f"payload byte count mismatch: row {index}")
        recipients = list(dict.fromkeys(row["recipients"]))
        if not recipients:
            raise ValueError(f"empty recipients: row {index}")
        messages.append(dict(original_message_id=row.get("message_id", index),
                             generated_at=generated, source=row["source"], recipients=recipients,
                             kind=row["kind"], payload=payload, key=row.get("key")))
    return messages


def describe(messages, overhead=0):
    sizes = [len(m["payload"]) + overhead for m in messages]
    groups = {}
    unit_bins = {}
    for message, size in zip(messages, sizes):
        when = message["generated_at"]
        groups[when] = groups.get(when, 0) + size
        unit_bins[math.floor(when)] = unit_bins.get(math.floor(when), 0) + size
    duration = messages[-1]["generated_at"] if messages else 0
    span = duration - messages[0]["generated_at"] if messages else 0
    percentile = MessageService._percentile
    return dict(messages=len(messages), recipients=sum(len(m["recipients"]) for m in messages),
                application_bytes=sum(len(m["payload"]) for m in messages), service_bytes=sum(sizes),
                overhead_bytes_per_message=overhead,
                first_generation=messages[0]["generated_at"] if messages else None,
                last_generation=duration if messages else None,
                mean_service_bytes_per_time_from_origin=sum(sizes) / duration if duration > 0 else None,
                mean_service_bytes_per_generation_span=sum(sizes) / span if span > 0 else None,
                message_bytes_p50=percentile(sizes, 0.5), message_bytes_p95=percentile(sizes, 0.95),
                message_bytes_max=max(sizes, default=0),
                same_time_burst_bytes_p50=percentile(list(groups.values()), 0.5),
                same_time_burst_bytes_p95=percentile(list(groups.values()), 0.95),
                same_time_burst_bytes_max=max(groups.values(), default=0),
                occupied_one_time_unit_bin_bytes_p50=percentile(list(unit_bins.values()), 0.5),
                occupied_one_time_unit_bin_bytes_p95=percentile(list(unit_bins.values()), 0.95),
                one_time_unit_bin_bytes_max=max(unit_bins.values(), default=0),
                time_unit="author_simulation_time_without_seconds_calibration")


def replay(messages, config, horizon, max_wall_seconds=30):
    service = MessageService(**config)
    started = time.monotonic()
    ids, deliveries = [], []
    for row in messages:
        if row["generated_at"] > horizon:
            break
        if time.monotonic() - started >= max_wall_seconds:
            raise TimeoutError("fixed catalogue replay exceeded wall-clock budget")
        message_id = service.submit(row["generated_at"], row["source"], row["recipients"],
                                    row["kind"], row["payload"], key=row["key"])
        ids.append(dict(original_message_id=row["original_message_id"], replay_message_id=message_id))
        for item in service.pop_due(row["generated_at"]):
            item["payload_hex"] = item.pop("payload").hex()
            deliveries.append(item)
    for item in service.pop_due(horizon):
        item["payload_hex"] = item.pop("payload").hex()
        deliveries.append(item)
    stats = service.stats(horizon)
    checks = dict(
        message_demand_conserved=stats["demanded"] == stats["accepted"] + stats["dropped"],
        byte_demand_conserved=stats["demand_service_bytes"] == stats["admitted_service_bytes"] + stats["rejected_service_bytes"],
        service_work_conserved=math.isclose(stats["admitted_service_bytes"], stats["serviced_bytes"] + stats["remaining_service_bytes"]),
        buffer_inventory_conserved=stats["buffer_occupied_bytes"] == stats["queue_bytes"] + stats["in_service_buffer_bytes"],
        accepted_inventory_conserved=stats["accepted"] == stats["pending"] + stats["delivered"],
        recipient_deliveries_match=stats["recipient_delivered"] == len(deliveries),
        no_future_delivery=all(d["delivered_at"] <= horizon for d in deliveries),
        no_early_delivery=all(d["delivered_at"] >= d["generated_at"] for d in deliveries),
    )
    if not all(checks.values()):
        raise AssertionError(checks)
    return dict(stats=stats, checks=checks, wall_seconds=time.monotonic() - started), service.ledger, deliveries, ids


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--describe", action="store_true", help="read-only catalogue statistics")
    parser.add_argument("--output", type=Path, help="new, nonexistent output directory")
    parser.add_argument("--mode", choices=("instant", "fixed_delay", "fifo"), default="fifo")
    parser.add_argument("--rate", type=float, default=1.0, help="application+overhead bytes per author simulation time")
    parser.add_argument("--capacity", type=int, help="whole waiting+in-service byte limit; omitted means unlimited")
    parser.add_argument("--delay", type=float, default=0.0)
    parser.add_argument("--overhead", type=int, default=0)
    parser.add_argument("--horizon", type=float, help="observation cutoff; defaults to final generation time")
    parser.add_argument("--max-wall-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if not 0 < args.max_wall_seconds <= 30:
        parser.error("max-wall-seconds must be in (0,30]")
    messages = load_catalogue(args.input)
    catalogue = describe(messages, args.overhead)
    if args.describe:
        print(json.dumps(catalogue, indent=2, ensure_ascii=False, allow_nan=False))
        return
    if args.output is None:
        parser.error("--output is required for a replay")
    horizon = args.horizon if args.horizon is not None else (catalogue["last_generation"] or 0.0)
    if not math.isfinite(horizon) or horizon < 0:
        parser.error("horizon must be finite and nonnegative")
    config = dict(mode=args.mode, delay=args.delay, rate_bytes_per_time=args.rate,
                  capacity_bytes=args.capacity, overhead_bytes=args.overhead)
    MessageService(**config)  # Validate before creating the output directory.
    args.output.mkdir(parents=True, exist_ok=False)
    snapshots = args.output / "source_snapshot"
    snapshots.mkdir()
    source_files = [Path(__file__), Path(__file__).with_name("message_service.py"),
                    Path(__file__).with_name("test_message_service.py")]
    for source in source_files:
        shutil.copyfile(source, snapshots / source.name)
    shutil.copyfile(args.input, args.output / ("input_catalogue" + args.input.suffix))
    manifest = dict(schema="shared-service-replay-v1", input_path=str(args.input.resolve()),
                    input_sha256=sha256(args.input), source_sha256={p.name: sha256(p) for p in source_files},
                    python=sys.version, platform=platform.platform(), argv=sys.argv,
                    config=config, horizon=horizon, max_wall_seconds=args.max_wall_seconds,
                    catalogue=catalogue, status="running",
                    evidence_scope="fixed traffic application-byte service replay; no task policy or wireless model")
    write_json(args.output / "manifest.json", manifest)
    try:
        summary, ledger, deliveries, ids = replay(messages, config, horizon, args.max_wall_seconds)
        write_json(args.output / "result.json", summary)
        write_json(args.output / "ledger.json", ledger)
        write_json(args.output / "deliveries.json", deliveries)
        write_json(args.output / "message_id_map.json", ids)
        manifest["status"] = "completed"
        manifest["output_sha256"] = {name: sha256(args.output / name) for name in
                                     ("result.json", "ledger.json", "deliveries.json", "message_id_map.json")}
        write_json(args.output / "manifest.json", manifest)
        print(json.dumps(summary, indent=2, ensure_ascii=False, allow_nan=False))
    except Exception as error:
        manifest.update(status="failed", error=f"{type(error).__name__}: {error}")
        write_json(args.output / "manifest.json", manifest)
        raise


if __name__ == "__main__":
    main()
