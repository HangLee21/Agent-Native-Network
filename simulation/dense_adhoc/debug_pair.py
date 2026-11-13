import json
import sys

sys.path.insert(0, r"D:\Multi-Agent Network\simulation\dense_adhoc")
import sim as S

n = 30
sim = S.Sim(n, 1000, S.DENSE, rate_bps=1_000_000)
t = 0.0
while t < 25000:
    sim.run_until(t + 250)
    if sim.now > 3000 and sim.converge(25000):
        break
    t += 250
sim.run_until(sim.now + 10000)

adj = {i: [j for j in range(n) if j != i and sim.in_range(i, j)] for i in range(n)}
print("converged at", round(sim.now), "mean degree",
      round(sum(len(v) for v in adj.values()) / n, 1))

fails = 0
checked = 0
for a in range(n):
    for b in range(n):
        if a == b or sim.live(a, b, sim.now):
            continue
        need = S.bfs_hops(adj, a, b)
        if need is None or need > 4:
            continue
        checked += 1
        before = dict(sim.stats)
        ok = sim.discover(a, b)
        d = {k: sim.stats.get(k, 0) - before.get(k, 0) for k in ("rreq", "rrep")}
        if not ok:
            fails += 1
            if fails <= 5:
                print(f"FAIL a={a} b={b} need={need} d={d} "
                      f"routes_a={len(sim.nodes[a].routes)} seen_a={len(sim.nodes[a].rreq_seen)} "
                      f"seen_b={len(sim.nodes[b].rreq_seen)} alive_b={sim.nodes[b].alive}")
        if checked >= 12:
            break
    if checked >= 12:
        break
print("checked", checked, "fails", fails)
