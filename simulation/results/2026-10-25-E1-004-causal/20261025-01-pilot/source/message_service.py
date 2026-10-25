"""Deterministic shared application-byte service, using only the standard library.

Time is the caller's simulation time (not calibrated seconds). FIFO capacity holds
whole waiting and in-service packets; propagation does not occupy that buffer.
One no-ACK broadcast consumes payload + overhead bytes once. Recipient deliveries
are separate. Instant/fixed_delay deliberately relax service rate and capacity.
"""

from __future__ import annotations

import hashlib
import heapq
import math
from typing import Any


class MessageService:
    def __init__(self, mode="instant", delay=0.0, rate_bytes_per_time=1.0,
                 capacity_bytes=math.inf, overhead_bytes=0):
        if mode not in {"instant", "fixed_delay", "fifo"}:
            raise ValueError("mode must be instant, fixed_delay or fifo")
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be finite and nonnegative")
        if not math.isfinite(rate_bytes_per_time) or rate_bytes_per_time <= 0:
            raise ValueError("rate_bytes_per_time must be finite and positive")
        if capacity_bytes is None:
            capacity_bytes = math.inf
        if capacity_bytes != math.inf and (
                not math.isfinite(capacity_bytes) or capacity_bytes < 0
                or int(capacity_bytes) != capacity_bytes):
            raise ValueError("capacity_bytes must be a nonnegative integer or infinity")
        if isinstance(overhead_bytes, bool) or not isinstance(overhead_bytes, int) or overhead_bytes < 0:
            raise ValueError("overhead_bytes must be a nonnegative integer")
        self.mode = mode
        self.delay = float(delay) if mode != "instant" else 0.0
        self.rate_bytes_per_time = float(rate_bytes_per_time)
        self.capacity_bytes = capacity_bytes
        self.overhead_bytes = overhead_bytes
        self.ledger: list[dict[str, Any]] = []
        self._records: list[dict[str, Any]] = []
        self._events: list[tuple[float, int, int]] = []
        self._ready: list[dict[str, Any]] = []
        self._now = 0.0
        self._tail_finish = 0.0
        self._occupied = 0

    def _log(self, event, when, record, **extra):
        self.ledger.append(dict(event=event, time=when,
                                message_id=record["message_id"],
                                source=record["source"], kind=record["kind"], **extra))

    def _advance(self, now):
        if not isinstance(now, (int, float)) or not math.isfinite(now) or now < self._now:
            raise ValueError("time must be finite, nonnegative and nondecreasing")
        self._now = float(now)
        while self._events and self._events[0][0] <= now:
            when, index, stage = heapq.heappop(self._events)
            record = self._records[index]
            if stage == 0:
                self._log("service_started", when, record,
                          application_bytes=record["application_bytes"],
                          service_bytes=record["service_bytes"])
            elif stage == 1:
                if self.mode == "fifo":
                    self._occupied -= record["service_bytes"]
                record["service_complete"] = True
                self._log("service_completed", when, record,
                          service_bytes=record["service_bytes"])
            else:
                record["delivered"] = True
                for recipient in record["recipients"]:
                    item = dict(message_id=record["message_id"], source=record["source"],
                                recipient=recipient, kind=record["kind"],
                                payload=record["payload"], generated_at=record["generated_at"],
                                delivered_at=when)
                    self._ready.append(item)
                    self._log("delivered", when, record, recipient=recipient,
                              application_bytes=record["application_bytes"])

    def submit(self, now, source, recipients, kind, payload: bytes, key=None):
        """Submit immutable bytes; return an ID even if FIFO rejects the packet.

        Recipients are deduplicated in caller order. Self recipients are allowed
        and charged like any other destination; callers normally exclude source
        because their own state is locally available. An empty recipient list is
        rejected as invalid input. key is metadata only: no replacement occurs.
        """
        if not isinstance(payload, bytes):
            raise TypeError("payload must be immutable bytes")
        recipients = list(dict.fromkeys(recipients))
        if not recipients:
            raise ValueError("at least one recipient is required")
        self._advance(now)
        index = len(self._records)
        record = dict(message_id=f"m{index + 1:08d}", source=source,
                      recipients=recipients, kind=kind, key=key, payload=bytes(payload),
                      application_bytes=len(payload), service_bytes=len(payload) + self.overhead_bytes,
                      generated_at=float(now), accepted=False, delivered=False,
                      service_complete=False)
        self._records.append(record)
        self._log("submitted", now, record, recipients=list(recipients), key=key,
                  payload_hex=payload.hex(), payload_sha256=hashlib.sha256(payload).hexdigest(),
                  application_bytes=record["application_bytes"], service_bytes=record["service_bytes"])
        if self.mode == "fifo" and self._occupied + record["service_bytes"] > self.capacity_bytes:
            self._log("rejected", now, record, reason="tail_drop_capacity",
                      occupied_bytes=self._occupied, service_bytes=record["service_bytes"],
                      unmet_recipients=list(recipients))
            return record["message_id"]
        record["accepted"] = True
        start = max(float(now), self._tail_finish) if self.mode == "fifo" else float(now)
        finish = start + record["service_bytes"] / self.rate_bytes_per_time if self.mode == "fifo" else start
        arrival = finish + self.delay
        if not all(math.isfinite(t) for t in (start, finish, arrival)):
            raise ValueError("scheduled times overflowed; use finite representable service parameters")
        record.update(service_start=start, service_finish=finish, arrival=arrival)
        if self.mode == "fifo":
            self._occupied += record["service_bytes"]
            self._tail_finish = finish
        self._log("admitted", now, record, service_start=start, service_finish=finish,
                  arrival=arrival, service_bytes=record["service_bytes"])
        for stage, when in enumerate((start, finish, arrival)):
            heapq.heappush(self._events, (when, index, stage))
        self._advance(now)
        return record["message_id"]

    def next_event_time(self):
        """Next internal event or uncollected delivery; infinity if none exist."""
        event = self._events[0][0] if self._events else math.inf
        ready = self._ready[0]["delivered_at"] if self._ready else math.inf
        return max(self._now, min(event, ready))

    def pop_due(self, now):
        """Advance through <= now, returning full-body deliveries exactly once."""
        self._advance(now)
        due, self._ready = self._ready, []
        return due

    @staticmethod
    def _percentile(values, fraction):
        if not values:
            return None
        ordered = sorted(values)
        position = fraction * (len(ordered) - 1)
        low, high = math.floor(position), math.ceil(position)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    def stats(self, now):
        """Observe at now; never bill scheduled future work or consume deliveries.

        serviced_bytes includes the fractional portion of a packet transmitted by
        now. Buffer inventory still holds that complete packet until completion.
        Delivered means available at recipient, not that a task consumed it.
        """
        self._advance(now)
        admitted = [r for r in self._records if r["accepted"]]
        rejected = [r for r in self._records if not r["accepted"]]
        waiting = [r for r in admitted if now < r["service_start"]]
        serving = [r for r in admitted if r["service_start"] <= now < r["service_finish"]]
        propagating = [r for r in admitted if r["service_finish"] <= now < r["arrival"]]
        delivered = [r for r in admitted if r["delivered"]]
        complete = [r for r in admitted if r["service_complete"]]
        sum_bytes = lambda rows, key="service_bytes": sum(r[key] for r in rows)
        partial = sum(min(r["service_bytes"], max(0.0, now - r["service_start"]) * self.rate_bytes_per_time)
                      for r in serving)
        completed_bytes = sum_bytes(complete)
        serviced = completed_bytes + partial
        latency = [r["arrival"] - r["generated_at"] for r in delivered]
        result = dict(
            observed_at=float(now), mode=self.mode,
            time_unit="author_simulation_time", service_byte_unit="application_plus_configured_overhead",
            resource_relaxed=self.mode != "fifo", capacity_applied=self.mode == "fifo",
            rate_bytes_per_time=self.rate_bytes_per_time,
            capacity_bytes=None if self.capacity_bytes == math.inf else self.capacity_bytes,
            overhead_bytes=self.overhead_bytes, propagation_delay=self.delay,
            demanded=len(self._records), accepted=len(admitted), dropped=len(rejected),
            pending=len(admitted) - len(delivered), delivered=len(delivered),
            recipient_demand=sum(len(r["recipients"]) for r in self._records),
            recipient_delivered=sum(len(r["recipients"]) for r in delivered),
            demand_application_bytes=sum_bytes(self._records, "application_bytes"),
            demand_service_bytes=sum_bytes(self._records),
            admitted_application_bytes=sum_bytes(admitted, "application_bytes"),
            admitted_service_bytes=sum_bytes(admitted),
            rejected_application_bytes=sum_bytes(rejected, "application_bytes"),
            rejected_service_bytes=sum_bytes(rejected),
            completed_service_bytes=completed_bytes, serviced_bytes=serviced,
            remaining_service_bytes=sum_bytes(admitted) - serviced,
            queue_messages=len(waiting), queue_bytes=sum_bytes(waiting),
            in_service_messages=len(serving), in_service_buffer_bytes=sum_bytes(serving),
            in_service_remaining_bytes=sum_bytes(serving) - partial,
            buffer_occupied_bytes=self._occupied,
            propagation_messages=len(propagating), propagation_bytes=sum_bytes(propagating),
            delivered_application_bytes=sum_bytes(delivered, "application_bytes"),
            recipient_delivered_application_bytes=sum(r["application_bytes"] * len(r["recipients"]) for r in delivered),
            ready_deliveries=len(self._ready),
            latency_mean=sum(latency) / len(latency) if latency else None,
            latency_p95=self._percentile(latency, 0.95),
            latency_max=max(latency) if latency else None,
        )
        result["recipient_unmet"] = result["recipient_demand"] - result["recipient_delivered"]
        result["by_kind"] = {}
        for kind in dict.fromkeys(r["kind"] for r in self._records):
            rows = [r for r in self._records if r["kind"] == kind]
            done = [r for r in rows if r["delivered"]]
            accepted_rows = [r for r in rows if r["accepted"]]
            work = sum(r["service_bytes"] if r["service_complete"] else
                       min(r["service_bytes"], max(0.0, now - r["service_start"]) * self.rate_bytes_per_time)
                       if self.mode == "fifo" else 0.0 for r in accepted_rows)
            result["by_kind"][kind] = dict(demanded=len(rows), accepted=len(accepted_rows),
                dropped=len(rows) - len(accepted_rows), delivered=len(done),
                demand_application_bytes=sum_bytes(rows, "application_bytes"),
                demand_service_bytes=sum_bytes(rows), serviced_bytes=work,
                recipient_demand=sum(len(r["recipients"]) for r in rows),
                recipient_delivered=sum(len(r["recipients"]) for r in done))
        return result
