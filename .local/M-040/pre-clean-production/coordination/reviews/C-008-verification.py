"""Read-only independent audit of saved C-008 evidence. No research imports/runs.

Imports only the previous independent audit's pure cache/service calculations.
Writes solely C-008-verification.json. In-progress runs are reported separately.
"""
import collections
import copy
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HASHES = {}


def raw(path):
    path = Path(path)
    data = path.read_bytes()
    HASHES[str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(data).hexdigest()
    return data


def load(path):
    path = Path(path)
    data = raw(path)
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def sha(path):
    return hashlib.sha256(raw(path)).hexdigest()


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


spec = importlib.util.spec_from_file_location('independent_c006', ROOT/'coordination/reviews/C-006-verification.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def keyed(seed, actor, kind, count):
    key = json.dumps([seed, actor, kind, count], separators=(',', ':')).encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], 'big')/2**64


def check_scale():
    base = ROOT/'simulation/outputs/E2-006/20261026-01'
    manifest, index = load(base/'manifest.json'), load(base/'catalog_index.json')
    for name, expected in manifest['source_hashes'].items():
        assert sha(base/'source'/name) == expected
        assert sha(ROOT/'simulation'/name) == expected
    masters = {}
    for r in manifest['masters']:
        initial, catalog = load(r['initial_path']), load(r['catalog_path'])
        assert sha(r['initial_path']) == r['initial_sha256']
        assert sha(r['catalog_path']) == r['catalog_sha256']
        expected = dict(tasks={i:{k:t[k] for k in ('requirements','location','time')} for i,t in initial['tasks'].items()},
                        agents={i:{k:a[k] for k in ('abilities','depot','velocity','species')} for i,a in initial['agents'].items()})
        assert catalog == expected
        assert len(catalog['tasks']) == 60 and len(catalog['agents']) == 9
        masters[r['seed']] = catalog
    rows=[]
    assert {(r['seed'],r['agents'],r['tasks']) for r in index['cases']} == {
        (s,n,t) for s in (5,6) for n,t in ((9,15),(18,15),(36,15),(18,30),(36,60))}
    for r in index['cases']:
        c, probe = load(r['catalog_path']), load(r['probe_path'])
        m = masters[r['seed']]
        assert sha(r['catalog_path']) == r['catalog_sha256']
        assert hashlib.sha256(encode(c)).hexdigest() == r['canonical_sha256']
        assert c['tasks'] == {str(i):m['tasks'][str(i)] for i in range(r['tasks'])}
        assert c['agents'] == {str(i):m['agents'][str(i%9)] for i in range(r['agents'])}
        assert r['probe_process_exit_code'] == 0 and r['probe_status'] == probe['status'] == 'passed'
        assert probe['catalog_sha256'] == r['catalog_sha256']
        assert [a['actor'] for a in probe['actors']] == [0,r['agents']-1]
        for a in probe['actors']:
            assert a['observation_shapes'] == [[1,r['tasks']+1,15],[1,r['agents'],11],[1,r['tasks']+1]]
            assert a['output_shape'] == [1,r['tasks']+1] and a['action_is_legal']
        rows.append(dict(case=r['case_id'], agents=r['agents'], tasks=r['tasks'], checks='pass'))
    return dict(cases=rows, configurations=10, single_step_forwards=20, full_episodes=0)


