"""Protocol-level discrete-event simulation of the field_agent ad-hoc stack.

Purpose: compare the current policy against a dense-ad-hoc policy at 5..40 nodes and
expose scaling limits. It mirrors the firmware constants and state machine
(hello/ACK discovery, ND state, RREQ/RREP source routing, route cache, pending queue,
single in-flight send, input queue overflow) rather than Wi-Fi PHY details.

Stated modelling limits (do not read results as measured throughput):
  * one shared channel, half-duplex deferral; NO collisions, so results are optimistic
    on airtime and pessimistic nowhere else;
  * airtime is frame_bits/rate + fixed overhead, rate is a parameter, not measured;
  * propagation is a disk range model with no fading, and no hidden terminals.
"""

import argparse
import heapq
import itertools
import json
import math
import random

# ---- firmware constants (field_agent) -------------------------------------
ND_PEERS = 8
SR_PEERS = 8
SR_ROUTES = 8
SR_PENDING = 8
SR_SEEN = 32
SR_OUT = 12
PATH_MAX = 5
ND_CONFIRM_MS = 9000
ND_LOST_MS = 12000
SR_CACHE_MS = 10000
SR_DEADLINE_MS = 1500
SR_W_MS = 200
SR_QUEUE_MS = 250
INPUT_QUEUE = 16
HELLO_MS = (2000, 3000)
CALLBACK_TIMEOUT_MS = 1000

DENSE = dict(nd_peers=32, sr_peers=32, sr_routes=32, sr_seen=128, sr_pending=16,
             input_queue=64, hello_base=2500, hello_max=8000, ack="mutual",
             rreq="ring", rreq_dedupe="origin", rreq_rate_ms=500, warm=False, lock_on_overflow=False)

BASE = dict(nd_peers=ND_PEERS, sr_peers=SR_PEERS, sr_routes=SR_ROUTES, sr_seen=SR_SEEN,
            sr_pending=SR_PENDING, input_queue=INPUT_QUEUE, hello_base=2500,
            hello_max=2500, ack="always", rreq="flood", rreq_rate_ms=0, warm=True,
            lock_on_overflow=True)
# Same protocol, but no fail-closed death and a deep queue, so the control-plane load
# can be measured without the population collapsing first.
BASE_MEASURE = dict(BASE)
BASE_MEASURE.update(input_queue=64, lock_on_overflow=False)

FRAME = dict(hello=41, ack=41, rreq=62, rrep=62, data=90)


class Channel:
    """Single shared channel with half-duplex deferral (no collisions)."""

    def __init__(self, rate_bps, overhead_us=250):
        self.rate = rate_bps
        self.overhead = overhead_us / 1000.0
        self.busy_until = 0.0
        self.busy_ms = 0.0
        self.frames = 0

    def airtime(self, nbytes):
        return nbytes * 8 * 1000.0 / self.rate + self.overhead


class Node:
    __slots__ = ("id", "x", "y", "alive", "nd", "peers", "routes", "rreq_seen",
                 "pending", "rreq_out", "queue", "queue_high", "dropped", "locked",
                 "hello_due", "acks", "sent", "rx", "last_rreq")

    def __init__(self, nid, x, y, cfg):
        self.id = nid
        self.x, self.y = x, y
        self.alive = True
        self.locked = False
        self.nd = {}          # peer -> dict(boot,seen,ack,confirm)
        self.peers = {}       # sr_peers: peer -> live
        self.routes = {}      # dst -> dict(path, until)
        self.rreq_seen = {}   # (boot,request) -> until
        self.pending = {}
        self.rreq_out = 0
        self.queue = 0
        self.queue_high = 0
        self.dropped = 0
        self.hello_due = 0.0
        self.acks = 0
        self.sent = 0
        self.rx = 0
        self.last_rreq = -1e9


def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


