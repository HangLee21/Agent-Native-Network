"""Runtime information provenance and common local recovery on frozen catalogs.

The original causal executor remains unchanged. The separate information ledger
records consultation, never causal value. All task episodes are bounded.
"""
from __future__ import annotations
import argparse
import copy
import gzip
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

ROOT = Path(os.environ.get('ANN_REPO_ROOT', Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT))
if __package__:
    from .heteromrta_causal import CausalWorld, LocalView, encode
    from .message_service import MessageService
else:
    from heteromrta_causal import CausalWorld, LocalView, encode
    from message_service import MessageService
from simulation.heteromrta_eval import ASSETS, COMMIT, asset_manifest, load_checkpoint, plain, write_json, digest

RECOVERY = dict(startup_window=1., wait_base=20., wait_jitter=5., idle_base=1., idle_jitter=1.)


def keyed_uniform(seed, actor, kind, count):
    raw = json.dumps([int(seed), int(actor), str(kind), int(count)], separators=(',', ':')).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], 'big') / 2**64


def read_json(path):
    path = Path(path)
    raw = path.read_bytes()
    return json.loads(gzip.decompress(raw) if path.suffix == '.gz' else raw)


def normalize_catalog(catalog):
    return {kind: {int(k): v for k, v in values.items()} for kind, values in catalog.items()}


class TrackedView(LocalView):
    def __init__(self, catalog, actor, sink):
        super().__init__(catalog, actor)
        self.sink = sink
        initial = self.sink('information_acquired', actor=actor, origin='initial', applied=True,
                            object='catalog_and_initial_idle_states',
                            catalog_sha256=hashlib.sha256(encode(catalog)).hexdigest(),
                            protocol_cost_bytes=0, modeling_condition='common_preloaded_catalog')
        self.initial_id = initial
        self.state_origin = {i: initial for i in self.states}
        self.scene_origin = {}

    def apply(self, body, now, via, evidence_id):
        changed = super().apply(body, now, via, evidence_id)
        kind = body['kind']
        obj = body['state']['source'] if kind == 'self_state' else body['scene']['task']
        version = body['state']['seq'] if kind == 'self_state' else body['scene']['version']
        fact_id = self.sink('information_acquired', actor=self.actor,
                            origin='network' if via == 'network' else 'local',
                            applied=changed, object=kind, object_id=obj, version=version,
                            evidence_id=evidence_id, evidence_prefix=len(self.evidence),
                            source=body['source'], generated_at=body['generated_at'],
                            payload_sha256=hashlib.sha256(encode(body)).hexdigest())
        if changed:
            (self.state_origin if kind == 'self_state' else self.scene_origin)[obj] = fact_id
        return changed

    def consultation(self, decision_id, obs, branch):
        # These entries reflect actual loops in LocalView.observation/planned_tasks.
        # Missing task scenes are recorded as unknown; no remote facts are acquired.
        refs = []
        for i, state in self.states.items():
            refs.append(dict(object='self_state', object_id=i, version=state['seq'],
                             fact_id=self.state_origin[i], knowledge='known',
                             consumer='LocalView.planned_tasks+observation',
                             fields='target,mode,arrival,destination; catalog abilities'))
        for tid in self.catalog['tasks']:
            scene = self.scenes.get(tid)
            refs.append(dict(object='task_scene', object_id=tid,
                             version=scene['version'] if scene else None,
                             fact_id=self.scene_origin.get(tid),
                             knowledge='known' if scene else 'unknown',
                             consumer='LocalView.planned_tasks',
                             fields='phase; workers/start when confirmed'))
        return self.sink('information_consulted', actor=self.actor, decision_id=decision_id,
                         demand_id='need-' + decision_id,
                         demand_type='policy_consultation_not_minimum_task_requirement',
                         catalog_fact_id=self.initial_id, references=refs,
                         observation_sha256=hashlib.sha256(encode(obs)).hexdigest(), branch=branch,
                         evidence_count=len(self.evidence), causal_value=None,
                         scene_unknown_count=sum(r['knowledge'] == 'unknown' for r in refs))