def check_case(base, row, manifest):
    case=base/row['case_id']
    result, config, catalog = load(case/'result.json'), load(case/'config.json'), load(case/'catalog.json')
    events, decisions = load(case/'events.json'), load(case/'decisions.json')
    messages, deliveries = load(case/'messages.json'), load(case/'deliveries.json')
    evidence, final = load(case/'view_evidence.json'), load(case/'final.json')
    info, ledger = load(case/'information_ledger.json'), load(case/'service_ledger.json')
    assert result['executor_sha256'] == manifest['source_hashes']['heteromrta_demand_execution.py']
    assert all(row[k] == v for k,v in result.items())
    assert sha(config['catalog_path']) == config['source_catalog_sha256']
    assert catalog == load(config['catalog_path'])
    assert len(info) == result['information_records']
    assert dict(collections.Counter(r['kind'] for r in info)) == result['information_record_counts']
    by_id={m['message_id']:m for m in messages}
    by_local={m['local_evidence']:m for m in messages}
    bodies={mid:json.loads(m['payload_utf8']) for mid,m in by_id.items()}
    delivered={(d['recipient'],d['message_id']):d for d in deliveries}
    assert len(by_id)==len(messages) and len(delivered)==len(deliveries)
    for m in messages:
        body=bodies[m['message_id']]; e=events[m['local_evidence']]
        assert body['generated_at']==m['generated_at']==e['time']
        assert body['source']==m['source']==e['actor']
        f='state' if body['kind']=='self_state' else 'scene'
        assert body[f]==e[f]
        assert m['recipients']==[int(i) for i in catalog['agents'] if int(i)!=m['source']]
    states,scenes,origins,scene_origins,consumed={},{},{},{},{}
    for actor in catalog['agents']:
        states[actor]={i:dict(source=int(i),seq=0,target=-1,mode='idle',origin=a['depot'],destination=a['depot'],departure=0.,arrival=0.,changed_at=0.,finish=None) for i,a in catalog['agents'].items()}
        scenes[actor],origins[actor],scene_origins[actor],consumed[actor]={},{},{},0
    facts={}; consultations={}; intents={}; action_results={}
    counts=collections.Counter(); reference_counts=collections.Counter()
    timer_counts=collections.Counter(); gates={int(i):0. for i in catalog['agents']}
    decision_count=0
    for ordinal,e in enumerate(info):
        assert e['ordinal']==ordinal and e['id']==f'i{ordinal:09d}'
        kind=e['kind']; actor=str(e.get('actor'))
        if kind=='local_timer_scheduled' and config['recovery']:
            ek=e['event_kind']; i=e['data']['actor']
            if ek in ('startup_ready','wait_timeout','idle_timer'):
                key='startup' if ek=='startup_ready' else ek
                jitter=keyed(config['seed'],i,key,timer_counts[(i,key)])
                timer_counts[(i,key)]+=1
                expected=e['time'] + (jitter if ek=='startup_ready' else 20.+5.*jitter if ek=='wait_timeout' else 1.+jitter)
                assert math.isclose(e['due_at'],expected,abs_tol=1e-9)
                if ek in ('startup_ready','idle_timer'):
                    gates[i]=e['due_at']
        elif kind=='information_acquired':
            counts[e['origin']]+=1
            facts[e['id']]=e
            if e['origin']=='initial':
                assert e['time']==0 and e['protocol_cost_bytes']==0
                assert e['catalog_sha256']==hashlib.sha256(encode(catalog)).hexdigest()
                origins[actor]={i:e['id'] for i in catalog['agents']}
                continue
            idx=consumed[actor]
            record=evidence[actor][idx]
            assert e['evidence_prefix']==idx+1
            assert record['evidence_id']==e['evidence_id'] and record['at']==e['time']
            assert record['applied']==e['applied']
            m=by_id[e['evidence_id']] if e['origin']=='network' else by_local[e['evidence_id']]
            body=bodies[m['message_id']]
            assert hashlib.sha256(encode(body)).hexdigest()==e['payload_sha256']
            assert body['generated_at']<=e['time']
            if e['origin']=='network':
                assert delivered[(int(actor),m['message_id'])]['delivered_at']==e['time']
            elif body['kind']=='self_state':
                assert body['source']==int(actor)
            else:
                assert int(actor) in body['scene']['witnesses']
            if body['kind']=='self_state':
                v=body['state']; key=str(body['source'])
                changed=v['seq']>states[actor][key]['seq']
                if changed: states[actor][key]=copy.deepcopy(v); origins[actor][key]=e['id']
            else:
                v=body['scene']; key=str(v['task']); previous=scenes[actor].get(key)
                changed=not previous or previous['phase']!='done' and v['version']>previous['version']
                if changed: scenes[actor][key]=copy.deepcopy(v); scene_origins[actor][key]=e['id']
            assert bool(changed)==e['applied']
            consumed[actor]+=1
        elif kind=='information_consulted':
            consultations[e['id']]=e
            d=decisions[int(e['decision_id'][1:])]
            assert d['time']==e['time'] and d['actor']==int(actor)
            assert e['evidence_count']==consumed[actor]==d['evidence_count']
            obs,branch=old.observation_from_evidence(catalog,states[actor],scenes[actor],actor,e['time'])
            assert old.close(obs,d['observation']) and branch==d['branch']==e['branch']
            assert hashlib.sha256(encode(d['observation'])).hexdigest()==e['observation_sha256']
            signature=dict(states=states[actor],scenes=scenes[actor])
            assert hashlib.sha256(encode(signature)).hexdigest()==d['view_sha256']
            assert len(e['references'])==len(catalog['agents'])+len(catalog['tasks'])
            unknown=0
            for ref in e['references']:
                key=str(ref['object_id'])
                source=origins[actor].get(key) if ref['object']=='self_state' else scene_origins[actor].get(key)
                assert ref['fact_id']==source
                if source is None:
                    assert ref['knowledge']=='unknown' and ref['version'] is None
                    unknown+=1
                else:
                    f=facts[source]; assert f['ordinal']<ordinal and f['actor']==int(actor) and f['applied']
                    assert ref['knowledge']=='known'
                    expected=states[actor][key]['seq'] if ref['object']=='self_state' else scenes[actor][key]['version']
                    assert expected==ref['version']
                    reference_counts[(ref['object'],f['origin'])]+=1
            assert unknown==e['scene_unknown_count'] and e['causal_value'] is None
        elif kind=='decision':
            assert e['decision_id']==f'd{decision_count:07d}'
            d=decisions[decision_count]; decision_count+=1
            assert d['time']==e['time'] and d['actor']==int(actor) and d['action']==e['action']
            assert consultations[e['consultation_id']]['decision_id']==e['decision_id']
            assert events[e['legacy_event_id']]['kind']=='decision'
            if config['recovery']: assert e['time']>=gates[int(actor)]-1e-10
        elif kind=='action_intent':
            intents[e['action_id']]=e
        elif kind=='action_result':
            action_results[e['action_id']]=e
            intent=intents[e['action_id']]
            assert intent['actor']==e['actor'] and intent['time']==e['time']
            if e['departed']:
                route=final['actors'][actor]['route'][e['route_index']]
                assert route['departure']==e['time'] and route['target']==intent['action']-1
    assert decision_count==len(decisions)==len(intents)==len(action_results)
    assert all(consumed[i]==len(evidence[i]) for i in evidence)
    positions={i:a['depot'] for i,a in catalog['agents'].items()}
    moving,locked,starts,finishes={},{},{},{}
    own={i:dict(mode='idle',target=-1) for i in catalog['agents']}
    lastdecision={}
    cancel=0
    for e in events:
        k=e['kind']; a=str(e.get('actor')); now=e['time']
        if k=='own_state': own[a]=e['state']
        elif k=='decision':
            assert a not in moving and a not in locked and own[a]['mode']=='idle'
            lastdecision[a]=e
        elif k=='departure':
            assert a not in moving and a not in locked
            assert lastdecision[a]['time']==now and lastdecision[a]['action']-1==e['target']
            assert old.close(positions[a],e['origin'])
            destination=catalog['tasks'][str(e['target'])]['location'] if e['target']>=0 else catalog['agents'][a]['depot']
            assert old.close(e['destination'],destination)
            assert math.isclose(math.dist(e['origin'],e['destination']),e['distance'],abs_tol=1e-9)
            assert math.isclose(now+e['distance']/catalog['agents'][a]['velocity'],e['arrival'],abs_tol=1e-9)
            moving[a]=e
        elif k=='arrival':
            leg=moving.pop(a); assert old.close(leg['destination'],e['position']) and leg['arrival']==now
            positions[a]=e['position']
        elif k=='task_start':
            tid=str(e['task']); assert tid not in starts; starts[tid]=e
            ability=[sum(catalog['agents'][str(i)]['abilities'][d] for i in e['workers']) for d in range(5)]
            assert ability==e['ability'] and all(x>=y for x,y in zip(ability,catalog['tasks'][tid]['requirements']))
            for i in e['workers']:
                key=str(i); assert key not in moving and key not in locked
                assert old.close(positions[key],catalog['tasks'][tid]['location']); locked[key]=tid
        elif k=='task_finish':
            tid=str(e['task']); assert tid not in finishes; finishes[tid]=e
            assert math.isclose(now,starts[tid]['time']+catalog['tasks'][tid]['time'],abs_tol=1e-9)
            for i in e['workers']: assert locked.pop(str(i))==tid
        elif k=='onsite_observation':
            s=e['scene']; tid=str(s['task'])
            assert int(a) in s['witnesses'] and set(s['workers']).issubset(s['witnesses'])
            for i in s['witnesses']:
                key=str(i); assert key not in moving and old.close(positions[key],catalog['tasks'][tid]['location'])
        elif k=='local_wait_cancel':
            assert a not in moving and a not in locked and own[a]['mode']=='idle'
            assert own[a]['target']==e['target']>=0
            assert old.close(positions[a],catalog['tasks'][str(e['target'])]['location'])
            cancel+=1
    assert len(finishes)==result['completed']
    assert len(finishes)/len(catalog['tasks'])==result['completion_fraction']
    assert len(events)+len(ledger)==result['budget_event_records']
    returned=sum(a['mode']=='idle' and a['target']<0 for a in final['actors'].values())
    assert returned==result['returned']
    if result['success']:
        assert len(finishes)==len(catalog['tasks']) and returned==len(catalog['agents'])
        assert result['makespan_return']==result['end_time']
        assert all(old.close(positions[i],a['depot']) for i,a in catalog['agents'].items())
    else: assert result['makespan_return'] is None
    service=old.check_service(messages,ledger,deliveries,result['network'],
        dict(mode='instant' if config['condition']=='instant' else 'fixed_delay',delay=0.5,
             rate_bytes_per_time=1024.,capacity_bytes=65536,overhead_bytes=0),result['end_time'])
    regression={}
    for name,entry in result.get('legacy_comparison',{}).items():
        reference=load(entry['reference'])
        assert sha(entry['reference'])==entry['sha256']
        assert reference==load(case/(name+'.json')) and entry['equal']
        regression[name]=True
    return dict(run=base.name,case=row['case_id'],seed=config['seed'],agents=len(catalog['agents']),tasks=len(catalog['tasks']),
        recovery=config['recovery'],condition=config['condition'],status=result['status'],completed=result['completed'],
        completion_fraction=result['completion_fraction'],makespan=result['makespan_return'],end_time=result['end_time'],
        decisions=len(decisions),messages=len(messages),application_bytes=sum(len(m['payload_utf8'].encode()) for m in messages),
        delivered_copies=len(deliveries),information_records=len(info),information_bytes=(case/'information_ledger.json').stat().st_size,
        acquired=dict(counts),references={':'.join(k):v for k,v in reference_counts.items()},cancelled_waits=cancel,
        budget_event_records=result['budget_event_records'],legacy_regression=regression,service=service,checks='pass')


