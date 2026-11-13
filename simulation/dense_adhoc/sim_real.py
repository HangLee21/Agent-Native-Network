"""Realistic-scenario evaluation: 8-channel LoRa gateway + lossy/asymmetric Wi-Fi.

Adds to sim_dynamic:
  * LoRa gateway with N_CH receivers (one per channel); senders are assigned to channels,
    each channel has its own half-duplex collision model and real SF7/BW125 airtime;
  * Wi-Fi link model: per-direction packet reception ratio from a logistic distance curve
    plus per-pair lognormal shadowing plus a per-node TX offset, so A->B != B->A;
  * MAC retries: unicast frames are retried up to RETRIES times, each attempt costing airtime;
  * node dropout: a fraction of nodes goes silent mid-run (battery / leaves the area).

Still NOT modelled on the Wi-Fi side: CSMA backoff and collisions. Wi-Fi delivery numbers
therefore stay optimistic; what is realistic here is `mean_hop_prr`, `mac_retries`,
asymmetry, dropout and the LoRa per-channel contention.
"""
import argparse
import json
import math
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S            # noqa: E402
import sim_dynamic as D    # noqa: E402

N_CH = 8
RETRIES = 3
D50 = 120.0            # distance where per-hop PRR = 0.5
W = 12.0               # logistic width, metres
SHADOW_DB = 6.0
PATHLOSS_N = 2.5
TX_OFFSET_DB = 2.0


class LoRaMultiChannel:
    """Gateway with one receiver per channel; a frame only contends within its channel."""

    def __init__(self, channels=N_CH, period_ms=10000):
        self.channels = channels
        self.period = period_ms
        self.rx = [dict(current=None) for _ in range(channels)]
        self.frames = [0] * channels
        self.ok = [0] * channels
        self.collided = [0] * channels
        self.busy_ms = [0.0] * channels

    def offer(self, src, ch, t, payload_bytes):
        toa = D.lora_toa_s(payload_bytes) * 1000.0
        self.frames[ch] += 1
        self.busy_ms[ch] += toa
        st = self.rx[ch]
        frame = dict(src=src, start=t, end=t + toa, collided=False, ch=ch)
        if st["current"] and t < st["current"]["end"]:
            frame["collided"] = True
            st["current"]["collided"] = True
            self.collided[ch] += 2
        st["current"] = frame
        return frame

    def finish(self, frame):
        if frame["collided"]:
            return False
        self.ok[frame["ch"]] += 1
        return True

    def totals(self):
        return dict(frames=sum(self.frames), ok=sum(self.ok),
                    collided=sum(self.collided), busy_ms=sum(self.busy_ms))


class SimReal(D.SimDyn):
    def __init__(self, n, seed, cfg, speed=0.0, period_ms=10000, traffic=True,
                 channels=N_CH, dropout=0.0, shadow_db=SHADOW_DB, tx_offset_db=TX_OFFSET_DB):
        self.shadow_db = shadow_db
        self.tx_offset_db = tx_offset_db
        super().__init__(n, seed, cfg, speed=speed, period_ms=period_ms,
                         traffic=traffic, lora=False)
        self.lora = LoRaMultiChannel(channels, period_ms)
        self.mac_retries = 0
        self.prr_sum = 0.0
        self.prr_n = 0
        self._build_links()
        for nd in self.nodes:
            if nd.id == 0:
                continue
            self.push(self.rnd.uniform(0, period_ms * 0.5), "lora", nd.id)
        if dropout > 0:
            for nd in self.nodes:
                if self.rnd.random() < dropout:
                    self.push(self.rnd.uniform(15000, 45000), "dropout", nd.id)

    # ---- link model ------------------------------------------------------
    def _build_links(self):
        n = len(self.nodes)
        self.tx_off = [self.rnd.uniform(-self.tx_offset_db, self.tx_offset_db)
                       for _ in range(n)]
        self.shadow = {(i, j): self.rnd.gauss(0.0, self.shadow_db)
                       for i in range(n) for j in range(n) if i != j}

    def prr(self, i, j):
        d = max(1.0, S.dist(self.nodes[i], self.nodes[j]))
        db = self.shadow[(i, j)] + self.tx_off[i]
        d_eff = d * (10 ** (db / (10.0 * PATHLOSS_N)))
        return 1.0 / (1.0 + math.exp((d_eff - D50) / W))

    # ---- transmit with link loss and MAC retries -------------------------
    def transmit(self, src, kind, size, dst=None, extra=None):
        nd = self.nodes[src]
        if not nd.alive:
            return None
        t0 = max(self.now, self.ch.busy_until)
        air = self.ch.airtime(size)
        targets = [dst] if dst is not None else self.neighbors_of(src)
        delivered, pending = [], [j for j in targets if j != src]
        attempts = 0
        limit = RETRIES if dst is not None else int(self.cfg.get("bcast_retries", 1))
        while pending and attempts < limit:
            attempts += 1
            self.ch.busy_until = t0 + air
            self.ch.busy_ms += air
            self.ch.frames += 1
            nxt = []
            for j in pending:
                if not self.nodes[j].alive:
                    continue
                p = self.prr(src, j)
                self.prr_sum += p
                self.prr_n += 1
                if self.rnd.random() < p and self.enqueue_rx(j):
                    delivered.append(j)
                else:
                    nxt.append(j)
            pending = nxt
            t0 = self.ch.busy_until
        if dst is not None:
            self.mac_retries += attempts - 1
        nd.sent += 1
        self.stats[kind] = self.stats.get(kind, 0) + 1
        if kind in ("hello", "ack") and delivered:
            self.push(t0, "land", dict(kind=kind, src=src, targets=delivered))
        return dict(t0=t0, t_end=t0, targets=delivered, extra=extra or {})

    # ---- LoRa on N channels ---------------------------------------------
    def lora_send(self, nid, t):
        nd = self.nodes[nid]
        if not nd.alive:
            self.push(t + self.lora.period, "lora", nid)
            return
        ch = nid % self.lora.channels
        rows = min(len(nd.nd), 8)
        self.stats["lora_tx"] += 1
        frame = self.lora.offer(nid, ch, t, 48 + 20 * rows)
        self.push(frame["end"], "lora_done", frame)
        self.push(t + self.lora.period * self.rnd.uniform(0.95, 1.05), "lora", nid)

    def extra_event(self, kind, payload, t):
        if kind == "lora_done":
            self.lora.finish(payload)
            return True
        if kind == "dropout":
            nd = self.nodes[payload]
            if nd.alive:
                nd.alive = False
                self.stats["dropouts"] = self.stats.get("dropouts", 0) + 1
            return True
        return False