class DemandWorld(CausalWorld):
    def __init__(self, catalog, service, choose, *, seed=0, recovery=False,
                 horizon=200., event_budget=100000, wall_budget=70.):
        super().__init__(catalog, service, choose, horizon=horizon, event_budget=event_budget,
                         wall_budget=wall_budget, idle_retry=1., task_wait=20. if recovery else 200.)
        self.info_ledger = []
        self.seed, self.recovery = seed, recovery
        self.gate_until = {i: 0. for i in self.actors}
        self.local_counts = {}
        self.active_action_id = None
        self.views = {i: TrackedView(catalog, i, self.info) for i in self.actors}
        if recovery:
            self.ready.clear()
            for i in self.actors:
                when = self.jitter(i, 'startup', RECOVERY['startup_window'])
                self.gate_until[i] = when
                self.schedule(when, 'startup_ready', actor=i)

    def info(self, kind, **data):
        ident = f'i{len(self.info_ledger):09d}'
        self.info_ledger.append(dict(id=ident, ordinal=len(self.info_ledger), time=self.now,
                                     kind=kind, parent_action_id=self.active_action_id, **plain(data)))
        return ident

    def jitter(self, actor, kind, scale):
        key = (actor, kind)
        count = self.local_counts.get(key, 0)
        self.local_counts[key] = count + 1
        return scale * keyed_uniform(self.seed, actor, kind, count)

    def schedule(self, when, kind, **data):
        if getattr(self, 'recovery', False) and kind == 'wait_timeout':
            when += self.jitter(data['actor'], 'wait_timeout', RECOVERY['wait_jitter'])
        super().schedule(when, kind, **data)
        if hasattr(self, 'info_ledger'):
            self.info('local_timer_scheduled' if kind in ('wait_timeout', 'idle_timer', 'startup_ready') else 'physical_event_scheduled',
                      event_kind=kind, due_at=when, data=data)

    def flush(self):
        super().flush()
        if self.recovery:
            self.ready = {i for i in self.ready if self.now >= self.gate_until[i]}

    def idle_timer(self, actor):
        if not self.recovery:
            return super().idle_timer(actor)
        a = self.actors[actor]
        a['timer'] += 1
        when = self.now + RECOVERY['idle_base'] + self.jitter(actor, 'idle_timer', RECOVERY['idle_jitter'])
        self.gate_until[actor] = when
        self.ready.discard(actor)
        self.schedule(when, 'idle_timer', actor=actor, token=a['timer'])

    def handle(self, kind, data):
        if self.recovery and kind == 'startup_ready':
            actor = data['actor']
            if self.actors[actor]['mode'] == 'idle' and self.now >= self.gate_until[actor]:
                self.info('local_timer_fired', event_kind=kind, actor=actor)
                self.ready.add(actor)
            return
        if self.recovery and kind == 'wait_timeout':
            i, a = data['actor'], self.actors[data['actor']]
            if a['mode'] == 'waiting' and a['arrival'] == data['arrival']:
                # Keep the physical site target: target<0 means at_depot in old observation.
                # mode=idle removes this actor from advertised active commitments.
                a.update(mode='idle', changed_at=self.now, finish=None)
                self.self_state(i, 'local_wait_cancel')
                self.event('local_wait_cancel', actor=i, target=a['target'])
                self.info('local_timer_fired', actor=i, event_kind=kind,
                          cancelled_target=a['target'], remote_effect='only_after_state_delivery')
                self.idle_timer(i)
            return
        return super().handle(kind, data)

    def decide(self, actor):
        if self.actors[actor]['mode'] != 'idle':
            return
        if self.recovery and self.now < self.gate_until[actor]:
            self.ready.discard(actor)
            return
        view = self.views[actor]
        decision_id = f'd{len(self.decisions):07d}'
        obs, branch = view.observation(self.now)
        consultation_id = view.consultation(decision_id, obs, branch)
        action = self.choose(obs, actor) if branch == 'infer' else None
        if action is not None and bool(obs[2][0, action]):
            raise AssertionError('Masked action')
        self.decisions.append(dict(time=self.now, actor=actor, branch=branch, action=action,
                                  observation=[x.tolist() for x in obs], view_sha256=view.signature(),
                                  source_versions={i:s['seq'] for i,s in view.states.items()},
                                  task_versions={i:s['version'] for i,s in view.scenes.items()},
                                  evidence_count=len(view.evidence)))
        eid = self.event('decision', actor=actor, branch=branch, action=action, view_sha256=view.signature())
        self.info('decision', decision_id=decision_id, actor=actor, consultation_id=consultation_id,
                  legacy_event_id=eid, action=action, branch=branch, policy_called=branch == 'infer')
        action_id = 'a' + decision_id[1:]
        self.info('action_intent', action_id=action_id, decision_id=decision_id, actor=actor,
                  action=action, kind_of_action='idle_retry' if action is None else 'task_or_depot_dispatch')
        previous_routes = len(self.actors[actor]['route'])
        self.active_action_id = action_id
        try:
            if action is None:
                self.idle_timer(actor)
            else:
                self.depart(actor, action)
        finally:
            self.active_action_id = None
        self.info('action_result', action_id=action_id, actor=actor,
                  departed=len(self.actors[actor]['route']) > previous_routes,
                  route_index=previous_routes if len(self.actors[actor]['route']) > previous_routes else None)

    def summary(self):
        result = super().summary()
        result['information_records'] = len(self.info_ledger)
        result['information_record_counts'] = {kind:sum(r['kind'] == kind for r in self.info_ledger)
                                               for kind in sorted({r['kind'] for r in self.info_ledger})}
        result['budget_definition'] = 'physical trace + message-service ledger; instrumentation separately counted'
        result['recovery'] = self.recovery
        return result


