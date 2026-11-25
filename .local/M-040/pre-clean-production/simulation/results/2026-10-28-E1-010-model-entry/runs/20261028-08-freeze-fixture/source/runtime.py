"""Standard-library causal event entry; no wireless or model simulation.

The fixture backend is scripted and must never be counted as autonomous agents.
Each backend receives only a copy of one node's local context. An evidence packet
is made visible only after complete delivery. Logging is evaluator-only.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import time
import zlib

SCHEMA_VERSION = "edge-agent-event/1"
ACTION_TYPES = {"request", "respond", "consume", "finish"}


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    Path(path).write_bytes(encode(value) + b"\n")


def synthetic_png(rgb, size=64):
    """Generated solid-color compatibility input, not a scene or model result."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    pixels = (b"\x00" + bytes(rgb) * size) * size
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


def parse_action(raw):
    """Strict external tool JSON; no hidden regex repair or fallback actions."""
    if not isinstance(raw, str):
        raise ValueError("backend output must be text")
    action = json.loads(raw)
    if not isinstance(action, dict) or action.get("tool") not in ACTION_TYPES:
        raise ValueError("unknown tool or non-object output")
    fields = {"request": {"tool", "peer", "query", "deadline_s"},
              "respond": {"tool", "request_id", "body", "evidence_refs"},
              "consume": {"tool", "message_id"},
              "finish": {"tool", "answer", "evidence_refs"}}[action["tool"]]
    if set(action) != fields:
        raise ValueError("missing or extra tool fields")
    for key in fields - {"tool", "deadline_s", "evidence_refs"}:
        if not isinstance(action[key], str) or not action[key]:
            raise ValueError("tool string fields must be nonempty")
    if action["tool"] == "request":
        duration = action["deadline_s"]
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("deadline_s must be positive finite duration")
    if "evidence_refs" in action:
        refs = action["evidence_refs"]
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs) or len(set(refs)) != len(refs):
            raise ValueError("evidence_refs must be distinct strings")
    return action


class BudgetStop(RuntimeError):
    pass


class FixtureBackend:
    label = "fixture_scripted_not_model"

    def __init__(self, actions):
        self.actions = copy.deepcopy(actions)
        self.positions = {}

    def decide(self, node_id, context):
        position = self.positions.get(node_id, 0)
        self.positions[node_id] = position + 1
        return encode(self.actions[node_id][position]).decode("utf-8")