def run(n, cfg, seed, speed=0.0, period_ms=10000, duration_ms=60000, traffic=True,
        channels=N_CH, dropout=0.0, shadow_db=SHADOW_DB, labels="base"):
    sim = SimReal(n, seed, cfg, speed=speed, period_ms=period_ms, traffic=traffic,
                  channels=channels, dropout=dropout, shadow_db=shadow_db)
    sim.run_until(duration_ms)
    pdr = (sim.stats["data_delivered"] / sim.stats["data_admitted"]
           if sim.stats["data_admitted"] else None)
    lat = sorted(sim.latency)
    lor = sim.lora.totals()
    return dict(n=n, policy=labels, seed=seed, speed_mps=speed, channels=channels,
                lora_period_ms=period_ms, dropout=dropout, shadow_db=shadow_db,
                alive=sum(1 for x in sim.nodes if x.alive),
                nodes_locked=sim.stats["nodes_locked"],
                dropouts=sim.stats.get("dropouts", 0),
                link_changes=sim.link_changes,
                data_admitted=sim.stats["data_admitted"],
                data_delivered=sim.stats["data_delivered"],
                pdr=None if pdr is None else round(pdr, 3),
                latency_mean_ms=None if not lat else round(sum(lat) / len(lat), 1),
                latency_p95_ms=None if not lat else round(lat[int(0.95 * (len(lat) - 1))], 1),
                mean_hop_prr=round(sim.prr_sum / sim.prr_n, 3) if sim.prr_n else None,
                mac_retries=sim.mac_retries,
                rreq_s=round(sim.stats["rreq"] / (duration_ms / 1000.0), 2),
                lora_frames=lor["frames"], lora_ok=lor["ok"],
                lora_delivery=round(lor["ok"] / lor["frames"], 3) if lor["frames"] else None,
                lora_busy_per_ch=round(lor["busy_ms"] / (duration_ms * channels), 3),
                per_channel_frames=sim.lora.frames,
                toa_ms=round(D.lora_toa_s(208) * 1000, 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[30])
    ap.add_argument("--policy", nargs="+", default=["base", "dense"])
    ap.add_argument("--speed", type=float, nargs="+", default=[0.0, 5.0])
    ap.add_argument("--channels", type=int, nargs="+", default=[1, 8])
    ap.add_argument("--dropout", type=float, nargs="+", default=[0.0])
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--duration", type=int, default=60000)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    pol = {"base": S.BASE, "dense": S.DENSE, "measure": S.BASE_MEASURE}
    rows = []
    for n in a.nodes:
        for p in a.policy:
            for sp in a.speed:
                for ch in a.channels:
                    for dr in a.dropout:
                        for s in range(a.seeds):
                            r = run(n, pol[p], 1000 + s, sp, 10000, a.duration,
                                    True, ch, dr, SHADOW_DB, p)
                            rows.append(r)
                            print(json.dumps(r), flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()

