"""Gateway-scheduled LoRa uplink (8 up + 1 down) plus Wi-Fi routing hardening.

Two algorithmic changes evaluated here:

1. LoRa: the single downlink is used to broadcast a per-superframe slot schedule.
   Each node then transmits in its own (channel, slot), so uplink collisions disappear
   instead of being merely reduced by more channels. Compared against the current
   random-access (ALOHA) scheme.

2. Wi-Fi: bounded RREQ forwarding (a per-request forward budget) and route-error
   propagation back to the source when a data hop fails, so a vanished relay is
   removed from the route table immediately instead of after ND_LOST.

Flash/RAM cost of each change is listed in analysis, not measured by this file.
"""
import argparse
import json
import math
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S            # noqa: E402
import sim_dynamic as D    # noqa: E402
import sim_real as R       # noqa: E402


class SimGW(R.SimReal):
    def __init__(self, n, seed, cfg, lora_mode="scheduled", fwd_cap=0, rerr=True,
                 lora_fail=0.05, guard_ms=20.0, **kw):
        self.lora_mode = lora_mode
        self.fwd_cap = fwd_cap
        self.rerr_on = rerr
        self.lora_fail = lora_fail
        self.guard = guard_ms
        self.dl_frames = 0
        self.dl_busy = 0.0
        self.fwd_used = {}
        self.rerr_sent = 0
        self.rerr_invalidations = 0
        super().__init__(n, seed, cfg, **kw)
        # replace the ALOHA schedule with slot scheduling
        if lora_mode == "scheduled":
            self.ev = [e for e in self.ev if e[2] != "lora"]
            self.push(0.0, "superframe", 0)

    # ---- scheduled uplink ------------------------------------------------
    def slot_plan(self):
        senders = [nd.id for nd in self.nodes if nd.id != 0]
        ch, slots = self.lora.channels, 1
        plan = {}
        for k, nid in enumerate(senders):
            plan[nid] = (k % ch, k // ch)
            slots = max(slots, k // ch + 1)
        return plan, slots

    def superframe(self, t):
        if self.lora_mode != "scheduled":
            return
        self.dl_frames += 1
        air = D.lora_toa_s(48) * 1000.0        # schedule frame ~48 B
        self.dl_busy += air
        plan, slots = self.slot_plan()
        period = self.lora.period
        per_slot = D.lora_toa_s(208) * 1000.0 + self.guard
        fit = slots * per_slot
        for nid, (ch, idx) in plan.items():
            if idx * per_slot + D.lora_toa_s(208) * 1000.0 > period:
                continue                       # schedule does not fit this superframe
            self.push(t + 60.0 + idx * per_slot, "lora_slot", dict(nid=nid, ch=ch))
        self.push(t + period, "superframe", 0)

    def lora_slot(self, p, t):
        nid, ch = p["nid"], p["ch"]
        nd = self.nodes[nid]
        if not nd.alive:
            return
        rows = min(len(nd.nd), 8)
        toa = D.lora_toa_s(48 + 20 * rows) * 1000.0
        self.stats["lora_tx"] += 1
        collide = False
        st = self.lora.rx[ch]
        if st["current"] and t < st["current"]["end"]:
            collide = True
            st["current"]["collided"] = True
        frame = dict(src=nid, start=t, end=t + toa, collided=collide, ch=ch)
        st["current"] = frame
        self.lora.frames[ch] += 1
        self.lora.busy_ms[ch] += toa
        self.push(frame["end"], "lora_done_fail", frame)

    def extra_event(self, kind, payload, t):
        if kind == "superframe":
            self.superframe(t)
            return True
        if kind == "lora_slot":
            self.lora_slot(payload, t)
            return True
        if kind == "lora_done_fail":
            if payload["collided"] or self.rnd.random() < self.lora_fail:
                return True
            self.lora.ok[payload["ch"]] += 1
            return True
        return super().extra_event(kind, payload, t)

    # ---- bounded RREQ forwarding ----------------------------------------
    def on_rreq_land(self, carrier, ttl):
        if not self.fwd_cap:
            return super().on_rreq_land(carrier, ttl)
        req = (carrier["extra"]["path"][0], carrier["extra"]["req"])
        used = self.fwd_used.get(req, 0)
        if used >= self.fwd_cap:
            self.stats["rreq_capped"] = self.stats.get("rreq_capped", 0) + 1
            return
        self.fwd_used[req] = used + 1
        return super().on_rreq_land(carrier, ttl)

    # ---- route error propagation ----------------------------------------
    def data_hop(self, p, t):
        path, idx = p["path"], p["index"]
        if idx + 1 >= len(path):
            return super().data_hop(p, t)
        if not self.nodes[path[idx]].alive or not self.in_range(path[idx], path[idx + 1]):
            self.stats["data_dropped"] += 1
            if self.rerr_on:
                self.route_error(p, idx, t)
            return
        super().data_hop(p, t)

    def route_error(self, p, idx, t):
        """Tell the origin the path broke and drop every route that uses this edge."""
        a, b = p["path"][idx], p["path"][idx + 1]
        self.rerr_sent += 1
        origin = p["origin"]
        for dst, route in list(self.nodes[origin].routes.items()):
            edges = list(zip(route["path"], route["path"][1:]))
            if (a, b) in edges or (b, a) in edges:
                del self.nodes[origin].routes[dst]
                self.rerr_invalidations += 1
        self.stats["rreq_capped"] = self.stats.get("rreq_capped", 0)


def run(n, cfg, seed, speed=0.0, period_ms=10000, duration_ms=60000, channels=8,
        dropout=0.0, lora_mode="scheduled", fwd_cap=0, labels="dense"):
    sim = SimGW(n, seed, cfg, lora_mode=lora_mode, fwd_cap=fwd_cap, rerr=True,
                speed=speed, period_ms=period_ms, traffic=True, channels=channels,
                dropout=dropout)
    sim.run_until(duration_ms)
    pdr = (sim.stats["data_delivered"] / sim.stats["data_admitted"]
           if sim.stats["data_admitted"] else None)
    lat = sorted(sim.latency)
    lor = sim.lora.totals()
    return dict(n=n, policy=labels, seed=seed, speed_mps=speed, channels=channels,
                lora_mode=lora_mode, fwd_cap=fwd_cap, dropout=dropout,
                period_ms=period_ms,
                alive=sum(1 for x in sim.nodes if x.alive),
                data_admitted=sim.stats["data_admitted"],
                data_delivered=sim.stats["data_delivered"],
                pdr=None if pdr is None else round(pdr, 3),
                latency_mean_ms=None if not lat else round(sum(lat) / len(lat), 1),
                latency_p95_ms=None if not lat else round(lat[int(0.95 * (len(lat) - 1))], 1),
                rreq_s=round(sim.stats["rreq"] / (duration_ms / 1000.0), 2),
                rreq_capped=sim.stats.get("rreq_capped", 0),
                rerr_sent=sim.rerr_sent, rerr_invalidations=sim.rerr_invalidations,
                lora_frames=lor["frames"], lora_ok=lor["ok"],
                lora_delivery=round(lor["ok"] / lor["frames"], 3) if lor["frames"] else None,
                lora_busy_per_ch=round(lor["busy_ms"] / (duration_ms * channels), 3),
                downlink_frames=sim.dl_frames,
                downlink_duty=round(sim.dl_busy / duration_ms, 4))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[30])
    ap.add_argument("--speed", type=float, nargs="+", default=[0.0, 5.0])
    ap.add_argument("--dropout", type=float, nargs="+", default=[0.0, 0.2])
    ap.add_argument("--period", type=int, nargs="+", default=[10000, 25000])
    ap.add_argument("--lora-mode", nargs="+", default=["aloha", "scheduled"])
    ap.add_argument("--fwd-cap", type=int, nargs="+", default=[0, 8])
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--duration", type=int, default=60000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for n in a.nodes:
        for sp in a.speed:
            for dr in a.dropout:
                for per in a.period:
                    for lm in a.lora_mode:
                        for cap in a.fwd_cap:
                            for s in range(a.seeds):
                                r = run(n, S.DENSE, 1000 + s, sp, per, a.duration,
                                        8, dr, lm, cap, "dense")
                                rows.append(r)
                                print(json.dumps(r), flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
