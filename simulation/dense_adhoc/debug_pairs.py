import random
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
rnd = random.Random(1000 ^ 0x5F5F)
live = [x.id for x in sim.nodes if x.alive]
probes = 0
for _ in range(60):
    a, b = rnd.sample(live, 2)
    if sim.live(a, b, sim.now):
        continue
    need = S.bfs_hops(adj, a, b)
    before = dict(sim.stats)
    ok = sim.discover(a, b)
    d = {k: sim.stats.get(k, 0) - before.get(k, 0) for k in ("rreq", "rrep")}
    probes += 1
    print(f"a={a:2d} b={b:2d} need={need} ok={ok} d={d} now={round(sim.now)}")
    if probes >= 20:
        break
