"""Travel-budget pilot with the unchanged Cuprite observation-v1 estimator."""
from dataclasses import dataclass, asdict
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import importlib.metadata

import numpy as np
import simpy
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from simulation.validate_observation import prepare, patch_data, PATCHES, select_diverse, reconstruct, rmse


@dataclass(frozen=True)
class RouteConfig:
    factor: float = 1.5
    speed: float = 1.0
    sensing: float = 4.0
    decision: float = 0.25

    def __post_init__(self):
        if self.factor < 1 or min(self.speed, self.sensing, self.decision) <= 0:
            raise ValueError('Invalid route budget/costs')


def geometry(xy, nodes):
    if nodes == 1:
        return [np.arange(len(xy))], [np.array([0., 0.])], [np.array([79., 79.])]
    if nodes == 2:
        return [np.flatnonzero(xy[:, 0] < 40), np.flatnonzero(xy[:, 0] >= 40)], [np.array([0., 0.]), np.array([79., 0.])], [np.array([39., 79.]), np.array([40., 79.])]
    raise ValueError('Only one or two nodes supported')


def choose(remote, xy, candidates, position, end, remaining, visited, library, cfg, nearest=False):
    ids = candidates[~np.isin(candidates, list(visited))]
    if not len(ids):
        return None
    travel = np.linalg.norm(xy[ids] - position, axis=1) / cfg.speed
    action = travel + cfg.sensing + cfg.decision
    return_time = np.linalg.norm(xy[ids] - end, axis=1) / cfg.speed
    feasible = action + return_time <= remaining + 1e-9
    ids, action, travel = ids[feasible], action[feasible], travel[feasible]
    if not len(ids):
        return None
    if nearest:
        return int(ids[np.argmin(travel)])
    novelty = np.min(np.mean((remote[ids, None] - library[None])**2, axis=2), axis=1)
    return int(ids[np.argmax((novelty + 1e-12) / action)])


def plan_static(remote, xy, regions, starts, ends, budgets, initial_remote, cfg, nearest=False):
    positions = [p.copy() for p in starts]
    elapsed = np.zeros(len(starts))
    visited = [set() for _ in starts]
    plans = [[] for _ in starts]
    library = initial_remote.copy()
    active = set(range(len(starts)))
    while active:
        node = min(active, key=lambda i: (elapsed[i], i))
        target = choose(remote, xy, regions[node], positions[node], ends[node],
                        budgets[node] - elapsed[node], visited[node], library, cfg, nearest)
        if target is None:
            active.remove(node)
            continue
        elapsed[node] += np.linalg.norm(xy[target] - positions[node]) / cfg.speed + cfg.sensing + cfg.decision
        positions[node] = xy[target].copy()
        visited[node].add(target)
        plans[node].append(target)
        library = np.vstack([library, remote[target]])
    return plans


