"""Public SubT topology, synthetic movement and deterministic contact abstraction."""
import csv
import gzip
import hashlib
import heapq
import json
import random
import re
import urllib.request
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = '083c6a8acb0c25aa1a35e34517e628cd3b52ae77'
DATA = ROOT / 'data/subt_urban'
OUT = ROOT / 'simulation/results/2026-10-21-rescue-graph-v1'


def fetch():
    DATA.mkdir(parents=True, exist_ok=True)
    manifest = []
    for path in ['LICENSE', 'COPYING'] + [
        f'subt_ign/worlds/urban_circuit/{i:02}/urban_circuit_{i:02}.dot' for i in range(1, 9)
    ]:
        url = f'https://raw.githubusercontent.com/osrf/subt/{SHA}/{path}'
        dest = DATA / Path(path).name
        if not dest.exists():
            dest.write_bytes(urllib.request.urlopen(url, timeout=60).read())
        manifest.append(dict(url=url, file=dest.name, sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
    return manifest


def parse(text):
    nodes = {int(n) for n in re.findall(r'^\s*(\d+)\s+\[label=', text, re.M)}
    graph = {n: {} for n in nodes}
    for a, b, w in re.findall(r'(\d+)\s*--\s*(\d+)\s*\[label=(\d+)\]', text):
        a, b, w = int(a), int(b), int(w)
        assert a in graph and b in graph and w > 0
        graph[a][b] = graph[b][a] = w
    assert 0 in graph
    assert len(shortest(graph, 0)[0]) == len(graph), 'Disconnected graph'
    return graph


def shortest(graph, start, weighted=False):
    dist, paths = {start: 0}, {start: [start]}
    heap = [(0, start)]
    while heap:
        cost, a = heapq.heappop(heap)
        if cost != dist[a]:
            continue
        for b in sorted(graph[a]):
            new = cost + (graph[a][b] if weighted else 1)
            if new < dist.get(b, float('inf')):
                dist[b], paths[b] = new, paths[a] + [b]
                heapq.heappush(heap, (new, b))
    return dist, paths


def prepare(graph, reach):
    distances, paths = {}, {}
    for n in graph:
        distances[n], paths[n] = shortest(graph, n)
    visibility, _ = shortest(graph, 0, True)
    covered = {n for n in graph if visibility[n] <= reach}
    queue, seen, order = deque([0]), {0}, []
    while queue:
        a = queue.popleft()
        for b in sorted(graph[a]):
            if b not in seen:
                seen.add(b); order.append(b); queue.append(b)
    return distances, paths, covered, [set(order[::2]), set(order[1::2])]


def episode(graph, setup, horizon, policy, parameter, seed, trace=False):
    distances, paths, covered, assignments = setup
    targets = set(random.Random(seed).sample(sorted(set(graph) - {0}), 8))
    reports, events = [], []
    moves = returns = scans = 0
    for robot, assigned in enumerate(assignments):
        pos, t, remaining, pending = 0, 0, set(assigned), []

        def contact():
            if pos in covered or policy == 'ideal':
                for r in pending:
                    r['received'] = t
                pending.clear()

        def walk(destination):
            nonlocal pos, t, moves
            for node in paths[pos][destination][1:]:
                t += 20; moves += 1; pos = node
                contact()
                if trace: events.append(dict(robot=robot, time=t, event='arrive', node=pos))

        while remaining:
            contact()
            nxt = min(remaining, key=lambda n: (distances[pos][n], n))
            if t + distances[pos][nxt]*20 + 10 + distances[nxt][0]*20 > horizon:
                break
            triggered = bool(pending) and (
                policy in ('base_age', 'contact_age') and t - min(r['discovered'] for r in pending) >= parameter
                or policy == 'contact_batch' and len(pending) >= parameter)
            if triggered:
                destination = 0 if policy == 'base_age' else min(covered, key=lambda n: (distances[pos][n], n))
                # Home is covered; nearest contact + home cannot exceed the reserved home path.
                # For non-tree graphs enforce the budget explicitly.
                if t + (distances[pos][destination] + distances[destination][0])*20 <= horizon:
                    returns += 1; walk(destination)
                    continue
                break
            walk(nxt)
            t += 10; scans += 1; remaining.remove(nxt)
            if nxt in targets:
                r = dict(robot=robot, node=nxt, discovered=t, received=None)
                reports.append(r); pending.append(r)
            contact()
            if trace: events.append(dict(robot=robot, time=t, event='scan', node=pos))
        walk(0)
        assert t <= horizon and not pending
    assert all(r['received'] >= r['discovered'] for r in reports)
    row = dict(discovered=len(reports), received=sum(r['received'] is not None for r in reports),
               report_auc=sum(horizon-r['received'] for r in reports)/(8*horizon),
               instant_route_auc=sum(horizon-r['discovered'] for r in reports)/(8*horizon),
               delay_sum=sum(r['received']-r['discovered'] for r in reports),
               edges=moves, returns=returns, scanned=scans)
    return row, dict(reports=reports, events=events, targets=sorted(targets))


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = fetch()
    candidates = [('ideal', 0), ('carry', 0)] + [
        (p, x) for p in ('base_age', 'contact_age') for x in (60, 120, 240)
    ] + [('contact_batch', x) for x in (1, 2, 4)]
    rows, traces, graphs = [], [], []
    for i in range(1, 9):
        graph = parse((DATA / f'urban_circuit_{i:02}.dot').read_text())
        for reach in (6, 12, 9999):
            setup = prepare(graph, reach)
            graphs.append(dict(world=i, reach=reach, nodes=len(graph), edges=sum(map(len, graph.values()))//2,
                               covered=len(setup[2])))
            for horizon in (600, 900):
                for policy, parameter in candidates:
                    for seed in range(24):
                        row, trace = episode(graph, setup, horizon, policy, parameter, seed, seed == 0)
                        key = dict(world=i, reach=reach, horizon=horizon, policy=policy, parameter=parameter, seed=seed)
                        rows.append(key | row)
                        if seed == 0: traces.append(key | trace)
    write_csv(OUT/'metrics.csv', rows)
    write_csv(OUT/'graphs.csv', graphs)
    selected = []
    for world in range(1, 9):
        for reach in (6, 12, 9999):
            for horizon in (600, 900):
                subset = [r for r in rows if (r['world'], r['reach'], r['horizon']) == (world, reach, horizon)]
                for family in ('ideal', 'carry', 'base_age', 'contact_age', 'contact_batch', 'best_existing'):
                    eligible = [(p, x) for p, x in candidates if (p != 'ideal' if family == 'best_existing' else p == family)]
                    def score(candidate):
                        dev = [r for r in subset if (r['policy'], r['parameter']) == candidate and r['seed'] < 8]
                        return sum(r['report_auc'] for r in dev)/8, candidate[1]
                    p, x = max(eligible, key=score)
                    test = [r for r in subset if (r['policy'], r['parameter']) == (p, x) and r['seed'] >= 8]
                    selected.append(dict(world=world, reach=reach, horizon=horizon, family=family, policy=p, parameter=x,
                                         **{k: sum(r[k] for r in test)/16 for k in ('report_auc','instant_route_auc','discovered','received','delay_sum','returns')}))
    write_csv(OUT/'selected.csv', selected)
    with gzip.open(OUT/'traces_seed0.json.gz', 'wt', encoding='utf-8') as f:
        json.dump(traces, f)
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__), ROOT/'simulation/RESCUE_GRAPH_PROTOCOL.md']}
    (OUT/'metadata.json').write_text(json.dumps(dict(upstream_commit=SHA, inputs=manifest, hashes=hashes,
        rows=len(rows), seeds=list(range(24)), development_seeds=list(range(8)), test_seeds=list(range(8,24))), indent=2)+'\n')
    print(json.dumps(dict(rows=len(rows), selected=len(selected), graphs=graphs)))


if __name__ == '__main__':
    main()
