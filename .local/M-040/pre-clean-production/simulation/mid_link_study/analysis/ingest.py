"""Read E1-019 saved output once, normalize explicit fields, export D data."""
import argparse,datetime,hashlib,json,math,sys,time
from pathlib import Path
try:
    from . import analyze
    from .truth import Truth
except ImportError:
    import analyze
    from truth import Truth

ROOT=Path(__file__).resolve().parents[3]


def read(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical_hash(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,ensure_ascii=False,allow_nan=False)


def load_run(folder,batch):
    raw_context=read(folder/'context.json');raw_events=[json.loads(line) for line in (folder/'events.jsonl').read_bytes().splitlines()]
    assert raw_context['evidence_kind']=='software_simulation' and raw_context['source_planned']==240
    assert raw_context['scenario_sha256']==sha(ROOT/raw_context['scenario_file'])
    assert all(e['run_id']==raw_context['run_id'] and e['evidence_kind']=='software_simulation' for e in raw_events)
    truth=Truth(raw_context['scenario_id']);events=[];tables={};causality=[];channel_draws={};observations={};published={};receives=set()
    planners=read(folder/'planner_inputs.json')
    virtual={f'02:00:00:00:00:{i+1:02x}':n for i,n in enumerate('ABCDE')}
    source_plan=[]
    for line,event in enumerate(raw_events,1):
        e=dict(event,source=dict(path=str(folder/'events.jsonl'),line=line));kind=e['event'];t=e['t_s']
        if kind=='generate':
            assert e['seq'] in range(1,121) and e['src'] in 'AB' and e['dst'] in 'AB' and e['src']!=e['dst']
            e.update(direction=0 if e['src']=='A' else 1,slot=e['seq']-1)
            assert e['packet_id']==f"{e['src']}>{e['dst']}:{e['slot']:03}" and t==e['slot']/2
            source_plan.append({k:e[k] for k in ['src','dst','slot','t_s','payload_bytes','payload_tag']})
        if kind=='rx':e['event']='relay_rx'
        elif kind=='relay':e['event']='forward_decision'
        elif kind=='link_result':
            if e['kind']!='data' or not e['success']:continue
            e['event']='forward';e['simulated_link_success']=True
        elif kind=='observed_state':
            e['event']='observation'
            if e['observed_at_s']>t or e['observed_at_s']!=max(0,t-.5) or e['observation']!=__import__('simulation.mid_link_study.scenarios.scenarios',fromlist=['state_at']).state_at(truth.scenario,e['observed_at_s']):causality.append('observation_not_declared_delayed_truth')
            observations[t]=e['observation']
        elif kind=='detection':e['event']='detected'
        elif kind=='config_publish':e['version']=e['update_id'];published[e['update_id']]=e['t_s']
        elif kind=='control_tx':e['bytes']=e['control_bytes']
        elif kind=='control_rx':receives.add((e['node'],e['update_id'],t))
        if kind in ('config_publish','config_install'):
            version=e.get('version',e['update_id']);table=e.pop('table');tables[str(version)]=table;e['table_ref']=version
            if kind=='config_install' and not e.get('initial'):
                if e['node'] not in truth.snapshot(min(60,t))['active_nodes'] or t<published.get(version,float('inf')):
                    causality.append('install_before_publish_or_inactive')
                if e['node']!='A' and (e['node'],version,t) not in receives:causality.append('non_source_install_without_control_rx')
        if kind in ('tx_attempt','control_tx'):
            key=json.loads(e['random_key']);expected=[raw_context['seed'],raw_context['scenario_id'],'channel',int(t*1000),e['node'],e['next_hop'],e.get('packet_id','control:'+str(e.get('update_id')))]
            if key!=expected:causality.append('channel_index_not_declared_common_index')
            draw=int.from_bytes(hashlib.sha256(e['random_key'].encode()).digest()[:8],'big')/2**64
            if not math.isclose(draw,e['draw'],abs_tol=1e-15):causality.append('channel_draw_mismatch')
            channel_draws[e['random_key']]=e['draw']
        if kind=='control_rx':
            edge=next(x for x in truth.snapshot(min(60,t))['edges'] if (x['src'],x['dst'])==(e['previous_hop'],e['node']))
            if edge['pdr']<=0 or edge['capacity_payload_bps']<=0:causality.append('control_received_across_zero_edge')
        if kind=='solve_end':
            observation_time=round(t-e['simulated_compute_delay_s'],9);obs=observations.get(observation_time)
            entry=planners[e['input_key']]
            if canonical_hash(entry['problem'])!=e['input_key'] or entry['result']['status']!=e['status']:causality.append('solver_input_key_or_status_mismatch')
            if obs is None or e['observed_at_s']!=obs['time_s']:causality.append('solve_not_tied_to_previous_observation')
            else:
                problem=entry['problem'];nodes=[virtual[n] for n in problem['nodes']];edges={(x['src'],x['dst']):x for x in obs['edges']}
                if set(nodes)!=set(obs['active_nodes']):causality.append('planner_members_not_delayed_observation')
                for i,a in enumerate(nodes):
                    for j,b in enumerate(nodes):
                        edge=edges.get((a,b),{});expected_mean=edge.get('expected_payload_bps',0)
                        if not math.isclose(problem['mean'][i][j],expected_mean,abs_tol=1e-7):causality.append('planner_mean_not_delayed_observation')
                if any(f['rate']!=512 or f['qos']!=.9 for f in problem['flows']):causality.append('planner_workload_differs')
        events.append(e)
    assert canonical_hash(tables['0'])==raw_context['initial_table_sha256']
    source_plan.sort(key=lambda p:(p['src'],p['slot']))
    model=raw_context['model']
    context=dict(raw_context,raw_context_source=dict(path=str(folder/'context.json'),sha256=sha(folder/'context.json')),
        interval_s=.5,payload_bytes=32,capture_complete=batch['status']=='complete',flows=raw_context['traffic']['flows'],evaluation=truth.evaluation(),
        control_bytes_layer='MID serialized configuration frame bytes per directed-edge service attempt; no PHY overhead',
        shared_inputs=dict(scenario_sha256=raw_context['scenario_sha256'],source_plan_sha256=canonical_hash(source_plan),initial_table_sha256=raw_context['initial_table_sha256'],
            channel_draw_index=model['channel'],delay_model=canonical_hash(model),engine_sha256=batch['engine_sha256'],planner_sha256=batch['planner_sha256']),
        interpretation='sim_boot is a virtual identifier/seed, not real device boot')
    result=analyze.analyze(context,events,truth)
    result.update(tables=tables,topology_truth=truth.timeline(),causality_issues=sorted(set(causality)),channel_draws=channel_draws,
        source_files={name:dict(path=str(folder/name),sha256=sha(folder/name)) for name in ['context.json','events.jsonl','summary.json','planner_inputs.json']},
        adapter_mapping=dict(generate_slot='seq-1, source event independently checked against packet_id and t_s',rx='relay_rx, successful simulated arrival',relay='forward_decision',link_result_success='forward (link service success, not destination delivery)',control_tx_bytes='control_bytes serialized MID frame size',evidence='original line retained in source',capture='completed producer batch manifest, no device capture'))
    if causality:result['metrics_valid']=False;result['issues']+=['causality_audit_issue']
    summary=read(folder/'summary.json')
    assert sum(d['delivered_observed'] for d in result['directions'])==summary['destination_unique']
    if 'destination_unique_before60' in summary:assert sum(d['delivered_in_window'] for d in result['directions'])==summary['destination_unique_before60']
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--index',required=True,action='append');parser.add_argument('--reuse',action='append',default=[]);parser.add_argument('--output',required=True);args=parser.parse_args()
    out=Path(args.output).resolve();assert out.is_relative_to(ROOT/'simulation/outputs/E2-019') and not out.exists();out.mkdir(parents=True);start=time.monotonic();runs=[];sources=[];new_count=0
    for name in args.reuse:
        index=read(name)
        for ref in index['runs']:
            result=read(ref['path']);runs.append(result);sources.append(ref)
    for name in args.index:
        index_path=Path(name).resolve();index=read(index_path);manifest=read(index_path.parent/'RUN_MANIFEST.json')
        assert index['status']=='complete' and manifest['exit_code']==0
        for run in index['runs']:
            folder=index_path.parent/run['run_id'];result=load_run(folder,index)
            if any((r['scenario_id'],r['seed'],r['arm'])==(result['scenario_id'],result['seed'],result['arm']) for r in runs):raise ValueError('duplicate run; reuse first pair instead of rerun')
            path=out/(result['run_id']+'.json');write(path,result);runs.append(result);sources.append(dict(path=str(path),sha256=sha(path),run_id=result['run_id'],scenario_id=result['scenario_id'],seed=result['seed'],arm=result['arm']))
            new_count+=1
    pairs=analyze.paired(runs)
    coupling=[]
    for pair in pairs['pairs']:
        chosen=[r for r in runs if (r['scenario_id'],r['seed'])==(pair['scenario_id'],pair['seed'])]
        if len(chosen)==2:
            a,b=[r['channel_draws'] for r in chosen];common=set(a)&set(b);matches=all(a[k]==b[k] for k in common)
            coupling.append(dict(scenario_id=pair['scenario_id'],seed=pair['seed'],overlapping_channel_query_keys=len(common),all_shared_draws_equal=matches))
            assert matches
    write(out/'pairs.json',pairs);write(out/'coupling-audit.json',coupling)
    summary=[dict(run_id=r['run_id'],scenario_id=r['scenario_id'],seed=r['seed'],arm=r['arm'],metrics_valid=r['metrics_valid'],issues=r['issues'],causality_issues=r['causality_issues'],generated=sum(d['generated_observed'] for d in r['directions']),received=sum(d['delivered_observed'] for d in r['directions']),received_before60=sum(d['delivered_in_window'] for d in r['directions']),control=r['control'],directions=r['directions']) for r in runs]
    write(out/'summary.json',summary)
    write(out/'DATASET.json',dict(schema='mid.link.dataset.v1',evidence_kind='software_simulation',runs=sources,pairs=str(out/'pairs.json'),summary=str(out/'summary.json'),complete_batch=len(runs)==30,expected_runs=30,source_planned=len(runs)*240,positions=Truth('gradual_link').scenario['positions'],limitations=['Assumed links and ideal centralized delayed sensing, no RF measurements.','Use packets.receive_events/actual_received_path for observed simulated arrivals, not intended weights.','Global control counters repeat across directional seconds; do not double-sum.']))
    m=read(ROOT/'coordination/templates/RUN_MANIFEST.json');m.update(template_only=False,task_id='E2-019',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),python_executable=sys.executable,command=sys.argv,output_directory=str(out),status='analyzed' if all(r['metrics_valid'] for r in runs) else 'issues_retained',exit_code=0,budget=dict(new_raw_analyses=new_count,reused_runs=len(runs)-new_count,hardware_operations=0,analysis_wall_s=time.monotonic()-start),dirty_files_sha256={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(analyze.__file__),Path(__file__).with_name('metrics.py'),Path(__file__).with_name('truth.py')]},data_and_weights_sha256={str(Path(x).resolve()):sha(Path(x)) for x in args.index},limitations=['No engine/solver imported or run; only completed saved producer batches read.','Metrics and causal audits retain source lines; no significance inference from five seeds.']);write(out/'RUN_MANIFEST.json',m)
    print(json.dumps(dict(runs=len(runs),summary=[{k:r[k] for k in ['run_id','generated','received','received_before60','metrics_valid','causality_issues']} for r in summary])))


if __name__=='__main__':main()
