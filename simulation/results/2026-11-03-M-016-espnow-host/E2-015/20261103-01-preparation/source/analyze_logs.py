"""Independent ann.serial.v1 bench analysis; no serial or radio access."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

SCHEMA = "ann.serial.v1"
MODES = {"raw_no_retry", "reliable"}
RADIO_METRICS = ("range_m", "pdr", "goodput_bps", "rtt_p95_ms")


def integer(value):
    return type(value) is int and value >= 0


def parse_lines(lines):
    events, ignored, malformed = [], 0, 0
    for line in lines:
        if len(line.encode("utf-8")) > 16384:
            raise ValueError("serial line exceeds analyzer 16KiB bound")
        try:
            row = json.loads(line)
        except (ValueError, TypeError):
            if line.lstrip().startswith("{"):
                malformed += 1
            else:
                ignored += 1
            continue
        if not isinstance(row, dict) or row.get("schema") != SCHEMA:
            ignored += 1
            continue
        events.append(row)
    return events, dict(ignored_non_schema_lines=ignored, malformed_json_lines=malformed)


def quantile95(values):
    # Explicit nearest-rank P95; successful same-clock echoes only.
    return sorted(values)[math.ceil(.95 * len(values))-1] if values else None


def validate_measurement_record(record, *, require_hardware=False):
    """Validate evidence tags; cannot authenticate physical provenance itself."""
    if require_hardware and record.get("evidence_kind") != "hardware_measured":
        raise ValueError("synthetic/unknown evidence cannot populate hardware measurement")
    if record.get("status") == "not_measured":
        if (record.get("reason") != "hardware_not_available" or record.get("source") is not None
                or any(record.get(k) is not None for k in RADIO_METRICS)):
            raise ValueError("unavailable hardware metrics must all be null with null source")
    elif record.get("status") == "measured":
        if not record.get("source"):
            raise ValueError("measured record needs an actual evidence source")
        for name in RADIO_METRICS:
            value = record.get(name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0):
                raise ValueError("invalid measured value: " + name)
        if record.get("pdr") is not None and record["pdr"] > 1:
            raise ValueError("PDR outside [0,1]")
    else:
        raise ValueError("unknown measurement status")


def analyze(events, config):
    """One explicitly configured mode/run; never derive cross-node one-way delay."""
    run_id, destination = config["run_id"], config["destination_id"]
    mode, kind = config["mode"], config["evidence_kind"]
    if mode not in MODES or kind not in {"synthetic", "hardware_measured"}:
        raise ValueError("explicit mode and evidence_kind required")
    selected = [r for r in events if r.get("run_id") == run_id]
    issues, counts = [], Counter(r.get("event") for r in selected)
    generations, generation_candidates = {}, defaultdict(set)
    clocks = {}
    for r in selected:
        if r.get("mode", mode) != mode:
            issues.append("mixed raw/reliable mode in run")
        boot = r.get("boot_id")
        valid_boot = (isinstance(boot,str) and bool(boot)) or integer(boot)
        if not isinstance(r.get("node_id"), str) or not valid_boot or not integer(r.get("t_us")):
            issues.append("missing node/boot/local monotonic timestamp")
            continue
        clock_key = (r["node_id"], r["boot_id"])
        if r["t_us"] < clocks.get(clock_key, 0):
            issues.append("out-of-order local clock within node+boot")
        clocks[clock_key] = r["t_us"]
        if r.get("event") != "generated":
            continue
        if r.get("origin_id") != r["node_id"] or not integer(r.get("seq")):
            issues.append("invalid generated origin/sequence")
            continue
        origin_boot = r.get("origin_boot_id", r["boot_id"])
        if origin_boot != r["boot_id"]:
            issues.append("generated origin boot differs from local boot")
            continue
        key = (run_id, r["origin_id"], origin_boot, r["seq"])
        if key in generations:
            issues.append("duplicate generated identity")
        generations[key] = r
        generation_candidates[(r["origin_id"],r["seq"])].add(key)

    def identify(row):
        if not isinstance(row.get("origin_id"), str) or not integer(row.get("seq")):
            return None
        if row.get("origin_boot_id") is not None:
            key = (run_id, row["origin_id"], row["origin_boot_id"], row["seq"])
            return key if key in generations else None
        candidates = generation_candidates[(row["origin_id"], row["seq"])]
        return next(iter(candidates)) if len(candidates) == 1 else None

    accepted = callbacks_ok = callbacks_failed = callbacks_unknown = 0
    submit_unknown = 0
    attempts, received, echoed, rtts, payloads = Counter(), set(), set(), [], {}
    duplicates = unmatched_rx = invalid_echoes = 0
    lengths_known = True
    for r in selected:
        event, key = r.get("event"), identify(r)
        frame, payload = r.get("frame_bytes"), r.get("payload_bytes")
        if frame is not None and (not integer(frame) or not 112 <= frame <= 250):
            issues.append("frame_bytes outside frozen ANN v1 112..250")
        if payload is not None and (not integer(payload) or (integer(frame) and payload != frame-112)):
            issues.append("payload_bytes inconsistent with frozen 112-byte protocol header")
        if event == "tx_submit":
            if key is not None:
                attempts[key] += 1
            value = r.get("accepted")
            if value is True or r.get("status") == "accepted":
                accepted += 1
            elif value is not False and r.get("status") not in {"rejected", "error"}:
                submit_unknown += 1
        elif event == "tx_result":
            if r.get("success") is True or r.get("status") == "success":
                callbacks_ok += 1
            elif r.get("success") is False or r.get("status") == "failed":
                callbacks_failed += 1
            else:
                callbacks_unknown += 1
        elif event == "rx" and r.get("node_id") == destination:
            if key is None:
                unmatched_rx += 1
                continue
            if key in received:
                duplicates += 1
            else:
                received.add(key)
                if not integer(payload):
                    lengths_known = False
                else:
                    payloads[key] = payload
                generated_payload = generations[key].get("payload_bytes")
                if payload is not None and generated_payload is not None and payload != generated_payload:
                    issues.append("source/receiver payload length differs")
        elif event == "echo":
            if key is None or r.get("node_id") != key[1] or r.get("boot_id") != key[2] or not integer(r.get("t_us")):
                invalid_echoes += 1
                continue
            elapsed = r["t_us"] - generations[key]["t_us"]
            if elapsed < 0:
                invalid_echoes += 1
            elif key not in echoed:
                echoed.add(key)
                rtts.append(elapsed / 1000.0)
    if mode == "raw_no_retry" and any(n > 1 for n in attempts.values()):
        issues.append("raw mode has repeated application tx_submit identity")
    complete = config.get("receiver_log_complete") is True
    duration = config.get("measurement_duration_us")
    duration_valid = (type(duration) is int and duration > 0 and config.get("duration_clock") in
                      {"receiver_local_window", "host_monotonic_controlled_window"})
    if len(received) > len(generations):
        issues.append("more received than generated")
    # Do not convert missing/ambiguous logs into a delivery result.
    delivery_known = complete and unmatched_rx == 0 and not issues
    pdr = len(received)/len(generations) if delivery_known and generations else None
    goodput = sum(payloads.values())*8*1_000_000/duration if delivery_known and duration_valid and lengths_known else None
    return dict(schema="ann.analysis.v1",run_id=run_id,mode=mode,evidence_kind=kind,
                generated_unique=len(generations),driver_accepted=accepted,driver_acceptance_unknown=submit_unknown,
                link_callbacks_success=callbacks_ok,link_callbacks_failed=callbacks_failed,link_callbacks_unknown=callbacks_unknown,
                destination_unique_rx_observed=len(received),destination_duplicates_observed=duplicates,
                unmatched_or_ambiguous_rx=unmatched_rx,pdr=pdr,goodput_bps=goodput,
                successful_same_boot_rtt_count=len(rtts),rtt_p95_ms=quantile95(rtts),
                generated_without_echo=len(generations)-len(echoed),invalid_echoes=invalid_echoes,
                range_m=None,one_way_delay_ms=None,rf_retry_count=None,airtime_us=None,
                raw_event_counts=dict(counts),issues=issues,
                limitations=["callback success is not end-to-end delivery", "one-way delay unavailable without synchronized clocks",
                             "RTT nearest-rank P95 covers successful same-origin-boot echoes; missing echoes remain counted",
                             "evidence_kind is provenance supplied by caller, not physical authentication",
                             "unknown receiver coverage/duration yields null metrics; RF retry/airtime/range not inferred"])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--log", action="append", required=True)
    p.add_argument("--output", required=True)
    args = p.parse_args()
    output = Path(args.output).resolve()
    root = Path(__file__).resolve().parents[2] / "simulation/outputs/E2-015"
    if not output.is_relative_to(root.resolve()) or output.exists():
        raise ValueError("output must be a new file under E2-015 outputs")
    events, parsing = [], Counter()
    for name in args.log:
        path = Path(name)
        if path.stat().st_size > 10*1024**2:
            raise ValueError("single bench log exceeds 10MiB analyzer limit")
        rows, info = parse_lines(path.read_text(encoding="utf-8",errors="replace").splitlines())
        events.extend(rows); parsing.update(info)
    result = analyze(events,json.loads(Path(args.config).read_text(encoding="utf-8")))
    result["parsing"] = dict(parsing)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write("\n")
    return int(bool(result["issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
