"""Algorithm v2 鈥?the candidate that is meant to be ported to firmware.

Differences from the earlier ad-hoc `dense` policy, all of them mechanisms rather
than parameter bumps:

1. Mobility-adaptive neighbour timers
   A link break must be detected within the time the pair traverses a fraction of
   the radio range, so `T_lost = clamp(0.3*R/v, 2 s, 12 s)` and `T_hello = T_lost/3`.
   At walking speed this reproduces the old 12 s/4 s; at 20 m/s it tightens to 2 s/0.7 s.

2. Gateway-scheduled LoRa uplink (8 up + 1 down) with an ALOHA fallback
   The gateway broadcasts a slot schedule on its single downlink every superframe.
   A node that misses the schedule falls back to a contention window at the end of
   the superframe, so a lost schedule never silences a node.

3. Token-bucket route discovery instead of a global forward cap
   Per-node bucket (burst B, rate R). Limits the *rate* of floods without truncating
   a single flood's coverage 鈥?the earlier fixed forward budget destroyed reachability.

4. Gratuitous RREP: an intermediate node holding a fresh route answers instead of
   forwarding, which cuts the flood radius in a dense graph.

5. Route-error propagation back to the origin (firmware already has SR_ERROR).
"""
import argparse
import json
import math
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S            # noqa: E402
import sim_dynamic as D    # noqa: E402
import sim_real as R       # noqa: E402
import sim_gw as G         # noqa: E402

RADIO_RANGE = 120.0


class SimAlg(G.SimGW):
    def __init__(self, n, seed, cfg, speed=0.0, period_ms=20000, channels=8,
                 dropout=0.0, sched_miss=0.02, bucket_burst=4, bucket_rate=4.0,
                 gratuitous=False, **kw):
        self.sched_miss = sched_miss
        self.bucket_burst = bucket_burst
        self.bucket_rate = bucket_rate
        self.gratuitous = gratuitous
        self.tokens = {}
        self.last_fill = {}
        self.sched_rx = {}
        self.aloha_fallback = 0
        # mobility-adaptive timers
        self.t_lost = max(2000.0, min(12000.0, 0.3 * RADIO_RANGE / max(speed, 0.5) * 1000.0))
        self.t_confirm = self.t_lost * 0.75
        self.hello_period_ms = max(700.0, self.t_lost / 3.0)
        super().__init__(n, seed, cfg, lora_mode="scheduled", fwd_cap=0, rerr=True,
                         speed=speed, period_ms=period_ms, channels=channels,
                         dropout=dropout, **kw)
        # keep the generic RNG jitter but use the adaptive period
        self.stats.update(dict(aloha_fallback=0, sched_missed=0, token_denied=0,
                               gratuitous_replies=0))

    # ---- mobility-adaptive ND -------------------------------------------
    def hello_period(self, nid):
        jitter = 0.85 + 0.3 * self.rnd.random()
        return self.hello_period_ms * jitter

    def live(self, nid, peer, t):
        slot = self.nodes[nid].nd.get(peer)
        if not slot or t - slot["seen"] >= self.t_lost:
            return False
        if self.cfg["ack"] == "mutual":
            back = self.nodes[peer].nd.get(nid)
            return bool(back) and (t - slot["seen"] < self.t_confirm) \
                and (t - back["seen"] < self.t_confirm)
        return slot["confirm"] and (t - slot["ack"] < self.t_confirm)

    # ---- token bucket for discovery -------------------------------------
    def _take_token(self, nid, t):
        tok = self.tokens.get(nid, float(self.bucket_burst))
        last = self.last_fill.get(nid, t)
        tok = min(float(self.bucket_burst), tok + (t - last) * self.bucket_rate / 1000.0)
        self.last_fill[nid] = t
        if tok < 1.0:
            self.tokens[nid] = tok
            self.stats["token_denied"] += 1
            return False
        self.tokens[nid] = tok - 1.0
        return True

    def start_rreq(self, src, dst, t, ttl, force=False):
        if not self._take_token(src, t):
            return
        return super().start_rreq(src, dst, t, ttl, force=True)

    # ---- gratuitous reply ------------------------------------------------
    def on_rreq_land(self, carrier, ttl):
        if not self.gratuitous:
            return super().on_rreq_land(carrier, ttl)
        pkt = carrier["extra"]
        path, dst = pkt["path"], pkt["dst"]
        for node in list(carrier["targets"]):
            if node == dst:
                continue
            route = self.nodes[node].routes.get(dst)
            if route and route["until"] > self.now and \
                    self.route_valid(node, route, self.now):
                # answer on behalf of the destination with the cached remainder
                merged = path + [node] + [x for x in route["path"][1:]]
                # a merged path is only usable if it is loop-free, short enough and
                # every hop is currently in range
                if len(set(merged)) != len(merged) or len(merged) > S.PATH_MAX:
                    continue
                if any(not self.in_range(merged[i], merged[i + 1])
                       for i in range(len(merged) - 1)):
                    continue
                self.stats["gratuitous_replies"] += 1
                super().send_rrep(dst, merged[:-1], pkt["req"], ttl)
                return
        return super().on_rreq_land(carrier, ttl)

    # ---- scheduled uplink with ALOHA fallback ---------------------------
    def superframe(self, t):
        self.dl_frames += 1
        air = D.lora_toa_s(48) * 1000.0
        self.dl_busy += air
        plan, slots = self.slot_plan()
        period = self.lora.period
        per_slot = D.lora_toa_s(208) * 1000.0 + self.guard
        window_start = t + period * 0.85
        for nid, (ch, idx) in plan.items():
            got = self.rnd.random() >= self.sched_miss
            self.sched_rx[nid] = got
            if not got:
                self.stats["sched_missed"] += 1
                self.push(window_start + self.rnd.uniform(0, period * 0.12),
                          "lora_aloha", dict(nid=nid, ch=ch))
                continue
            at = t + 60.0 + idx * per_slot
            if idx * per_slot + D.lora_toa_s(208) * 1000.0 > period * 0.85:
                continue
            self.push(at, "lora_slot", dict(nid=nid, ch=ch))
        self.push(t + period, "superframe", 0)

    def lora_aloha(self, p, t):
        self.stats["aloha_fallback"] += 1
        self.lora_slot(p, t)

    def extra_event(self, kind, payload, t):
        if kind == "lora_aloha":
            self.lora_aloha(payload, t)
            return True
        return super().extra_event(kind, payload, t)


