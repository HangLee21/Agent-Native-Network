"""Deterministic synthetic 30-node trajectories; coordinates are metres, time seconds."""
import math
import random


def reflect(value, bound):
    value %= 2 * bound
    return value if value <= bound else 2 * bound - value


def positions(mode, speed, seed, t, n=30, extent=1000):
    if mode not in ('formation', 'crossing', 'reorganize') or n != 30:
        raise ValueError('unsupported motion or node count')
    rng = random.Random(seed)
    points = []
    for i in range(n):
        if mode == 'formation':
            # Common translation preserves the relative geometry.
            x = (i % 6 - 2.5) * 45 + rng.uniform(-5, 5)
            y = (i // 6 - 2) * 45 + rng.uniform(-5, 5)
            points.append((x + speed * t, y))
        elif mode == 'crossing':
            side = -1 if i < 15 else 1
            x = 500 + side * 250 + (i % 5 - 2) * 35 + rng.uniform(-4, 4)
            y = 500 + ((i % 15) // 5 - 1) * 45 + rng.uniform(-4, 4)
            points.append((reflect(x - side * speed * t, extent), reflect(y, extent)))
        else:
            x = rng.uniform(300, 700)
            y = rng.uniform(300, 700)
            angle = rng.uniform(0, 2 * math.pi)
            points.append((reflect(x + math.cos(angle) * speed * t, extent),
                           reflect(y + math.sin(angle) * speed * t, extent)))
    return points


def graph(points, radius):
    return {(i, j) for i in range(len(points)) for j in range(i + 1, len(points))
            if math.dist(points[i], points[j]) <= radius}


def scale_initial_separation(current, initial, factor):
    """Spread initial positions while retaining each trajectory's displacement."""
    if len(current) != len(initial) or factor <= 0:
        raise ValueError('invalid initial geometry or scale')
    return [(x+(factor-1)*initial[i][0], y+(factor-1)*initial[i][1])
            for i,(x,y) in enumerate(current)]


def connected_pairs(n, edges):
    adj = [set() for _ in range(n)]
    for a, b in edges:
        adj[a].add(b); adj[b].add(a)
    seen = set(); total = 0
    for node in range(n):
        if node in seen:
            continue
        todo = [node]; seen.add(node); size = 0
        while todo:
            v = todo.pop(); size += 1
            for w in adj[v] - seen:
                seen.add(w); todo.append(w)
        total += size * (size - 1) // 2
    return total
