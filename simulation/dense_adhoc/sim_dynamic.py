"""Dynamic scenario: Wi-Fi data plane + LoRa control plane + mobility + autostart.

Reuses the validated protocol core from sim.py (ND, source routing, RREQ/RREP, queues)
and adds:
  * business traffic: each node generates a packet every U(2,3) s to a roster destination;
  * mobility: random-waypoint within the disc, links form and break continuously;
  * LoRa reference uplink: one gateway (rx) + N-1 senders (tx) at a configurable period,
    with real airtime (SF7/BW125) and a single half-duplex gateway receiver, so
    overlapping frames collide and both are lost;
  * autostart: nothing is configured at runtime, everything resumes from saved state.

Still no Wi-Fi collision model (deferral only), so Wi-Fi numbers are optimistic.
"""
import argparse
import heapq
import json
import math
import random
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S  # noqa: E402

SF, BW = 7, 125_000
PREAMBLE = 8
CR = 1  # 4/5


def lora_toa_s(payload_bytes):
    """Semtech LoRa time-on-air for SF7/BW125, explicit header, CRC on."""
    tsym = (1 << SF) / BW
    preamble = (PREAMBLE + 4.25) * tsym
    de = 1 if tsym > 0.016 else 0
    denom = 4 * (SF - 2 * de)
    num = 8 * payload_bytes - 4 * SF + 28 + 16
    nsym = 8 + max(math.ceil(num / denom) * (CR + 4), 0)
    return preamble + nsym * tsym


class LoRaPlane:
    """One gateway, N-1 senders. No retransmission; overlaps collide and are lost."""

    def __init__(self, n, period_ms, gateway=0, jitter_ms=250):
        self.n = n
        self.period = period_ms
        self.gateway = gateway
        self.jitter = jitter_ms
        self.rx_until = 0.0
        self.current = None          # (src, start, end, collided)
        self.frames = 0
        self.ok = 0
        self.collided = 0
        self.busy_ms = 0.0

    def offer(self, src, t, payload_bytes):
        toa = lora_toa_s(payload_bytes) * 1000.0
        self.frames += 1
        self.busy_ms += toa
        frame = dict(src=src, start=t, end=t + toa, collided=False)
        if self.current and frame["start"] < self.current["end"]:
            # overlap with the frame being received: both are corrupted
            frame["collided"] = True
            self.current["collided"] = True
            self.collided += 2
        self.current = frame
        return frame

    def finish(self, frame):
        if frame["collided"]:
            return False
        self.ok += 1
        return True


