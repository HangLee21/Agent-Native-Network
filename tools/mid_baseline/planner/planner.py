"""Independent candidate-source SOCP formulation. No ROS or physical defaults."""
import argparse
import json
import math
from statistics import NormalDist


def channel_from_positions(positions, params):
    """Candidate PathLossModel equations; every parameter must be explicit."""
    n0, exponent, l0, a, b = (float(params[x]) for x in ('N0', 'n', 'L0', 'a', 'b'))
    if any(not math.isfinite(x) for x in (n0, exponent, l0, a, b)) or exponent <= 0 or a < 0 or b <= 0:
        raise ValueError('invalid explicit channel parameters')
    if any(len(p) != 2 or any(not math.isfinite(x) for x in p) for p in positions):
        raise ValueError('finite Nx2 positions required')
    mean, variance = [], []
    for i, pi in enumerate(positions):
        mr, vr = [], []
        for j, pj in enumerate(positions):
            if i == j:
                mr.append(0.0); vr.append(0.0)
                continue
            d = math.dist(pi, pj)
            if d <= 0:
                raise ValueError('distinct positions required')
            snr = 10**((l0-10*exponent*math.log10(d)-n0)/10)
            mr.append(math.erf(math.sqrt(snr)))
            vr.append((a*d/(b+d))**2)
        mean.append(mr); variance.append(vr)
    return mean, variance


def validate(problem):
    nodes = problem['nodes']
    flows = problem['flows']
    n = len(nodes)
    if not 2 <= n <= 5 or not 1 <= len(flows) <= 2 or len(set(nodes)) != n:
        raise ValueError('require 2..5 unique nodes and 1..2 flows')
    if not problem.get('channel_provenance'):
        raise ValueError('channel_provenance required; inputs are model rates, not measured PDR')
    for name in ('mean', 'variance'):
        a = problem[name]
        if len(a) != n or any(len(row) != n for row in a):
            raise ValueError(name + ' shape')
        if any(not math.isfinite(x) or x < 0 for row in a for x in row):
            raise ValueError(name + ' must be finite nonnegative')
    seen = set()
    for f in flows:
        key = (f['src'], f['dst'])
        if key in seen or key[0] == key[1] or any(x not in nodes for x in key):
            raise ValueError('invalid/duplicate flow')
        seen.add(key)
        if not 0.5 < f['qos'] < 1 or not math.isfinite(f['rate']) or f['rate'] < 0:
            raise ValueError('qos must be (0.5,1), rate nonnegative')


def network_update(nodes, flows, routes):
    """Routes ordered [flow][executor][gateway]; author uses NxNxK Fortran order."""
    entries = []
    for k, flow in enumerate(flows):
        for i, node in enumerate(nodes):
            if node == flow['dst']:
                continue
            gateways = [{'node': nodes[j], 'weight': float(w)} for j, w in enumerate(routes[k][i])
                        if w > 0.01 and j != i]
            if gateways:
                entries.append(dict(node=node, src=flow['src'], dst=flow['dst'], gateways=gateways))
    return dict(schema='mid.network_update.v1', nodes=nodes,
                flows=[dict(src=f['src'], dst=f['dst']) for f in flows], routes=entries)


def solve(problem):
    problem = dict(problem)
    if 'positions' in problem:
        if 'mean' in problem or 'variance' in problem:
            raise ValueError('choose explicit matrices or positions, not both')
        if len(problem['positions']) != len(problem['nodes']):
            raise ValueError('position count')
        problem['mean'], problem['variance'] = channel_from_positions(problem['positions'], problem['channel_parameters'])
    validate(problem)
    import numpy as np
    import cvxpy as cp
    n = len(problem['nodes'])
    flows = problem['flows']
    mean = np.array(problem['mean'])
    std = np.sqrt(problem['variance'])
    r = [cp.Variable((n, n), nonneg=True) for _ in flows]
    slack = cp.Variable(nonneg=True)
    constraints = []
    for k, f in enumerate(flows):
        constraints += [r[k] <= 1, cp.diag(r[k]) == 0]
        dest = problem['nodes'].index(f['dst'])
        src = problem['nodes'].index(f['src'])
        for i in range(n):
            if i == dest:
                continue
            # Same independent link variance terms and common slack as candidate source.
            terms = [std[i, j]*r[k][i, j] for j in range(n) if j != i]
            terms += [std[j, i]*r[k][j, i] for j in range(n) if j != i]
            margin = cp.sum(cp.multiply(mean[i, :], r[k][i, :])) - cp.sum(cp.multiply(mean[:, i], r[k][:, i]))
            demand = f['rate'] if i == src else 0
            constraints += [margin-demand-slack >= NormalDist().inv_cdf(f['qos'])*cp.norm(cp.hstack(terms))]
    total = sum(r)
    constraints += [cp.sum(total, axis=0) <= 1, cp.sum(total, axis=1) <= 1]
    prob = cp.Problem(cp.Maximize(slack), constraints)
    prob.solve(solver='CLARABEL')
    if prob.status != 'optimal':
        return dict(status=prob.status, update=None)
    routes = [np.maximum(x.value, 0).tolist() for x in r]
    return dict(status=prob.status, slack=float(slack.value), routes=routes,
                update=network_update(problem['nodes'], flows, routes),
                provenance=problem['channel_provenance'], solver='CLARABEL',
                scope='candidate source adaptation; no SDP, motion or RF measurement')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('problem')
    p.add_argument('--output', required=True)
    args = p.parse_args()
    from pathlib import Path
    out = Path(args.output)
    # Exclusive output creation prevents accidental history replacement.
    result = solve(json.loads(Path(args.problem).read_text(encoding='utf-8')))
    with out.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    return 0 if result['status'] == 'optimal' else 2


if __name__ == '__main__':
    raise SystemExit(main())
