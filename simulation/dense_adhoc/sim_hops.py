"""Does the 4-hop limit hold for sparse / stretched UAV formations?

Three layouts at the same node count:
  disc   — compact formation, high density (the case the old limit was tuned for)
  sparse — same area scaled up, so mean degree drops to ~3-4
  chain  — a relay line, 0.9 x range spacing, so diameter is N-1 hops

Each layout is swept over the hop limit (max path length), which is what `path[5]`
and `RREQ ttl=4` currently hard-code. Frame size grows by 6 B per hop beyond 5 nodes,
mirroring the source-route header cost.
"""
import argparse
import json
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S            # noqa: E402
import sim_alg as A        # noqa: E402


def place(sim, layout, n, spacing_factor=0.9):
    rng = 120.0
    if layout == "chain":
        step = rng * spacing_factor
        for i, nd in enumerate(sim.nodes):
            nd.x = i * step
            nd.y = 0.0
        sim.tx_range = rng
    elif layout == "sparse":
        # keep the default disc but enlarge it so mean degree falls
        import math
        for i, nd in enumerate(sim.nodes):
            nd.x *= 2.4
            nd.y *= 2.4
    # disc: leave as generated


def run(n, layout, hop_limit, seed, duration_ms=90000, dropout=0.0):
    cfg = dict(S.DENSE)
    cfg["hop_limit"] = hop_limit
    cfg["max_path"] = hop_limit + 1
    sim = A.SimAlg(n, seed, cfg, speed=0.0, period_ms=20000, channels=8, dropout=dropout)
    place(sim, layout, n)
    sim._build_links()          # shadow values are per-pair, positions changed
    sim.run_until(duration_ms)
    pdr = (sim.stats["data_delivered"] / sim.stats["data_admitted"]
           if sim.stats["data_admitted"] else None)
    lat = sorted(sim.latency)
    deg = sum(len([j for j in range(n) if j != i and sim.in_range(i, j)])
              for i in range(n)) / n
    # graph diameter of the reachable component from node 0
    adj = {i: [j for j in range(n) if j != i and sim.in_range(i, j)] for i in range(n)}
    seen, frontier, diam = {0}, [0], 0
    while frontier:
        nxt = [v for u in frontier for v in adj[u] if v not in seen]
        if not nxt:
            break
        for v in nxt:
            seen.add(v)
        diam += 1
        frontier = nxt
    return dict(n=n, layout=layout, hop_limit=hop_limit, seed=seed,
                mean_degree=round(deg, 1), ecc_from_0=diam,
                admitted=sim.stats["data_admitted"], delivered=sim.stats["data_delivered"],
                pdr=None if pdr is None else round(pdr, 3),
                lat_p50=None if not lat else round(lat[len(lat) // 2], 1),
                lat_p95=None if not lat else round(lat[int(0.95 * (len(lat) - 1))], 1),
                rreq_s=round(sim.stats["rreq"] / (duration_ms / 1000.0), 2),
                rreq_denied=sim.stats.get("token_denied", 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, default=30)
    ap.add_argument("--layouts", nargs="+", default=["disc", "sparse", "chain"])
    ap.add_argument("--hops", type=int, nargs="+", default=[4, 6, 8, 12])
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    rows = []
    for lay in a.layouts:
        for h in a.hops:
            for s in range(a.seeds):
                r = run(a.nodes, lay, h, 1000 + s)
                rows.append(r)
                print(json.dumps(r), flush=True)
    json.dump(rows, open(a.out, "w"), indent=2)
    print("wrote", a.out)


if __name__ == "__main__":
    main()
