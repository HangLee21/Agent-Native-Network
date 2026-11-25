"""Synthetic link environment and evaluation-only reachability. No device access.

All times are simulated seconds; override intervals are [start,end).
"""
import argparse
from collections import deque
import copy
import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IDS = ('gradual_link', 'relay_exit', 'partition_restore')


def definitions():
    common = dict(schema='mid.link_scenario.v1', version=1,
        evidence_kind='synthetic_simulation', nodes=list('ABCDE'), duration_s=60,
        seeds=[11, 23, 37, 53, 71],
        traffic=dict(flows=[dict(src='A', dst='B'), dict(src='B', dst='A')],
            packets_per_direction_per_s=2, payload_bytes=32,
            first_generation_s=0, generation_end_exclusive_s=60, planned_per_arm=240),
        units=dict(time='simulated_seconds', capacity_payload_bps='application_payload_bits_per_simulated_second',
                   pdr='conditional_success_probability_per_link_attempt'),
        assumptions=[
            'All coefficients are synthetic assumptions, not RF measurements.',
            'Capacity and success probability are separate quantities; unlisted directed edges have both zero.',
            'Listed edges default to PDR 1; segments override only their half-open interval.',
            'Capacity excludes protocol overhead. Engine must declare queue, contention and retry treatment.',
            'Coordinates are schematic; they do not imply a physical propagation model.',
            'Reachability witnesses are evaluation-only truth, never privileged policy inputs.',
            'Observation, detection, computation and configuration delays belong to the engine contract.'],
        positions={'A':[0,0], 'C':[1,1], 'E':[1,-1], 'D':[2,0], 'B':[3,0]},
        initial_reference_path=list('ACDB'), alternative_reference_path=list('AEDB'),
        edges=[], node_intervals=[], events=[])
    for a,b,capacity in [('A','C',8192), ('C','D',8192), ('D','B',8192), ('A','E',4096), ('E','D',4096)]:
        for src,dst in [(a,b),(b,a)]:
            common['edges'].append(dict(src=src,dst=dst,capacity_payload_bps=capacity,pdr=1.0,segments=[]))
    result=[]
    for sid in IDS:
        s=copy.deepcopy(common);s['id']=sid
        if sid=='gradual_link':
            s['description']='AC/CA gradually fail, stay failed, then recover; alternative AE/ED stays available.'
            s['events']=[dict(time_s=t,kind=k) for t,k in [(20,'degradation_begins'),(35,'AC_CA_zero_success'),(45,'recovery_begins'),(50,'AC_CA_restored')]]
            for e in s['edges']:
                if {e['src'],e['dst']}=={'A','C'}:
                    e['segments']=[dict(start_s=20,end_s=35,pdr_start=1.0,pdr_end=0.0),
                        dict(start_s=35,end_s=45,pdr_start=0.0,pdr_end=0.0),
                        dict(start_s=45,end_s=50,pdr_start=0.0,pdr_end=1.0)]
        elif sid=='relay_exit':
            s['description']='C offline during [20,40); AE/ED/DB alternative stays available.'
            s['node_intervals']=[dict(node='C',start_s=20,end_s=40,online=False)]
            s['events']=[dict(time_s=20,kind='C_offline'),dict(time_s=40,kind='C_online')]
            for e in s['edges']:
                if 'C' in (e['src'],e['dst']):
                    e['segments']=[dict(start_s=20,end_s=40,pdr_start=0.0,pdr_end=0.0,capacity_payload_bps=0)]
        else:
            s['description']='DB/BD absent during [20,40), isolating B; both endpoint directions have no path.'
            s['events']=[dict(time_s=20,kind='partition_begins'),dict(time_s=40,kind='partition_ends')]
            for e in s['edges']:
                if {e['src'],e['dst']}=={'D','B'}:
                    e['segments']=[dict(start_s=20,end_s=40,pdr_start=0.0,pdr_end=0.0,capacity_payload_bps=0)]
        validate(s);result.append(s)
    return result


def validate(s):
    assert s['schema']=='mid.link_scenario.v1' and s['nodes']==list('ABCDE') and s['duration_s']==60
    seen=set()
    for e in s['edges']:
        key=e['src'],e['dst']
        assert key not in seen and key[0]!=key[1] and all(x in s['nodes'] for x in key)
        seen.add(key)
        assert math.isfinite(e['capacity_payload_bps']) and e['capacity_payload_bps']>=0
        assert math.isfinite(e['pdr']) and 0<=e['pdr']<=1
        until=0
        for x in e['segments']:
            assert until<=x['start_s']<x['end_s']<=60
            until=x['end_s']
            assert all(math.isfinite(x[k]) and 0<=x[k]<=1 for k in ['pdr_start','pdr_end'])
            capacity=x.get('capacity_payload_bps',e['capacity_payload_bps'])
            assert math.isfinite(capacity) and capacity>=0
    for x in s['node_intervals']:
        assert x['node'] in s['nodes'] and type(x['online']) is bool and 0<=x['start_s']<x['end_s']<=60


def load(scenario_id):
    if scenario_id not in IDS:raise ValueError('unknown fixed scenario')
    return json.loads((HERE/(scenario_id+'.json')).read_text(encoding='utf-8'))