def episode(remote, xy, initial_library, response, measure, nodes, mode, cfg, sharing=True):
    """measure is the only environment callback; policies cannot read fine truth."""
    if mode not in ('nearest', 'static', 'local', 'ideal'):
        raise ValueError(mode)
    regions, starts, ends = geometry(xy, nodes)
    budgets = [float(np.linalg.norm(e-s) / cfg.speed * cfg.factor) for s,e in zip(starts,ends)]
    plans = plan_static(remote, xy, regions, starts, ends, budgets, initial_library @ response,
                        cfg, mode == 'nearest') if mode in ('static','nearest') else [[] for _ in starts]
    env = simpy.Environment()
    events, observations = [], []
    pending = [[] for _ in starts]
    node_results = []

    def log(event, node, **kwargs):
        events.append(dict(time=float(env.now), event=event, node=node, **kwargs))

    def robot(node):
        position = starts[node].copy()
        library = (initial_library @ response).copy()
        visited, known = set(), []
        distance = 0.
        path, decisions = [position.tolist()], []
        own = []
        while True:
            for oid, spectrum in pending[node]:
                library = np.vstack([library, spectrum @ response])
                known.append(oid)
                log('consume', node, oid=oid)
            pending[node].clear()
            if mode in ('nearest','static'):
                target = plans[node].pop(0) if plans[node] else None
            else:
                target = choose(remote, xy, regions[node], position, ends[node], budgets[node]-env.now,
                                visited, library, cfg)
            if target is None:
                break
            leg = float(np.linalg.norm(xy[target]-position))
            cost = leg / cfg.speed + cfg.decision + cfg.sensing
            assert env.now + cost + np.linalg.norm(xy[target]-ends[node]) / cfg.speed <= budgets[node]+1e-8
            log('decision', node, site=target, known_ids=list(known))
            decisions.append([float(env.now),target])
            yield env.timeout(cfg.decision)
            yield env.timeout(leg / cfg.speed)
            position = xy[target].copy()
            path.append(position.tolist())
            distance += leg
            log('arrive',node,site=target)
            yield env.timeout(cfg.sensing)
            value = np.asarray(measure(target)).copy()
            oid = node*1000000 + len(own)
            own.append(target)
            observations.append((oid,target,value))
            log('sample',node,site=target,oid=oid)
            visited.add(target)
            library = np.vstack([library,value @ response])
            known.append(oid)
            if mode == 'ideal' and sharing:
                for peer in range(nodes):
                    if peer != node:
                        pending[peer].append((oid,value.copy()))
                        log('deliver',peer,oid=oid)
        leg = float(np.linalg.norm(ends[node]-position))
        yield env.timeout(leg/cfg.speed)
        distance += leg
        path.append(ends[node].tolist())
        log('finish',node)
        assert env.now <= budgets[node]+1e-8
        node_results.append(dict(node=node,finish_time=float(env.now),budget=budgets[node],
                                 distance=distance,samples=own,path=path,decisions=decisions))

    for node in range(nodes):
        env.process(robot(node))
    env.run()
    node_results.sort(key=lambda row:row['node'])
    # Sort terminal union consistently to avoid NNLS tie-breaking by arrival order.
    observations.sort(key=lambda obs:obs[1])
    terminal = np.vstack([initial_library] + [obs[2][None] for obs in observations])
    return terminal, dict(nodes=node_results, events=events,
                         sites=[obs[1] for obs in observations],samples=len(observations))