class Sim:
    def __init__(self, n, seed, cfg, tx_range=120.0, rate_bps=1_000_000, service_hz=200.0):
        self.rnd = random.Random(seed)
        self.cfg = cfg
        self.tx_range = tx_range
        self.rate = rate_bps
        self.ch = Channel(rate_bps)
        self.service_hz = service_hz
        self.now = 0.0
        self.seq = itertools.count()
        self.ev = []
        self.nodes = []
        self.rrep_success = 0
        self.stats = dict(hello=0, ack=0, rreq=0, rrep=0, data=0, rreq_lost=0,
                          overflow_events=0, frames_dropped=0, nodes_locked=0)
        # uniform disc placement, radius scaled so mean degree is controlled by n
        radius = 60.0 * math.sqrt(n / 5.0)
        for i in range(n):
            r = radius * math.sqrt(self.rnd.random())
            a = self.rnd.uniform(0, 2 * math.pi)
            self.nodes.append(Node(i, r * math.cos(a), r * math.sin(a), cfg))
        for nd in self.nodes:
            self.push(nd.hello_due + self.rnd.uniform(*HELLO_MS), "hello", nd.id)

    # -- event plumbing ----------------------------------------------------
    def push(self, t, kind, payload):
        heapq.heappush(self.ev, (t, next(self.seq), kind, payload))

    def in_range(self, a, b):
        return dist(self.nodes[a], self.nodes[b]) <= self.tx_range

    def neighbors_of(self, nid):
        return [j for j in range(len(self.nodes)) if j != nid and self.in_range(nid, j)
                and self.nodes[j].alive]

    # -- radio -------------------------------------------------------------
    def transmit(self, src, kind, size, dst=None, extra=None):
        if not self.nodes[src].alive:
            return None
        t0 = max(self.now, self.ch.busy_until)
        air = self.ch.airtime(size)
        self.ch.busy_until = t0 + air
        self.ch.busy_ms += air
        self.ch.frames += 1
        self.nodes[src].sent += 1
        self.stats[kind] = self.stats.get(kind, 0) + 1
        targets = [dst] if dst is not None else self.neighbors_of(src)
        delivered = []
        for j in targets:
            if j == src or not self.in_range(src, j) or not self.nodes[j].alive:
                continue
            if self.enqueue_rx(j):
                delivered.append(j)
        if kind in ("hello", "ack") and delivered:
            self.push(t0 + air, "land", dict(kind=kind, src=src, targets=delivered))
        return dict(t0=t0, t_end=t0 + air, targets=delivered, extra=extra or {})

    def enqueue_rx(self, nid):
        nd = self.nodes[nid]
        nd.rx += 1
        if nd.queue >= self.cfg["input_queue"]:
            nd.dropped += 1
            self.stats["frames_dropped"] += 1
            self.stats["overflow_events"] += 1
            if self.cfg["lock_on_overflow"] and not nd.locked:
                nd.locked = True
                nd.alive = False
                self.stats["nodes_locked"] += 1
            return False
        nd.queue += 1
        nd.queue_high = max(nd.queue_high, nd.queue)
        # service at a fixed rate drains one slot
        self.push(self.now + 1000.0 / self.service_hz, "drain", nid)
        return True

    # -- discovery ---------------------------------------------------------
    def hello_period(self, nid):
        nd = self.nodes[nid]
        if self.cfg["hello_max"] <= self.cfg["hello_base"]:
            return self.cfg["hello_base"]
        deg = max(1, len(nd.nd))
        scale = min(1.0, 8.0 / deg) if self.cfg["ack"] == "mutual" else 1.0
        p = self.cfg["hello_max"] - (self.cfg["hello_max"] - self.cfg["hello_base"]) * scale
        return p

    def on_hello(self, src, t):
        nd = self.nodes[src]
        self.transmit(src, "hello", FRAME["hello"])
        if nd.alive:
            nd.hello_due = t + self.hello_period(src) * self.rnd.uniform(0.85, 1.15)
            self.push(nd.hello_due, "hello", src)

    def receive_hello(self, receiver, sender, t):
        """Called when a hello lands; updates receiver's view of sender."""
        if not self.nodes[receiver].alive:
            return
        rd = self.nodes[receiver]
        slot = rd.nd.get(sender)
        if slot is None:
            if len(rd.nd) >= self.cfg["nd_peers"]:
                return                      # silently full, mirrors neighbor_table_full
            slot = rd.nd[sender] = dict(boot=0, seen=0.0, ack=0.0, confirm=False)
        slot["seen"] = t
        slot["boot"] = 1
        if self.cfg["ack"] == "always":
            self.transmit(receiver, "ack", FRAME["ack"], dst=sender)

    def receive_ack(self, receiver, sender, t):
        if not self.nodes[receiver].alive:
            return
        rd = self.nodes[receiver]
        slot = rd.nd.setdefault(sender, dict(boot=0, seen=t, ack=0.0, confirm=False))
        slot["ack"] = t
        slot["confirm"] = True

    def live(self, nid, peer, t):
        rd = self.nodes[nid]
        slot = rd.nd.get(peer)
        if not slot:
            return False
        if t - slot["seen"] >= ND_LOST_MS:
            return False
        if self.cfg["ack"] == "mutual":
            # passive mutual evidence: both sides have heard each other recently
            back = self.nodes[peer].nd.get(nid)
            return bool(back) and (t - slot["seen"] < ND_CONFIRM_MS) and \
                (t - back["seen"] < ND_CONFIRM_MS)
        return slot["confirm"] and (t - slot["ack"] < ND_CONFIRM_MS)

    # -- routing -----------------------------------------------------------
    def start_rreq(self, src, dst, t, ttl=None, force=False):
        if not self.nodes[src].alive:
            return
        if ttl is None:
            ttl = self.cfg.get("hop_limit", 4)
        if self.cfg["rreq_rate_ms"] and not force and \
                t - self.nodes[src].last_rreq < self.cfg["rreq_rate_ms"]:
            return
        self.nodes[src].last_rreq = t
        rd = self.nodes[src]
        rd.rreq_out += 1
        req = rd.rreq_out
        rd.rreq_seen[(1, req)] = t + 5000
        res = self.transmit(src, "rreq", FRAME["rreq"], extra=dict(
            path=[src], dst=dst, req=req, ttl=ttl))
        if res:
            self.push(res["t_end"], "rreq_land", dict(res=res, ttl=ttl))

    def on_rreq_land(self, carrier, ttl):
        pkt = carrier["extra"]
        path, dst, req = pkt["path"], pkt["dst"], pkt["req"]
        for node in carrier["targets"]:
            if not self.nodes[node].alive:
                continue
            if node == dst:
                self.send_rrep(node, path, req, ttl)
                continue
            if len(path) + 1 > self.cfg.get("max_path", PATH_MAX):
                continue
            seen = self.nodes[node].rreq_seen
            # base mirrors the firmware: dedupe per (request, path), so the same node
            # reached over a different path re-floods and the SR_SEEN cap truncates the
            # search. dense dedupes per origin request (AODV-style) instead.
            if self.cfg.get("rreq_dedupe", "path") == "origin":
                key = (1, path[0], req)
            else:
                key = (1, path[0], req, tuple(path))
            if key in seen:
                continue
            if len(seen) >= self.cfg["sr_seen"]:
                # firmware reuses expired slots instead of rejecting forever
                for k in [k for k, exp in seen.items() if exp <= self.now]:
                    del seen[k]
                if len(seen) >= self.cfg["sr_seen"]:
                    self.stats["rreq_rejected"] = self.stats.get("rreq_rejected", 0) + 1
                    continue
            seen[key] = self.now + 5000
            newpath = path + [node]
            nttl = ttl - 1
            if nttl <= 0:
                continue
            res = self.transmit(node, "rreq", FRAME["rreq"] + 6 * max(0, len(newpath) - 4),
                                extra=dict(path=newpath, dst=dst, req=req, ttl=nttl))
            if res:
                self.push(res["t_end"], "rreq_land", dict(res=res, ttl=nttl))

    def send_rrep(self, dst, path, req, ttl):
        route_path = path + [dst]
        for i in range(len(route_path) - 2, -1, -1):
            res = self.transmit(route_path[i + 1], "rrep", FRAME["rrep"],
                                dst=route_path[i], extra=dict(path=route_path, req=req))
            if not res or route_path[i] not in res["targets"]:
                return
        src = route_path[0]
        if self.nodes[src].alive and len(self.nodes[src].routes) < self.cfg["sr_routes"]:
            self.nodes[src].routes[route_path[-1]] = dict(path=route_path,
                                                          until=self.now + SR_CACHE_MS)
            self.rrep_success += 1

    def discover(self, a, b):
        """Policy-aware discovery. dense = expanding ring (TTL 2 -> 3 -> 4)."""
        if self.cfg["rreq"] != "ring":
            before = self.rrep_success
            self.start_rreq(a, b, self.now, ttl=4, force=True)
            self.run_until(self.now + SR_DEADLINE_MS + 200)
            return self.rrep_success > before
        for ttl in (2, 3, 4):
            before = self.rrep_success
            self.start_rreq(a, b, self.now, ttl=ttl, force=True)
            self.run_until(self.now + SR_DEADLINE_MS)
            if self.rrep_success > before:
                return True
        return False

    # -- measurement -------------------------------------------------------
    def converge(self, deadline_ms):
        """All nodes know every in-range peer (capped by table size), mutually."""
        for nd in self.nodes:
            if not nd.alive:
                continue
            want = [j for j in self.neighbors_of(nd.id) if self.live(nd.id, j, self.now)]
            if len(nd.nd) < min(len(want), self.cfg["nd_peers"]):
                return False
            if len(want) < min(len(self.neighbors_of(nd.id)), self.cfg["nd_peers"]):
                return False
        return True

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

    def warm_tick(self, t):
        """Baseline policy: periodically refresh routes to roster destinations.

        Mirrors field_warm_tick(): at most one route query per node per tick.
        """
        if not self.cfg["warm"]:
            return
        cap = min(len(self.nodes) - 1, 8)
        for nid, nd in enumerate(self.nodes):
            if not nd.alive or nd.locked:
                continue
            for dst in range(1, cap + 1):
                if (dst in nd.routes and nd.routes[dst]["until"] - t > 4000):
                    continue
                if self.live(nid, dst, t):
                    continue
                self.start_rreq(nid, dst, t, ttl=4)
                break


