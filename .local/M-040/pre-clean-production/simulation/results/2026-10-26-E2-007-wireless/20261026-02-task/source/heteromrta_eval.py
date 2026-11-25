"""Bounded paired evaluation of pinned HeteroMRTA inference and author Greedy.

No training, network emulation or edits to upstream files. Run --fetch first when
assets are missing; evaluation requires a new, empty output directory.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
from pathlib import Path
import pickle
import platform
import random
import subprocess
import sys
import time
import traceback
import types
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COMMIT = "db51e29535e34bcaa8cb75f70be3fd28b0027988"
BASE = f"https://raw.githubusercontent.com/marmotlab/HeteroMRTA/{COMMIT}/"
ASSETS = ROOT / "data/heteromrta/upstream"
FILES = ["README.md", "LICENSE", "parameters.py", "worker.py", "env/task_env.py",
         "env/__init__.py", "attention.py", "baseline/Greedy.py", "test.py",
         "model/save/checkpoint.pth"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(v) for v in value]
    if hasattr(value, "tolist"):
        return plain(value.tolist())
    if isinstance(value, float) and not __import__('math').isfinite(value):
        return str(value)
    return value


def write_json(path, obj):
    Path(path).write_text(json.dumps(plain(obj), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def asset_manifest(fetch=False):
    tree_path = ASSETS.parent / "tree.json"
    if fetch and not tree_path.exists():
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://api.github.com/repos/marmotlab/HeteroMRTA/git/trees/{COMMIT}?recursive=1"
        tree_path.write_bytes(urllib.request.urlopen(url, timeout=60).read())
    tree = json.loads(tree_path.read_text(encoding="utf-8"))
    blobs = {x['path']: x for x in tree['tree'] if x['type'] == 'blob'}
    previous = json.loads((ROOT / 'research/agent_native_network/task_baseline_sources.json').read_text())
    known = {x['path']: x['sha256'] for x in previous[0]['files']}
    records = []
    for rel in FILES:
        path = ASSETS / rel
        if fetch and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(urllib.request.urlopen(BASE + rel, timeout=120).read())
        data = path.read_bytes()
        git_hash = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        assert git_hash == blobs[rel]['sha'], f'Git blob mismatch: {rel}'
        sha = digest(path)
        if rel in known:
            assert sha == known[rel], f'Historical SHA256 mismatch: {rel}'
        records.append(dict(path=rel, url=BASE + rel, bytes=len(data), sha256=sha, git_blob=git_hash))
    return records


class CheckpointUnpickler(pickle.Unpickler):
    """Allow only the six globals in the pinned checkpoint (no arbitrary globals)."""
    ALLOWED = {('_codecs', 'encode'), ('collections', 'OrderedDict'),
               ('numpy', 'dtype'), ('numpy.core.multiarray', 'scalar'),
               ('torch', 'FloatStorage'), ('torch._utils', '_rebuild_tensor_v2')}

    def find_class(self, module, name):
        if (module, name) not in self.ALLOWED:
            raise pickle.UnpicklingError(f'Forbidden checkpoint global: {module}.{name}')
        return super().find_class(module, name)


def load_checkpoint(torch):
    # PyTorch 2.3 weights_only rejects the author's NumPy scalar metadata.
    # All globals are restricted; tensor-only state dict is used for inference.
    restricted = types.ModuleType('restricted_checkpoint_pickle')
    restricted.Unpickler = CheckpointUnpickler
    return torch.load(ASSETS / 'model/save/checkpoint.pth', map_location='cpu',
                      pickle_module=restricted, weights_only=False)['best_model']


def child(args):
    os.environ['MPLBACKEND'] = 'Agg'
    sys.path.insert(0, str(ASSETS))
    import numpy as np
    import torch
    from env.task_env import TaskEnv
    from worker import Worker
    from attention import AttentionNet
    from parameters import EnvParams, TrainParams

    torch.set_num_threads(1)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    env = TaskEnv(per_species_range=(3, 3), species_range=(3, 3),
                  tasks_range=(args.tasks, args.tasks), traits_dim=5, decision_dim=30, seed=args.seed)
    env.init_state()
    initial = plain(dict(tasks=env.task_dic, agents=env.agent_dic, depots=env.depot_dic,
                         species=env.species_dict))
    initial_bytes = json.dumps(initial, sort_keys=True).encode()
    initial_hash = hashlib.sha256(initial_bytes).hexdigest()
    out = Path(args.output)
    write_json(out / 'initial.json', initial)
    observations = {}
    events = []
    original_observe = env.agent_observe
    original_step = env.agent_step

    def observe(agent_id, max_waiting=False):
        result = original_observe(agent_id, max_waiting)
        observations[agent_id] = (result[2].copy(), bool(max_waiting))
        return result

    def step(agent_id, action, decision_step):
        if len(events) >= 10000:
            raise RuntimeError('Evaluation action budget exhausted (10000); trajectory retained')
        mask, max_waiting = observations[agent_id]
        event = dict(time=float(env.current_time), agent=int(agent_id), action=int(action),
                     masked=bool(mask[0, action]), max_waiting=max_waiting,
                     mask=mask.astype(int).tolist())
        assert not event['masked'], 'selected a masked action'
        events.append(event)
        return original_step(agent_id, action, decision_step)

    env.agent_observe = observe
    env.agent_step = step
    start = time.perf_counter()
    result = dict(seed=args.seed, method=args.method, initial_sha256=initial_hash,
                  agents=env.agents_num, tasks=env.tasks_num, status='error')
    execution_start = None
    try:
        if args.method == 'policy':
            net = AttentionNet(TrainParams.AGENT_INPUT_DIM, TrainParams.TASK_INPUT_DIM,
                               TrainParams.EMBEDDING_DIM).to('cpu')
            net.load_state_dict(load_checkpoint(torch), strict=True)
            net.eval()
            worker = Worker(0, net, net, 0, device='cpu', seed=args.seed)
            worker.env = env
            # Match test.py: training=False, sampling=False, max_task=False.
            execution_start = time.perf_counter()
            _, _, upstream_metrics = worker.run_episode(False, False, False)
        else:
            if args.method == 'corrected_nearest':
                # Diagnostic only: one missing assignment in the author's rule.
                source = (ASSETS / 'env/task_env.py').read_text()
                old = 'if dist_ < dist:\n                            action = task_id'
                new = 'if dist_ < dist:\n                            dist = dist_\n                            action = task_id'
                assert source.count(old) == 1
                module = types.ModuleType('corrected_nearest_env')
                exec(compile(source.replace(old, new), '<corrected-nearest>', 'exec'), module.__dict__)
                env.execute_greedy_action = types.MethodType(module.TaskEnv.execute_greedy_action, env)
            execution_start = time.perf_counter()
            env.execute_greedy_action(str(out), 'author_greedy', False)
            upstream_metrics = None
        _, finished_tasks = env.get_episode_reward(200)
        completed = int(np.sum(finished_tasks))
        returned = int(sum(bool(x['returned']) for x in env.agent_dic.values()))
        success = completed == env.tasks_num and returned == env.agents_num and bool(env.finished)
        within_horizon = bool(np.isfinite(env.current_time) and env.current_time <= 200)
        result.update(status='success' if success and within_horizon else 'simulation_timeout_or_incomplete',
                      within_horizon=within_horizon,
                      completed=completed, completion_fraction=completed/env.tasks_num,
                      returned=returned, env_finished=bool(env.finished),
                      simulation_end_time=float(env.current_time),
                      makespan_return=float(env.current_time) if success else None,
                      last_task_finish=max(float(t['time_finish']) for t in env.task_dic.values()
                                           if t['finished']) if completed else None,
                      travel_distance=float(sum(a['travel_dist'] for a in env.agent_dic.values())),
                      mean_waiting=float(np.mean(env.get_matrix(env.agent_dic, 'sum_waiting_time'))),
                      upstream_metrics=upstream_metrics)
    except Exception as exc:
        result['error'] = traceback.format_exc()
        if 'action budget exhausted' in str(exc):
            result['status'] = 'action_budget_exhausted'
        result.update(completed=int(sum(bool(t['finished']) for t in env.task_dic.values())),
                      completion_fraction=sum(bool(t['finished']) for t in env.task_dic.values())/env.tasks_num,
                      returned=int(sum(bool(a['returned']) for a in env.agent_dic.values())),
                      simulation_end_time=float(env.current_time), makespan_return=None,
                      within_horizon=bool(np.isfinite(env.current_time) and env.current_time <= 200))
    result.update(wall_seconds=time.perf_counter()-start, actions=len(events),
                  initialization_seconds=execution_start-start if execution_start else None,
                  execution_seconds=time.perf_counter()-execution_start if execution_start else None,
                  masked_actions=sum(x['masked'] for x in events))
    write_json(out / 'events.json', events)
    write_json(out / 'final.json', dict(tasks=env.task_dic, agents=env.agent_dic, depots=env.depot_dic))
    write_json(out / 'result.json', result)
    print(json.dumps(plain(result)))
    return 0 if result['status'] == 'success' else 1


def run(args):
    records = asset_manifest()
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Output must be new/empty: {out}')
    out.mkdir(parents=True, exist_ok=True)
    import numpy, torch, scipy, matplotlib
    config = dict(commit=COMMIT, source_files=records, seeds=args.seeds, methods=args.methods,
                  agents=9, tasks=args.tasks, species=3, per_species=3, trait_dim=5,
                  decision_dim=30, simulation_horizon=200, wall_timeout_seconds=args.timeout,
                  policy_call='Worker.run_episode(False, False, False)',
                  greedy_call='TaskEnv.execute_greedy_action(plot_figure=False)',
                  information='Original instantaneous global observation and original masks',
                  compatibility_patches=[], diagnostic_patch='corrected_nearest adds dist = dist_',
                  python=sys.version, executable=sys.executable, platform=platform.platform(),
                  inherited_system_site_packages=True,
                  package_versions={m.__name__: m.__version__ for m in [numpy, torch, scipy, matplotlib]},
                  package_paths={m.__name__: m.__file__ for m in [numpy, torch, scipy, matplotlib]},
                  script_sha256=digest(__file__), command=sys.argv,
                  checkpoint_loading='restricted six-global Unpickler; strict best_model state_dict',
                  started_utc=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
    write_json(out / 'manifest.json', config)
    (out / 'heteromrta_eval.py').write_bytes(Path(__file__).read_bytes())
    rows = []
    for seed in args.seeds:
        for method in args.methods:
            case = out / f'seed-{seed:03d}-{method}'
            case.mkdir()
            command = [sys.executable, '-X', 'utf8', str(Path(__file__).resolve()), '--child',
                       '--seed', str(seed), '--tasks', str(args.tasks), '--method', method, '--output', str(case)]
            t = time.perf_counter()
            with (case / 'stdout.log').open('w', encoding='utf-8') as stdout, (case / 'stderr.log').open('w', encoding='utf-8') as stderr:
                try:
                    proc = subprocess.run(command, stdout=stdout, stderr=stderr, timeout=args.timeout)
                    status = 'error'
                    exit_code = proc.returncode
                except subprocess.TimeoutExpired:
                    status, exit_code = 'wall_timeout', None
            if (case / 'result.json').exists():
                row = json.loads((case / 'result.json').read_text())
            else:
                row = dict(seed=seed, method=method, status=status, wall_seconds=time.perf_counter()-t,
                           completed=None, completion_fraction=None, returned=None, makespan_return=None)
            row['process_exit_code'] = exit_code
            rows.append(row)
            write_json(out / 'results.json', rows)
            print(seed, method, row['status'], row.get('makespan_return'), flush=True)
    paired = []
    for seed in args.seeds:
        cases = {r['method']: r for r in rows if r['seed'] == seed}
        hashes = {r.get('initial_sha256') for r in cases.values()}
        if None not in hashes:
            assert len(hashes) == 1, 'Unpaired initial instances'
        a, b = cases.get('policy', {}), cases.get('author_greedy', {})
        both = a.get('status') == b.get('status') == 'success'
        paired.append(dict(seed=seed, policy_status=a.get('status'), greedy_status=b.get('status'),
                           initial_sha256=a.get('initial_sha256'),
                           policy_makespan=a.get('makespan_return'), greedy_makespan=b.get('makespan_return'),
                           policy_minus_greedy=a['makespan_return']-b['makespan_return'] if both else None))
    with (out / 'paired.csv').open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(paired[0]))
        writer.writeheader()
        writer.writerows(paired)
    summary = {}
    for method in args.methods:
        group = [r for r in rows if r['method'] == method]
        successes = [r for r in group if r['status'] == 'success']
        summary[method] = dict(attempts=len(group), success=len(successes),
                              statuses=dict(collections.Counter(r['status'] for r in group)),
                              mean_makespan_return=sum(r['makespan_return'] for r in successes)/len(successes) if successes else None)
    write_json(out / 'summary.json', summary)
    return 0 if all(r['status'] == 'success' for r in rows) else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch', action='store_true')
    p.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--tasks', type=int, default=15)
    p.add_argument('--method', choices=['policy', 'author_greedy', 'corrected_nearest'], default='policy')
    p.add_argument('--seeds', nargs='+', type=int, default=list(range(5)))
    p.add_argument('--methods', nargs='+', choices=['policy', 'author_greedy', 'corrected_nearest'], default=['policy', 'author_greedy'])
    p.add_argument('--timeout', type=float, default=120)
    p.add_argument('--output', type=str)
    args = p.parse_args()
    if args.fetch:
        write_json(ASSETS.parent / 'sources.json', asset_manifest(fetch=True))
        return 0
    if not args.output:
        p.error('--output is required for evaluation')
    return child(args) if args.child else run(args)


if __name__ == '__main__':
    raise SystemExit(main())