def main():
    report=dict(scope='Saved evidence only; no task policies, simulations or research code imported',scale=check_scale(),cases=[],pending=[],errors=[])
    pre=ROOT/'simulation/outputs/E1-006/20261026-00-preflight'
    pf=load(pre/'preflight.json')
    assert pf['test_exit_code']==0 and pf['case_counts']==dict(legacy=10,recovery=10,scale=10)
    assert sha(ROOT/'simulation/heteromrta_demand_execution.py')==pf['script_sha256']
    assert sha(ROOT/'simulation/test_heteromrta_demand_execution.py')==pf['test_sha256']
    for name,expected in pf['files'].items(): assert sha(pre/name)==expected
    testlog=raw(pre/'tests.stderr.txt').decode()
    assert 'Ran 7 tests' in testlog and '\nOK' in testlog
    scale_log=ROOT/'simulation/outputs/E2-006/20261026-01/unit_tests.log'
    assert 'Ran 5 tests' in raw(scale_log).decode() and '\nOK' in raw(scale_log).decode()
    report['saved_test_evidence']=dict(execution_tests=7,scale_tests=5,tests_run_by_auditor=0)
    for summary_path in sorted((ROOT/'simulation/outputs/E1-006').glob('*/summary.json')):
        base=summary_path.parent
        if not (base/'manifest.json').exists():
            assert base.name=='20261026-04-analysis'
            continue
        summary,manifest=load(summary_path),load(base/'manifest.json')
        for name,expected in manifest['source_hashes'].items():
            assert sha(base/'source'/name)==expected
        assert sha(ROOT/'simulation/heteromrta_eval.py')==manifest['inherited_eval_sha256']
        for asset in manifest['assets']:
            assert sha(ROOT/'data/heteromrta/upstream'/asset['path'])==asset['sha256']
        assert manifest['event_budget']==100000 and manifest['horizon']==200
        assert manifest['recovery_config']==dict(startup_window=1.,wait_base=20.,wait_jitter=5.,idle_base=1.,idle_jitter=1.)
        for row in summary['cases']:
            try:
                report['cases'].append(check_case(base,row,manifest))
            except Exception as error:
                import traceback
                report['errors'].append(dict(run=base.name,case=row['case_id'],error=repr(error),traceback=traceback.format_exc()))
        if len(summary['cases'])!=summary['planned']:
            report['pending'].append(dict(run=base.name,recorded=len(summary['cases']),planned=summary['planned']))
    if len(report['cases'])==30 and not report['errors']:
        report['totals']={k:sum(r[k] for r in report['cases']) for k in ('decisions','messages','application_bytes','delivered_copies','information_records','information_bytes')}
        report['max_budget_event_records']=max(r['budget_event_records'] for r in report['cases'])
        analysis=ROOT/'simulation/outputs/E1-006/20261026-04-analysis'
        if analysis.exists():
            summary=load(analysis/'summary.json')
            assert sha(pre/'analyze.py')==summary['analysis_script_sha256']
            for s in summary['source_files']: assert sha(ROOT/s['path'])==s['sha256']
            rows=list(csv.DictReader(io.StringIO(raw(analysis/'cases.csv').decode('utf-8-sig'))))
            assert len(rows)==30
            checked={r['case']:r for r in report['cases']}
            mapping=dict(messages='messages',application_bytes='application_bytes',delivered_copies='delivered_copies',
                decisions='decisions',information_records='information_records',information_log_bytes='information_bytes',
                wait_cancels='cancelled_waits',counted_event_records='budget_event_records',completed='completed')
            for r in rows:
                c=checked[r['case_id']]
                assert c['status']==r['status']
                for name,key in mapping.items(): assert int(r[name])==c[key]
                for origin in ('initial','local','network'):
                    assert int(r[origin+'_references'])==sum(v for k,v in c['references'].items() if k.endswith(':'+origin))
            report['analysis_csv_checked_rows']=30
    report['reviewed_documents']={}
    for name in ('SCALE_ENTRY_PREFLIGHT.md','DEMAND_EXECUTION_IMPLEMENTATION.md','DEMAND_EXECUTION_STAGE.md'):
        p=ROOT/'research/agent_native_network'/name
        if p.exists(): report['reviewed_documents'][name]=sha(p)
    report['verifier_sha256']=sha(__file__)
    sha(ROOT/'coordination/reviews/C-006-verification.py')
    report['input_sha256']=HASHES
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(scale=report['scale']['configurations'],cases=len(report['cases']),pending=report['pending'],errors=report['errors']),ensure_ascii=False,indent=2))
    return 1 if report['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
