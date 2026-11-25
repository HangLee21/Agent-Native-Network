"""Independent ann.serial.v1 bench analysis; no serial or radio access."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path

SCHEMA = "ann.serial.v1"
MODES = {"raw_no_retry", "reliable"}
RADIO_METRICS = ("range_m", "pdr", "goodput_bps", "rtt_p95_ms")


def strict_json(text):
    def pairs(items):
        value = {}
        for key,item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    def constant(value):
        raise ValueError("non-finite JSON number")
    return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)


def integer(value):
    return type(value) is int and value >= 0


def parse_lines(lines, source=None):
    events, ignored, malformed = [], 0, 0
    for line_number,line in enumerate(lines,1):
        if len(line.encode("utf-8")) > 16384:
            raise ValueError("serial line exceeds analyzer 16KiB bound")
        try:
            row = strict_json(line)
        except (ValueError, TypeError):
            if line.lstrip().startswith("{"):
                malformed += 1
            else:
                ignored += 1
            continue
        if not isinstance(row, dict) or row.get("schema") != SCHEMA:
            if (isinstance(row,dict) and row.get("direction") == "device_rx"
                    and isinstance(row.get("event"),dict) and row["event"].get("schema") == SCHEMA):
                # H's frozen serial.jsonl envelope; host commands are never RX.
                nested = dict(row["event"])
                nested["_capture_evidence_kind"] = row.get("evidence_kind")
                if source is not None:
                    nested["_source"] = dict(file=str(source),line=line_number)
                events.append(nested)
                continue
            ignored += 1
            continue
        if source is not None:
            row["_source"] = dict(file=str(source),line=line_number)
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
    if kind == "hardware_measured" and any(r.get("_capture_evidence_kind") == "synthetic" or r.get("evidence_kind")=="synthetic" for r in selected):
        raise ValueError("synthetic capture cannot be promoted to hardware measured evidence")
    issues, counts = [], Counter(r.get("event") for r in selected)
    clock_order_warnings = []
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
            clock_order_warnings.append(dict(node_id=r["node_id"],boot_id=r["boot_id"],t_us=r["t_us"],
                                            reason="buffered_event_timestamp_precedes_already_emitted_record",source=r.get("_source")))
        clocks[clock_key] = max(r["t_us"],clocks.get(clock_key,0))
        if r.get("event") != "generated":
            continue
        if config.get("source_node_id") is not None and r.get("node_id") != config["source_node_id"]:
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
    if config.get("source_node_id") is None and len({key[1] for key in generations})>1:
        issues.append("multiple generation origins require source_node_id selection")

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
    rx_evidence,echo_evidence = defaultdict(list),{}
    lengths_known = True
    for r in selected:
        event, key = r.get("event"), identify(r)
        frame, payload = r.get("frame_bytes"), r.get("payload_bytes")
        if frame is not None and (not integer(frame) or not 112 <= frame <= 250):
            issues.append("frame_bytes outside frozen ANN v1 112..250")
        if payload is not None and (not integer(payload) or (integer(frame) and payload != frame-112)):
            issues.append("payload_bytes inconsistent with frozen 112-byte protocol header")
        if event == "tx_submit":
            if key is not None and r.get("node_id")==r.get("origin_id") and integer(payload) and payload>0:
                attempts[key] += 1
            value = r.get("accepted")
            if value is True or r.get("status") == "accepted":
                accepted += 1
            elif value is not False and r.get("status") not in {"rejected", "error"}:
                submit_unknown += 1
        elif event == "tx_result":
            if r.get("success") is True or r.get("status") == "success" or (type(r.get("status")) is int and r["status"]==1):
                callbacks_ok += 1
            elif r.get("success") is False or r.get("status") == "failed" or (type(r.get("status")) is int and r["status"]==0):
                callbacks_failed += 1
            else:
                callbacks_unknown += 1
        elif (event == "rx" or (event=="echo" and r.get("unique_receive") is True)) and r.get("node_id") == destination and r.get("unique_receive") is not False:
            if config.get("source_node_id") is not None and r.get("origin_id")!=config["source_node_id"]:
                continue
            if key is None:
                unmatched_rx += 1
                continue
            rx_evidence[key].append(r.get("_source"))
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
        elif event=="duplicate" and r.get("node_id")==destination and key is not None and r.get("status") in {0,3}:
            duplicates += 1
        elif event=="echo_correlation":
            key=(run_id,r.get("request_origin_id"),r.get("request_boot_id"),r.get("request_seq"))
            if (key not in generations or r.get("same_source_boot") is not True
                    or r.get("node_id")!=key[1] or r.get("boot_id")!=key[2] or not integer(r.get("t_us"))):
                invalid_echoes += 1
                continue
            elapsed=r["t_us"]-generations[key]["t_us"]
            if elapsed<0:
                invalid_echoes += 1
            elif key not in echoed:
                echoed.add(key);rtts.append(elapsed/1000.0);echo_evidence[key]=r.get("_source")
        elif event == "echo" and r.get("unique_receive") is not True:
            # Legacy fixture marker only. Final E1 v3 uses echo_correlation.
            if key is None or r.get("node_id") != key[1] or r.get("boot_id") != key[2] or not integer(r.get("t_us")):
                invalid_echoes += 1
                continue
            elapsed = r["t_us"] - generations[key]["t_us"]
            if elapsed < 0:
                invalid_echoes += 1
            elif key not in echoed:
                echoed.add(key)
                rtts.append(elapsed / 1000.0)
                echo_evidence[key] = r.get("_source")
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
    delivery_reason = ("receiver_log_coverage_not_confirmed" if not complete else
                       "origin_boot_identity_ambiguous_or_unmatched" if unmatched_rx else
                       "log_integrity_issue" if issues else "no_generated_denominator" if not generations else None)
    goodput_reason = None if goodput is not None else (delivery_reason or
                         ("measured_window_missing_or_wrong_clock" if not duration_valid else
                          "payload_length_unknown" if not lengths_known else None))
    return dict(schema="ann.analysis.v1",run_id=run_id,mode=mode,evidence_kind=kind,
                generated_unique=len(generations),driver_accepted=accepted if not submit_unknown else None,
                driver_accepted_known=accepted,driver_acceptance_unknown=submit_unknown,
                link_callbacks_success=callbacks_ok,link_callbacks_failed=callbacks_failed,link_callbacks_unknown=callbacks_unknown,
                destination_unique_rx_observed=len(received),destination_duplicates_observed=duplicates,
                unmatched_or_ambiguous_rx=unmatched_rx,pdr=pdr,goodput_bps=goodput,
                successful_same_boot_rtt_count=len(rtts),rtt_p95_ms=quantile95(rtts),
                generated_without_echo=len(generations)-len(echoed),invalid_echoes=invalid_echoes,
                range_m=None,one_way_delay_ms=None,rf_retry_count=None,airtime_us=None,
                raw_event_counts=dict(counts),issues=issues,clock_order_warnings=clock_order_warnings,
                metric_status=dict(pdr=dict(status="calculated" if pdr is not None else "unavailable",reason=delivery_reason),
                                   goodput_bps=dict(status="calculated" if goodput is not None else "unavailable",reason=goodput_reason),
                                   rtt_p95_ms=dict(status="calculated_successful_echo_subset" if rtts else "unavailable",reason=None if rtts else "no_valid_same_source_boot_echo"),
                                   one_way_delay_ms=dict(status="unavailable",reason="cross_device_clock_synchronization_not_established"),
                                   range_m=dict(status="unavailable",reason="distance_not_measured"),
                                   rf_retry_count=dict(status="unavailable",reason="RF_retry_counter_not_observed"),
                                   airtime_us=dict(status="unavailable",reason="PHY_airtime_not_observed")),
                identity_evidence=[dict(identity=list(key),generated_source=row.get("_source"),
                                        destination_rx_sources=rx_evidence[key],echo_source=echo_evidence.get(key))
                                   for key,row in generations.items()],
                limitations=["callback success is not end-to-end delivery", "one-way delay unavailable without synchronized clocks",
                             "event creation timestamps may be emitted after later TX logs; ordering warnings alone do not prove clock regression",
                             "RTT nearest-rank P95 covers successful same-origin-boot echoes; missing echoes remain counted",
                             "evidence_kind is provenance supplied by caller, not physical authentication",
                             "unknown receiver coverage/duration yields null metrics; RF retry/airtime/range not inferred"])


def analyze_files(config_path, log_paths, manifest_paths=()):
    """Stable host API. Inputs read-only; returns ann.analysis.v1 with SHA provenance.

    H's host_tx/device_rx serial.jsonl envelopes are accepted. Hardware declaration
    requires its capture manifest and hardware_serial tags; not device attestation.
    """
    config_path = Path(config_path)
    config = strict_json(config_path.read_text(encoding="utf-8-sig"))
    events, parsing, sources = [], Counter(), []
    for name in log_paths:
        path = Path(name).resolve()
        data = path.read_bytes()
        if len(data)>10*1024**2:
            raise ValueError("single bench log exceeds 10MiB analyzer limit")
        rows, info = parse_lines(data.decode("utf-8",errors="replace").splitlines(),source=path)
        events.extend(rows);parsing.update(info)
        sources.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data)))
    manifests=[]
    for name in manifest_paths:
        path=Path(name).resolve(); data=path.read_bytes(); value=strict_json(data)
        manifests.append(dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),
                              task_id=value.get("task_id"),run_id=value.get("run_id"),status=value.get("status")))
    if config.get("evidence_kind")=="hardware_measured":
        if not any(m["task_id"]=="H-001" and m["status"]=="hardware_capture_unanalyzed" for m in manifests):
            raise ValueError("hardware metrics require H capture manifest")
        selected=[r for r in events if r.get("run_id")==config["run_id"]]
        if any(r.get("_capture_evidence_kind")!="hardware_serial" for r in selected):
            raise ValueError("hardware metrics require H hardware_serial capture, never fixture/raw unknown provenance")
    if parsing["malformed_json_lines"]:
        config=dict(config,receiver_log_complete=False)
    result=analyze(events,config)
    result.update(parsing=dict(parsing),source_logs=sources,source_manifests=manifests,
                  source_config=dict(path=str(config_path.resolve()),sha256=hashlib.sha256(config_path.read_bytes()).hexdigest()),
                  analyzer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", required=True)
    p.add_argument("--log", action="append", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--manifest", action="append",default=[])
    args = p.parse_args()
    output = Path(args.output).resolve()
    root = Path(__file__).resolve().parents[2] / "simulation/outputs/E2-015"
    if not output.is_relative_to(root.resolve()) or output.exists():
        raise ValueError("output must be a new file under E2-015 outputs")
    result = analyze_files(args.config,args.log,args.manifest)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("x",encoding="utf-8") as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False); stream.write("\n")
    return int(bool(result["issues"]))


if __name__ == "__main__":
    raise SystemExit(main())
