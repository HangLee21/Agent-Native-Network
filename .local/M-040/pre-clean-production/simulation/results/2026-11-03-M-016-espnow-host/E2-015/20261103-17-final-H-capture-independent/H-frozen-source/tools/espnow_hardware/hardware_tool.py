"""Enumerate by default; probe only explicitly bound ports; never flash firmware.

Run from the repository root with python -m tools.espnow_hardware.hardware_tool.
No persistent service or automatic RF run is installed by this module.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "ann.serial.v1"
MAC = re.compile(r"^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$")
METRICS = ("range_m", "pdr", "goodput_bps", "rtt_p95_ms", "rf_retries", "airtime_s")
MAX_BYTES = 2 * 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    # All run artifacts are newly created. No historical result is replaced.
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def measurement_ledger(reason="hardware_not_available"):
    return {"schema": "ann.hardware.measurements.v1", "evidence_kind": "not_measured",
            "metrics": {key: {"value": None, "status": "not_measured", "reason": reason,
                              "source": None} for key in METRICS}}


def enumerate_ports():
    """OS enumeration only. A CH340 match never asserts board identity."""
    try:
        from serial.tools import list_ports
        ports = [{key: getattr(p, key, None) for key in
                  ("device", "description", "hwid", "vid", "pid", "serial_number", "location")}
                 for p in list_ports.comports()]
        return {"status": "enumerated", "backend": "pyserial", "ports": ports,
                "board_identity": "unverified"}
    except (ImportError, OSError) as exc:
        first_error = str(exc)
    if os.name != "nt":
        return {"status": "unknown", "backend": None, "ports": [], "reason": first_error}
    shell = shutil.which("powershell.exe")
    if not shell:
        return {"status": "unknown", "backend": None, "ports": [], "reason": "no_enumerator"}
    script = ("[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
              "@(Get-CimInstance Win32_SerialPort -ErrorAction Stop | "
              "Select-Object DeviceID,Name,PNPDeviceID) | ConvertTo-Json -Compress")
    try:
        result = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, timeout=8, check=True)
        raw = json.loads(result.stdout.decode("utf-8-sig").strip() or "[]")
        raw = raw if isinstance(raw, list) else [raw]
        ports = []
        for item in raw:
            hwid = item.get("PNPDeviceID") or ""
            vid, pid = re.search(r"VID_([0-9A-F]{4})", hwid, re.I), re.search(r"PID_([0-9A-F]{4})", hwid, re.I)
            ports.append({"device": item["DeviceID"], "description": item.get("Name"),
                          "hwid": hwid, "vid": int(vid[1], 16) if vid else None,
                          "pid": int(pid[1], 16) if pid else None,
                          "serial_number": None, "location": None})
        return {"status": "enumerated", "backend": "windows_cim", "ports": ports,
                "board_identity": "unverified", "pyserial_error": first_error}
    except (subprocess.SubprocessError, UnicodeError, ValueError) as exc:
        return {"status": "unknown", "backend": "windows_cim", "ports": [],
                "reason": str(exc), "pyserial_error": first_error}


def bindings_from(config):
    if config.get("schema") != "ann.hardware.bindings.v1":
        raise ValueError("invalid bindings schema")
    bindings = config.get("bindings")
    if not isinstance(bindings, list) or len(bindings) > 5:
        raise ValueError("bindings must be a list of at most five devices")
    for key in ("id", "port", "node_id"):
        values = [str(b.get(key, "")).lower() for b in bindings]
        if len(set(values)) != len(values) or any(not v for v in values):
            raise ValueError("binding ids, ports and node_ids must be unique and nonempty")
    for b in bindings:
        if not MAC.fullmatch(b["node_id"]) or not isinstance(b.get("allow_probe"), bool):
            raise ValueError("binding needs MAC node_id and boolean allow_probe")
        if not b.get("binding_basis") or b.get("physically_confirmed") is not True:
            raise ValueError("binding needs explicit physical confirmation and its basis")
        if any(type(b.get(k)) is not int for k in ("vid", "pid")):
            raise ValueError("binding VID/PID must be integers")
        if not (b.get("serial_number") or b.get("location") or b.get("hwid")):
            raise ValueError("binding needs serial_number, location or exact OS hardware id")
    return bindings


def resolve_binding(binding, inventory):
    if binding.get("allow_probe") is not True:
        raise ValueError("probe is not enabled for binding")
    matches = [p for p in inventory.get("ports", [])
               if str(p.get("device", "")).lower() == binding["port"].lower()]
    if len(matches) != 1:
        raise ValueError("bound port missing or ambiguous")
    port = matches[0]
    for field in ("vid", "pid", "serial_number", "location", "hwid"):
        if binding.get(field) is not None and port.get(field) != binding[field]:
            raise ValueError("OS identity mismatch: " + field)
    return port


def parse_event(line):
    if len(line) > 4096:
        return None
    try:
        def pairs(items):
            row = {}
            for key, value in items:
                if key in row:
                    raise ValueError("duplicate JSON key")
                row[key] = value
            return row
        def constant(value):
            raise ValueError("non-finite JSON value")
        item = json.loads(line, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError):
        return None
    if isinstance(item, dict) and item.get("schema") == SCHEMA:
        return item
    return None


def command_bytes(command):
    encoded = json.dumps(command, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
    if len(encoded) > 512:
        raise ValueError("command exceeds 512 bytes including newline")
    return encoded


def validate_info(item, nonce, binding, *, allow_active=False):
    if not item or item.get("schema") != SCHEMA or item.get("event") != "info":
        raise ValueError("not an info response")
    checks = {"nonce": nonce, "firmware": "ann-espnow", "protocol": 1, "chip": "esp32s3"}
    for field, value in checks.items():
        if item.get(field) != value or (field == "protocol" and type(item.get(field)) is not int):
            raise ValueError("info mismatch: " + field)
    if item.get("mode") not in (("idle", "active") if allow_active else ("idle",)):
        raise ValueError("info mismatch: mode")
    if str(item.get("node_id", "")).lower() != binding["node_id"].lower():
        raise ValueError("info node_id mismatch")
    if not all(isinstance(item.get(k), str) and item[k] for k in ("boot_id", "build_id", "board")):
        raise ValueError("missing info identity fields")
    return item


def open_bound(binding, inventory):
    # Construct CLOSED, set requested control-line states, then open only this identity.
    resolve_binding(binding, inventory)
    try:
        import serial
    except ImportError as exc:
        raise RuntimeError("pyserial unavailable; enumeration fallback cannot probe") from exc
    port = serial.Serial(port=None, baudrate=115200, bytesize=8, parity="N", stopbits=1,
                         timeout=0, write_timeout=0.25, rtscts=False, dsrdtr=False)
    port.dtr = False
    port.rts = False
    port.port = binding["port"]
    try:
        port.open()
    except Exception:
        port.close()
        raise
    return port


class Capture:
    def __init__(self, out, evidence_kind="hardware_serial"):
        self.path = Path(out) / "serial.jsonl"
        self.stream = self.path.open("x", encoding="utf-8", newline="\n")
        self.total = 0
        self.pending = {}
        self.evidence_kind = evidence_kind
        self.malformed_devices = set()
        self.observed_boots = {}
        self.unique_rx = {}

    def record(self, device, direction, line):
        event = parse_event(line)
        if direction == "device_rx":
            if event is None and line.lstrip().startswith(b"{"):
                self.malformed_devices.add(device)
            if event and isinstance(event.get("boot_id"), str):
                self.observed_boots.setdefault(device, set()).add(event["boot_id"])
            if event and event.get("event") == "rx" and event.get("unique_receive") is True:
                identity = (event.get("origin_id"), event.get("origin_boot_id"), event.get("seq"))
                if all(type(value) in (str, int) for value in identity):
                    self.unique_rx.setdefault(device, set()).add(identity)
        entry = {"host_time": now(), "device_id": device, "direction": direction,
                 "raw": line.decode("utf-8", errors="replace"), "event": event,
                 "evidence_kind": self.evidence_kind}
        text = json.dumps(entry, ensure_ascii=True) + "\n"
        self.total += len(text.encode())
        if self.total > MAX_BYTES:
            raise RuntimeError("capture byte budget reached")
        self.stream.write(text)
        self.stream.flush()
        return entry["event"]

    def send(self, device, port, command):
        data = command_bytes(command)
        if port.write(data) != len(data):
            raise RuntimeError("partial serial command write")
        self.record(device, "host_tx", data)

    def poll(self, device, port):
        chunk = port.read(min(max(port.in_waiting, 1), 4096))
        if self.pending.get(device + "_discard"):
            if b"\n" not in chunk:
                return []
            _, chunk = chunk.split(b"\n", 1)
            self.pending.pop(device + "_discard", None)
        buf = self.pending.get(device, b"") + chunk
        events = []
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            event = self.record(device, "device_rx", line)
            if event is not None:
                events.append(event)
        if len(buf) > 4096:
            self.malformed_devices.add(device)
            self.record(device, "device_rx_oversize", buf[:4096])
            buf = b""  # Discard this malformed line until its next newline.
            self.pending[device + "_discard"] = True
        self.pending[device] = buf
        return events

    def close(self):
        self.stream.close()


def wait_response(device, port, capture, nonce, deadline):
    while time.monotonic() < deadline:
        for item in capture.poll(device, port):
            if item.get("nonce") == nonce:
                if item.get("event") == "error" or item.get("error") or item.get("ok") is False:
                    raise RuntimeError("firmware rejected command: " + str(item))
                return item
        time.sleep(0.01)
    raise TimeoutError("nonce response timeout")


def handshake(binding, port, capture, deadline, *, allow_active=False):
    nonce = secrets.token_hex(12)
    capture.send(binding["id"], port, {"cmd": "info", "nonce": nonce})
    item = wait_response(binding["id"], port, capture, nonce, min(deadline, time.monotonic() + 3))
    return validate_info(item, nonce, binding, allow_active=allow_active)


def validate_command_response(item, command):
    if item.get("event") != command or item.get("ok") is False:
        raise ValueError(command + " acknowledgement mismatch")
    if command == "stop" and "mode" in item and item["mode"] != "idle":
        raise ValueError("stop response does not report idle")
    return item


def validate_plan(plan, bindings):
    if plan.get("schema") != "ann.hardware.bench.v1" or plan.get("armed") is not True:
        raise ValueError("bench requires an explicit armed plan")
    ids = plan.get("device_ids", [])
    by_id = {b["id"]: b for b in bindings}
    if not isinstance(ids, list) or not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise ValueError("bench requires two to five unique devices")
    if any(key not in by_id or by_id[key]["allow_probe"] is not True for key in ids):
        raise ValueError("bench devices must all be bound and probe-enabled")
    if plan.get("sender_id") not in ids or plan.get("receiver_id") not in ids or plan["sender_id"] == plan["receiver_id"]:
        raise ValueError("invalid sender/receiver")
    for key, lo, hi in (("count", 1, 1000), ("interval_ms", 10, 60000), ("frame_bytes", 112, 250), ("capture_seconds", 1, 45)):
        if type(plan.get(key)) is not int or not lo <= plan[key] <= hi:
            raise ValueError("invalid plan field: " + key)
    if type(plan.get("echo")) is not bool or plan.get("max_runs") != 1:
        raise ValueError("bench needs boolean echo and max_runs=1")
    if plan["echo"] and plan["frame_bytes"] < 120:
        raise ValueError("echo frame requires at least 120 bytes")
    if not isinstance(plan.get("run_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", plan["run_id"]):
        raise ValueError("invalid run_id")
    if plan["count"] * plan["interval_ms"] > (plan["capture_seconds"] - 1) * 1000:
        raise ValueError("bench does not fit capture window with stop margin")
    if plan["count"] * plan["interval_ms"] > 60000:
        raise ValueError("bench exceeds 60 seconds")
    return by_id


def inspect_log(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("log missing or exceeds bounded import size")
    count = 0
    for line in path.read_bytes().splitlines():
        count += parse_event(line) is not None
    return {"source": str(path.resolve()), "sha256": sha(path), "schema_events": count,
            "evidence_kind": "unverified_external_log", "metrics_imported": False}


def source_hashes():
    return {str(p.relative_to(ROOT)): sha(p) for folder in
            (ROOT / "tools/espnow_hardware", ROOT / "hardware/eora_hub_400tb")
            for p in sorted(folder.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", choices=("H-001", "H-002"), default="H-001",
                        help="select the matching repository output root (default H-001)")
    parser.add_argument("--once", action="store_true", help="one bounded check; never loops")
    parser.add_argument("--bindings", type=Path, default=ROOT / "hardware/eora_hub_400tb/bindings.example.json")
    parser.add_argument("--probe", action="store_true", help="info only on allow_probe bound identities")
    parser.add_argument("--command", choices=("stats", "stop"), help="nonce command on one probed binding")
    parser.add_argument("--device", help="binding id for stats/stop")
    parser.add_argument("--bench", type=Path, help="one armed finite bench plan; implies probe")
    parser.add_argument("--log", type=Path, help="hash/classify one saved log; never imports measurements")
    parser.add_argument("--output", type=Path, required=True, help="new directory under simulation/outputs/<task-id>")
    args = parser.parse_args(argv)
    started = time.monotonic()
    deadline = started + 55
    out = args.output.resolve()
    allowed = (ROOT / "simulation/outputs" / args.task_id).resolve()
    if out.parent != allowed:
        parser.error("output must be a new run directory directly beneath simulation/outputs/" + args.task_id)
    if args.task_id == "H-002" and (not args.once or args.bench or args.command or args.device or args.log):
        parser.error("H-002 requires --once and permits only enumeration or --probe; bench/commands/log import are disabled")
    if args.command and (not args.probe or not args.device):
        parser.error("stats/stop requires --probe and --device")
    if args.bench and args.command:
        parser.error("bench and standalone command cannot be combined")
    # Validate everything before opening a port or creating output.
    config = read_json(args.bindings)
    bindings = bindings_from(config)
    plan = read_json(args.bench) if args.bench else None
    by_id = validate_plan(plan, bindings) if plan else {b["id"]: b for b in bindings}
    if args.command and args.device not in by_id:
        parser.error("unknown device")
    if plan and out.name != plan["run_id"]:
        parser.error("bench output directory must match frozen run_id")
    out.mkdir(parents=True, exist_ok=False)
    manifest = read_json(ROOT / "coordination/templates/RUN_MANIFEST.json")
    manifest.update(template_only=False, task_id=args.task_id, run_id=out.name, started_at=now(),
                    worktree=str(ROOT), command=[sys.executable, *sys.argv], python_executable=sys.executable,
                    config_file=str(args.bindings.resolve()), dirty_files_sha256=source_hashes(),
                    data_and_weights_sha256={str(args.bindings.resolve()): sha(args.bindings)},
                    seeds=[], output_directory=str(out), process_id=os.getpid(), status="running",
                    budget={"wall_seconds": 60, "internal_deadline_seconds": 55, "serial_bytes": MAX_BYTES, "bench_runs": 1 if plan else 0},
                    dependency_snapshot={"python": sys.version, "pyserial_available": importlib.util.find_spec("serial") is not None},
                    limitations=["No board identity inferred from USB bridge", "No target compilation or RF measurement asserted", "DTR/RTS requested false before open; OS transient behavior unverified"])
    if plan:
        manifest["data_and_weights_sha256"][str(args.bench.resolve())] = sha(args.bench)
        write_json(out / "bench_plan.json", plan)
    capture, opened = None, {}
    runtime = {"baseline_stats": {}, "final_stats": {}, "stats_errors": []}
    result = {"schema": "ann.hardware.check.v1", "time": now(), "status": "waiting_hardware",
              "board_identity": "unverified", "probes": [], "bench_started": False,
              "arm_attempted": False}
    ledger = measurement_ledger()
    exit_code = 0
    try:
        manifest["git_commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                capture_output=True, text=True, timeout=2, check=True).stdout.strip()
        inventory = enumerate_ports()
        write_json(out / "inventory.json", inventory)
        if inventory["status"] == "unknown":
            result["status"] = "enumeration_unknown"
        if args.log:
            result["external_log"] = inspect_log(args.log)
        selected = ([by_id[k] for k in plan["device_ids"]] if plan else
                    [b for b in bindings if b["allow_probe"] and (not args.command or b["id"] == args.device)])
        if args.probe or plan:
            capture = Capture(out)
            # Preflight all identities before opening any member of an armed set.
            for binding in selected:
                resolve_binding(binding, inventory)
            for binding in selected:
                if time.monotonic() + 4 >= deadline:
                    raise TimeoutError("no remaining probe budget")
                port = open_bound(binding, inventory)
                opened[binding["id"]] = port
                info = handshake(binding, port, capture, deadline, allow_active=args.command == "stop")
                result["probes"].append({"id": binding["id"], "status": "ready" if info["mode"] == "idle" else "identity_verified_active", "info": info,
                                         "board_identity": "unverified", "binding_basis": binding["binding_basis"]})
            if selected:
                result["status"] = "bound_firmware_ready"
                ledger = measurement_ledger("not_run")
        if args.command:
            nonce = secrets.token_hex(12)
            port = opened[args.device]
            capture.send(args.device, port, {"cmd": args.command, "nonce": nonce})
            result["command_response"] = wait_response(args.device, port, capture, nonce, min(deadline, time.monotonic() + 3))
            validate_command_response(result["command_response"], args.command)
            result["status"] = "stopped" if args.command == "stop" else "stats_received"
        if plan:
            for key in plan["device_ids"]:
                try:
                    nonce = secrets.token_hex(12)
                    capture.send(key, opened[key], {"cmd": "stats", "nonce": nonce})
                    stats = wait_response(key, opened[key], capture, nonce, min(deadline, time.monotonic() + 0.4))
                    runtime["baseline_stats"][key] = validate_command_response(stats, "stats")
                except Exception as exc:
                    runtime["stats_errors"].append({"id": key, "stage": "baseline", "error": str(exc)})
            if time.monotonic() + plan["capture_seconds"] + 8 >= deadline:
                raise TimeoutError("insufficient budget for frozen bench")
            # Arm every receiver/relay before any start; stop/disarm on any failure.
            result["arm_attempted"] = True
            for key in plan["device_ids"]:
                nonce = secrets.token_hex(12)
                capture.send(key, opened[key], {"cmd": "arm", "nonce": nonce,
                             "node_id": by_id[key]["node_id"].lower(), "run_id": plan["run_id"],
                             "duration_ms": (plan["capture_seconds"] + 5) * 1000})
                reply = wait_response(key, opened[key], capture, nonce, min(deadline, time.monotonic() + 3))
                if reply.get("event") != "arm":
                    raise ValueError("arm acknowledgement event mismatch")
            sender = plan["sender_id"]
            for key in plan["device_ids"]:
                if key != sender:
                    nonce = secrets.token_hex(12)
                    capture.send(key, opened[key], {"cmd": "start", "nonce": nonce, "run_id": plan["run_id"]})
                    reply = wait_response(key, opened[key], capture, nonce, min(deadline, time.monotonic() + 3))
                    if reply.get("event") != "start":
                        raise ValueError("start acknowledgement event mismatch")
            if time.monotonic() + plan["capture_seconds"] + 8 >= deadline:
                raise TimeoutError("insufficient budget after arming")
            command = {key: plan[key] for key in ("run_id", "count", "interval_ms", "frame_bytes", "echo")}
            command.update(cmd="bench", dst=by_id[plan["receiver_id"]]["node_id"], nonce=secrets.token_hex(12))
            # Hardware execution only reaches this line after explicit armed plan and all handshakes.
            result["bench_started"] = True
            runtime["window_start_ns"] = time.monotonic_ns()
            capture.send(sender, opened[sender], command)
            stop_at = time.monotonic() + plan["capture_seconds"]
            acknowledged = False
            while time.monotonic() < stop_at:
                for key, port in opened.items():
                    for event in capture.poll(key, port):
                        if key == sender and event.get("nonce") == command["nonce"]:
                            if event.get("event") == "error" or event.get("error"):
                                raise RuntimeError("firmware rejected bench: " + str(event))
                            acknowledged = True
                time.sleep(0.005)
            if not acknowledged:
                raise TimeoutError("bench nonce acknowledgement missing")
            result["status"] = "hardware_capture_unanalyzed"
            ledger = measurement_ledger("awaiting_receive_log_validation")
    except Exception as exc:
        result.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        exit_code = 1
    finally:
        # Stop every opened board after any possible bench submission, including errors.
        if result["arm_attempted"]:
            result["stop_attempts"] = []
            for key, port in opened.items():
                try:
                    nonce = secrets.token_hex(12)
                    capture.send(key, port, {"cmd": "stop", "nonce": nonce})
                    reply = wait_response(key, port, capture, nonce, min(deadline, time.monotonic() + 0.4))
                    validate_command_response(reply, "stop")
                    result["stop_attempts"].append({"id": key, "acknowledged": True, "response": reply})
                except Exception as exc:
                    result["stop_attempts"].append({"id": key, "acknowledged": False, "error": str(exc)})
                    result["status"] = "stop_unconfirmed"
                    exit_code = 1
            if result["bench_started"]:
                for key, port in opened.items():
                    try:
                        nonce = secrets.token_hex(12)
                        capture.send(key, port, {"cmd": "stats", "nonce": nonce})
                        stats = wait_response(key, port, capture, nonce, min(deadline, time.monotonic() + 0.4))
                        runtime["final_stats"][key] = validate_command_response(stats, "stats")
                    except Exception as exc:
                        runtime["stats_errors"].append({"id": key, "stage": "final", "error": str(exc)})
                try:
                    until = min(deadline - 2, time.monotonic() + 0.15)
                    while time.monotonic() < until:
                        for key, port in opened.items():
                            capture.poll(key, port)
                        time.sleep(0.005)
                except Exception as exc:
                    result.update(status="failed", error="final serial drain: " + str(exc))
                    exit_code = 1
                runtime["window_end_ns"] = time.monotonic_ns()
        result["cleanup_errors"] = []
        for key, port in opened.items():
            try:
                port.close()
            except Exception as exc:
                result["cleanup_errors"].append({"stage": "port_close", "id": key,
                                                "error": type(exc).__name__ + ": " + str(exc)})
        if capture:
            try:
                capture.close()
            except Exception as exc:
                result["cleanup_errors"].append({"stage": "capture_close",
                                                "error": type(exc).__name__ + ": " + str(exc)})
        if result["cleanup_errors"]:
            result["status"] = "cleanup_failed"
            exit_code = 1
        if result["bench_started"] and capture and capture.stream.closed:
            try:
                from .analysis_bridge import finalize_capture
                result["analysis"] = finalize_capture(ROOT, out, plan, result, capture, by_id, runtime)
                if result["analysis"]["status"] == "analyzed":
                    result["status"] = "hardware_capture_analyzed" if capture.evidence_kind == "hardware_serial" else "synthetic_capture_analyzed"
            except Exception as exc:
                result["analysis"] = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}
                result["status"] = "analysis_failed"
                exit_code = 1
        result["elapsed_seconds"] = time.monotonic() - started
        # A write failure must not prevent attempts to preserve the other artifacts.
        result["artifact_errors"] = []
        for name, value in (("check.json", result), ("measurements.json", ledger)):
            try:
                write_json(out / name, value)
            except Exception as exc:
                result["artifact_errors"].append({"artifact": name, "error": type(exc).__name__ + ": " + str(exc)})
                result["status"] = "artifact_write_failed"
                exit_code = 1
        manifest.update(finished_at=now(), exit_code=exit_code, status=result["status"],
                        cleanup_errors=result["cleanup_errors"], artifact_errors=result["artifact_errors"],
                        operation_error=result.get("error"))
        try:
            write_json(out / "RUN_MANIFEST.json", manifest)
        except Exception as exc:
            result["artifact_errors"].append({"artifact": "RUN_MANIFEST.json", "error": type(exc).__name__ + ": " + str(exc)})
            result["status"] = "artifact_write_failed"
            exit_code = 1
    print(json.dumps({"status": result["status"], "output": str(out), "opened_ports": len(opened)}, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
