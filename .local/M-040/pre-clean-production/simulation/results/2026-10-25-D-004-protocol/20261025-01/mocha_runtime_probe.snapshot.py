#!/usr/bin/env python3
"""Bounded two-process MOCHA protocol run, with explicitly isolated ROS adapters.

Imports the complete pinned upstream modules and original SMACH. No AST extraction
or protocol/socket implementation replacement. ROS/CDR/LZ4 operations fail closed.
Output directories must be new. --prepare-smach fetches only 12 pinned small files.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import queue
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import types
import urllib.request

MOCHA_COMMIT = "bfbde0d186d77278085b25a365bf735d5acdc6bd"
SMACH_COMMIT = "f14c51a949519a6532125cc1fa5d026e07e210a0"  # official tag 3.0.3
SMACH_BLOBS = {
    "package.xml": "9193c18d984a4fd7c086bc442f485b85085f8bac",
    "smach/__init__.py": "8f1b40965f05e6184f5ad314107473c2ccbac905",
    "smach/concurrence.py": "3d40a8dbe0d27517f8b963d7eb70263b58a0024d",
    "smach/container.py": "04ab7f04b96441129ac69c7c9d2ed57c67bdea02",
    "smach/exceptions.py": "2f9e8acf891cfe9322a750227d42ff349b0be397",
    "smach/iterator.py": "5682b2d372fe51ebb6b526219c999d6d810c6672",
    "smach/log.py": "5ac01cc671b8e92e0c1e7cd06ca620add5d309a5",
    "smach/sequence.py": "1f4b75043c347e0f9aa7de0ec34cf7021cddbb17",
    "smach/state.py": "1d231a8db7f3ee2997a9e5d0725c89bb9d218aaa",
    "smach/state_machine.py": "8c27a0f126e38921e78c17d54f74331112e39f31",
    "smach/user_data.py": "f1da50bb17f2cc2182aaf6ffaa6ebd0c3322b4d8",
    "smach/util.py": "7fd436c5b4cefb43feb04ba813a2e5ce7f85d8e5",
}
MOCHA_MODULES = ["hash_comm", "database", "database_utils", "zmq_comm_node", "synchronize_channel"]
ADAPTERS = {
    "rclpy.time.Time": "Integer nanosecond arithmetic, comparison, seconds_nanoseconds and to_msg; not ROS clock domains.",
    "rclpy.logging/node": "Local logger and monotonic clock; no DDS, ROS executor or services.",
    "builtin_interfaces.msg.Time/mocha_core.msg": "Plain holders for Time, SMState and ClientStats telemetry; publish appends JSONL.",
    "rclpy.serialization": "Import-only placeholders; serialize_message and deserialize_message raise if called.",
    "lz4.frame": "Import-only placeholder; compress/decompress raise if called. Payloads are opaque supplied bytes.",
    "InstrumentedChannel": "Calls original callback_server/client unchanged; records requests, replies and arrival callbacks.",
    "trigger": "Explicit trigger_sync commands; RSSI discovery, translators and task topic consumers are outside this run.",
}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def smach_files(root, fetch=False):
    records = []
    for name, blob in SMACH_BLOBS.items():
        target = root / name
        url = f"https://raw.githubusercontent.com/ros/executive_smach/{SMACH_COMMIT}/smach/{name}"
        if not target.exists():
            if not fetch:
                raise FileNotFoundError(f"Missing {target}; run --prepare-smach first")
            data = urllib.request.urlopen(url, timeout=20).read()
            if git_blob(data) != blob:
                raise ValueError(f"Downloaded SMACH blob mismatch: {name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        data = target.read_bytes()
        if git_blob(data) != blob:
            raise ValueError(f"SMACH blob mismatch: {name}")
        records.append(dict(path=name, url=url, git_blob=blob, sha256=sha256(data), bytes=len(data)))
    return dict(repository="ros/executive_smach", tag="3.0.3", commit=SMACH_COMMIT, files=records)


def verify_sources(root, smach_root):
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest["commit"] != MOCHA_COMMIT:
        raise ValueError("Unexpected MOCHA source commit")
    for item in manifest["files"]:
        data = (root / "source" / item["path"]).read_bytes()
        if sha256(data) != item["sha256"] or git_blob(data) != item["git_blob"]:
            raise ValueError(f"MOCHA source mismatch: {item['path']}")
    return dict(mocha=manifest, smach=smach_files(smach_root))


@functools.total_ordering
class AdapterTime:
    def __init__(self, *, seconds=0, nanoseconds=0):
        self.nanoseconds = int(seconds * 1_000_000_000 + nanoseconds)

    def seconds_nanoseconds(self):
        return divmod(self.nanoseconds, 1_000_000_000)

    def to_msg(self):
        sec, nanosec = self.seconds_nanoseconds()
        return types.SimpleNamespace(sec=sec, nanosec=nanosec)

    def __eq__(self, other):
        return isinstance(other, AdapterTime) and self.nanoseconds == other.nanoseconds

    def __lt__(self, other):
        return self.nanoseconds < other.nanoseconds

    def __sub__(self, other):
        return types.SimpleNamespace(nanoseconds=self.nanoseconds - other.nanoseconds)


class EventLog:
    def __init__(self, path):
        self.file = path.open("x", encoding="utf-8")
        self.lock = threading.Lock()
        self.phase = "initialization"
        self.events = []

    def add(self, kind, **fields):
        row = dict(t_ns=time.perf_counter_ns(), pid=os.getpid(), phase=self.phase, kind=kind, **fields)
        with self.lock:
            self.events.append(row)
            self.file.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.file.flush()


class Logger:
    def __init__(self, events):
        self.events = events

    def __getattr__(self, level):
        if level not in {"debug", "info", "warn", "warning", "error"}:
            raise AttributeError(level)
        return lambda message, *a, **kw: self.events.add("log", level=level, message=str(message))


class Telemetry:
    def __init__(self):
        self.header = types.SimpleNamespace(stamp=None, frame_id="")


class NodeAdapter:
    def __init__(self, name, events):
        self.name, self.events = name, events
        self.logger = Logger(events)

    def get_logger(self):
        return self.logger

    def get_fully_qualified_name(self):
        return "/" + self.name

    def get_clock(self):
        return types.SimpleNamespace(now=lambda: AdapterTime(nanoseconds=time.monotonic_ns()))

    def create_publisher(self, msg_type, topic, depth):
        def publish(msg):
            fields = {key: getattr(msg, key) for key in ["state", "msg", "rtt", "bw", "answ_len"] if hasattr(msg, key)}
            self.events.add("publish", topic=topic, fields=fields)
        return types.SimpleNamespace(publish=publish)


def install_ros_adapters(events):
    def module(name):
        value = types.ModuleType(name)
        value.__path__ = []
        sys.modules[name] = value
        if "." in name:
            parent, child = name.rsplit(".", 1)
            setattr(sys.modules[parent], child, value)
        return value

    def unsupported(*a, **kw):
        events.add("unsupported_adapter_call")
        raise RuntimeError("ROS serialization/LZ4 is excluded from the isolated protocol run")

    module("rclpy")
    module("rclpy.time").Time = AdapterTime
    module("rclpy.logging").get_logger = lambda name: Logger(events)
    module("rclpy.node").Node = NodeAdapter
    serialization = module("rclpy.serialization")
    serialization.serialize_message = unsupported
    serialization.deserialize_message = unsupported
    module("builtin_interfaces")
    module("builtin_interfaces.msg").Time = Telemetry
    module("lz4")
    frame = module("lz4.frame")
    frame.compress = frame.decompress = unsupported
    importlib.import_module("mocha_core")
    msgs = module("mocha_core.msg")
    msgs.SMState = msgs.ClientStats = Telemetry


def records(dbl):
    headers = dbl.get_header_list()
    result = []
    for header in headers:
        m = dbl.find_header(header)
        result.append(dict(robot=m.robot_id, topic=m.topic_id, dtype=m.dtype, priority=m.priority,
                           timestamp_ns=m.ts.nanoseconds, header=header.hex(), payload=m.data.hex()))
    return result


def worker(args):
    sys.dont_write_bytecode = True
    verify_sources(args.source_root, args.smach_root)
    events = EventLog(args.output / f"{args.worker}_events.jsonl")
    sys.path.insert(0, str(args.smach_root))
    sys.path.insert(0, str(args.source_root / "source/mocha_core"))
    install_ros_adapters(events)
    threading.excepthook = lambda x: events.add("thread_exception", error="".join(traceback.format_exception(x.exc_type, x.exc_value, x.exc_traceback)))
    sync = importlib.import_module("mocha_core.synchronize_channel")
    db = importlib.import_module("mocha_core.database")
    node = NodeAdapter(args.worker, events)
    dbl = db.DBwLock(ros_node=node)

    def inserted(robot, topic, stamp, header):
        events.add("db_insert", robot=robot, topic=topic, timestamp_ns=stamp.nanoseconds,
                   header=header.hex(), payload=dbl.find_header(header).data.hex())
    dbl.insertion_cb = inserted

    class InstrumentedChannel(sync.Channel):
        def callback_server(self, msg):
            events.add("server_request", payload=msg.hex(), code=msg[:5].decode())
            answer = super().callback_server(msg)
            events.add("server_exchange", code=msg[:5].decode(), request=msg.hex(), reply=answer.hex(),
                       request_envelope_bytes=len(msg) + 6, reply_envelope_bytes=len(answer) + 6)
            return answer

        def callback_client(self, msg):
            events.add("client_arrival", payload=None if msg is None else msg.hex())
            return super().callback_client(msg)

    config = json.loads((args.output / "config.json").read_text(encoding="utf-8"))
    peer = "robot_b" if args.worker == "robot_a" else "robot_a"
    channel = InstrumentedChannel(dbl, args.worker, peer, config["robots"], config["client_timeout"], node)
    channel.run()
    time.sleep(0.15)
    modules = {name: importlib.import_module("mocha_core." + name).__file__ for name in MOCHA_MODULES}
    modules["smach"] = importlib.import_module("smach").__file__
    modules["zmq"] = importlib.import_module("zmq").__file__
    events.add("worker_started", modules=modules, sm_thread_alive=channel.th.is_alive(), server_thread_alive=channel.comm_node.th.is_alive())
    print(json.dumps(dict(ready=True, pid=os.getpid(), modules=modules)), flush=True)
    try:
        for line in sys.stdin:
            command = json.loads(line)
            operation = command["op"]
            if operation == "phase":
                events.phase = command["name"]
                answer = {"phase": events.phase}
            elif operation == "insert":
                m = command["record"]
                dbm = db.DBMessage(m["robot"], m["topic"], m.get("dtype", 1), m["priority"],
                                   AdapterTime(seconds=m["seconds"]), bytes.fromhex(m["payload"]))
                answer = {"header": dbl.add_modify_data(dbm).hex()}
            elif operation == "trigger":
                events.add("trigger_sync")
                channel.trigger_sync()
                answer = {"triggered": True}
            elif operation == "snapshot":
                with events.lock:
                    saved = list(events.events)
                answer = dict(records=records(dbl), busy=channel.sync.get_state(),
                              client_complete=sum(e["kind"] == "publish" and "/client_sync_complete/" in e["topic"] for e in saved),
                              sm_thread_alive=channel.th.is_alive(), server_thread_alive=channel.comm_node.th.is_alive(),
                              thread_exceptions=[e for e in saved if e["kind"] == "thread_exception"])
            elif operation == "stop":
                channel.stop()
                answer = dict(stopped=True, sm_thread_alive=channel.th.is_alive(), server_thread_alive=channel.comm_node.th.is_alive())
                events.add("worker_stopped", **answer)
                print(json.dumps(answer), flush=True)
                break
            else:
                raise ValueError(operation)
            print(json.dumps(answer), flush=True)
    finally:
        if channel.th.is_alive():
            channel.stop()
        events.file.close()


class Peer:
    def __init__(self, args, name):
        self.name = name
        self.queue = queue.Queue()
        self.stderr_file = (args.output / f"{name}_stderr.txt").open("x", encoding="utf-8")
        command = [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--worker", name,
                   "--source-root", str(args.source_root), "--smach-root", str(args.smach_root), "--output", str(args.output)]
        options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr_file, text=True, encoding="utf-8")
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(command, **options)
        def reader():
            for line in self.process.stdout:
                self.queue.put(line)
        self.reader = threading.Thread(target=reader, daemon=True)
        self.reader.start()
        self.ready = self.receive(8)

    def receive(self, timeout=5):
        try:
            return json.loads(self.queue.get(timeout=timeout))
        except queue.Empty as error:
            raise TimeoutError(f"{self.name} no response; exit={self.process.poll()}") from error

    def call(self, command):
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()
        return self.receive()

    def stop(self):
        answer = None
        forced = False
        if self.process.poll() is None:
            try:
                answer = self.call({"op": "stop"})
                self.process.wait(timeout=4)
            except (TimeoutError, subprocess.TimeoutExpired, BrokenPipeError):
                forced = True
                self.process.kill()
                self.process.wait(timeout=3)
        self.stderr_file.close()
        return dict(pid=self.process.pid, exit_code=self.process.returncode, forced=forced, response=answer)


def latest(snapshot):
    result = {}
    for m in snapshot["records"]:
        key = f"{m['robot']}:{m['topic']}"
        if key not in result or m["timestamp_ns"] > result[key]["timestamp_ns"]:
            result[key] = m
    return result


def free_ports():
    sockets = []
    try:
        for _ in range(2):
            s = socket.socket()
            s.bind(("127.0.0.1", 0))
            sockets.append(s)
        return [s.getsockname()[1] for s in sockets]
    finally:
        for s in sockets:
            s.close()


def run(args):
    if args.output.exists():
        raise FileExistsError("Use a new output directory")
    sources = verify_sources(args.source_root, args.smach_root)
    args.output.mkdir(parents=True)
    write_json(args.output / "sources.json", sources)
    shutil.copyfile(__file__, args.output / "mocha_runtime_probe.snapshot.py")
    import zmq
    dependency_names = ["rclpy", "smach", "zmq", "lz4", "yaml", "std_msgs"]
    environment = dict(python=sys.version, executable=sys.executable, platform=platform.platform(),
                       dependencies={n: (None if importlib.util.find_spec(n) is None else importlib.util.find_spec(n).origin) for n in dependency_names},
                       pyzmq=zmq.__version__, libzmq=zmq.zmq_version(), script_sha256=sha256(Path(__file__).read_bytes()),
                       source_root=str(args.source_root), smach_root=str(args.smach_root), adapters=ADAPTERS)
    write_json(args.output / "environment.json", environment)
    ports = free_ports()
    robots = {name: {"IP-address": "127.0.0.1", "base-port": ports[i], "clients": ["robot_b" if i == 0 else "robot_a"]}
              for i, name in enumerate(["robot_a", "robot_b"])}
    write_json(args.output / "config.json", dict(robots=robots, client_timeout=0.4,
               label="original_MOCHA_SMACH_ZMQ_with_isolated_ROS_adapter", max_seconds=args.max_seconds,
               listener="Upstream binds tcp://*:port; both clients use 127.0.0.1; no remote peers are used"))
    peers = []
    evidence, checks, cleanup = {}, [], {}
    start = time.monotonic()
    deadline = start + args.max_seconds
    watchdog_expired = threading.Event()
    def kill_at_deadline():
        watchdog_expired.set()
        for p in peers:
            if p.process.poll() is None:
                p.process.kill()
    timer = threading.Timer(args.max_seconds, kill_at_deadline)
    timer.daemon = True
    timer.start()

    def check(name, result):
        checks.append({"name": name, "passed": bool(result)})
        if not result:
            raise AssertionError(name)

    def snapshot(p):
        s = p.call({"op": "snapshot"})
        if s["thread_exceptions"]:
            raise RuntimeError(s["thread_exceptions"])
        return s

    def phase(name):
        for p in peers:
            if p.process.poll() is None:
                p.call({"op": "phase", "name": name})

    def insert(p, robot, topic, seconds, priority, text):
        return p.call({"op": "insert", "record": dict(robot=robot, topic=topic, seconds=seconds, priority=priority, payload=text.encode().hex())})

    def synchronize(p, completed):
        p.call({"op": "trigger"})
        limit = min(deadline - 3, time.monotonic() + 6)
        while time.monotonic() < limit:
            s = snapshot(p)
            if s["client_complete"] == completed and not s["busy"]:
                return s
            time.sleep(0.03)
        raise TimeoutError(f"{p.name} sync did not complete")

    error = None
    try:
        # Construct peers separately so startup failures are also owned by cleanup.
        for name in ["robot_a", "robot_b"]:
            p = Peer.__new__(Peer)
            peers.append(p)
            p.__init__(args, name)
        a, b = peers
        evidence["processes"] = [p.ready for p in peers]
        check("two_distinct_processes", a.process.pid != b.process.pid)
        phase("initial_sync")
        insert(a, 0, 7, 12, 3, "local-A")
        insert(a, 1, 1, 5, 1, "stale-A")
        insert(b, 1, 1, 10, 3, "old-state")
        insert(b, 1, 1, 20, 1, "new-state")
        insert(b, 1, 2, 15, 2, "task-evidence")
        evidence["a_before_sync"] = snapshot(a)
        check("remote_new_payload_absent_before_sync", latest(evidence["a_before_sync"])["1:1"]["payload"] == b"stale-A".hex())
        evidence["a_after_initial"] = synchronize(a, 1)
        check("newest_remote_payload_delivered", latest(evidence["a_after_initial"])["1:1"]["payload"] == b"new-state".hex())
        check("second_topic_delivered", latest(evidence["a_after_initial"])["1:2"]["payload"] == b"task-evidence".hex())
        check("old_remote_version_not_fetched", not any(m["payload"] == b"old-state".hex() for m in evidence["a_after_initial"]["records"]))
        phase("no_change_sync")
        evidence["a_after_no_change"] = synchronize(a, 2)
        check("no_change_database_unchanged", evidence["a_after_no_change"]["records"] == evidence["a_after_initial"]["records"])
        phase("updated_sync")
        insert(b, 1, 1, 30, 1, "newest-state")
        evidence["a_before_update_trigger"] = snapshot(a)
        check("source_update_not_instantly_visible", latest(evidence["a_before_update_trigger"])["1:1"]["payload"] == b"new-state".hex())
        evidence["a_after_update"] = synchronize(a, 3)
        check("updated_payload_delivered", latest(evidence["a_after_update"])["1:1"]["payload"] == b"newest-state".hex())
        phase("reverse_sync")
        evidence["b_after_reverse"] = synchronize(b, 1)
        check("latest_views_converge_bidirectionally", latest(evidence["a_after_update"]) == latest(evidence["b_after_reverse"]))
        cleanup[b.name] = b.stop()
        phase("peer_absent_timeout")
        a.call({"op": "trigger"})
        time.sleep(1.4)
        evidence["a_after_peer_absent"] = snapshot(a)
        check("missing_peer_returns_idle", not evidence["a_after_peer_absent"]["busy"])
        check("missing_peer_no_false_completion", evidence["a_after_peer_absent"]["client_complete"] == 3)
        check("missing_peer_database_unchanged", evidence["a_after_peer_absent"]["records"] == evidence["a_after_update"]["records"])
    except Exception:
        error = traceback.format_exc()
    finally:
        for p in peers:
            if hasattr(p, "process") and p.name not in cleanup:
                cleanup[p.name] = p.stop()
        timer.cancel()
        timer.join(timeout=1)
    event_rows = []
    for path in args.output.glob("*_events.jsonl"):
        event_rows.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    exchanges = [e for e in event_rows if e["kind"] == "server_exchange"]
    phases = {}
    for e in exchanges:
        p = phases.setdefault(e["phase"], dict(codes=[], request_envelope_bytes=0, reply_envelope_bytes=0))
        p["codes"].append(e["code"])
        p["request_envelope_bytes"] += e["request_envelope_bytes"]
        p["reply_envelope_bytes"] += e["reply_envelope_bytes"]
    checks.append(dict(name="no_change_requests_no_data", passed=phases.get("no_change_sync", {}).get("codes") == ["GHEAD", "DENDT"]))
    initial_requests = [bytes.fromhex(e["request"])[5:].hex() for e in exchanges if e["phase"] == "initial_sync" and e["code"] == "GDATA"]
    checks.append(dict(name="latest_then_priority_order", passed=initial_requests == ["0102000f0000", "010100140000"]))
    checks.append(dict(name="no_excluded_adapter_calls", passed=not any(e["kind"] == "unsupported_adapter_call" for e in event_rows)))
    checks.append(dict(name="no_background_thread_exceptions", passed=not any(e["kind"] == "thread_exception" for e in event_rows)))
    checks.append(dict(name="all_children_cleanly_stopped", passed=len(cleanup) == 2 and all(c["exit_code"] == 0 and not c["forced"] for c in cleanup.values())))
    checks.append(dict(name="within_runtime_budget", passed=not watchdog_expired.is_set() and time.monotonic() - start < args.max_seconds))
    result = dict(label="isolated_original_protocol_runtime_not_full_ROS_or_wireless_reproduction",
                  passed=error is None and all(c["passed"] for c in checks), error=error, checks=checks,
                  elapsed_seconds=time.monotonic() - start, cleanup=cleanup, evidence=evidence, phase_exchanges=phases,
                  byte_scope="MOCHA application frame including six-byte request ID; excludes ZMTP/TCP/IP/ACK/retransmissions/airtime",
                  adapters=ADAPTERS, script_sha256=environment["script_sha256"])
    write_json(args.output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "checks": checks, "elapsed_seconds": result["elapsed_seconds"], "cleanup": cleanup, "error": error}, indent=2))
    return 0 if result["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=Path("data/network_baselines/MOCHA"))
    parser.add_argument("--smach-root", type=Path, default=Path("simulation/outputs/D-004/dependencies/smach-3.0.3"))
    parser.add_argument("--prepare-smach", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--worker", choices=["robot_a", "robot_b"], help=argparse.SUPPRESS)
    parser.add_argument("--max-seconds", type=float, default=45)
    args = parser.parse_args()
    args.source_root, args.smach_root = args.source_root.resolve(), args.smach_root.resolve()
    if args.prepare_smach:
        manifest = smach_files(args.smach_root, fetch=True)
        write_json(args.smach_root / "manifest.json", manifest)
        print(json.dumps(dict(files=len(manifest["files"]), bytes=sum(x["bytes"] for x in manifest["files"]), commit=SMACH_COMMIT)))
        return 0
    if args.output is None or not 10 <= args.max_seconds <= 60:
        parser.error("--output required; --max-seconds must be 10..60")
    args.output = args.output.resolve()
    if args.worker:
        worker(args)
        return 0
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