class SimDyn(S.Sim):
    def __init__(self, n, seed, cfg, speed=0.0, period_ms=10000, traffic=True,
                 lora=True, roster=8):
        super().__init__(n, seed, cfg, rate_bps=1_000_000)
        self.speed = speed
        self.traffic = traffic
        self.lora_on = lora
        self.roster = min(roster, n - 1)
        self.lora = LoRaPlane(n, period_ms) if lora else None
        self.data_seq = 0
        self.stats.update(dict(data_admitted=0, data_delivered=0, data_dropped=0,
                               data_routed=0, data_pending=0, hops=0,
                               lora_tx=0, lora_ok=0, lora_collided=0, lora_bad_payload=0))
        self.latency = []
        self.pending_data = {}       # (src,dst) -> list[(deadline, seq, submit_t)]
        self.rounds_active = {}      # (src,dst) -> deadline; mirrors an open RREQ round
        self.delivered = set()
        self.link_count = 0
        self.link_changes = 0
        self._adj = None
        # velocities for random waypoint
        self.vel = []
        rad = 60.0 * math.sqrt(n / 5.0)
        self.radius = rad
        for _ in range(n):
            a = self.rnd.uniform(0, 2 * math.pi)
            self.vel.append((math.cos(a) * speed, math.sin(a) * speed))
        if speed > 0:
            self.push(250.0, "move", None)
        if traffic:
            for nd in self.nodes:
                self.push(self.rnd.uniform(2000, 3000), "gen", nd.id)
        if lora:
            for nd in self.nodes:
                if nd.id == self.lora.gateway:
                    continue
                self.push(self.rnd.uniform(0, period_ms * 0.5), "lora", nd.id)

    # ---- event loop ------------------------------------------------------
    def run_until(self, t_end):
        while self.ev and self.ev[0][0] <= t_end:
            t, _, kind, payload = heapq.heappop(self.ev)
            self.now = t
            if kind == "hello":
                self.on_hello(payload, t)
            elif kind == "drain":
                nd = self.nodes[payload]
                if nd.queue > 0:
                    nd.queue -= 1
            elif kind == "rreq_land":
                self.on_rreq_land(payload["res"], payload["ttl"])
            elif kind == "land":
                for j in payload["targets"]:
                    if payload["kind"] == "hello":
                        self.receive_hello(j, payload["src"], t)
                    else:
                        self.receive_ack(j, payload["src"], t)
            elif kind == "move":
                self.step_mobility(t)
            elif kind == "gen":
                self.generate(payload, t)
            elif kind == "lora":
                self.lora_send(payload, t)
            elif kind == "lora_done":
                self.lora.finish(payload)
            elif kind == "data_hop":
                self.data_hop(payload, t)
            elif getattr(self, "extra_event", None) and self.extra_event(kind, payload, t):
                pass
            elif kind == "pending_expire":
                self.expire_pending(payload, t)
        self.now = max(self.now, min(t_end, self.now))

    # ---- mobility --------------------------------------------------------
    def step_mobility(self, t):
        r, speed = self.radius, self.speed
        for i, nd in enumerate(self.nodes):
            vx, vy = self.vel[i]
            x, y = nd.x + vx * 0.25, nd.y + vy * 0.25
            if x * x + y * y > r * r:
                a = self.rnd.uniform(0, 2 * math.pi)
                vx, vy = math.cos(a) * speed, math.sin(a) * speed
                nrm = max(1e-6, math.hypot(nd.x, nd.y))
                x, y = nd.x * 0.98, nd.y * 0.98
            nd.x, nd.y = x, y
            self.vel[i] = (vx, vy)
        adj = {i: frozenset(j for j in range(len(self.nodes))
                            if j != i and self.in_range(i, j)) for i in range(len(self.nodes))}
        if self._adj is not None:
            changed = sum(1 for i in adj if adj[i] != self._adj[i])
            self.link_changes += changed
        self._adj = adj
        self.link_count = sum(len(v) for v in adj.values()) // 2
        self.push(t + 250.0, "move", None)

    # ---- business traffic ------------------------------------------------
    def generate(self, nid, t):
        nd = self.nodes[nid]
        if not nd.alive:
            return
        self.data_seq += 1
        dst = self.rnd.randrange(len(self.nodes))
        if dst == nid:
            dst = (dst + 1) % len(self.nodes)
        self.stats["data_admitted"] += 1
        route = nd.routes.get(dst)
        if route and route["until"] > t and self.route_valid(nid, route, t):
            self.stats["data_routed"] += 1
            self.send_along(nid, dst, self.data_seq, list(route["path"]), 1, t, t)

        else:
            key = (nid, dst)
            self.pending_data.setdefault(key, []).append((t + S.SR_QUEUE_MS,
                                                          self.data_seq, t))
            self.stats["data_pending"] += 1
            if self.rounds_active.get((nid, dst), 0) <= t:
                self.rounds_active[(nid, dst)] = t + S.SR_DEADLINE_MS
                self.start_rreq(nid, dst, t, ttl=self.cfg.get("hop_limit", 4), force=True)
            self.push(t + S.SR_QUEUE_MS, "pending_expire", key)
        self.push(t + self.rnd.uniform(2000, 3000), "gen", nid)

    def route_valid(self, nid, route, t):
        for i in range(1, len(route["path"])):
            if not self.in_range(route["path"][i - 1], route["path"][i]):
                return False
        return self.live(nid, route["path"][1], t)

    def send_along(self, src, dst, seq, path, index, t, submit):
        nxt = path[index]
        res = self.transmit(src, "data", S.FRAME["data"], dst=nxt)
        if not res or nxt not in res["targets"]:
            self.stats["data_dropped"] += 1
            return
        self.stats["hops"] += 1
        self.push(res["t_end"], "data_hop",
                  dict(path=path, index=index, dst=dst, seq=seq,
                       submit=submit, origin=src))

    def data_hop(self, p, t):
        path, idx = p["path"], p["index"]
        if idx + 1 >= len(path):
            key = (p["origin"], p["seq"])
            if key not in self.delivered:
                self.delivered.add(key)
                self.stats["data_delivered"] += 1
                self.latency.append(t - p["submit"])
            return
        if not self.nodes[path[idx]].alive:
            self.stats["data_dropped"] += 1
            return
        self.send_along(path[idx], p["dst"], p["seq"], path, idx + 1, t, p["submit"])

    def expire_pending(self, key, t):
        lst = self.pending_data.get(key)
        if not lst:
            return
        keep = []
        for deadline, seq, submit in lst:
            if deadline <= t:
                self.stats["data_dropped"] += 1
            else:
                keep.append((deadline, seq, submit))
        if keep:
            self.pending_data[key] = keep
        else:
            del self.pending_data[key]

    def send_rrep(self, dst, path, req, ttl):
        before = self.rrep_success
        super().send_rrep(dst, path, req, ttl)
        if self.rrep_success == before:
            return
        src = path[0]
        route = self.nodes[src].routes.get(dst)
        if not route:
            return
        key = (src, dst)
        for deadline, seq, submit in self.pending_data.pop(key, []):
            if deadline > self.now:
                self.stats["data_routed"] += 1
                self.send_along(src, dst, seq, list(route["path"]), 1, self.now, submit)

    # ---- LoRa control plane ---------------------------------------------
    def lora_send(self, nid, t):
        nd = self.nodes[nid]
        if not nd.alive:
            self.push(t + self.lora.period, "lora", nid)
            return
        rows = min(len(nd.nd), 8)
        payload = 48 + 20 * rows
        self.stats["lora_tx"] += 1
        frame = self.lora.offer(nid, t, payload)
        self.push(frame["end"], "lora_done", frame)
        self.push(t + self.lora.period * self.rnd.uniform(0.95, 1.05), "lora", nid)