def run(n, seed, speed=0.0, period_ms=20000, duration_ms=90000, channels=8,
        dropout=0.0, cfg=None, labels="algv2"):
    sim = SimAlg(n, seed, cfg or S.DENSE, speed=speed, period_ms=period_ms,
                 channels=channels, dropout=dropout)
    sim.run_until(duration_ms)
    pdr = (sim.stats["data_delivered"] / sim.stats["data_admitted"]
           if sim.stats["data_admitted"] else None)
    lat = sorted(sim.latency)
    lor = sim.lora.totals()
    pc = lambda q: (round(lat[int(q * (len(lat) - 1))], 1) if lat else None)
    return dict(n=n, seed=seed, speed_mps=speed, period_ms=period_ms, channels=channels,
                dropout=dropout, policy=labels,
                alive=sum(1 for x in sim.nodes if x.alive),
                t_lost_ms=round(sim.t_lost), hello_ms=round(sim.hello_period_ms),
                data_admitted=sim.stats["data_admitted"],
                data_delivered=sim.stats["data_delivered"],
                pdr=None if pdr is None else round(pdr, 3),
                lat_p50=pc(0.50), lat_p95=pc(0.95), lat_p99=pc(0.99),
                lat_mean=None if not lat else round(sum(lat) / len(lat), 1),
                rreq_s=round(sim.stats["rreq"] / (duration_ms / 1000.0), 2),
                token_denied=sim.stats["token_denied"],
                gratuitous=sim.stats["gratuitous_replies"],
                rerr_sent=sim.rerr_sent,
                lora_delivery=round(lor["ok"] / lor["frames"], 3) if lor["frames"] else None,
                lora_frames=lor["frames"],
                sched_missed=sim.stats["sched_missed"],
                aloha_fallback=sim.stats["aloha_fallback"],
                downlink_duty=round(sim.dl_busy / duration_ms, 4),
                link_changes=sim.link_changes)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[30])
    ap.add_argument("--speed", type=float, nargs="+", default=[0, 5, 10, 20])
    ap.add_argument("--dropout", type=float, nargs="+", default=[0.0, 0.2])
    ap.add_argument("--period", type=int, nargs="+", default=[20000])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--duration", type=int, default=90000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for n in a.nodes:
        for v in a.speed:
            for dr in a.dropout:
                for per in a.period:
                    for s in range(a.seeds):
                        r = run(n, 1000 + s, v, per, a.duration, 8, dr)
                        rows.append(r)
                        print(json.dumps(r), flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()