def state_at(s,time_s):
    """Environment truth. Policies must receive only their causally delayed view."""
    if not math.isfinite(time_s) or not 0<=time_s<=s['duration_s']:raise ValueError('time outside scenario')
    active=set(s['nodes'])
    for x in s['node_intervals']:
        if x['start_s']<=time_s<x['end_s'] and not x['online']:active.discard(x['node'])
    edges=[]
    for e in s['edges']:
        pdr,capacity=e['pdr'],e['capacity_payload_bps']
        for x in e['segments']:
            if x['start_s']<=time_s<x['end_s']:
                f=(time_s-x['start_s'])/(x['end_s']-x['start_s'])
                pdr=x['pdr_start']+f*(x['pdr_end']-x['pdr_start'])
                capacity=x.get('capacity_payload_bps',capacity);break
        if e['src'] not in active or e['dst'] not in active:pdr,capacity=0.0,0.0
        edges.append(dict(src=e['src'],dst=e['dst'],pdr=pdr,capacity_payload_bps=capacity,expected_payload_bps=capacity*pdr))
    return dict(time_s=time_s,active_nodes=sorted(active),edges=edges)


def path_witness(state,src,dst,avoid_edges=()):
    graph={n:[] for n in state['active_nodes']}
    for e in state['edges']:
        if e['pdr']>0 and e['capacity_payload_bps']>0 and (e['src'],e['dst']) not in avoid_edges:
            graph[e['src']].append(e['dst'])
    if src not in graph or dst not in graph:return None
    queue,seen=deque([[src]]),{src}
    while queue:
        path=queue.popleft()
        if path[-1]==dst:return path
        for n in sorted(graph[path[-1]]):
            if n not in seen:seen.add(n);queue.append(path+[n])
    return None


def truth_at(s,t):
    state=state_at(s,t);flows=[]
    for f in s['traffic']['flows']:
        p=path_witness(state,f['src'],f['dst'])
        alt=path_witness(state,f['src'],f['dst'],(('A','C'),('C','A')))
        flows.append(dict(f,reachable=p is not None,path=p,alternative_without_AC=alt))
    return dict(state,flows=flows)


def truth_document(s):
    knots=sorted({0,60}|{e['time_s'] for e in s['events']})
    intervals=[dict(start_s=a,end_s=b,witness_time_s=(a+b)/2,flows=truth_at(s,(a+b)/2)['flows']) for a,b in zip(knots,knots[1:])]
    probes=sorted(set(knots+[max(0,t-.000001) for t in knots]+[min(60,t+.000001) for t in knots]))
    return dict(schema='mid.link_truth.v1',scenario_id=s['id'],
        scope='Evaluation-only positive-probability path existence, not delivery probability, capacity feasibility or oracle policy.',
        intervals=intervals,critical_samples=[truth_at(s,t) for t in probes],
        source_slot_samples=[truth_at(s,slot/2) for slot in range(120)])


def save_new(path,data):
    with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,allow_nan=False);f.write('\n')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--write-inputs',action='store_true');args=p.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-008'):raise ValueError('output outside H-008')
    out.mkdir(parents=True,exist_ok=False);started=datetime.datetime.now(datetime.timezone.utc).isoformat();sources=[];checks=[]
    for s in definitions():
        path=HERE/(s['id']+'.json')
        if args.write_inputs:save_new(path,s)
        else:assert load(s['id'])==s
        truth=truth_document(s);save_new(out/(s['id']+'-truth.json'),truth)
        for sample in truth['source_slot_samples']:
            wanted=not(s['id']=='partition_restore' and 20<=sample['time_s']<40)
            assert all(f['reachable']==wanted for f in sample['flows'])
        for t in [19.999999,20,25,35,39.999999,40,45,50]:
            state=state_at(s,t)
            if s['id']!='partition_restore':
                assert all(path_witness(state,f['src'],f['dst'],(('A','C'),('C','A'))) for f in s['traffic']['flows'])
            if s['id']=='relay_exit' and 20<=t<40:
                assert 'C' not in state['active_nodes'] and all(e['pdr']==e['capacity_payload_bps']==0 for e in state['edges'] if 'C' in (e['src'],e['dst']))
        if s['id']=='gradual_link':
            edge=next(e for e in state_at(s,27.5)['edges'] if (e['src'],e['dst'])==('A','C'))
            assert edge['pdr']==.5 and edge['capacity_payload_bps']==8192
        checks.append(dict(scenario=s['id'],source_slots=120,endpoint_pairs_per_slot=2,passed=True))
        sources.append(dict(scenario=s['id'],path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),truth_path=str((out/(s['id']+'-truth.json')).relative_to(ROOT))))
    result=dict(schema='mid.link_scenario_checks.v1',passed=True,checks=checks,sources=sources,
        serial_ports_opened=0,RF_operations=0,solver_calls=0,planned_runs=30,planned_source_packets=7200,
        note='Scenario construction and reachability only; packet simulation belongs to E1-019.')
    save_new(out/'result.json',result)
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    tracked=[Path(__file__).resolve()]+[ROOT/x['path'] for x in sources]
    manifest.update(template_only=False,task_id='H-008',run_id=out.name,started_at=started,
        finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirty_files_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in tracked},
        command=sys.argv,python_executable=sys.executable,dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
        seeds=[11,23,37,53,71],budget={'cpu_jobs':1,'wall_seconds':30},output_directory=str(out),exit_code=0,
        status='scenario_truth_verified',limitations=['Synthetic assumed links only, not RF/PHY/solver/packet validation.',
        'Reachability means positive capacity and positive success probability, not QoS feasibility.'])
    save_new(out/'RUN_MANIFEST.json',manifest);print(json.dumps(result))


if __name__=='__main__':main()