def compare_legacy(world, reference):
    result = {}
    for name, value in [('events',world.trace),('decisions',world.decisions),('messages',world.messages),
                        ('deliveries',world.deliveries),('view_evidence',{i:v.evidence for i,v in world.views.items()})]:
        p = Path(reference) / (name + '.json')
        if not p.exists():
            p = p.with_suffix('.json.gz')
        expected = read_json(p)
        result[name] = dict(equal=plain(value) == expected, reference=str(p), sha256=digest(p))
    return result


def child(spec_path, output):
    spec = read_json(spec_path)
    seed = spec['seed']
    out = Path(output)
    world = None
    result = dict(case_id=spec['case_id'], seed=seed, recovery=spec['recovery'],
                  condition=spec['condition'], status='error', task_executed=True)
    began = time.perf_counter()
    try:
        sys.path.insert(0, str(ASSETS))
        import numpy as np
        import torch
        from attention import AttentionNet
        from parameters import TrainParams
        torch.set_num_threads(1)
        torch.manual_seed(seed); np.random.seed(seed); random.seed(seed)
        catalog = normalize_catalog(read_json(out / 'catalog.json'))
        result.update(agents=len(catalog['agents']), tasks=len(catalog['tasks']),
                      catalog_sha256=hashlib.sha256(encode(catalog)).hexdigest())
        net = AttentionNet(TrainParams.AGENT_INPUT_DIM, TrainParams.TASK_INPUT_DIM, TrainParams.EMBEDDING_DIM)
        net.load_state_dict(load_checkpoint(torch), strict=True); net.eval()
        def choose(obs, actor):
            with torch.no_grad():
                values = [torch.tensor(a, dtype=torch.float) for a in obs]
                probs, _ = net(*values, torch.LongTensor([actor]).reshape(1,1,1))
                return int(torch.argmax(probs, dim=1).item())
        mode = 'instant' if spec['condition'] == 'instant' else 'fixed_delay'
        delay = 0. if mode == 'instant' else .5
        service = MessageService(mode=mode, delay=delay, rate_bytes_per_time=1024., capacity_bytes=65536)
        world = DemandWorld(catalog, service, choose, seed=seed, recovery=spec['recovery'],
                            horizon=200., event_budget=100000, wall_budget=70.)
        result.update(world.run())
        if spec.get('legacy_reference') and not spec['recovery']:
            result['legacy_comparison'] = compare_legacy(world, spec['legacy_reference'])
            if not all(x['equal'] for x in result['legacy_comparison'].values()):
                result['status'] = 'regression_mismatch'
    except Exception:
        result['error'] = traceback.format_exc()
        if world is not None:
            world.status='error'; result.update(world.summary())
    finally:
        result['wall_seconds'] = time.perf_counter()-began
        result['executor_sha256'] = digest(__file__)
        if world is not None:
            for name, value in [('events',world.trace),('decisions',world.decisions),('messages',world.messages),
                                ('deliveries',world.deliveries),('service_ledger',world.service.ledger),
                                ('view_evidence',{i:v.evidence for i,v in world.views.items()}),
                                ('information_ledger',world.info_ledger),
                                ('final',dict(actors=world.actors,tasks={i:{**t,'present':sorted(t['present'])} for i,t in world.tasks.items()}))]:
                write_json(out / (name+'.json'), value)
        write_json(out/'result.json', result)
    return 0 if result['status'] in ('success','horizon_incomplete','event_budget_exhausted') else 1


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--case-spec', required=True)
    p.add_argument('--child', action='store_true')
    args = p.parse_args()
    if args.child:
        return child(args.case_spec, args.output)
    out = Path(args.output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E1-006'):
        p.error('Output must be inside simulation/outputs/E1-006')
    specs = read_json(args.case_spec)
    if not isinstance(specs, list) or not 1 <= len(specs) <= 40:
        p.error('case-spec must contain 1..40 cases; global card budget also applies')
    if len({s['case_id'] for s in specs}) != len(specs):
        p.error('Repeated case_id')
    for s in specs:
        if s['condition'] not in ('instant','delay0.5') or not isinstance(s['recovery'], bool):
            p.error('Only frozen instant/delay0.5 and boolean recovery are supported')
        if Path(s['case_id']).name != s['case_id'] or s['case_id'] in ('.','..'):
            p.error('case_id must be one safe path component')
    out.mkdir(parents=True, exist_ok=False)
    snapshots = out/'source'; snapshots.mkdir()
    for name in ('heteromrta_demand_execution.py','heteromrta_causal.py','message_service.py','test_heteromrta_demand_execution.py'):
        (snapshots/name).write_bytes((ROOT/'simulation'/name).read_bytes())
    manifest = dict(command=sys.argv, python=sys.executable, python_version=platform.python_version(),
                    author_commit=COMMIT, assets=asset_manifest(), recovery_config=RECOVERY,
                    case_spec_sha256=digest(args.case_spec), cases=specs,
                    source_hashes={x.name:digest(x) for x in snapshots.iterdir()},
                    inherited_eval_sha256=digest(ROOT/'simulation/heteromrta_eval.py'),
                    horizon=200., event_budget=100000, budget_definition='physical trace + service ledger',
                    internal_wall_seconds=70, external_wall_seconds=90, torch_threads=1,
                    scope='runtime provenance and common recovery; no wireless service/scaling claim')
    write_json(out/'manifest.json', manifest)
    results = []
    for spec in specs:
        case = out/spec['case_id']; case.mkdir()
        if spec.get('expected_catalog_sha256') and digest(spec['catalog_path']) != spec['expected_catalog_sha256']:
            raise ValueError('Source catalog changed after case specification')
        catalog = read_json(spec['catalog_path'])
        write_json(case/'catalog.json', catalog)
        config = dict(spec, source_catalog_sha256=digest(spec['catalog_path']))
        write_json(case/'config.json', config)
        cmd = [sys.executable,'-B',str(snapshots/'heteromrta_demand_execution.py'),'--child',
               '--case-spec',str(case/'config.json'),'--output',str(case)]
        env = dict(os.environ, ANN_REPO_ROOT=str(ROOT), OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', MPLBACKEND='Agg')
        with (case/'stdout.txt').open('w',encoding='utf-8') as log:
            try:
                proc = subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=90)
                code = proc.returncode
            except subprocess.TimeoutExpired:
                code = -999
        result = read_json(case/'result.json') if (case/'result.json').exists() else dict(status='missing_result_or_external_timeout')
        result.update(case_id=spec['case_id'], process_exit_code=code)
        results.append(result)
        write_json(out/'summary.json',dict(planned=len(specs),cases=results))
        print(f"{spec['case_id']}: {result['status']} {result.get('completed')}/{result.get('tasks')} time={result.get('makespan_return')}",flush=True)
    return 0 if all(r['process_exit_code'] == 0 for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())