def run(n, cfg, seed, speed=0.0, period_ms=10000, duration_ms=60000, traffic=True,
        lora=True, labels="base"):
    sim = SimDyn(n, seed, cfg, speed=speed, period_ms=period_ms, traffic=traffic, lora=lora)
    sim.run_until(duration_ms)
    first_delivery = None
    pdr = (sim.stats["data_delivered"] / sim.stats["data_admitted"]
           if sim.stats["data_admitted"] else None)
    lat = sorted(sim.latency)
    out = dict(n=n, policy=labels, seed=seed, speed_mps=speed, lora_period_ms=period_ms,
               duration_s=duration_ms / 1000.0,
               alive=sum(1 for x in sim.nodes if x.alive),
               nodes_locked=sim.stats["nodes_locked"],
               mean_degree=round(sum(len([j for j in range(n)
                                          if j != i and sim.in_range(i, j)])
                                     for i in range(n)) / n, 1),
               link_changes=sim.link_changes,
               data_admitted=sim.stats["data_admitted"],
               data_delivered=sim.stats["data_delivered"],
               data_dropped=sim.stats["data_dropped"],
               data_pending=sim.stats["data_pending"],
               pdr=None if pdr is None else round(pdr, 3),
               latency_mean_ms=None if not lat else round(sum(lat) / len(lat), 1),
               latency_p95_ms=None if not lat else round(lat[int(0.95 * (len(lat) - 1))], 1),
               wi_fi_control_s=round((sim.stats["hello"] + sim.stats["ack"]) /
                                     (duration_ms / 1000.0), 2),
               rreq_s=round(sim.stats["rreq"] / (duration_ms / 1000.0), 2),
               lora_tx=sim.lora.frames,
               lora_ok=sim.lora.ok,
               lora_collided=sim.lora.collided,
               lora_delivery=None if not sim.lora.frames else
               round(sim.lora.ok / sim.lora.frames, 3),
               lora_duty=None if not lora else round(sim.lora.busy_ms / duration_ms, 3),
               lora_toa_ms=round(lora_toa_s(208) * 1000, 1))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[10, 20, 30])
    ap.add_argument("--policy", nargs="+", default=["base", "dense"])
    ap.add_argument("--speed", type=float, nargs="+", default=[0.0, 5.0])
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--duration", type=int, default=60000)
    ap.add_argument("--lora-period", type=int, nargs="+", default=[10000])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pol = {"base": S.BASE, "dense": S.DENSE, "measure": S.BASE_MEASURE}
    rows = []
    for n in a.nodes:
        for p in a.policy:
            for sp in a.speed:
                for per in a.lora_period:
                    for s in range(a.seeds):
                        r = run(n, pol[p], 1000 + s, sp, per, a.duration, labels=p)
                        rows.append(r)
                        print(json.dumps(r), flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()