class Runtime:
    def __init__(self, nodes, backend, *, run_id="unit", max_calls=8,
                 max_action_bytes=4096, max_wire_bytes=32768, max_wall_s=15,
                 latency_s=0.25, event_sink=None):
        if (not isinstance(nodes, dict) or not nodes or
                any(not isinstance(node, str) or not isinstance(private, dict) for node, private in nodes.items())):
            raise ValueError("nodes must map IDs to private evidence dictionaries")
        for value in (max_calls, max_action_bytes, max_wire_bytes):
            if type(value) is not int or value < 0:
                raise ValueError("budgets must be nonnegative integers")
        if not math.isfinite(max_wall_s) or max_wall_s <= 0 or not math.isfinite(latency_s) or latency_s < 0:
            raise ValueError("invalid time budget or fixture latency")
        self.nodes = copy.deepcopy(nodes)
        self.backend = backend
        self.run_id, self.max_calls = run_id, max_calls
        self.max_action_bytes, self.max_wire_bytes = max_action_bytes, max_wire_bytes
        self.max_wall_s, self.latency_s = max_wall_s, latency_s
        self.calls = self.wire_bytes = 0
        self.now = 0.0
        self.started = time.monotonic()
        self.status = "running"
        self.events, self.messages, self.call_log = [], {}, []
        self.inboxes = {node: [] for node in nodes}
        self.consumed = {node: set() for node in nodes}
        self.finished = set()
        self.event_sink = event_sink

    def emit(self, kind, node_id=None, parents=(), **details):
        event = dict(schema_version=SCHEMA_VERSION, run_id=self.run_id,
                     event_id=f"e{len(self.events) + 1:06d}", kind=kind,
                     node_id=node_id, root_task_id="compatibility-fixture",
                     t_logical_s=self.now, wall_elapsed_s=time.monotonic() - self.started,
                     parent_event_ids=list(parents), backend=self.backend.label, details=details)
        self.events.append(event)
        if self.event_sink:
            self.event_sink(event)
        return event["event_id"]

    def stop(self, reason):
        self.status = "budget_stopped"
        self.emit("budget_stopped", reason=reason, calls=self.calls, wire_bytes=self.wire_bytes)
        raise BudgetStop(reason)

    def check_budget(self):
        if time.monotonic() - self.started > self.max_wall_s:
            self.stop("wall_seconds")

    def visible_evidence(self, node):
        evidence = copy.deepcopy(self.nodes[node])
        for mid in self.inboxes[node]:
            msg = self.messages[mid]
            if msg["packet"]["kind"] == "evidence":
                evidence[mid] = {"kind": "arrived_remote_evidence", "body": msg["packet"]["body"],
                                 "external_evidence_refs": msg["packet"]["evidence_refs"],
                                 "source": msg["packet"]["source"]}
        return evidence

    def context(self, node):
        # No messages[] global ledger, other private inputs, fixture action script,
        # labels/correctness evaluator, or queued remote packets in this boundary.
        return dict(node_id=node, peers=[peer for peer in self.nodes if peer != node],
                    logical_time_s=self.now, private_and_arrived_evidence=self.visible_evidence(node),
                    inbox=[copy.deepcopy(self.messages[mid]["packet"])
                           for mid in self.inboxes[node]], consumed_message_ids=sorted(self.consumed[node]))

    def _send(self, node, peer, kind, parents, **body):
        if peer not in self.nodes or peer == node:
            raise ValueError("peer must be another declared node")
        mid = f"m{len(self.messages) + 1:06d}"
        packet = dict(schema_version="edge-agent-packet/1", message_id=mid,
                      source=node, recipient=peer, kind=kind, **body)
        raw = encode(packet)
        if self.wire_bytes + len(raw) > self.max_wire_bytes:
            self.stop("wire_bytes")
        self.wire_bytes += len(raw)
        generated = self.emit("generated", node, parents, message_id=mid,
                              payload_utf8=raw.decode("utf-8"), payload_sha256=sha(raw),
                              payload_bytes=len(raw), evidence_refs=body.get("evidence_refs", []))
        sent = self.emit("sent", node, [generated], message_id=mid, recipient=peer,
                         payload_bytes=len(raw), payload_sha256=sha(raw),
                         transport="fixture_complete_packet_no_radio")
        self.messages[mid] = dict(packet=packet, raw=raw, sent_event=sent,
                                  complete_at=self.now + self.latency_s, arrived_event=None,
                                  expired_event=None)
        return mid

    def deliver_until(self, now):
        self.check_budget()
        if not math.isfinite(now) or now < self.now:
            raise ValueError("clock must be finite and nondecreasing")
        for mid, record in sorted(self.messages.items(), key=lambda item: (item[1]["complete_at"], item[0])):
            if record["arrived_event"] or record["expired_event"] or record["complete_at"] > now:
                continue
            self.now = record["complete_at"]
            packet = record["packet"]
            if self.now > packet["deadline_at_s"]:
                record["expired_event"] = self.emit("expired", packet["recipient"],
                                                    [record["sent_event"]], message_id=mid)
                continue
            record["arrived_event"] = self.emit("arrived_complete", packet["recipient"],
                                               [record["sent_event"]], message_id=mid,
                                               payload_bytes=len(record["raw"]), payload_sha256=sha(record["raw"]))
            self.inboxes[packet["recipient"]].append(mid)
        self.now = now

    def call(self, node):
        self.check_budget()
        if node not in self.nodes or node in self.finished:
            raise ValueError("unknown or finished node")
        if self.calls >= self.max_calls:
            self.stop("model_or_fixture_calls")
        ctx = self.context(node)
        prompt = encode(ctx)
        self.calls += 1
        started = self.emit("call_started", node, context_sha256=sha(prompt),
                            context_utf8=prompt.decode("utf-8"), context_bytes=len(prompt),
                            visible_evidence_ids=sorted(self.visible_evidence(node)))
        began = time.monotonic()
        raw = None
        try:
            raw = self.backend.decide(node, copy.deepcopy(ctx))
            ended = self.emit("call_finished", node, [started], raw_output=raw,
                              output_utf8_bytes=len(raw.encode("utf-8")) if isinstance(raw, str) else None,
                              duration_s=time.monotonic() - began,
                              output_tokens=None if self.backend.label.startswith("fixture") else "backend_log")
            self.call_log.append(dict(node_id=node, context_sha256=sha(prompt), raw_output=raw))
            self.check_budget()
            if isinstance(raw, str) and len(raw.encode("utf-8")) > self.max_action_bytes:
                self.stop("action_utf8_bytes")
            action = parse_action(raw)
            return self.apply(node, action, ended)
        except BudgetStop:
            raise
        except Exception as exc:
            self.status = "failed"
            self.emit("tool_or_backend_failed", node, [started],
                      error_type=type(exc).__name__, error=str(exc), raw_output=raw)
            raise

    def apply(self, node, action, parent):
        tool = action["tool"]
        refs = action.get("evidence_refs", [])
        if any(ref not in self.visible_evidence(node) for ref in refs):
            raise ValueError("unavailable evidence reference")
        if tool == "request":
            return self._send(node, action["peer"], "request", [parent],
                              query=action["query"], deadline_at_s=self.now + action["deadline_s"])
        if tool == "respond":
            request_id = action["request_id"]
            if request_id not in self.inboxes[node] or self.messages[request_id]["packet"]["kind"] != "request":
                raise ValueError("request has not completely arrived")
            request = self.messages[request_id]
            if self.now > request["packet"]["deadline_at_s"]:
                raise ValueError("request deadline expired")
            if not refs:
                raise ValueError("response requires visible evidence reference")
            return self._send(node, request["packet"]["source"], "evidence",
                              [parent, request["arrived_event"]], request_id=request_id,
                              body=action["body"], evidence_refs=refs,
                              deadline_at_s=request["packet"]["deadline_at_s"])
        if tool == "consume":
            mid = action["message_id"]
            if mid not in self.inboxes[node] or self.messages[mid]["packet"]["kind"] != "evidence":
                raise ValueError("evidence has not completely arrived")
            if mid in self.consumed[node]:
                raise ValueError("evidence already consumed")
            if self.now > self.messages[mid]["packet"]["deadline_at_s"]:
                raise ValueError("evidence no longer within deadline")
            self.consumed[node].add(mid)
            self.emit("consumed", node, [parent, self.messages[mid]["arrived_event"]], message_id=mid)
            return mid
        for ref in refs:
            if ref in self.messages and ref not in self.consumed[node]:
                raise ValueError("finish must explicitly consume arrived remote evidence first")
        self.finished.add(node)
        self.emit("finished", node, [parent], answer=action["answer"], evidence_refs=refs)
        return None

    def summary(self):
        return dict(status=self.status, backend=self.backend.label, calls=self.calls,
                    actual_model_forwards=0 if self.backend.label.startswith("fixture") else getattr(self.backend, "forward_started", 0),
                    scripted_fixture=self.backend.label.startswith("fixture"),
                    wire_payload_bytes=self.wire_bytes, logical_time_s=self.now,
                    messages=len(self.messages), completely_arrived=sum(bool(m["arrived_event"]) for m in self.messages.values()),
                    pending=sum(not m["arrived_event"] and not m["expired_event"] for m in self.messages.values()),
                    consumed=sum(map(len, self.consumed.values())), finished_nodes=sorted(self.finished))
