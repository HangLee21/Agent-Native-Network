"""Bounded probes of pinned upstream functions; no ROS, CARLA or radio run.

Requires existing source/manifest.json under --source-root (see runtime report).
AST nodes are compiled unchanged, avoiding heavyweight module imports. Fixture
objects are explicitly listed in the result. Never writes downloaded source.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import platform
import struct
import threading
from types import SimpleNamespace as NS
import sys
import urllib.request

import numpy as np

PINS = {
    "MOCHA": "bfbde0d186d77278085b25a365bf735d5acdc6bd",
    "AutoCast": "5a69701081dcda9741106ad749270dc27b647ee9",
    "AutoCastSim": "10837c2a942e92312ea1a53697bc4513d9325454",
}
REPOSITORIES = {"MOCHA": "KumarRobotics/MOCHA", "AutoCast": "hangqiu/AutoCast",
                "AutoCastSim": "hangqiu/AutoCastSim"}


def fetch_sources(root, manifest_path):
    """Restore pinned files from the archived manifest; never overwrite sources."""
    manifests = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, pin in PINS.items():
        m = manifests[name]
        assert m["commit"] == pin and m["repository"] == REPOSITORIES[name]
        for entry in m["files"]:
            relative = Path(entry["path"])
            assert not relative.is_absolute() and ".." not in relative.parts
            url = f"https://raw.githubusercontent.com/{REPOSITORIES[name]}/{pin}/{entry['path']}"
            assert entry["url"] == url
            path = root / name / "source" / relative
            if path.exists():
                raw = path.read_bytes()
            else:
                request = urllib.request.Request(url, headers={"User-Agent": "network-baseline-probe"})
                with urllib.request.urlopen(request, timeout=60) as response:
                    raw = response.read()
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"], str(path)
            blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            assert blob == entry["git_blob"], str(path)
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(raw)
        target = root / name / "manifest.json"
        if target.exists():
            assert json.loads(target.read_text(encoding="utf-8")) == m
        else:
            target.write_text(json.dumps(m, indent=2), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--fetch-manifest", type=Path,
                    help="Optional archived sources.json: download missing pinned files, hash-check before write")
    args = ap.parse_args()
    # Refuse reuse even if the existing directory is empty.
    args.output.mkdir(parents=True, exist_ok=False)
    if args.fetch_manifest:
        fetch_sources(args.source_root, args.fetch_manifest)
    manifest = {}
    for name, pin in PINS.items():
        m = json.loads((args.source_root / name / "manifest.json").read_text())
        assert m["commit"] == pin
        for entry in m["files"]:
            p = args.source_root / name / "source" / entry["path"]
            raw = p.read_bytes()
            assert hashlib.sha256(raw).hexdigest() == entry["sha256"], str(p)
            git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            assert git_blob == entry["git_blob"], str(p)
        manifest[name] = m
    (args.output / "sources.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    extraction = []

    def extract(repo, relative, symbol, env):
        path = args.source_root / repo / "source" / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        node = tree
        for part in symbol.split("."):
            node = next(n for n in node.body if getattr(n, "name", None) == part)
        # Do not rewrite nodes or decorators. Plain methods receive fixture self.
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), "exec"), env)
        extraction.append({"repo": repo, "file": relative, "symbol": symbol,
                           "start_line": node.lineno, "end_line": node.end_lineno})
        return env[node.name]

    results = []
    def record(name, inputs, observed, expected, fixtures):
        passed = observed == expected
        results.append(dict(name=name, inputs=inputs, observed=observed,
                            expected=expected, passed=passed, fixtures=fixtures))

    # Actual original six-byte wire header operations; no ROS Time calls.
    henv = {"struct": struct, "LENGTH": 6}
    header = extract("MOCHA", "mocha_core/mocha_core/hash_comm.py", "TsHeader", henv)
    h = header(robot_id=2, topic_id=3, secs=12, msecs=345)
    wire = h.bindigest()
    decoded = header.from_header(wire)
    record("mocha_header_roundtrip", [2, 3, 12, 345],
           [len(wire), decoded.robot_id, decoded.topic_id, decoded.secs, decoded.msecs],
           [6, 2, 3, 12, 345], "Construct numeric TsHeader fields directly; ROS conversion methods not invoked.")
    denv = {"HEADER_LENGTH": 6}
    serial = extract("MOCHA", "mocha_core/mocha_core/database_utils.py", "serialize_headers", denv)
    deser = extract("MOCHA", "mocha_core/mocha_core/database_utils.py", "deserialize_headers", denv)
    headers = [wire, header(robot_id=4, topic_id=1, secs=13, msecs=0).bindigest()]
    record("mocha_header_list_roundtrip", [x.hex() for x in headers],
           [x.hex() for x in deser(serial(headers))], [x.hex() for x in headers], "No dependency shim.")
    try:
        deser(b"12345")
        invalid_rejected = False
    except Exception:
        invalid_rejected = True
    record("mocha_malformed_header_list", "five bytes", invalid_rejected, True, "No dependency shim.")
    # Native get_header_list uses rclpy.time.Time() only as zero comparison epoch.
    # Supply scalar timestamps plus that epoch factory, without claiming ROS time verification.
    db_env = {"rclpy": NS(time=NS(Time=lambda: 0))}
    get_headers = extract("MOCHA", "mocha_core/mocha_core/database.py", "DBwLock.get_header_list", db_env)
    messages = [(1, 1, b"old", 9, 10), (1, 1, b"new", 1, 20), (1, 2, b"urgent", 5, 15), (2, 1, b"peer", 3, 18)]
    fixture_db = {}
    for robot, topic, key, priority, timestamp in messages:
        fixture_db.setdefault(robot, {}).setdefault(topic, {})[key] = NS(header=key, priority=priority, ts=timestamp)
    fixture = NS(db=fixture_db, lock=threading.Lock())
    record("mocha_latest_per_topic_then_priority", [[r,t,k.decode(),p,s] for r,t,k,p,s in messages],
           [v.decode() for v in get_headers(fixture, filter_latest=True)], ["urgent", "peer", "new"],
           "Fixture DB records use integer timestamps; rclpy.time.Time() replaced by zero epoch factory only.")
    record("mocha_robot_filter", {"robot": 1, "latest": True},
           [v.decode() for v in get_headers(fixture, filter_robot_id=1, filter_latest=True)], ["urgent", "new"],
           "Same scalar-time fixture; DB insertion/ROS services not exercised.")

    greedy = extract("AutoCastSim", "AVR/Sched.py", "mckp_greedy_scheduling_algorithm", {"np": np})
    reward = {"0": [3, 2, 0], "1": [2]}
    sizes = {"0": [300, 100, 10], "1": [100]}
    policy, values = greedy(reward, sizes)
    record("autocast_reward_per_size_order", {"reward": reward, "points": sizes},
           policy, [[1, 0], [0, 1], [0, 0]], "Original function; NumPy only; no reward geometry model invoked.")
    record("autocast_tie_break_rewards", {"reward": reward, "points": sizes},
           [round(float(x), 5) for x in values], [2.0001, 2.00001, 3.0], "Original deterministic small ID perturbation.")
    policy, _ = greedy({"0": [1, 2]}, {"0": [0, 10]})
    record("autocast_zero_size_retained_last", {"reward": [1,2], "points": [0,10]},
           policy, [[0,1],[0,0]], "No dependency shim; diagnostic zero-size input.")
    comm_env = {"threading": threading, "beacon_topic": "Beacon", "data_topic": "Data"}
    buffer = extract("AutoCastSim", "AVR/Comm.py", "LockBuffer", comm_env)
    b = buffer(NS(topic="Beacon", FrameId=12))
    b.set_content(NS(topic="Beacon", FrameId=11))
    record("autocast_out_of_order_beacon", [12,11], b.get_content().FrameId, 11,
           "SimpleNamespace received messages; no MQTT delivery simulation.")
    b = buffer(NS(topic="Data", FrameId=12, data=[1]))
    b.set_content(NS(topic="Data", FrameId=11, data=[2]))
    b.set_content(NS(topic="Data", FrameId=12, data=[3]))
    record("autocast_data_old_drop_equal_frame_merge", [[12,[1]],[11,[2]],[12,[3]]],
           [b.get_content().FrameId,b.get_content().data], [12,[1,3]], "SimpleNamespace received payloads.")
    object_env = {"np": np}
    extract("AutoCastSim", "AVR/DetectedObject.py", "ObjectForComm", object_env)
    detected = extract("AutoCastSim", "AVR/DetectedObject.py", "DetectedObject", object_env)
    beacon = extract("AutoCastSim", "AVR/Comm.py", "Beacon", comm_env)
    payload_sizes = []
    point_counts = []
    for npoints in [10, 1000]:
        obj = detected(0)
        obj.insert_point_cloud([[1.0,2.0,3.0] for _ in range(npoints)])
        msg = beacon(0,1,0,0,0,0,0,0,1,1,1,NS(x=0,y=0,z=0),[obj.get_obj_for_comm()],{},{},True)
        raw = json.dumps(msg, default=lambda o:o.__dict__).encode("utf-8")
        payload_sizes.append(len(raw))
        point_counts.append(len(json.loads(raw)["detected_object_list"][0]["point_cloud_list"]))
    record("autocast_beacon_contains_point_cloud", {"points":[10,1000]},
           point_counts, [10,1000], "Original DetectedObject/ObjectForComm/Beacon; fixture xyz points and speed. Original JSON serialization expression; no MQTT framing.")
    record("autocast_beacon_payload_growth", {"points":[10,1000],"json_bytes":payload_sizes},
           payload_sizes[1]-payload_sizes[0], 16830, "990 extra xyz rows at 17 JSON bytes each; application bytes only.")
    beacon_list = extract("AutoCastSim", "AVR/BeaconList.py", "BeaconList", {"threading": threading})
    bl = beacon_list(); bl.append_beacon_list("peer-A")
    before = list(bl.get_beacon_list()); bl.tick(); after = list(bl.get_beacon_list())
    bl.tick(); next_frame = list(bl.get_beacon_list())
    record("autocast_central_beacon_tick", ["append peer-A", "tick", "tick"],
           [before,after,next_frame], [[],["peer-A"],[]], "String marker payload; original cache implementation.")
    transmission = extract("AutoCastSim", "AVR/__init__.py", "Utils.transmission_time_sec", {})
    u = NS(Rate=7.2, AgentDebug=False, transmission_time_sec=transmission)
    tx = extract("AutoCastSim", "AVR/Collaborator.py", "Collaborator.TX_Data", {"Utils": u})
    sends = []
    def send_fixture(state, item, offset):
        duration = transmission(2250, 7.2) * 1000
        sends.append({"item": item, "offset_ms": offset, "duration_ms": duration})
        return duration
    sender = NS(id=0, TX_Detected_Object=send_fixture)
    last_idx = tx(sender, None, [["0",0],["0",1],["0",2]], [2250,2250,2250])
    record("autocast_100ms_budget_crossing", {"points_each":2250,"rate_Mbps":7.2,"schedule":[["0",0],["0",1],["0",2]]},
           {"last_index":last_idx,"sends":sends,"scheduled_end_ms":sends[-1]["offset_ms"]+sends[-1]["duration_ms"]},
           {"last_index":1,"sends":[{"item":0,"offset_ms":0,"duration_ms":60.0},{"item":1,"offset_ms":60.0,"duration_ms":60.0}],"scheduled_end_ms":120.0},
           "Original TX_Data and transmission_time_sec; TX_Detected_Object replaced by capture callback returning original payload airtime formula. No real transmit or delay.")
    report = {"scope":"original-function component probes, not full baseline reproduction",
              "python":sys.version,"platform":platform.platform(),"numpy":np.__version__,
              "python_executable":sys.executable,"numpy_file":np.__file__,
              "probe_script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "source_root":str(args.source_root.resolve()),"invocation":sys.argv,
              "upstream_nodes":extraction,"checks":results,
              "passed":sum(x["passed"] for x in results),"total":len(results),
              "not_run":["ROS2 services and sync state machine", "MQTT, CARLA and perception",
                         "wireless packet delivery/contention", "full driving or rescue task"]}
    (args.output / "probe_results.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
    print(json.dumps({"passed":report["passed"],"total":report["total"],"output":str(args.output)}))
    if report["passed"] != report["total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
