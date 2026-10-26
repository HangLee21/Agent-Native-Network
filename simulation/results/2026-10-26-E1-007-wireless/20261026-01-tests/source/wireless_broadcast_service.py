"""Auditable single-domain, no-ACK slotted broadcast service (E1-007).

Integer microsecond event jumps; deliberately a simplified CSMA model, not a
complete IEEE 802.11 implementation. See WIRELESS_SERVICE_IMPLEMENTATION.md.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter

US_PER_MODEL = 20_000_000
SLOT_US = 9
DIFS_US = 34
OVERHEAD_BYTES = 64
MAX_PAYLOAD_BYTES = 1472
CW_MIN = 15


def _ticks(value):
    scaled = float(value) * US_PER_MODEL
    nearest = round(scaled)
    # Recognize integer-event -> model float -> integer-event round trips only.
    if abs(scaled - nearest) <= 4 * math.ulp(scaled):
        return float(nearest)
    return scaled


def ppdu_duration_us(payload_bytes):
    if isinstance(payload_bytes, bool) or not isinstance(payload_bytes, int) or not 0 <= payload_bytes <= MAX_PAYLOAD_BYTES:
        raise ValueError("supported application length is 0..1472 bytes")
    return 20 + 4 * ((16 + 8 * (payload_bytes + OVERHEAD_BYTES) + 6 + 23) // 24)


class WirelessBroadcastService:
    def __init__(self, policy="fifo", seed=0, capacity_bytes=65536):
        if policy not in {"fifo", "latest_state"}:
            raise ValueError("policy must be fifo or latest_state")
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("seed must be an integer")
        if isinstance(capacity_bytes, bool) or not isinstance(capacity_bytes, int) or capacity_bytes < 0:
            raise ValueError("capacity_bytes must be a nonnegative integer")
        self.policy, self.seed, self.capacity_bytes = policy, seed, capacity_bytes
        self.mode = "wireless_broadcast"
        self.ledger = []
        self._records = []
        self._stations = {}
        self._active = {}
        self._ready = []
        self._now = 0.0
        self._idle_origin = 0
        self._high_versions = {}

    def _log(self, event, tick, record=None, **extra):
        item = dict(event=event, time_us=tick, time=tick / US_PER_MODEL)
        if record is not None:
            item.update(message_id=record["message_id"], source=record["source"], kind=record["kind"])
        self.ledger.append(dict(item, **extra))

    @staticmethod
    def _identity(source, kind, payload):
        """Only known complete snapshot schemas are eligible for replacement."""
        try:
            body = json.loads(payload)
            when = body.get("generated_at")
            info_time = float(when) if isinstance(when, (int, float)) and math.isfinite(when) else None
            if body.get("kind") != kind or body.get("source") != source:
                return None, None, info_time
            if kind == "self_state":
                state = body["state"]
                if not {"source", "seq", "mode", "target"}.issubset(state) or state["source"] != source:
                    return None, None, info_time
                if not isinstance(state["seq"], int):
                    return None, None, info_time
                return (source, kind, source), (state["seq"],), info_time
            if kind == "task_scene":
                scene = body["scene"]
                if not {"task", "phase", "workers", "witnesses", "version", "observed_at"}.issubset(scene):
                    return None, None, info_time
                version = scene["version"]
                if not isinstance(scene["task"], int) or not isinstance(version, list) or len(version) != 4:
                    return None, None, info_time
                if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in version):
                    return None, None, info_time
                return (source, kind, scene["task"]), tuple(version), info_time
            return None, None, info_time
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            return None, None, None

    def _station(self, source):
        return self._stations.setdefault(source, dict(queue=[], occupied=0, draw_count=0,
                                                     backoff=None, countdown_start=None))

    def _schedule_idle(self, station, activated_at):
        anchor = self._idle_origin + DIFS_US
        ready = max(anchor, activated_at + DIFS_US)
        station["countdown_start"] = anchor + ((ready - anchor + SLOT_US - 1) // SLOT_US) * SLOT_US

    def _activate(self, source, tick):
        station = self._stations[source]
        if not station["queue"] or source in self._active:
            return
        index = station["queue"][0]
        record = self._records[index]
        station["draw_count"] += 1
        key = f"E1-007|{self.seed}|{source}|{station['draw_count']}"
        backoff = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") % (CW_MIN + 1)
        station["backoff"] = backoff
        station["countdown_start"] = None
        self._log("head_activated", tick, record, draw_count=station["draw_count"],
                  backoff_slots=backoff, draw_key=key)
        if not self._active:
            self._schedule_idle(station, tick)

    def _next_tick(self):
        if self._active:
            return min(self._records[i]["tx_finish_us"] for i in self._active.values())
        return min((s["countdown_start"] + s["backoff"] * SLOT_US
                    for s in self._stations.values() if s["queue"] and s["countdown_start"] is not None), default=math.inf)

    def _start_batch(self, tick):
        contenders = []
        for source, station in self._stations.items():
            if station["queue"] and station["countdown_start"] is not None:
                attempt = station["countdown_start"] + station["backoff"] * SLOT_US
                if attempt == tick:
                    contenders.append(source)
        contenders.sort()
        self._log("contention_batch", tick, sources=contenders, collision=len(contenders) > 1)
        for source, station in self._stations.items():
            if not station["queue"] or source in contenders:
                continue
            before = station["backoff"]
            elapsed = max(0, (tick - station["countdown_start"]) // SLOT_US)
            station["backoff"] = max(0, before - elapsed)
            station["countdown_start"] = None
            self._log("backoff_frozen", tick, self._records[station["queue"][0]],
                      before_slots=before, completed_idle_slots=elapsed, remaining_slots=station["backoff"])
        for source in contenders:
            station = self._stations[source]
            index = station["queue"][0]
            record = self._records[index]
            duration = ppdu_duration_us(record["application_bytes"])
            record.update(status="transmitting", tx_start_us=tick, tx_finish_us=tick + duration,
                          collision=len(contenders) > 1)
            station["countdown_start"] = None
            self._active[source] = index
            self._log("tx_started", tick, record, finish_us=tick + duration, duration_us=duration,
                      collision=record["collision"], service_bytes=record["service_bytes"])

    def _finish_batch(self, tick):
        finished = sorted(source for source, index in self._active.items()
                          if self._records[index]["tx_finish_us"] == tick)
        for source in finished:
            index = self._active.pop(source)
            record = self._records[index]
            station = self._stations[source]
            assert station["queue"].pop(0) == index
            station["occupied"] -= record["service_bytes"]
            station["backoff"], station["countdown_start"] = None, None
            record["status"] = "collided" if record["collision"] else "delivered"
            self._log("tx_completed", tick, record, outcome=record["status"])
            if not record["collision"]:
                for recipient in record["recipients"]:
                    self._ready.append(dict(message_id=record["message_id"], source=source,
                        recipient=recipient, kind=record["kind"], payload=record["payload"],
                        generated_at=record["enqueued_at"], information_generated_at=record["information_generated_at"],
                        enqueued_at=record["enqueued_at"], delivered_at=tick / US_PER_MODEL,
                        delivered_at_us=tick))
                    self._log("delivered", tick, record, recipient=recipient, application_bytes=record["application_bytes"])
            self._activate(source, tick)
        if not self._active:
            self._idle_origin = tick
            for station in self._stations.values():
                if station["queue"]:
                    station["countdown_start"] = tick + DIFS_US
            self._log("channel_idle", tick, resume_at_us=tick + DIFS_US)

    def _advance(self, now):
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < self._now:
            raise ValueError("time must be finite, nonnegative and nondecreasing")
        self._now = float(now)
        horizon = math.floor(_ticks(now))
        while self._next_tick() <= horizon:
            tick = self._next_tick()
            if self._active:
                self._finish_batch(tick)
            else:
                self._start_batch(tick)

    def submit(self, now, source, recipients, kind, payload: bytes, key=None):
        if not isinstance(payload, bytes):
            raise TypeError("payload must be immutable bytes")
        if isinstance(source, bool) or not isinstance(source, int):
            raise TypeError("source must be an integer node ID")
        recipients = list(dict.fromkeys(recipients))
        if not recipients or any(isinstance(x, bool) or not isinstance(x, int) for x in recipients):
            raise ValueError("recipients must contain integer node IDs")
        self._advance(now)
        tick = math.ceil(_ticks(now))
        semantic_key, version, info_time = self._identity(source, kind, payload)
        index = len(self._records)
        digest = hashlib.sha256(payload).hexdigest()
        record = dict(message_id=f"m{index + 1:08d}", source=source, recipients=recipients,
                      kind=kind, payload=payload, payload_sha256=digest, application_bytes=len(payload),
                      service_bytes=len(payload) + OVERHEAD_BYTES, semantic_key=semantic_key, version=version,
                      enqueued_at=float(now), eligibility_us=tick, information_generated_at=info_time,
                      status="rejected", accepted=False)
        self._records.append(record)
        self._log("submitted", tick, record, enqueued_at=float(now), eligibility_us=tick,
                  information_generated_at=info_time, recipients=recipients, key=key,
                  semantic_key=semantic_key, version=version, payload_hex=payload.hex(),
                  payload_sha256=digest, application_bytes=len(payload), service_bytes=record["service_bytes"])
        station = self._station(source)
        def reject(reason):
            record["reject_reason"] = reason
            self._log("rejected", tick, record, reason=reason, occupied_bytes=station["occupied"])
            return record["message_id"]
        if len(payload) > MAX_PAYLOAD_BYTES:
            return reject("frame_too_large")
        old_index = None
        if self.policy == "latest_state" and semantic_key is not None:
            highest = self._high_versions.get(semantic_key)
            if highest and version < highest[0]:
                return reject("stale_version")
            if highest and version == highest[0] and digest != highest[1]:
                return reject("same_version_conflict")
            for candidate in station["queue"]:
                old = self._records[candidate]
                if old["status"] == "queued" and old["semantic_key"] == semantic_key:
                    old_index = candidate
                    if old["version"] == version and old["payload"] == payload and old["recipients"] == recipients:
                        record["status"] = "coalesced"
                        record["coalesced_into"] = old["message_id"]
                        self._log("coalesced", tick, record, into_message_id=old["message_id"])
                        return record["message_id"]
                    break
        old_bytes = self._records[old_index]["service_bytes"] if old_index is not None else 0
        if station["occupied"] - old_bytes + record["service_bytes"] > self.capacity_bytes:
            return reject("tail_drop_capacity")
        record.update(accepted=True, status="queued")
        station["occupied"] += record["service_bytes"] - old_bytes
        if old_index is not None:
            old = self._records[old_index]
            old["status"] = "replaced"
            station["queue"][station["queue"].index(old_index)] = index
            self._log("replaced", tick, old, by_message_id=record["message_id"], preserved_backoff_slots=station["backoff"])
        else:
            station["queue"].append(index)
        if self.policy == "latest_state" and semantic_key is not None:
            self._high_versions[semantic_key] = (version, digest)
        self._log("admitted", tick, record, occupied_bytes=station["occupied"],
                  replaced_message_id=self._records[old_index]["message_id"] if old_index is not None else None)
        if len(station["queue"]) == 1 and old_index is None:
            self._activate(source, tick)
        return record["message_id"]

    def next_event_time(self):
        ready = self._ready[0]["delivered_at"] if self._ready else math.inf
        return max(self._now, min(self._next_tick() / US_PER_MODEL, ready))

    def pop_due(self, now):
        self._advance(now)
        due, self._ready = self._ready, []
        return due

    @staticmethod
    def _percentile(values, fraction):
        if not values:
            return None
        ordered = sorted(values)
        position = fraction * (len(ordered) - 1)
        lo, hi = math.floor(position), math.ceil(position)
        return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)

    def stats(self, now):
        self._advance(now)
        horizon = math.floor(_ticks(now))
        rows = self._records
        counts = Counter(r["status"] for r in rows)
        done = [r for r in rows if r["status"] == "delivered"]
        attempted = [r for r in rows if "tx_start_us" in r]
        intervals = sorted((r["tx_start_us"], min(horizon, r["tx_finish_us"])) for r in attempted)
        attempt_us = sum(max(0, b - a) for a, b in intervals)
        busy_us, tail = 0, 0
        for begin, end in intervals:
            busy_us += max(0, end - max(begin, tail))
            tail = max(tail, end)
        latency = [r["tx_finish_us"] / US_PER_MODEL - r["enqueued_at"] for r in done]
        age = [r["tx_finish_us"] / US_PER_MODEL - r["information_generated_at"] for r in done
               if r["information_generated_at"] is not None]
        result = dict(observed_at=float(now), observed_through_us=horizon, mode=self.mode, policy=self.policy,
            seed=self.seed, model_time_seconds=20, time_unit="model_time", physical_time_unit="microsecond",
            capacity_bytes_per_source=self.capacity_bytes, overhead_bytes=OVERHEAD_BYTES,
            max_payload_bytes=MAX_PAYLOAD_BYTES, rate_bps=6_000_000, slot_us=SLOT_US, difs_us=DIFS_US, cw_min=CW_MIN,
            demanded=len(rows), accepted=sum(r["accepted"] for r in rows),
            dropped=counts["rejected"], rejected=counts["rejected"], coalesced=counts["coalesced"],
            replaced=counts["replaced"], collided=counts["collided"], pending=counts["queued"] + counts["transmitting"],
            delivered=counts["delivered"], transmitting=counts["transmitting"],
            queue_messages=counts["queued"], recipient_demand=sum(len(r["recipients"]) for r in rows),
            recipient_delivered=sum(len(r["recipients"]) for r in done),
            demand_application_bytes=sum(r["application_bytes"] for r in rows),
            demand_service_bytes=sum(r["service_bytes"] for r in rows),
            admitted_application_bytes=sum(r["application_bytes"] for r in rows if r["accepted"]),
            admitted_service_bytes=sum(r["service_bytes"] for r in rows if r["accepted"]),
            completed_service_bytes=sum(r["service_bytes"] for r in attempted if r["tx_finish_us"] <= horizon),
            delivered_application_bytes=sum(r["application_bytes"] for r in done),
            recipient_delivered_application_bytes=sum(r["application_bytes"] * len(r["recipients"]) for r in done),
            attempted_frames=len(attempted), collision_attempts=sum(r["collision"] for r in attempted),
            attempted_frame_bytes=sum(r["service_bytes"] for r in attempted),
            airtime_attempt_us=attempt_us, channel_busy_us=busy_us,
            airtime_attempt_seconds=attempt_us / 1e6, channel_busy_seconds=busy_us / 1e6,
            buffer_occupied_bytes=sum(s["occupied"] for s in self._stations.values()),
            buffer_bytes_by_source={str(k): s["occupied"] for k, s in self._stations.items()},
            ready_deliveries=len(self._ready), rejection_reasons=dict(Counter(r["reject_reason"] for r in rows if "reject_reason" in r)))
        result["recipient_unmet"] = result["recipient_demand"] - result["recipient_delivered"]
        for prefix, values in (("latency", latency), ("information_age", age)):
            result[prefix + "_mean"] = sum(values) / len(values) if values else None
            result[prefix + "_p95"] = self._percentile(values, .95)
            result[prefix + "_max"] = max(values) if values else None
            for statistic in ("mean", "p95", "max"):
                value = result[prefix + "_" + statistic]
                result[prefix + "_" + statistic + "_seconds"] = 20 * value if value is not None else None
        result["by_kind"] = {}
        for kind in sorted({r["kind"] for r in rows}):
            subset = [r for r in rows if r["kind"] == kind]
            result["by_kind"][kind] = dict(demanded=len(subset),
                statuses=dict(Counter(r["status"] for r in subset)),
                application_bytes=sum(r["application_bytes"] for r in subset))
        return result