def bfs_hops(adj, a, b):
    if a == b:
        return 0
    seen, frontier, d = {a}, [a], 0
    while frontier:
        d += 1
        nxt = []
        for u in frontier:
            for v in adj[u]:
                if v == b:
                    return d
                if v not in seen:
                    seen.add(v)
                    nxt.append(v)
        frontier = nxt
    return None


def measure(n, cfg, seed, rate_bps, conv_deadline_ms=25000.0, steady_ms=10000.0):
    sim = Sim(n, seed, cfg, rate_bps=rate_bps)
    t = 0.0
    conv_t = None
    while t < conv_deadline_ms:
        step = 250.0
        if cfg["warm"] and int(t) % 500 == 0:
            sim.warm_tick(t + step)
        sim.run_until(t + step)
        if conv_t is None and sim.now > 3000 and sim.converge(conv_deadline_ms):
            conv_t = sim.now
            break
        t += step

    # ---- steady-state window: rates are measured here, not during cold start ----
    mark_t, mark_busy = sim.now, sim.ch.busy_ms
    snap = {k: sim.stats.get(k, 0) for k in ("hello", "ack", "rreq", "rrep")}
    sim.run_until(mark_t + steady_ms)
    span = max(1.0, (sim.now - mark_t) / 1000.0)
    steady = {k: round((sim.stats.get(k, 0) - snap[k]) / span, 2)
              for k in ("hello", "ack", "rreq", "rrep")}
    busy = (sim.ch.busy_ms - mark_busy) / max(1.0, sim.now - mark_t)

    # ---- route reachability probe: random pairs that are not direct neighbours ----
    rnd = random.Random(seed ^ 0x5F5F)
    adj = {i: [j for j in range(n) if j != i and sim.in_range(i, j)
               and sim.nodes[j].alive] for i in range(n)}
    probes, ok, hops = 0, 0, []
    fails_within = fails_beyond = 0
    max_needed = 0
    rreq0 = sim.stats.get("rreq", 0)
    live_nodes = [x.id for x in sim.nodes if x.alive]
    for _ in range(60):
        if len(live_nodes) < 2:
            break
        a, b = rnd.sample(live_nodes, 2)
        if sim.live(a, b, sim.now):
            continue
        need = bfs_hops(adj, a, b)
        probes += 1
        if need:
            max_needed = max(max_needed, need)
        if sim.discover(a, b):
            r = sim.nodes[a].routes.get(b)
            ok += 1
            if r:
                hops.append(len(r["path"]))
        else:
            # attribute the failure: within the 4-hop TTL, or beyond it
            if need is None or need > 4:
                fails_beyond += 1
            else:
                fails_within += 1
        if probes >= 20:
            break

    out = dict(n=n, policy="dense" if cfg is DENSE else "base", seed=seed, rate_bps=rate_bps,
               convergence_ms=None if conv_t is None else round(conv_t, 1),
               nodes_total=n, nodes_locked=sim.stats["nodes_locked"],
               alive=sum(1 for x in sim.nodes if x.alive),
               overflow_events=sim.stats["overflow_events"],
               frames_dropped=sim.stats["frames_dropped"],
               steady_hello_s=steady["hello"], steady_ack_s=steady["ack"],
               steady_rreq_s=steady["rreq"], steady_rrep_s=steady["rrep"],
               control_per_s=round(steady["hello"] + steady["ack"], 2),
               channel_busy=round(busy, 4),
               neighbor_table_used=round(sum(len(x.nd) for x in sim.nodes) / n, 1),
               mean_degree=round(sum(len([j for j in range(n) if j != i and
                                          sim.in_range(i, j)]) for i in range(n)) / n, 1),
               route_probe=probes, route_ok=ok,
               route_ok_ratio=round(ok / probes, 3) if probes else None,
               rreq_frames_per_discovery=round((sim.stats.get("rreq", 0) - rreq0) / max(1, probes), 1),
               fails_within_ttl=fails_within, fails_beyond_ttl=fails_beyond,
               max_graph_hops=max_needed,
               mean_hops=round(sum(hops) / len(hops), 2) if hops else None,
               max_queue=max((x.queue_high for x in sim.nodes), default=0))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[5, 10, 20, 30, 40])
    ap.add_argument("--policy", choices=["base", "dense", "measure", "all"], default="all")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--rate", type=int, default=1_000_000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    table = [("base", BASE), ("measure", BASE_MEASURE), ("dense", DENSE)]
    rows = []
    for n in a.nodes:
        for pol, cfg in table:
            if a.policy not in ("all", pol):
                continue
            for s in range(a.seeds):
                rows.append(measure(n, cfg, 1000 + s, a.rate))
                print(json.dumps(rows[-1]), flush=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()

