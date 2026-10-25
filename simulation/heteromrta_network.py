"""Intent delivery/cache equivalence and fixed-trajectory shadow diagnostics.

The original Worker remains the execution oracle. Shadow actions NEVER control
the world; this is not a distributed task/network closed loop or wireless model.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import heapq
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from simulation.heteromrta_eval import ASSETS, COMMIT, asset_manifest, digest, load_checkpoint, plain, write_json


def encode_body(source, seq, generated_at, action, agent, decision_step):
    """Only the source's accepted command, never a global task/agent snapshot."""
    command = dict(action=int(action), arrival=float(agent['arrival_time'][-1]),
                   departure=float(agent['arrival_time'][-1]-agent['travel_time']),
                   travel_time=float(agent['travel_time']), travel_dist=float(agent['travel_dist']),
                   decision_step=int(decision_step))
    message = dict(kind='body', schema=1, source=int(source), seq=int(seq),
                   generated_at=float(generated_at), command=command)
    return json.dumps(message, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


class IntentView:
    """Independent reducer; its only state inputs are initial catalog and bodies."""
    def __init__(self, initial_env):
        self.env = copy.deepcopy(initial_env)
        self.expected = {i: 1 for i in self.env.agent_dic}
        self.pending = {i: {} for i in self.env.agent_dic}
        self.applied = []
        self.received_bodies = 0
        self.duplicate_bodies = 0
        self.headers = 0

    def receive(self, raw, received_at):
        msg = json.loads(raw)
        if msg['kind'] == 'header':
            self.headers += 1
            return []
        if msg.get('kind') != 'body' or msg.get('schema') != 1:
            raise ValueError('Unsupported frame')
        source, seq = msg['source'], msg['seq']
        if source not in self.expected or not isinstance(seq, int) or seq < 1:
            raise ValueError('Invalid source/sequence')
        if msg['generated_at'] > received_at:
            raise ValueError('Cannot deliver before generation')
        command = msg['command']
        if not 0 <= command['action'] <= self.env.tasks_num:
            raise ValueError('Invalid action')
        if any(not __import__('math').isfinite(command[k]) for k in ('arrival', 'departure', 'travel_time', 'travel_dist')):
            raise ValueError('Nonfinite command')
        self.received_bodies += 1
        if seq < self.expected[source] or seq in self.pending[source]:
            self.duplicate_bodies += 1
            return []
        self.pending[source][seq] = msg
        applied = []
        while self.expected[source] in self.pending[source]:
            message = self.pending[source].pop(self.expected[source])
            self._apply(message, received_at)
            self.expected[source] += 1
            applied.append(message['seq'])
        return applied

    def _apply(self, msg, now):
        env, source, cmd = self.env, msg['source'], msg['command']
        env.current_time = float(now)
        agent = env.agent_dic[source]
        task_index = cmd['action']-1
        target = env.task_dic[task_index] if task_index >= 0 else env.depot_dic[agent['species']]
        agent['route'].append(target['ID'])
        agent['current_task'] = task_index
        agent['travel_time'] = cmd['travel_time']
        agent['travel_dist'] = cmd['travel_dist']
        agent['arrival_time'].append(cmd['arrival'])
        agent['location'] = target['location'].copy()
        agent['decision_step'] = cmd['decision_step']
        agent['no_choice'] = False
        if source not in target['members']:
            target['members'].append(source)
        # These derive a PLAN from this replica's received intents. They are not
        # asserted to be physical coalition start/completion observations.
        env.task_update()
        env.agent_update()
        self.applied.append(dict(source=source, seq=msg['seq'], generated_at=msg['generated_at'], applied_at=float(now)))

    def tick_original_checkpoint(self, now):
        """Replay an original check_finished timer checkpoint (shadow only)."""
        self.env.current_time = float(now)
        self.env.task_update()

    def observation(self, actor, now):
        self.env.current_time = float(now)
        return self.env.agent_observe(actor, False)

    def branch(self, actor, mask):
        all_feasible = all(bool(t['feasible_assignment']) for t in self.env.task_dic.values())
        blocked = bool(mask[0, 1:].all())
        if blocked and not all_feasible:
            return 'no_choice'
        if blocked and all_feasible and self.env.agent_dic[actor]['current_task'] < 0:
            return 'skip_at_depot'
        return 'infer'

    def signature(self):
        obj = dict(agents=self.env.agent_dic, tasks=self.env.task_dic, depots=self.env.depot_dic)
        return hashlib.sha256(json.dumps(plain(obj), sort_keys=True).encode()).hexdigest()


class ShadowBank:
    def __init__(self, initial_env, delays):
        self.delays = delays
        self.views = {delay: {i: IntentView(initial_env) for i in initial_env.agent_dic} for delay in delays}
        self.heap = []
        self.order = 0
        self.events = []
        self.source_sequences = {i: 0 for i in initial_env.agent_dic}
        self.sent = []

    def publish(self, source, now, action, agent, step):
        self.source_sequences[source] += 1
        seq = self.source_sequences[source]
        raw = encode_body(source, seq, now, action, agent, step)
        entry = json.loads(raw)
        entry.update(serialized_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        self.sent.append(entry)
        for delay, views in self.views.items():
            for receiver in views:
                self.order += 1
                delivery = now if receiver == source else now+delay
                heapq.heappush(self.heap, (delivery, self.order, delay, receiver, raw))
        self.flush(now)

    def flush(self, now):
        while self.heap and self.heap[0][0] <= now:
            delivery, _, delay, receiver, raw = heapq.heappop(self.heap)
            msg = json.loads(raw)
            applied = self.views[delay][receiver].receive(raw, delivery)
            self.events.append(dict(kind='local_command' if receiver == msg['source'] else 'body_delivery',
                                    delay=delay, receiver=receiver, source=msg['source'], seq=msg['seq'],
                                    generated_at=msg['generated_at'], delivered_at=delivery,
                                    applied_sequences=applied, serialized_bytes=len(raw)))

    def tick(self, now):
        self.flush(now)
        for views in self.views.values():
            for view in views.values():
                view.tick_original_checkpoint(now)


def original_branch(env, actor, mask):
    all_feasible = all(bool(t['feasible_assignment']) for t in env.task_dic.values())
    if mask[0, 1:].all() and not all_feasible:
        return 'no_choice'
    if mask[0, 1:].all() and all_feasible and env.agent_dic[actor]['current_task'] < 0:
        return 'skip_at_depot'
    return 'infer'


def infer(net, observation, actor, torch):
    with torch.no_grad():
        args = [torch.tensor(a, dtype=torch.float) for a in observation]
        idx = torch.LongTensor([actor]).reshape(1, 1, 1)
        probs, _ = net(*args, idx)
        return int(torch.argmax(probs, dim=1).item())


def array_digest(arr):
    return hashlib.sha256(arr.tobytes()).hexdigest()


def read_archived_json(path):
    path=Path(path)
    actual=path if path.exists() else path.with_suffix(path.suffix+'.gz')
    raw=actual.read_bytes()
    text=gzip.decompress(raw) if actual.suffix=='.gz' else raw
    return json.loads(text), dict(path=str(actual.relative_to(ROOT)), stored_sha256=hashlib.sha256(raw).hexdigest(),
                                 content_sha256=hashlib.sha256(text).hexdigest())


def case_passed(result):
    return (result.get('status')=='completed' and result.get('reference_success') is True
            and result.get('zero_delay_equivalent') is True
            and result.get('archived_reference_equal') is True)


def child(args):
    os.environ['MPLBACKEND'] = 'Agg'
    sys.path.insert(0, str(ASSETS))
    import numpy as np
    import torch
    from env.task_env import TaskEnv
    from attention import AttentionNet
    from worker import Worker
    from parameters import TrainParams
    torch.set_num_threads(1)
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    random.seed(args.seed)
    output = Path(args.output)
    net = AttentionNet(TrainParams.AGENT_INPUT_DIM, TrainParams.TASK_INPUT_DIM, TrainParams.EMBEDDING_DIM)
    net.load_state_dict(load_checkpoint(torch), strict=True)
    net.eval()
    worker = Worker(0, net, net, 0, device='cpu', seed=args.seed)
    env = TaskEnv(per_species_range=(3, 3), species_range=(3, 3), tasks_range=(args.tasks, args.tasks),
                  traits_dim=5, decision_dim=30, seed=args.seed)
    env.init_state()
    worker.env = env
    initial = plain(dict(tasks=env.task_dic, agents=env.agent_dic, depots=env.depot_dic, species=env.species_dict))
    write_json(output/'initial.json', initial)
    initial_sha = hashlib.sha256(json.dumps(initial, sort_keys=True).encode()).hexdigest()
    bank = ShadowBank(env, args.delays)
    reference_decisions, comparison, reference_actions, checkpoints = [], [], [], []
    observe_orig, step_orig, finish_orig = env.agent_observe, env.agent_step, env.check_finished
    last_decision = {}

    def observe(actor, max_waiting=False):
        obs = observe_orig(actor, max_waiting)
        now = float(env.current_time)
        bank.flush(now)
        branch = original_branch(env, actor, obs[2])
        action = infer(net, obs, actor, torch) if branch == 'infer' else None
        record = dict(index=len(reference_decisions), time=now, actor=actor, branch=branch, action=action,
                      observation=[x.tolist() for x in obs], observation_sha256=[array_digest(x) for x in obs])
        reference_decisions.append(record)
        last_decision[actor] = record
        for delay in args.delays:
            view = bank.views[delay][actor]
            other = view.observation(actor, now)
            other_branch = view.branch(actor, other[2])
            other_action = infer(net, other, actor, torch) if other_branch == 'infer' else None
            equal = [bool(np.array_equal(a, b)) for a, b in zip(obs, other)]
            comparison.append(dict(decision=record['index'], delay=delay, actor=actor, time=now,
                                   observation_equal=all(equal), task_features_equal=equal[0],
                                   agent_features_equal=equal[1], mask_equal=equal[2],
                                   max_abs_feature_difference=max(float(np.max(np.abs(a-b))) for a,b in zip(obs[:2],other[:2])),
                                   reference_branch=branch, shadow_branch=other_branch,
                                   reference_action=action, shadow_action=other_action,
                                   branch_equal=branch == other_branch, action_equal=action == other_action,
                                   observation=[x.tolist() for x in other],
                                   delivered_versions={str(k): v-1 for k,v in view.expected.items()}))
        return obs

    def step(actor, action, decision_step):
        if len(reference_actions) >= 10000:
            raise RuntimeError('action budget exhausted')
        record = last_decision[actor]
        assert action == record['action'], 'Reference inference changed actual Worker action'
        outcome = step_orig(actor, action, decision_step)
        now = float(env.current_time)
        reference_actions.append(dict(time=now, actor=actor, action=action, accepted=bool(outcome[1]),
                                      decision=record['index']))
        if outcome[1]:
            bank.publish(actor, now, action, env.agent_dic[actor], decision_step)
        return outcome

    def check_finished():
        now = float(env.current_time)
        result = finish_orig()
        # task_update is called at the pre-check time, before the author's
        # optional final current_time jump. Keep this exact E0 micro-order.
        bank.tick(now)
        checkpoints.append(dict(before=now, after=float(env.current_time), finished=bool(result)))
        return result

    env.agent_observe, env.agent_step, env.check_finished = observe, step, check_finished
    started = time.perf_counter()
    result = dict(seed=args.seed, tasks=args.tasks, initial_sha256=initial_sha,
                  layer='fixed_trajectory_shadow', status='error')
    try:
        _, _, metrics = worker.run_episode(False, False, False)
        result.update(status='completed', reference_metrics=metrics, reference_finished=bool(env.finished),
                      reference_return_time=float(env.current_time),
                      reference_completed=sum(bool(t['finished']) for t in env.task_dic.values()),
                      reference_returned=sum(bool(a['returned']) for a in env.agent_dic.values()))
    except Exception:
        result['error'] = traceback.format_exc()
    bank.flush(env.current_time)
    result['reference_success'] = bool(result.get('reference_finished') and
        result.get('reference_completed')==args.tasks and result.get('reference_returned')==env.agents_num
        and 0 <= result.get('reference_return_time',float('inf')) <= 200)
    result['wall_seconds'] = time.perf_counter()-started
    summaries = {}
    for delay in args.delays:
        rows = [r for r in comparison if r['delay']==delay]
        summaries[str(delay)] = dict(decisions=len(rows),
            observation_mismatch=sum(not r['observation_equal'] for r in rows),
            mask_mismatch=sum(not r['mask_equal'] for r in rows),
            branch_mismatch=sum(not r['branch_equal'] for r in rows),
            action_mismatch=sum(not r['action_equal'] for r in rows),
            pending_deliveries=sum(x[2]==delay for x in bank.heap),
            blocked_intents=sum(len(p) for v in bank.views[delay].values() for p in v.pending.values()))
    result['shadow_summary'] = summaries
    result['zero_delay_equivalent'] = bool(summaries['0.0']['decisions']>0 and all(summaries['0.0'][k]==0 for k in
        ['observation_mismatch','mask_mismatch','branch_mismatch','action_mismatch'])) if '0.0' in summaries else None
    result['command_bytes_once_per_publication'] = sum(x['serialized_bytes'] for x in bank.sent)
    result['backdated_legacy_commands'] = [dict(source=x['source'], seq=x['seq'], generated_at=x['generated_at'],
       departure=x['command']['departure'], backdate=x['generated_at']-x['command']['departure'])
       for x in bank.sent if x['command']['departure'] < x['generated_at']-1e-9]
    # Persist new evidence BEFORE any archive access so validation errors cannot
    # destroy this run's observations or failure history.
    write_json(output/'reference_decisions.json', reference_decisions)
    write_json(output/'reference_actions.json', reference_actions)
    write_json(output/'comparisons.json', comparison)
    write_json(output/'intent_publications.json', bank.sent)
    write_json(output/'delivery_events.json', bank.events)
    write_json(output/'checkpoints.json', checkpoints)
    write_json(output/'reference_final.json',dict(tasks=env.task_dic,agents=env.agent_dic,depots=env.depot_dic))
    archive = ROOT/'simulation/results/2026-10-23-E1-002-heteromrta'/('20261023-02' if args.tasks==15 else '20261023-03')/f'seed-{args.seed:03d}-policy'
    try:
        old_result, result_file = read_archived_json(archive/'result.json')
        old_events, events_file = read_archived_json(archive/'events.json')
        old_final, final_file = read_archived_json(archive/'final.json')
        expected = [(x['time'], x['agent'], x['action']) for x in old_events]
        observed = [(x['time'], x['actor'], x['action']) for x in reference_actions]
        observed_masks=[reference_decisions[x['decision']]['observation'][2] for x in reference_actions]
        validation = dict(archive=str(archive.relative_to(ROOT)),files=[result_file,events_file,final_file],
                          initial_equal=initial_sha==old_result['initial_sha256'],
                          action_trace_equal=expected==observed,
                          masks_equal=observed_masks==[x['mask'] for x in old_events],
                          final_state_equal=plain(dict(tasks=env.task_dic,agents=env.agent_dic,depots=env.depot_dic))==old_final,
                          return_time_equal=result.get('reference_return_time')==old_result['makespan_return'])
        write_json(output/'archive_validation.json',validation)
        result['archived_reference_equal']=all(validation[k] for k in ['initial_equal','action_trace_equal','masks_equal','final_state_equal','return_time_equal'])
    except Exception:
        result['archived_reference_equal']=False
        result['archive_validation_error']=traceback.format_exc()
    write_json(output/'result.json', result)
    print(json.dumps(result))
    return 0 if case_passed(result) else 1


def run(args):
    records = asset_manifest()
    out = Path(args.output).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output must be new/empty')
    if len(args.seeds)*len(args.task_counts)>60:
        raise ValueError('Maximum 60 original episodes')
    out.mkdir(parents=True, exist_ok=True)
    import importlib.metadata
    source_hash=digest(__file__)
    write_json(out/'manifest.json', dict(layer='fixed_trajectory_shadow', author_commit=COMMIT,
       sources=records, source_sha256=digest(__file__), eval_helper_sha256=digest(ROOT/'simulation/heteromrta_eval.py'),
       python=sys.version, executable=sys.executable, command=sys.argv, delays=args.delays,
       package_versions={name:importlib.metadata.version(name) for name in ['numpy','torch','scipy','matplotlib']},
       seeds=args.seeds, task_counts=args.task_counts, timeout=args.timeout,
       initial_catalog='Pre-mission common initial task/agent/depot catalog; not transmitted',
       publication='Accepted original source command only; no global task snapshots',
       intervention='Remote intent body delay; own command immediate; no loss or wireless contention',
       schedule='Original global Worker decisions/actions/check_finished clock checkpoints replayed',
       bytes='Serialized application command only; not airtime and not complete protocol overhead',
       shadow_actions_executed=False, simulator_time_unit='upstream simulation unit'))
    (out/'heteromrta_network.py').write_bytes(Path(__file__).read_bytes())
    results=[]
    for tasks in args.task_counts:
        for seed in args.seeds:
            if digest(__file__)!=source_hash:
                raise RuntimeError('Evaluation source changed during run')
            case=out/f'tasks-{tasks}-seed-{seed:03d}'
            case.mkdir()
            cmd=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--child','--seed',str(seed),
                 '--tasks',str(tasks),'--output',str(case),'--delays',*[str(x) for x in args.delays]]
            with (case/'stdout.log').open('w',encoding='utf-8') as so,(case/'stderr.log').open('w',encoding='utf-8') as se:
                try:
                    proc=subprocess.run(cmd,stdout=so,stderr=se,timeout=args.timeout)
                    status,code='error',proc.returncode
                except subprocess.TimeoutExpired:
                    status,code='wall_timeout',None
            r=json.loads((case/'result.json').read_text()) if (case/'result.json').exists() else dict(seed=seed,tasks=tasks,status=status)
            r['process_exit_code']=code
            r['source_unchanged_after_child']=digest(__file__)==source_hash
            results.append(r)
            write_json(out/'results.json',results)
            print(tasks,seed,r['status'],r.get('zero_delay_equivalent'),flush=True)
    total={str(d): {k:sum(r.get('shadow_summary',{}).get(str(d),{}).get(k,0) for r in results)
           for k in ['decisions','observation_mismatch','mask_mismatch','branch_mismatch','action_mismatch','pending_deliveries','blocked_intents']} for d in args.delays}
    write_json(out/'summary.json',dict(episodes=len(results),completed=sum(r['status']=='completed' for r in results),
       zero_delay_equivalent=sum(r.get('zero_delay_equivalent',False) for r in results),shadows=total,
       legacy_backdated=sum(len(r.get('backdated_legacy_commands',[])) for r in results)))
    return 0 if all(case_passed(r) and r.get('process_exit_code')==0 and r.get('source_unchanged_after_child') for r in results) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    p.add_argument('--child',action='store_true')
    p.add_argument('--seed',type=int,default=0)
    p.add_argument('--tasks',type=int,default=15)
    p.add_argument('--seeds',nargs='+',type=int,default=list(range(5)))
    p.add_argument('--task-counts',nargs='+',type=int,default=[15,20])
    p.add_argument('--delays',nargs='+',type=float,default=[0.0,0.5,2.0])
    p.add_argument('--timeout',type=float,default=60)
    args=p.parse_args()
    if any(d<0 for d in args.delays) or len(set(args.delays))!=len(args.delays) or 0.0 not in args.delays:
        p.error('Unique nonnegative delays including 0 are required')
    return child(args) if args.child else run(args)


if __name__=='__main__':
    raise SystemExit(main())