def run(output, seeds=12):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output folder must be empty')
    output.mkdir(parents=True,exist_ok=True)
    cube,response,qc = prepare(Path('data/cuprite/Cuprite_data_R188.mat'))
    dev,_,_ = patch_data(cube,PATCHES['development'])
    dev_remote = dev @ response
    initial_ids = select_diverse(dev_remote,dev_remote.mean(axis=0,keepdims=True),4)
    initial = dev[initial_ids]
    rows, details = [], []
    for patch in ('A','B','C'):
        truth,evaluation,xy = patch_data(cube,PATCHES[patch])
        remote,test_remote = truth @ response,evaluation @ response
        baseline = rmse(reconstruct(test_remote,initial,response),evaluation)
        for factor in (1.5,2.5):
            cfg=RouteConfig(factor=factor)
            for noise_std in (0.,.002):
                for seed in range(seeds):
                    # Same per-site measurements for all modes and node counts.
                    measured=np.maximum(truth+np.random.default_rng(seed).normal(0,noise_std,truth.shape),0)
                    for nodes in (1,2):
                        modes=('nearest','static','local') if nodes==1 else ('nearest','static','local','ideal')
                        for mode in modes:
                            library,detail=episode(remote,xy,initial,response,lambda site:measured[site],nodes,mode,cfg)
                            error=rmse(reconstruct(test_remote,library,response),evaluation)
                            row=dict(patch=patch,factor=factor,noise_std=noise_std,seed=seed,nodes=nodes,mode=mode,
                                     rmse=error,baseline_rmse=baseline,reduction_pct=100*(baseline-error)/baseline,
                                     samples=detail['samples'],distance=sum(r['distance'] for r in detail['nodes']))
                            rows.append(row)
                            detail['node_runs'] = detail.pop('nodes')
                            detail.update(row)
                            if seed!=0:
                                detail.pop('events')
                            details.append(detail)
        print('Completed patch',patch,flush=True)
    def save_csv(name, records):
        with (output/name).open('w',newline='',encoding='utf8') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(records[0]))
            writer.writeheader();writer.writerows(records)
    save_csv('metrics.csv',rows)
    (output/'episodes.json.gz').write_bytes(gzip.compress(json.dumps(details).encode(),mtime=0))
    summary,paired=[],[]
    for patch in ('A','B','C'):
        for factor in (1.5,2.5):
            for noise in (0.,.002):
                for nodes in (1,2):
                    group=[r for r in rows if (r['patch'],r['factor'],r['noise_std'],r['nodes'])==(patch,factor,noise,nodes)]
                    for mode in sorted({r['mode'] for r in group}):
                        subset=[r for r in group if r['mode']==mode]
                        summary.append(dict(patch=patch,factor=factor,noise_std=noise,nodes=nodes,mode=mode,
                                            mean_rmse=float(np.mean([r['rmse'] for r in subset])),
                                            reduction_pct=float(np.mean([r['reduction_pct'] for r in subset])),
                                            mean_samples=float(np.mean([r['samples'] for r in subset]))))
                    comparisons=[('static','nearest'),('local','static')]
                    if nodes==2:comparisons += [('ideal','local'),('ideal','static')]
                    for a,b in comparisons:
                        aa={r['seed']:r for r in group if r['mode']==a}
                        bb={r['seed']:r for r in group if r['mode']==b}
                        changes=np.array([100*(bb[s]['rmse']-aa[s]['rmse'])/bb[s]['rmse'] for s in sorted(aa)])
                        paired.append(dict(patch=patch,factor=factor,noise_std=noise,nodes=nodes,
                                           comparison=f'{a} vs {b}',mean_improvement_pct=float(changes.mean()),
                                           min_improvement_pct=float(changes.min()),max_improvement_pct=float(changes.max()),
                                           wins=int(np.sum(changes>1e-8))))
    save_csv('summary.csv',summary);save_csv('paired.csv',paired)
    metadata=dict(qc=qc,initial_ids=initial_ids.tolist(),seeds=list(range(seeds)),
                  configs=[asdict(RouteConfig(factor=f)) for f in (1.5,2.5)],
                  noise_std=[0,.002],source_sha256={str(p).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in (Path(__file__).relative_to(Path.cwd()),Path('simulation/validate_observation.py'),Path('simulation/ROUTE_PROTOCOL.md'))},
                  packages={p:importlib.metadata.version(p) for p in ('numpy','scipy','simpy','matplotlib')},
                  units='Uncalibrated image-grid distances and simulation time; not meters or seconds',
                  interpretation='No network impairment. Ideal is a condition, not an optimality bound.')
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
    fig,axes=plt.subplots(1,3,figsize=(12,4),layout='constrained')
    for ax,patch in zip(axes,('A','B','C')):
        for factor in (1.5,2.5):
            subset=[r for r in summary if r['patch']==patch and r['factor']==factor and r['noise_std']==.002 and r['nodes']==2]
            mapping={r['mode']:r for r in subset};modes=['nearest','static','local','ideal']
            ax.plot(modes,[mapping[m]['mean_rmse'] for m in modes],marker='o',label=f'Budget factor {factor}')
        ax.set_title(f'Patch {patch}');ax.set_ylabel('Held-out unit-spectrum RMSE');ax.grid(alpha=.2);ax.legend()
    fig.suptitle('Cuprite proxy | TWO nodes | travel + measurement budget | lower is better')
    fig.savefig(output/'routes_rmse.png',dpi=160);plt.close(fig)
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,default=12)
    args=parser.parse_args()
    if args.seeds<1:parser.error('seeds must be positive')
    run(args.output,args.seeds)
