"""Paired HeteroMRTA scale catalogs and bounded initial policy shape probes.

Creates two author 9-agent/60-task masters, then task prefixes and whole
9-agent clones. Never executes a task episode, changes assets, or invents
wireless conditions. Run only into a new directory under outputs/E2-006.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SCALE_CASES = ((9, 15), (18, 15), (36, 15), (18, 30), (36, 60))


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha256(value):
    # JSON keys use string representations consistently with archived catalogs.
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'),
                         allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2,
                                    allow_nan=False) + '\n', encoding='utf-8')


def normalize_catalog(catalog):
    if set(catalog) != {'agents', 'tasks'}:
        raise ValueError('Catalog requires only agents and tasks')
    normalized = {}
    for kind in ('tasks', 'agents'):
        mapping = catalog[kind]
        keys = sorted(map(int, mapping))
        if keys != list(range(len(keys))) or len(set(keys)) != len(mapping):
            raise ValueError(f'{kind} must have unique contiguous integer IDs')
        normalized[kind] = {
            i: copy.deepcopy(mapping[i] if i in mapping else mapping[str(i)])
            for i in keys
        }
    return normalized


def expand_catalog(master, agents, tasks):
    master = normalize_catalog(master)
    if len(master['agents']) != 9 or len(master['tasks']) != 60:
        raise ValueError('Expected author master with 9 agents and 60 tasks')
    if agents not in (9, 18, 36) or tasks not in (15, 30, 60):
        raise ValueError('Out-of-scope catalog size')
    return {
        'tasks': {i: copy.deepcopy(master['tasks'][i]) for i in range(tasks)},
        'agents': {i: copy.deepcopy(master['agents'][i % 9])
                   for i in range(agents)},
    }


def validate_pairing(master, catalog):
    master, catalog = normalize_catalog(master), normalize_catalog(catalog)
    if len(master['agents']) != 9 or len(master['tasks']) != 60:
        raise ValueError('Invalid master')
    if len(catalog['agents']) not in (9, 18, 36):
        raise ValueError('Invalid agent count')
    if len(catalog['tasks']) not in (15, 30, 60):
        raise ValueError('Invalid task count')
    if any(t != master['tasks'][i] for i, t in catalog['tasks'].items()):
        raise AssertionError('Task prefix changed')
    if any(a != master['agents'][i % 9] for i, a in catalog['agents'].items()):
        raise AssertionError('Agent clone changed')
    dimensions = {len(t['requirements']) for t in catalog['tasks'].values()}
    dimensions.update(len(a['abilities']) for a in catalog['agents'].values())
    if dimensions != {5}:
        raise AssertionError('Trait dimension differs from pinned task')
    total = [sum(a['abilities'][d] for a in catalog['agents'].values())
             for d in range(5)]
    infeasible = [i for i, t in catalog['tasks'].items()
                  if any(t['requirements'][d] > total[d] for d in range(5))]
    if infeasible:
        raise AssertionError(f'Aggregate capabilities insufficient: {infeasible}')
    return dict(task_prefix_exact=True, original_nine_exact=True,
                appended_clones_exact=True, capability_dimensions=5,
                aggregate_capabilities=total, infeasible_tasks=infeasible)


def families(agents, tasks):
    values = []
    if tasks == 15:
        values.append('fixed_total_15')
    if tasks * 3 == agents * 5:
        values.append('fixed_tasks_per_agent_5_over_3')
    return values


def master_from_author(seed):
    from simulation.heteromrta_eval import ASSETS, plain
    from simulation.heteromrta_causal import make_catalog
    os.environ['MPLBACKEND'] = 'Agg'
    sys.path.insert(0, str(ASSETS))
    import numpy as np
    from env.task_env import TaskEnv
    np.random.seed(seed)
    random.seed(seed)
    env = TaskEnv(per_species_range=(3, 3), species_range=(3, 3),
                  tasks_range=(60, 60), traits_dim=5, decision_dim=30, seed=seed)
    env.init_state()
    initial = plain(dict(tasks=env.task_dic, agents=env.agent_dic,
                         depots=env.depot_dic, species=env.species_dict))
    catalog = make_catalog(env)
    return initial, catalog


def probe(args):
    result = dict(status='error', seed=args.seed, catalog_path=str(Path(args.catalog).resolve()),
                  catalog_sha256=sha256(args.catalog), actors=[])
    started = time.perf_counter()
    try:
        os.environ['MPLBACKEND'] = 'Agg'
        from simulation.heteromrta_eval import ASSETS, load_checkpoint
        from simulation.heteromrta_causal import LocalView
        sys.path.insert(0, str(ASSETS))
        import numpy as np
        import torch
        from attention import AttentionNet
        from parameters import TrainParams
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        random.seed(args.seed)
        catalog = normalize_catalog(json.loads(Path(args.catalog).read_text(encoding='utf-8')))
        net = AttentionNet(TrainParams.AGENT_INPUT_DIM, TrainParams.TASK_INPUT_DIM,
                           TrainParams.EMBEDDING_DIM)
        net.load_state_dict(load_checkpoint(torch), strict=True)
        net.eval()
        n, task_count = len(catalog['agents']), len(catalog['tasks'])
        for actor in (0, n - 1):
            obs, branch = LocalView(catalog, actor).observation(0.)
            expected = [(1, task_count + 1, 15), (1, n, 11), (1, task_count + 1)]
            if [tuple(x.shape) for x in obs] != expected:
                raise AssertionError('Unexpected observation shape')
            if not all(np.isfinite(x).all() for x in obs):
                raise AssertionError('Nonfinite observation')
            t0 = time.perf_counter()
            with torch.no_grad():
                tensors = [torch.tensor(x, dtype=torch.float) for x in obs]
                probs, _ = net(*tensors, torch.LongTensor([actor]).reshape(1, 1, 1))
                action = int(torch.argmax(probs, dim=1).item())
            if tuple(probs.shape) != (1, task_count + 1):
                raise AssertionError('Unexpected action vector shape')
            if not bool(torch.isfinite(probs).all()) or bool(obs[2][0, action]):
                raise AssertionError('Invalid policy action')
            result['actors'].append(dict(actor=actor, branch=branch, action=action,
                action_is_legal=True, observation_shapes=[list(x.shape) for x in obs],
                output_shape=list(probs.shape), initial_state_only=True,
                forward_seconds=time.perf_counter()-t0))
        result.update(status='passed', torch_version=torch.__version__,
                      task_count=task_count, agent_count=n)
    except Exception:
        result['error'] = traceback.format_exc()
    result['wall_seconds'] = time.perf_counter() - started
    write_json(args.probe_output, result)
    return 0 if result['status'] == 'passed' else 1


def run(args):
    for name in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
        os.environ[name] = '1'
    from simulation.heteromrta_eval import asset_manifest, COMMIT
    out = Path(args.output).resolve()
    allowed = (ROOT / 'simulation/outputs/E2-006').resolve()
    if not out.is_relative_to(allowed) or out == allowed:
        raise ValueError('Use a new child directory under simulation/outputs/E2-006')
    out.mkdir(parents=True, exist_ok=False)
    assets = asset_manifest()
    snap = out / 'source'
    snap.mkdir()
    for rel in ('simulation/heteromrta_scale_catalog.py',
                'simulation/test_heteromrta_scale_catalog.py',
                'simulation/heteromrta_causal.py', 'simulation/heteromrta_eval.py'):
        (snap / Path(rel).name).write_bytes((ROOT / rel).read_bytes())
    manifest = dict(schema_version='ann.scale-preflight.v1', command=sys.argv,
        baseline_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        author_commit=COMMIT, assets=assets, seeds=[5,6],
        generator=dict(per_species_range=[3,3], species_range=[3,3],
                       tasks_range=[60,60], traits_dim=5, decision_dim=30),
        construction='One 9-agent/60-task master per seed; exact task prefixes; complete nine-agent copies',
        scopes=dict(task_episodes=0, catalog_configurations=10, probe_actors_per_configuration=2,
                    cpu_threads=1, per_probe_wall_timeout_seconds=args.timeout),
        units=dict(position='author normalized coordinate', time='author simulation time',
                   velocity='author coordinate/time; no physical conversion'),
        interpretive_limits=['No new physical platform types', 'All catalogs share initial known capability/task information',
            'Single initial forward pass does not establish task completion or policy generalization',
            'Fixed region with extra agents; no wireless contention test',
            '60-task master and clone construction are explicit adaptations, not unchanged original task distribution'],
        python=sys.version, executable=sys.executable, platform=platform.platform(),
        source_hashes={p.name:sha256(p) for p in snap.iterdir()}, masters=[], cases=[])
    write_json(out / 'manifest.json', manifest)
    index = dict(schema_version='ann.scale-catalog-index.v1', cases=[])
    for seed in (5,6):
        master_dir = out / 'masters' / f'seed-{seed:03d}'
        master_dir.mkdir(parents=True)
        initial, master = master_from_author(seed)
        write_json(master_dir / 'initial.json', initial)
        write_json(master_dir / 'catalog.json', master)
        master_record = dict(seed=seed, initial_path=str(master_dir/'initial.json'),
            initial_sha256=sha256(master_dir/'initial.json'), catalog_path=str(master_dir/'catalog.json'),
            catalog_sha256=sha256(master_dir/'catalog.json'),
            canonical_sha256=canonical_sha256(json.loads((master_dir/'catalog.json').read_text())))
        manifest['masters'].append(master_record)
        write_json(out/'manifest.json',manifest)
        for n,tasks in SCALE_CASES:
            case_id = f'seed-{seed:03d}-n{n:03d}-t{tasks:03d}'
            case_dir = out / 'catalogs' / case_id
            case_dir.mkdir(parents=True)
            catalog = expand_catalog(master,n,tasks)
            validation = validate_pairing(master,catalog)
            catalog_path = case_dir / 'catalog.json'
            write_json(catalog_path,catalog)
            write_json(case_dir/'pairing.json',validation)
            row = dict(case_id=case_id, seed=seed, agents=n, tasks=tasks, families=families(n,tasks),
                catalog_path=str(catalog_path), catalog_sha256=sha256(catalog_path),
                canonical_sha256=canonical_sha256(json.loads(catalog_path.read_text())),
                master_catalog_sha256=master_record['catalog_sha256'],
                pairing_path=str(case_dir/'pairing.json'), probe_status='pending')
            command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--probe',
                     '--catalog',str(catalog_path),'--seed',str(seed),
                     '--probe-output',str(case_dir/'probe.json')]
            with (case_dir/'stdout.log').open('w',encoding='utf-8') as stdout, (case_dir/'stderr.log').open('w',encoding='utf-8') as stderr:
                try:
                    proc = subprocess.run(command,stdout=stdout,stderr=stderr,timeout=args.timeout)
                    exit_code = proc.returncode
                except subprocess.TimeoutExpired:
                    exit_code = None
                    write_json(case_dir/'probe.json',dict(status='wall_timeout',actors=[]))
            probe_result = json.loads((case_dir/'probe.json').read_text()) if (case_dir/'probe.json').exists() else dict(status='process_error',actors=[])
            row.update(probe_status=probe_result['status'],probe_process_exit_code=exit_code,
                       probe_path=str(case_dir/'probe.json'))
            index['cases'].append(row)
            manifest['cases'].append(dict(**row,command=command))
            write_json(out/'catalog_index.json',index)
            write_json(out/'manifest.json',manifest)
            print(case_id, row['probe_status'], flush=True)
    write_json(out/'summary.json',dict(configurations=len(index['cases']),
        passed=sum(r['probe_status']=='passed' for r in index['cases']),
        masters=len(manifest['masters']), full_episodes_run=0,
        families={f:sum(f in r['families'] for r in index['cases'])
                  for f in ('fixed_total_15','fixed_tasks_per_agent_5_over_3')}))
    return 0 if all(r['probe_status']=='passed' for r in index['cases']) else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output')
    p.add_argument('--timeout',type=float,default=30.)
    p.add_argument('--probe',action='store_true')
    p.add_argument('--catalog')
    p.add_argument('--probe-output')
    p.add_argument('--seed',type=int,default=5)
    args=p.parse_args()
    if args.timeout <= 0 or args.timeout > 30:
        p.error('Timeout must be in (0,30]')
    if args.probe:
        if not args.catalog or not args.probe_output:
            p.error('Probe requires catalog and probe-output')
        # A failed child may leave results; do not permit replacement.
        if Path(args.probe_output).exists():
            p.error('Probe output exists')
        return probe(args)
    if not args.output:
        p.error('--output required')
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
