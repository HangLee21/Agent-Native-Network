"""Bounded causal adaptation of the pinned HeteroMRTA policy.

This is a new execution model, not a reproduction of original Worker timing.
Physical facts enter policies only through local observations or delivered bodies.
All durations/bytes are simulator/application units, not wireless airtime.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import heapq
import importlib.metadata
import json
import math
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
from simulation.heteromrta_eval import ASSETS, COMMIT, asset_manifest, digest, load_checkpoint, plain, write_json


def encode(obj):
    return json.dumps(plain(obj), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


class LocalView:
    """No reference to World. Inputs: catalog, own/onsite facts, delivered bodies."""
    def __init__(self, catalog, actor):
        self.catalog = copy.deepcopy(catalog)
        self.actor = actor
        self.states = {int(i): dict(source=int(i), seq=0, target=-1, mode='idle',
                       origin=a['depot'], destination=a['depot'], departure=0., arrival=0.,
                       changed_at=0., finish=None) for i, a in catalog['agents'].items()}
        self.scenes = {}
        self.evidence = []

    def apply(self, body, now, via, evidence_id):
        if body['generated_at'] > now + 1e-9:
            raise ValueError('Future information')
        changed = False
        if body['kind'] == 'self_state':
            state = body['state']
            if body['source'] != state['source']:
                raise ValueError('Only owner can publish its state')
            source = state['source']
            if state['seq'] > self.states[source]['seq']:
                self.states[source] = copy.deepcopy(state)
                changed = True
        elif body['kind'] == 'task_scene':
            scene = body['scene']
            if body['source'] not in scene['witnesses']:
                raise ValueError('Scene publisher lacks onsite evidence')
            old = self.scenes.get(scene['task'])
            # A completed static task is absorbing, including across publishers.
            if not old or (old['phase'] != 'done' and scene['version'] > old['version']):
                self.scenes[scene['task']] = copy.deepcopy(scene)
                changed = True
        else:
            raise ValueError('Unknown body kind')
        self.evidence.append(dict(at=now, via=via, evidence_id=evidence_id,
                                  source=body['source'], kind=body['kind'], applied=changed))
        return changed

    def planned_tasks(self, now):
        import numpy as np
        result = {}
        for tid, task in self.catalog['tasks'].items():
            tid = int(tid)
            members = [i for i, s in self.states.items()
                       if s['target'] == tid and s['mode'] in ('travel', 'waiting', 'working')]
            scene = self.scenes.get(tid)
            confirmed = bool(scene and scene['phase'] in ('running', 'done'))
            if confirmed:
                members = scene['workers']
            ability = np.sum([self.catalog['agents'][i]['abilities'] for i in members], axis=0) if members else np.zeros(5)
            residual = np.asarray(task['requirements']) - ability
            feasible = confirmed or bool(np.all(residual <= 0))
            start = (scene['started_at'] if confirmed else
                     max([self.states[i]['arrival'] for i in members], default=0.) if feasible else 0.)
            result[tid] = dict(residual=residual, feasible=feasible, members=members,
                               start=float(start), duration=task['time'],
                               done=bool(scene and scene['phase'] == 'done'))
        return result

    def observation(self, now):
        """Author feature layout; planned reservation features are not world facts."""
        import numpy as np
        plans = self.planned_tasks(now)
        mine = self.states[self.actor]
        loc = np.asarray(mine['destination'])  # decisions only while stationary
        own = self.catalog['agents'][self.actor]
        velocity = own['velocity']
        task_rows, agent_rows, mask = [], [], [False]
        depot = np.asarray(own['depot'])
        task_rows.append(np.hstack([np.zeros(5), -np.ones(5), 0., np.linalg.norm(loc-depot)/velocity, loc-depot, 1.]))
        for tid, task in self.catalog['tasks'].items():
            plan = plans[int(tid)]
            target = np.asarray(task['location'])
            task_rows.append(np.hstack([plan['residual'], task['requirements'], task['time'],
                                       np.linalg.norm(loc-target)/velocity, loc-target, plan['feasible']]))
            useful = np.maximum(np.minimum(plan['residual'], own['abilities']), 0).sum() > 0
            mask.append(plan['feasible'] or not useful)
        for i, info in self.catalog['agents'].items():
            state = self.states[int(i)]
            remaining, waiting, travel = 0., 0., 0.
            if state['target'] >= 0:
                plan = plans[state['target']]
                travel = max(state['arrival']-now, 0.)
                if now <= plan['start']:
                    waiting = max(now-state['arrival'], 0.)
                    remaining = max(plan['start']+plan['duration']-now, 0.)
            # Same destination/intent position feature as author; physical pose is separate.
            assigned = state['mode'] == 'working'
            agent_rows.append(np.hstack([info['abilities'], travel, remaining, waiting,
                                        loc-np.asarray(state['destination']), assigned]))
        obs = (np.asarray(task_rows)[None], np.asarray(agent_rows)[None], np.asarray(mask, dtype=bool)[None])
        all_feasible = all(p['feasible'] for p in plans.values())
        at_depot = mine['target'] < 0
        branch = ('no_choice' if obs[2][0, 1:].all() and not all_feasible else
                  'skip_at_depot' if obs[2][0, 1:].all() and all_feasible and at_depot else 'infer')
        return obs, branch

    def signature(self):
        return hashlib.sha256(encode(dict(states=self.states, scenes=self.scenes))).hexdigest()


class CausalWorld:
    def __init__(self, catalog, service, choose, horizon=200., event_budget=10000,
                 wall_budget=55., idle_retry=1., task_wait=200.):
        self.catalog = copy.deepcopy(catalog)
        self.service, self.choose = service, choose
        self.horizon, self.event_budget = horizon, event_budget
        self.wall_budget, self.idle_retry, self.task_wait = wall_budget, idle_retry, task_wait
        self.now, self.serial, self.events_processed = 0., 0, 0
        self.started_wall = time.perf_counter()
        self.heap, self.trace, self.decisions, self.messages, self.deliveries = [], [], [], [], []
        self.actors = {int(i): dict(mode='idle', target=-1, position=list(a['depot']),
                       origin=list(a['depot']), destination=list(a['depot']), departure=0., arrival=0.,
                       changed_at=0., finish=None, seq=0, timer=0, route=[], distance=0.)
                       for i, a in catalog['agents'].items()}
        self.tasks = {int(t): dict(phase='open', present=set(), workers=[], version=0,
                       started_at=None, finished_at=None) for t in catalog['tasks']}
        self.views = {i: LocalView(catalog, i) for i in self.actors}
        self.ready = set(self.actors)
        self.status = 'running'

    def event(self, kind, **data):
        event = dict(id=len(self.trace), time=self.now, kind=kind, **plain(data))
        self.trace.append(event)
        return event['id']

    def schedule(self, when, kind, **data):
        if when < self.now-1e-9:
            raise AssertionError('Scheduling into the past')
        self.serial += 1
        heapq.heappush(self.heap, (float(when), self.serial, kind, data))

    def network_pose(self, actor, now):
        a = self.actors[actor]
        if a['mode'] != 'travel' or a['arrival'] <= a['departure']:
            return list(a['position'])
        fraction = min(max((now-a['departure'])/(a['arrival']-a['departure']), 0.), 1.)
        return [x+fraction*(y-x) for x, y in zip(a['origin'], a['destination'])]

    def publish(self, body, local_receivers, local_evidence):
        raw = encode(body)
        source = body['source']
        # Local facts are observations, not secretly delivered remote messages.
        for i in local_receivers:
            self.views[i].apply(body, self.now, 'local_observation', local_evidence)
        recipients = [i for i in self.actors if i != source]
        mid = self.service.submit(self.now, source, recipients, body['kind'], raw)
        self.messages.append(dict(message_id=mid, source=source, recipients=recipients,
                                  kind=body['kind'], generated_at=self.now, payload_utf8=raw.decode(),
                                  payload_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw),
                                  local_evidence=local_evidence))

    def self_state(self, actor, cause):
        a = self.actors[actor]
        a['seq'] += 1
        state = {k: copy.deepcopy(a[k]) for k in ('seq', 'mode', 'target', 'origin', 'destination',
                  'departure', 'arrival', 'changed_at', 'finish')}
        state['source'] = actor
        evidence = self.event('own_state', actor=actor, cause=cause, state=state)
        self.publish(dict(kind='self_state', source=actor, generated_at=self.now, state=state), [actor], evidence)

    def scene(self, tid, cause):
        task = self.tasks[tid]
        witnesses = sorted(task['present'])
        if not witnesses:
            raise AssertionError('No onsite observer')
        source = min(witnesses)
        task['version'] += 1
        scene = dict(task=tid, phase=task['phase'], workers=list(task['workers']),
                     witnesses=witnesses, version=task['version'], observed_at=self.now,
                     started_at=task['started_at'], finished_at=task['finished_at'])
        evidence = self.event('onsite_observation', actor=source, cause=cause, scene=scene,
                              witness_positions={i: self.network_pose(i, self.now) for i in witnesses})
        self.publish(dict(kind='task_scene', source=source, generated_at=self.now, scene=scene), witnesses, evidence)

    def flush(self):
        for delivery in self.service.pop_due(self.now):
            body = json.loads(delivery['payload'])
            i = delivery['recipient']
            record = {k: v for k, v in delivery.items() if k != 'payload'}
            record['payload_sha256'] = hashlib.sha256(delivery['payload']).hexdigest()
            changed = self.views[i].apply(body, self.now, 'network', delivery['message_id'])
            record['applied'] = changed
            self.deliveries.append(record)
            if changed and self.actors[i]['mode'] == 'idle':
                self.ready.add(i)

    def idle_timer(self, actor):
        a = self.actors[actor]
        a['timer'] += 1
        self.schedule(self.now+self.idle_retry, 'idle_timer', actor=actor, token=a['timer'])

    def depart(self, actor, action):
        a = self.actors[actor]
        if a['mode'] != 'idle':
            raise AssertionError('Non-idle actor cannot depart')
        target = action-1
        destination = (self.catalog['tasks'][target]['location'] if target >= 0
                       else self.catalog['agents'][actor]['depot'])
        distance = math.dist(a['position'], destination)
        if distance < 1e-12 and target < 0:
            self.idle_timer(actor)
            return
        if a['target'] >= 0:
            self.tasks[a['target']]['present'].discard(actor)
        departure, arrival = self.now, self.now+distance/self.catalog['agents'][actor]['velocity']
        route = dict(decision_time=self.now, departure=departure, arrival=arrival, origin=a['position'][:],
                     destination=list(destination), target=target, distance=distance)
        a['route'].append(route)
        a.update(mode='travel', target=target, origin=a['position'][:], destination=list(destination),
                 departure=departure, arrival=arrival, changed_at=self.now, finish=None,
                 distance=a['distance']+distance, timer=a['timer']+1)
        self.event('departure', actor=actor, **route)
        self.self_state(actor, 'accepted_local_action')
        self.schedule(arrival, 'arrival', actor=actor, seq=a['seq'])

    def decide(self, actor):
        a = self.actors[actor]
        if a['mode'] != 'idle':
            return
        view = self.views[actor]
        obs, branch = view.observation(self.now)
        action = self.choose(obs, actor) if branch == 'infer' else None
        if action is not None and bool(obs[2][0, action]):
            raise AssertionError('Masked action')
        self.decisions.append(dict(time=self.now, actor=actor, branch=branch, action=action,
                                  observation=[x.tolist() for x in obs], view_sha256=view.signature(),
                                  source_versions={i:s['seq'] for i,s in view.states.items()},
                                  task_versions={i:s['version'] for i,s in view.scenes.items()},
                                  evidence_count=len(view.evidence)))
        self.event('decision', actor=actor, branch=branch, action=action, view_sha256=view.signature())
        if action is None:
            self.idle_timer(actor)
        else:
            self.depart(actor, action)

    def arrive(self, actor):
        a = self.actors[actor]
        assert a['mode'] == 'travel' and a['arrival'] <= self.now+1e-9
        a['position'] = a['destination'][:]
        a.update(mode='idle' if a['target'] < 0 else 'waiting', changed_at=self.now)
        self.event('arrival', actor=actor, target=a['target'], position=a['position'])
        if a['target'] < 0:
            self.self_state(actor, 'own_arrival_depot')
            self.ready.add(actor)
            return
        tid, task = a['target'], self.tasks[a['target']]
        task['present'].add(actor)
        if task['phase'] != 'open':
            a['mode'] = 'idle'  # late visitor observes the site, not an en-route rejection
            self.self_state(actor, 'own_arrival_closed_task')
            self.scene(tid, 'arrival_discovery')
            self.ready.add(actor)
            return
        self.self_state(actor, 'own_arrival_waiting')
        self.schedule(self.now+self.task_wait, 'wait_timeout', actor=actor, arrival=a['arrival'])
        members = sorted(i for i in task['present'] if self.actors[i]['mode'] == 'waiting')
        import numpy as np
        ability = np.sum([self.catalog['agents'][i]['abilities'] for i in members], axis=0)
        if np.all(ability >= np.asarray(self.catalog['tasks'][tid]['requirements'])):
            task.update(phase='running', workers=members, started_at=self.now,
                        finished_at=self.now+self.catalog['tasks'][tid]['time'])
            for i in members:
                self.actors[i].update(mode='working', changed_at=self.now, finish=task['finished_at'])
                self.self_state(i, 'onsite_coalition_started')
            self.event('task_start', task=tid, workers=members, ability=ability,
                       requirements=self.catalog['tasks'][tid]['requirements'])
            self.scene(tid, 'physical_start')
            self.schedule(task['finished_at'], 'task_finish', task=tid)
        else:
            self.scene(tid, 'arrival_waiting_for_capability')

    def handle(self, kind, data):
        if kind == 'arrival':
            self.arrive(data['actor'])
        elif kind == 'task_finish':
            tid, task = data['task'], self.tasks[data['task']]
            assert task['phase'] == 'running'
            assert all(self.actors[i]['mode']=='working' and i in task['present'] for i in task['workers'])
            task['phase'] = 'done'
            self.event('task_finish', task=tid, workers=task['workers'])
            self.scene(tid, 'physical_finish')
            for i in task['workers']:
                self.actors[i].update(mode='idle', changed_at=self.now, finish=None)
                self.self_state(i, 'own_work_finished')
                self.ready.add(i)
        elif kind == 'idle_timer':
            i = data['actor']
            if self.actors[i]['mode']=='idle' and self.actors[i]['timer']==data['token']:
                self.event('local_retry_timer', actor=i)
                self.ready.add(i)
        elif kind == 'wait_timeout':
            i, a = data['actor'], self.actors[data['actor']]
            if a['mode']=='waiting' and a['arrival']==data['arrival']:
                a.update(mode='idle', changed_at=self.now)
                self.self_state(i, 'local_wait_timeout')
                self.event('local_wait_timeout', actor=i)
                self.ready.add(i)
        else:
            raise ValueError(kind)

    def success(self):
        return (all(t['phase']=='done' for t in self.tasks.values()) and
                all(a['mode']=='idle' and a['target']<0 for a in self.actors.values()))

    def run(self):
        while True:
            if self.events_processed+len(self.decisions) >= self.event_budget:
                self.status='event_budget_exhausted'; break
            if time.perf_counter()-self.started_wall >= self.wall_budget:
                self.status='wall_budget_exhausted'; break
            self.flush()
            if self.ready:
                actor=min(self.ready)
                self.ready.remove(actor)
                self.decide(actor)
                continue  # zero-delay bodies drain before the next decision microstep
            if self.success():
                self.status='success'; break
            next_time=min(self.heap[0][0] if self.heap else math.inf, self.service.next_event_time())
            if next_time > self.horizon or not math.isfinite(next_time):
                self.now=self.horizon; self.flush(); self.status='horizon_incomplete'; break
            if next_time < self.now-1e-9:
                raise AssertionError('Time went backwards')
            self.now=next_time
            # Physics at this time is processed before scheduling new local actions.
            while self.heap and self.heap[0][0] <= self.now+1e-10:
                _,_,kind,data=heapq.heappop(self.heap)
                self.handle(kind,data)
                self.events_processed += 1
            self.flush()
        return self.summary()

    def summary(self):
        completed=sum(t['phase']=='done' for t in self.tasks.values())
        returned=sum(a['mode']=='idle' and a['target']<0 for a in self.actors.values())
        success=self.status=='success'
        return dict(status=self.status, completed=completed, tasks=len(self.tasks),
                    completion_fraction=completed/len(self.tasks), returned=returned,
                    success=success, end_time=self.now,
                    makespan_return=self.now if success else None,
                    capped_makespan=self.now if success else self.horizon,
                    last_task_finish=max([t['finished_at'] for t in self.tasks.values() if t['phase']=='done'],default=None),
                    actions=sum(len(a['route']) for a in self.actors.values()), decisions=len(self.decisions),
                    processed_physical_events=self.events_processed,
                    task_phases={phase:sum(t['phase']==phase for t in self.tasks.values()) for phase in ('open','running','done')},
                    actor_modes={mode:sum(a['mode']==mode for a in self.actors.values()) for mode in ('idle','travel','waiting','working')},
                    travel_distance=sum(a['distance'] for a in self.actors.values()),
                    network=self.service.stats(self.now))


def make_catalog(env):
    return dict(tasks={i:dict(requirements=t['requirements'].tolist(), location=t['location'].tolist(),
                             time=t['time']) for i,t in env.task_dic.items()},
                agents={i:dict(abilities=a['abilities'].tolist(), depot=a['depot'].tolist(),
                              velocity=a['velocity'], species=a['species']) for i,a in env.agent_dic.items()})


def child(args):
    os.environ['MPLBACKEND']='Agg'
    sys.path.insert(0,str(ASSETS))
    import numpy as np
    import torch
    from env.task_env import TaskEnv
    from attention import AttentionNet
    from parameters import TrainParams
    # In a run snapshot this sibling is a frozen copy, not a changing repo file.
    from message_service import MessageService
    torch.set_num_threads(1)
    torch.manual_seed(args.seed); np.random.seed(args.seed); random.seed(args.seed)
    out=Path(args.output)
    world=None
    result=dict(seed=args.seed,tasks=args.tasks,mode=args.mode,delay=args.delay,
                rate=args.rate,capacity=args.capacity,status='error')
    start=time.perf_counter()
    try:
        env=TaskEnv(per_species_range=(3,3),species_range=(3,3),tasks_range=(args.tasks,args.tasks),
                    traits_dim=5,decision_dim=30,seed=args.seed)
        env.init_state()
        initial=plain(dict(tasks=env.task_dic,agents=env.agent_dic,depots=env.depot_dic,species=env.species_dict))
        write_json(out/'initial.json',initial)
        result['initial_sha256']=hashlib.sha256(json.dumps(initial,sort_keys=True).encode()).hexdigest()
        catalog=make_catalog(env)
        write_json(out/'catalog.json',catalog)
        result['catalog_sha256']=hashlib.sha256(encode(catalog)).hexdigest()
        net=AttentionNet(TrainParams.AGENT_INPUT_DIM,TrainParams.TASK_INPUT_DIM,TrainParams.EMBEDDING_DIM)
        net.load_state_dict(load_checkpoint(torch),strict=True); net.eval()
        def choose(obs,actor):
            with torch.no_grad():
                values=[torch.tensor(a,dtype=torch.float) for a in obs]
                probs,_=net(*values,torch.LongTensor([actor]).reshape(1,1,1))
                return int(torch.argmax(probs,dim=1).item())
        service=MessageService(mode=args.mode,delay=args.delay,rate_bytes_per_time=args.rate,
                               capacity_bytes=args.capacity,overhead_bytes=0)
        world=CausalWorld(catalog,service,choose,horizon=args.horizon,event_budget=args.event_budget,
                          wall_budget=50.,idle_retry=args.idle_retry)
        result.update(world.run())
    except Exception:
        result['error']=traceback.format_exc()
        if world is not None:
            world.status='error'; result.update(world.summary())
    finally:
        result['wall_seconds']=time.perf_counter()-start
        result['executor_sha256']=digest(__file__)
        if world is not None:
            write_json(out/'events.json',world.trace)
            write_json(out/'decisions.json',world.decisions)
            write_json(out/'messages.json',world.messages)
            write_json(out/'deliveries.json',world.deliveries)
            write_json(out/'service_ledger.json',world.service.ledger)
            final=dict(actors=world.actors,tasks={i:{**t,'present':sorted(t['present'])} for i,t in world.tasks.items()})
            write_json(out/'final.json',final)
            write_json(out/'view_evidence.json',{i:v.evidence for i,v in world.views.items()})
        write_json(out/'result.json',result)
    return 0 if result['status'] not in ('error','wall_budget_exhausted','event_budget_exhausted') else 1


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--output',required=True)
    p.add_argument('--child',action='store_true')
    p.add_argument('--seed',type=int,default=0); p.add_argument('--tasks',type=int,default=15)
    p.add_argument('--seeds',default='0'); p.add_argument('--task-counts',default='15')
    p.add_argument('--conditions',default='instant')
    p.add_argument('--mode',default='instant'); p.add_argument('--delay',type=float,default=0.)
    p.add_argument('--rate',type=float,default=1024.); p.add_argument('--capacity',type=int,default=65536)
    p.add_argument('--horizon',type=float,default=200.); p.add_argument('--event-budget',type=int,default=10000)
    p.add_argument('--idle-retry',type=float,default=1.)
    args=p.parse_args()
    if args.child:
        return child(args)
    out=Path(args.output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E1-004'):
        p.error('Output must be inside simulation/outputs/E1-004')
    out.mkdir(parents=True,exist_ok=False)
    assets=asset_manifest()
    configs=[]
    for task in map(int,args.task_counts.split(',')):
        for seed in map(int,args.seeds.split(',')):
            for condition in args.conditions.split(','):
                mode='instant' if condition=='instant' else 'fifo' if condition.startswith('fifo') else 'fixed_delay'
                delay=float(condition[5:]) if condition.startswith('delay') else 0.
                rate=float(condition[4:]) if condition.startswith('fifo') else args.rate
                configs.append(dict(tasks=task,seed=seed,condition=condition,mode=mode,delay=delay,rate=rate))
    if len(configs)>60:
        p.error('Per-invocation case budget exceeds 60')
    snap=out/'source'; snap.mkdir()
    for filename in ('heteromrta_causal.py','message_service.py','test_heteromrta_causal.py'):
        (snap/filename).write_bytes((ROOT/'simulation'/filename).read_bytes())
    manifest=dict(command=sys.argv,root=str(ROOT),python=sys.executable,python_version=platform.python_version(),
                  platform=platform.platform(),author_commit=COMMIT,assets=assets,
                  dependencies={k:importlib.metadata.version(k) for k in ('numpy','torch','matplotlib')},
                  source_hashes={p.name:digest(p) for p in snap.iterdir()},
                  inherited_eval_sha256=digest(ROOT/'simulation/heteromrta_eval.py'),
                  configs=configs,horizon=args.horizon,event_budget=args.event_budget,
                  wall_timeout_seconds=60,idle_retry=args.idle_retry,task_wait=200.,
                  scope='causal adaptation; shared application service; no MAC/PHY or added task data payload')
    write_json(out/'manifest.json',manifest)
    results=[]
    for cfg in configs:
        name=f"tasks{cfg['tasks']}_seed{cfg['seed']}_{cfg['condition']}"
        case=out/name; case.mkdir()
        cmd=[sys.executable,str(snap/'heteromrta_causal.py'),'--child','--output',str(case),
             '--tasks',str(cfg['tasks']),'--seed',str(cfg['seed']),'--mode',cfg['mode'],
             '--delay',str(cfg['delay']),'--rate',str(cfg['rate']),'--capacity',str(args.capacity),
             '--horizon',str(args.horizon),'--event-budget',str(args.event_budget),'--idle-retry',str(args.idle_retry)]
        env=dict(os.environ,ANN_REPO_ROOT=str(ROOT),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
        with (case/'stdout.txt').open('w',encoding='utf-8') as log:
            try:
                proc=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,env=env,timeout=60)
                code=proc.returncode
            except subprocess.TimeoutExpired:
                code=-999
        result=json.loads((case/'result.json').read_text()) if (case/'result.json').exists() else dict(status='wall_timeout_or_missing_result',completed=None,completion_fraction=None,makespan_return=None)
        result.update(**cfg,case=name,process_exit_code=code)
        results.append(result)
        write_json(out/'summary.json',dict(cases=results,planned=len(configs)))
        print(f"{name}: {result['status']} completed={result.get('completed')} makespan={result.get('makespan_return')}",flush=True)
    return 0 if all(r['process_exit_code']==0 for r in results) else 1


if __name__=='__main__':
    raise SystemExit(main())
