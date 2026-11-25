"""Independent saved-evidence calculations. No policy or research imports.

Only this review's JSON is written. Input bodies, hashes and wire intervals are
read from preserved artifacts; no traffic or task execution is generated.
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

ROOT=Path(__file__).resolve().parents[2]
HASHES={}
_spec=importlib.util.spec_from_file_location('independent_c006',ROOT/'coordination/reviews/C-006-verification.py')
OLD=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(OLD)


def encode(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()


def raw(path):
    path=Path(path).resolve()
    if not path.exists() and path.suffix=='.json':
        path=path.with_suffix('.json.gz')
    data=path.read_bytes()
    HASHES[path.relative_to(ROOT).as_posix()]=hashlib.sha256(data).hexdigest()
    return gzip.decompress(data) if path.suffix=='.gz' else data


def load(path):
    return json.loads(raw(path))


def file_sha(path):
    raw(path)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def frame_us(payload_bytes):
    return 20+4*((16+8*(payload_bytes+64)+6+23)//24)


def ticks(t):
    x=t*20_000_000
    nearest=round(x)
    return nearest if abs(x-nearest)<=4*math.ulp(x) else x


def percentile(values,q=.95):
    if not values: return None
    v=sorted(values); p=(len(v)-1)*q; a=math.floor(p); b=math.ceil(p)
    return v[a]+(v[b]-v[a])*(p-a)


def near(a,b):
    return a==b or isinstance(a,(int,float)) and isinstance(b,(int,float)) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-9)


def identity(payload,source,kind):
    try:
        body=json.loads(payload)
        if body.get('source')!=source or body.get('kind')!=kind: return None,None
        if kind=='self_state':
            s=body['state']
            if not {'source','seq','mode','target'}.issubset(s) or s['source']!=source or not isinstance(s['seq'],int): return None,None
            return (source,kind,source),(s['seq'],)
        if kind=='task_scene':
            s=body['scene']
            if not {'task','phase','workers','witnesses','version','observed_at'}.issubset(s): return None,None
            return (source,kind,s['task']),tuple(s['version'])
    except (ValueError,TypeError,KeyError,AttributeError): pass
    return None,None


def check_wireless(ledger,stats,deliveries=None):
    """Derive queue/slot states from logged events and independently bill intervals."""
    records={}; stations={}; high={}; active={}; idle_origin=0; batch={}; expected_deliveries=[]
    def station(source):
        return stations.setdefault(source,dict(queue=[],occupied=0,draw=0,backoff=None,start=None))
    def next_attempts():
        return {source:s['start']+9*s['backoff'] for source,s in stations.items() if s['queue'] and s['start'] is not None}
    for event in ledger:
        k=event['event']; t=event['time_us']; mid=event.get('message_id')
        assert isinstance(t,int) and near(event['time'],t/20_000_000)
        if k=='submitted':
            payload=bytes.fromhex(event['payload_hex'])
            assert hashlib.sha256(payload).hexdigest()==event['payload_sha256']
            assert len(payload)==event['application_bytes'] and len(payload)+64==event['service_bytes']
            assert t==math.ceil(ticks(event['enqueued_at']))==event['eligibility_us']
            key,version=identity(payload,event['source'],event['kind'])
            assert (tuple(event['semantic_key']) if event['semantic_key'] is not None else None)==key
            assert (tuple(event['version']) if event['version'] is not None else None)==version
            assert mid not in records
            r=dict(event,payload=payload,key=key,version_tuple=version,status='new',accepted=False)
            records[mid]=r; s=station(event['source']); old=None; reject=None; coalesced=None
            if len(payload)>1472: reject='frame_too_large'
            elif stats['policy']=='latest_state' and key is not None:
                previous=high.get(key)
                if previous and version<previous[0]: reject='stale_version'
                elif previous and version==previous[0] and event['payload_sha256']!=previous[1]: reject='same_version_conflict'
                else:
                    old=next((p for p in s['queue'] if records[p]['status']=='queued' and records[p]['key']==key),None)
                    if old and records[old]['version_tuple']==version and records[old]['payload']==payload and records[old]['recipients']==event['recipients']:
                        coalesced=old
            prior=records[old]['service_bytes'] if old else 0
            if not reject and not coalesced and s['occupied']-prior+r['service_bytes']>stats['capacity_bytes_per_source']:
                reject='tail_drop_capacity'
            r.update(expected_reject=reject,expected_coalesced=coalesced,expected_old=old)
        elif k=='rejected':
            r=records[mid]; assert event['reason']==r['expected_reject']
            r.update(status='rejected',reject_reason=event['reason'])
            assert event['occupied_bytes']==station(r['source'])['occupied']
        elif k=='coalesced':
            r=records[mid]; assert event['into_message_id']==r['expected_coalesced'] and not r['expected_reject']
            r['status']='coalesced'
        elif k=='replaced':
            r=records[mid]; new=records[event['by_message_id']];s=station(r['source'])
            assert r['status']=='queued' and new['expected_old']==mid and not new['expected_reject']
            assert r['key']==new['key'] and r['version_tuple']<=new['version_tuple']
            assert s['backoff']==event['preserved_backoff_slots']
            s['queue'][s['queue'].index(mid)]=new['message_id'];s['occupied']-=r['service_bytes'];r['status']='replaced'
        elif k=='admitted':
            r=records[mid];s=station(r['source'])
            assert not r['expected_reject'] and not r['expected_coalesced']
            assert event['replaced_message_id']==r['expected_old']
            if not r['expected_old']: s['queue'].append(mid)
            else: assert mid in s['queue']
            s['occupied']+=r['service_bytes']; assert s['occupied']==event['occupied_bytes']<=stats['capacity_bytes_per_source']
            r.update(status='queued',accepted=True)
            if stats['policy']=='latest_state' and r['key'] is not None: high[r['key']]=(r['version_tuple'],r['payload_sha256'])
        elif k=='head_activated':
            r=records[mid];s=station(r['source']); assert s['queue'][0]==mid and r['source'] not in active
            s['draw']+=1
            key=f"E1-007|{stats['seed']}|{r['source']}|{s['draw']}"
            value=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')%16
            assert event['draw_count']==s['draw'] and event['draw_key']==key and event['backoff_slots']==value
            s['backoff']=value; s['start']=None
            if not active:
                anchor=idle_origin+34; ready=max(anchor,t+34)
                s['start']=anchor+((ready-anchor+8)//9)*9
        elif k=='contention_batch':
            assert not active
            attempts=next_attempts(); assert attempts and min(attempts.values())==t
            contenders=sorted(source for source,due in attempts.items() if due==t)
            assert contenders==event['sources'] and event['collision']==(len(contenders)>1)
            batch=dict(time=t,sources=contenders,seen=[])
        elif k=='backoff_frozen':
            r=records[mid];s=station(r['source'])
            assert r['source'] not in batch['sources'] and s['queue'][0]==mid
            elapsed=max(0,(t-s['start'])//9); before=s['backoff']
            assert event['before_slots']==before and event['completed_idle_slots']==elapsed
            s['backoff']=max(0,before-elapsed);s['start']=None
            assert s['backoff']==event['remaining_slots']
        elif k=='tx_started':
            r=records[mid];s=station(r['source'])
            assert t==batch['time'] and r['source'] in batch['sources'] and r['source'] not in batch['seen']
            batch['seen'].append(r['source'])
            assert s['queue'][0]==mid and r['status']=='queued' and r['source'] not in active
            assert t==s['start']+9*s['backoff'] and t>=r['eligibility_us']
            duration=frame_us(r['application_bytes'])
            assert event['duration_us']==duration and event['finish_us']==t+duration
            assert event['collision']==(len(batch['sources'])>1)
            r.update(status='transmitting',tx_start=t,tx_finish=t+duration,collision=event['collision'])
            active[r['source']]=mid;s['start']=None
        elif k=='tx_completed':
            r=records[mid];s=station(r['source'])
            assert r['status']=='transmitting' and r['tx_finish']==t and active.pop(r['source'])==mid
            assert s['queue'].pop(0)==mid
            s['occupied']-=r['service_bytes'];s['backoff']=None;s['start']=None
            r['status']='collided' if r['collision'] else 'delivered'
            assert event['outcome']==r['status']
        elif k=='delivered':
            r=records[mid]; assert r['status']=='delivered' and t==r['tx_finish']
            assert event['recipient'] in r['recipients'] and event['application_bytes']==r['application_bytes']
            expected_deliveries.append((mid,event['recipient'],t))
        elif k=='channel_idle':
            assert not active and event['resume_at_us']==t+34
            idle_origin=t
            for s in stations.values():
                if s['queue']: s['start']=t+34
        else: raise AssertionError(('unrecognized service event',k))
    if batch: assert sorted(batch['seen'])==batch['sources']
    observation=stats['observed_at']; horizon=math.floor(ticks(observation))
    assert stats['observed_through_us']==horizon
    visible={mid:r for mid,r in records.items() if r['enqueued_at']<=observation}
    status={}
    for mid,r in visible.items():
        s=r['status']
        if 'tx_start' in r:
            s='queued' if r['tx_start']>horizon else 'transmitting' if r['tx_finish']>horizon else 'collided' if r['collision'] else 'delivered'
        status[mid]=s
    counts=collections.Counter(status.values());done=[r for mid,r in visible.items() if status[mid]=='delivered']
    attempts=[r for r in visible.values() if r.get('tx_start',math.inf)<=horizon]
    intervals=sorted((r['tx_start'],min(horizon,r['tx_finish'])) for r in attempts)
    attempt=sum(b-a for a,b in intervals);busy=0;end=0
    for a,b in intervals: busy+=max(0,b-max(a,end));end=max(end,b)
    expected=dict(demanded=len(visible),accepted=sum(r['accepted'] for r in visible.values()),dropped=counts['rejected'],
        rejected=counts['rejected'],coalesced=counts['coalesced'],replaced=counts['replaced'],collided=counts['collided'],
        pending=counts['queued']+counts['transmitting'],delivered=counts['delivered'],transmitting=counts['transmitting'],
        queue_messages=counts['queued'],recipient_demand=sum(len(r['recipients']) for r in visible.values()),
        recipient_delivered=sum(len(r['recipients']) for r in done),demand_application_bytes=sum(r['application_bytes'] for r in visible.values()),
        demand_service_bytes=sum(r['service_bytes'] for r in visible.values()),attempted_frames=len(attempts),
        collision_attempts=sum(r['collision'] for r in attempts),airtime_attempt_us=attempt,channel_busy_us=busy,
        buffer_occupied_bytes=sum(r['service_bytes'] for mid,r in visible.items() if status[mid] in ('queued','transmitting')))
    for name,value in expected.items(): assert stats[name]==value,(name,stats[name],value)
    assert len(visible)==sum(counts.values()) and counts['new']==0
    for name,values in [('latency',[r['tx_finish']/20_000_000-r['enqueued_at'] for r in done]),
        ('information_age',[r['tx_finish']/20_000_000-r['information_generated_at'] for r in done if r['information_generated_at'] is not None])]:
        for suffix,value in [('mean',sum(values)/len(values) if values else None),('p95',percentile(values)),('max',max(values) if values else None)]:
            assert near(stats[name+'_'+suffix],value)
    complete=[(m,r,t) for m,r,t in expected_deliveries if t<=horizon]
    assert len(complete)==len(set(complete))==expected['recipient_delivered']
    if deliveries is not None:
        actual=[]
        for d in deliveries:
            if d['delivered_at']>observation: continue
            r=records[d['message_id']]
            assert near(d['delivered_at'],r['tx_finish']/20_000_000)
            assert d['payload_sha256']==r['payload_sha256'] and d['generated_at']==r['enqueued_at']
            actual.append((d['message_id'],d['recipient'],r['tx_finish']))
        assert sorted(actual)==sorted(complete)
    return dict(**expected,checks='pass'),records


def check_preview():
    preview=load(ROOT/'coordination/reviews/M-009-load-preview.json')
    assert file_sha(ROOT/'coordination/reviews/M-009-load-preview.py')==preview['script_sha256']
    for item in preview['inputs']:
        assert file_sha(ROOT/item['path'])==item['sha256']
    rows=[]
    base=ROOT/'simulation/results/2026-10-26-E1-006-execution/20261026-03-scale'
    for r in preview['cases']:
        messages=load(base/r['case']/'messages.json')
        result=load(base/r['case']/'result.json')
        batches=collections.defaultdict(list)
        sizes=[]
        for m in messages:
            size=len(m['payload_utf8'].encode())
            assert size==m['bytes']
            sizes.append(size)
            batches[math.ceil(m['generated_at']*20_000_000)].append(m)
        duration=result['makespan_return']*20
        offered=sum(frame_us(s) for s in sizes)/1e6
        expected=dict(application_bytes=sum(sizes),messages=len(messages),duration_seconds=duration,
            payload_max_bytes=max(sizes),offered_tx_seconds=offered,offered_tx_time_fraction=offered/duration,
            peak_same_us_messages=max(map(len,batches.values())),
            peak_same_us_sources=max(len({m['source'] for m in b}) for b in batches.values()),
            multi_source_batches=sum(len({m['source'] for m in b})>1 for b in batches.values()))
        assert all(r[k]==v for k,v in expected.items())
        rows.append(dict(case=r['case'],checks='pass',**expected))
    assert len(rows)==10 and len(preview['inputs'])==20
    return dict(rows=rows,checked_input_hashes=20,
        offered_fraction_min=min(r['offered_tx_time_fraction'] for r in rows),
        offered_fraction_max=max(r['offered_tx_time_fraction'] for r in rows),
        interpretation='offered frame-time sum, not observed channel busy or capacity failure')


def check_micro():
    base=ROOT/'simulation/outputs/E1-007/20261026-02-tests'
    manifest=load(base/'manifest.json'); assert manifest['tests_run']==17 and manifest['successful']
    assert manifest['failures']==manifest['errors']==0
    for name,expected in manifest['sources'].items():
        assert file_sha(name)==expected==file_sha(base/'source'/Path(name).name)
    log=raw(base/'tests.txt').decode(); assert 'Ran 17 tests' in log and '\nOK' in log
    rows=[]
    for test in load(base/'evidence.json'):
        for i,service in enumerate(test['services']):
            check,_=check_wireless(service['ledger'],service['final_stats'])
            rows.append(dict(test=test['test'],fixture=i,**check))
    return rows


def check_replays(report):
    base=ROOT/'simulation/outputs/E2-007/20261026-01-replay'
    if not (base/'summary.json').exists():
        report['pending'].append('60 replays not produced');return
    manifest,summary=load(base/'manifest.json'),load(base/'summary.json')
    assert manifest['planned']==summary['planned']==60 and manifest['task_episodes']==0
    assert file_sha(manifest['source_summary'])==manifest['source_summary_sha256']
    source_cases={r['case_id'] for r in load(manifest['source_summary'])['cases']}
    for name,expected in manifest['source_hashes'].items(): assert file_sha(base/'source'/name)==expected
    assert file_sha(base/'WIRELESS_SERVICE_CONTRACT.md')==manifest['contract_sha256']
    for row in summary['cases']:
        try:
            case=base/row['case_id'];config=load(case/'config.json');result=load(case/'result.json')
            ledger,deliveries,mapping=load(case/'service_ledger.json'),load(case/'deliveries.json'),load(case/'mapping.json')
            assert result['status']=='completed' and result['task_executed'] is False
            assert file_sha(config['messages_path'])==config['messages_sha256']
            assert file_sha(config['reference_result_path'])==config['reference_result_sha256']
            originals=load(config['messages_path']); assert len(mapping)==len(originals)
            drained,records=check_wireless(ledger,result['drained_stats'],deliveries)
            window,_=check_wireless(ledger,result['window_stats'],deliveries)
            for original,link in zip(originals,mapping):
                r=records[link['message_id']];payload=original['payload_utf8'].encode()
                assert link['original_message_id']==original['message_id']
                assert payload==r['payload'] and original['source']==r['source']
                assert original['generated_at']==r['enqueued_at']==link['generated_at']
                assert original['recipients']==r['recipients'] and hashlib.sha256(payload).hexdigest()==link['payload_sha256']
            assert result['window_receiver_copies']==window['recipient_delivered']
            assert result['drained_receiver_copies']==drained['recipient_delivered']
            assert drained['pending']==0
            for name in ('demanded','delivered','collided','replaced','dropped','recipient_delivered','airtime_attempt_us','channel_busy_us'):
                assert row[name]==drained[name]
            ages=[(d['delivered_at']-json.loads(records[d['message_id']]['payload'])['generated_at'])*20 for d in deliveries]
            assert near(result['fact_age_seconds_p95'],percentile(ages))
            report['replay_cases'].append(dict(case=row['case_id'],source_case=config['source_case'],mac_seed=config['mac_seed'],policy=config['policy'],
                window_pending=window['pending'],**drained))
        except Exception as error:
            import traceback
            report['errors'].append(dict(scope='replay',case=row['case_id'],error=repr(error),traceback=traceback.format_exc()))
    if len(summary['cases'])!=60: report['pending'].append(dict(replay_recorded=len(summary['cases']),expected=60))
    elif not any(e.get('scope')=='replay' for e in report['errors']):
        assert {(r['source_case'],r['mac_seed'],r['policy']) for r in report['replay_cases']}=={(c,s,p) for c in source_cases for s in (0,1,2) for p in ('fifo','latest_state')}


def check_task(base,row):
    case=base/row['case_id'];r,catalog,config=load(case/'result.json'),load(case/'catalog.json'),load(case/'config.json')
    events,decisions,info=load(case/'events.json'),load(case/'decisions.json'),load(case/'information_ledger.json')
    messages,deliveries,evidence=load(case/'messages.json'),load(case/'deliveries.json'),load(case/'view_evidence.json')
    final,service=load(case/'final.json'),load(case/'service_ledger.json')
    assert all(row[k]==v for k,v in r.items()) and row['process_exit_code']==0
    assert file_sha(config['catalog_path'])==config['expected_catalog_sha256'] and catalog==load(config['catalog_path'])
    ref=config['instant_reference']; assert file_sha(ref['path'])==ref['sha256']
    reference=load(ref['path']); assert reference['makespan_return']==ref['makespan_return'] and reference['success']
    network,record=check_wireless(service,r['network'],deliveries)
    by_id={m['message_id']:m for m in messages}; by_local={m['local_evidence']:m for m in messages if m['local_evidence'] is not None}
    bodies={mid:json.loads(m['payload_utf8']) for mid,m in by_id.items()};arrivals={(d['recipient'],d['message_id']):d for d in deliveries}
    assert len(by_id)==len(messages)==len(record) and len(arrivals)==len(deliveries)
    publication=collections.Counter();last_authored={};refresh_count=0
    for m in messages:
        mid=m['message_id'];body=bodies[mid];rr=record[mid];publication[m['publication_reason']]+=1
        assert body['generated_at']==m['body_generated_at']<=m['enqueued_at']==m['generated_at']==rr['enqueued_at']
        assert m['payload_utf8'].encode()==rr['payload'] and m['source']==body['source']==rr['source']
        assert m['recipients']==[int(i) for i in catalog['agents'] if int(i)!=m['source']]
        key,_=identity(rr['payload'],m['source'],m['kind'])
        if m['publication_reason']=='event':
            e=events[m['local_evidence']];field='state' if body['kind']=='self_state' else 'scene'
            assert e['time']==body['generated_at'] and e['actor']==body['source'] and e[field]==body[field]
            assert m['refresh_origin_message_id'] is None
            last_authored[key]=m
        else:
            assert config['condition']=='refresh_latest' and m['local_evidence'] is None
            original=last_authored[key]
            assert m['refresh_origin_message_id']==original['message_id']
            assert m['origin_local_evidence']==original['local_evidence'] and m['payload_utf8']==original['payload_utf8']
            refresh_count+=1
    assert dict(publication)=={k:v for k,v in r['publication_counts'].items() if v}
    states={};scenes={};origins={};scene_origins={};consumed={};facts={};consultations={};intents={}
    for actor in catalog['agents']:
        states[actor]={i:dict(source=int(i),seq=0,target=-1,mode='idle',origin=a['depot'],destination=a['depot'],departure=0.,arrival=0.,changed_at=0.,finish=None) for i,a in catalog['agents'].items()}
        scenes[actor],origins[actor],scene_origins[actor],consumed[actor]={},{},{},0
    gates={int(i):0. for i in catalog['agents']};counts=collections.Counter();refresh_due={};n_dec=0;n_action=0
    origin_counts=collections.Counter();ref_counts=collections.Counter()
    for ordinal,e in enumerate(info):
        assert e['id']==f'i{ordinal:09d}' and e['ordinal']==ordinal
        kind=e['kind'];actor=str(e.get('actor'))
        if kind=='local_timer_scheduled':
            ek=e['event_kind']
            if ek=='refresh_timer':
                i=e['actor'];expected=refresh_due.get(i,i/len(catalog['agents']))
                assert near(expected,e['due_at']);refresh_due[i]=expected+1
            elif ek in ('startup_ready','idle_timer','wait_timeout'):
                i=e['data']['actor'];key='startup' if ek=='startup_ready' else ek
                random_key=json.dumps([config['seed'],i,key,counts[(i,key)]],separators=(',',':')).encode()
                jitter=int.from_bytes(hashlib.sha256(random_key).digest()[:8],'big')/2**64;counts[(i,key)]+=1
                delay=jitter if ek=='startup_ready' else 1+jitter if ek=='idle_timer' else 20+5*jitter
                assert near(e['due_at'],e['time']+delay)
                if ek!='wait_timeout': gates[i]=e['due_at']
        elif kind=='local_timer_fired' and e['event_kind']=='refresh_timer':
            assert near(e['time'],refresh_due[e['actor']]-1)
            following=info[ordinal+1]
            assert following['kind']=='local_timer_scheduled' and following['event_kind']=='refresh_timer'
            assert following['actor']==e['actor'] and near(following['due_at'],e['time']+1)
        elif kind=='information_acquired':
            facts[e['id']]=e;origin_counts[e['origin']]+=1
            if e['origin']=='initial':
                assert e['time']==0 and e['protocol_cost_bytes']==0 and e['catalog_sha256']==hashlib.sha256(encode(catalog)).hexdigest()
                origins[actor]={i:e['id'] for i in catalog['agents']};continue
            index=consumed[actor];ev=evidence[actor][index]
            assert e['evidence_prefix']==index+1 and ev['evidence_id']==e['evidence_id']
            assert ev['at']==e['time'] and ev['applied']==e['applied']
            m=by_id[e['evidence_id']] if e['origin']=='network' else by_local[e['evidence_id']]
            body=bodies[m['message_id']]
            assert hashlib.sha256(encode(body)).hexdigest()==e['payload_sha256'] and body['generated_at']<=e['time']
            if e['origin']=='network': assert arrivals[(int(actor),m['message_id'])]['delivered_at']==e['time']
            elif body['kind']=='self_state': assert body['source']==int(actor)
            else: assert int(actor) in body['scene']['witnesses']
            if body['kind']=='self_state':
                v=body['state'];key=str(body['source']);changed=v['seq']>states[actor][key]['seq']
                if changed: states[actor][key]=copy.deepcopy(v);origins[actor][key]=e['id']
            else:
                v=body['scene'];key=str(v['task']);prior=scenes[actor].get(key)
                changed=not prior or prior['phase']!='done' and v['version']>prior['version']
                if changed: scenes[actor][key]=copy.deepcopy(v);scene_origins[actor][key]=e['id']
            assert bool(changed)==e['applied'];consumed[actor]+=1
        elif kind=='information_consulted':
            consultations[e['id']]=e;d=decisions[int(e['decision_id'][1:])]
            assert d['time']==e['time'] and d['actor']==int(actor) and e['evidence_count']==consumed[actor]==d['evidence_count']
            obs,branch=OLD.observation_from_evidence(catalog,states[actor],scenes[actor],actor,e['time'])
            assert OLD.close(obs,d['observation']) and branch==d['branch']==e['branch']
            assert hashlib.sha256(encode(dict(states=states[actor],scenes=scenes[actor]))).hexdigest()==d['view_sha256']
            assert hashlib.sha256(encode(d['observation'])).hexdigest()==e['observation_sha256']
            assert e['causal_value'] is None and len(e['references'])==len(catalog['agents'])+len(catalog['tasks'])
            for ref in e['references']:
                key=str(ref['object_id']);state=ref['object']=='self_state'
                source=(origins if state else scene_origins)[actor].get(key)
                assert ref['fact_id']==source
                if source is None: assert ref['knowledge']=='unknown' and ref['version'] is None
                else:
                    f=facts[source];assert f['ordinal']<ordinal and f['applied'] and f['actor']==int(actor)
                    assert ref['version']==(states[actor][key]['seq'] if state else scenes[actor][key]['version'])
                    ref_counts[f['origin']]+=1
        elif kind=='decision':
            assert e['decision_id']==f'd{n_dec:07d}';d=decisions[n_dec];n_dec+=1
            assert d['time']==e['time'] and d['actor']==int(actor) and d['action']==e['action']
            assert e['time']>=gates[int(actor)]-1e-10
            assert consultations[e['consultation_id']]['decision_id']==e['decision_id']
            assert events[e['legacy_event_id']]['kind']=='decision'
            if d['action'] is not None: assert not d['observation'][2][0][d['action']]
        elif kind=='action_intent': intents[e['action_id']]=e
        elif kind=='action_result':
            n_action+=1;intent=intents[e['action_id']]
            assert intent['actor']==e['actor'] and intent['time']==e['time']
            if e['departed']:
                route=final['actors'][actor]['route'][e['route_index']]
                assert route['departure']==e['time'] and route['target']==intent['action']-1
    assert n_dec==n_action==len(decisions)==r['decisions'] and all(consumed[i]==len(evidence[i]) for i in evidence)
    assert len(info)==r['information_records'] and dict(collections.Counter(e['kind'] for e in info))==r['information_record_counts']
    # Physical trajectory and coalition locking, calculated from raw event order.
    positions={i:a['depot'] for i,a in catalog['agents'].items()};moving={};locked={};starts={};finishes={};own={};last={}
    for i in catalog['agents']: own[i]=dict(mode='idle',target=-1)
    for e in events:
        k=e['kind'];a=str(e.get('actor'));now=e['time']
        if k=='own_state': own[a]=e['state']
        elif k=='decision':
            assert a not in moving and a not in locked and own[a]['mode']=='idle';last[a]=e
        elif k=='departure':
            assert a not in moving and a not in locked and last[a]['time']==now and last[a]['action']-1==e['target']
            dest=catalog['tasks'][str(e['target'])]['location'] if e['target']>=0 else catalog['agents'][a]['depot']
            assert OLD.close(positions[a],e['origin']) and OLD.close(dest,e['destination'])
            assert near(e['distance'],math.dist(e['origin'],dest)) and near(e['arrival'],now+e['distance']/catalog['agents'][a]['velocity'])
            moving[a]=e
        elif k=='arrival':
            leg=moving.pop(a); assert near(now,leg['arrival']) and OLD.close(e['position'],leg['destination']);positions[a]=e['position']
        elif k=='task_start':
            tid=str(e['task']);assert tid not in starts;starts[tid]=e
            ability=[sum(catalog['agents'][str(i)]['abilities'][d] for i in e['workers']) for d in range(5)]
            assert ability==e['ability'] and all(x>=y for x,y in zip(ability,catalog['tasks'][tid]['requirements']))
            for i in e['workers']:
                key=str(i);assert key not in moving and key not in locked and OLD.close(positions[key],catalog['tasks'][tid]['location']);locked[key]=tid
        elif k=='task_finish':
            tid=str(e['task']);assert tid not in finishes;finishes[tid]=e
            assert near(now,starts[tid]['time']+catalog['tasks'][tid]['time'])
            for i in e['workers']: assert locked.pop(str(i))==tid
        elif k=='onsite_observation':
            s=e['scene'];tid=str(s['task']);assert int(a) in s['witnesses'] and set(s['workers']).issubset(s['witnesses'])
            for i in s['witnesses']:
                key=str(i);assert key not in moving and OLD.close(positions[key],catalog['tasks'][tid]['location'])
        elif k=='local_wait_cancel':
            assert a not in moving and a not in locked and own[a]['mode']=='idle' and own[a]['target']==e['target']>=0
            assert OLD.close(positions[a],catalog['tasks'][str(e['target'])]['location'])
        elif k=='refresh_submitted':
            m=by_id[e['message_id']];assert m['publication_reason']=='refresh' and m['source']==e['actor'] and m['enqueued_at']==now
    assert len(finishes)==r['completed'] and r['completion_fraction']==len(finishes)/len(catalog['tasks'])
    assert len(events)+len(service)==r['budget_event_records']
    if r['success']:
        assert len(finishes)==len(catalog['tasks']) and r['returned']==len(catalog['agents'])
        assert all(OLD.close(positions[i],a['depot']) for i,a in catalog['agents'].items())
        assert r['makespan_return']==r['end_time'] and near(r['makespan_to_instant_ratio'],r['makespan_return']/reference['makespan_return'])
    else: assert r['makespan_return'] is None
    metric=r['delivery_metrics'];age=[(d['delivered_at']-by_id[d['message_id']]['body_generated_at'])*20 for d in deliveries]
    latency=[(d['delivered_at']-by_id[d['message_id']]['enqueued_at'])*20 for d in deliveries]
    assert metric['cache_applied']==sum(d['applied'] for d in deliveries) and metric['cache_unchanged']==sum(not d['applied'] for d in deliveries)
    assert near(metric['fact_age_seconds_p95'],percentile(age)) and near(metric['queue_delay_seconds_p95'],percentile(latency))
    return dict(case=row['case_id'],seed=config['seed'],agents=len(catalog['agents']),tasks=len(catalog['tasks']),condition=config['condition'],
        status=r['status'],completed=r['completed'],makespan=r['makespan_return'],ratio_instant=r.get('makespan_to_instant_ratio'),
        decisions=n_dec,information_records=len(info),event_messages=publication['event'],refresh_messages=refresh_count,
        cache_applied=metric['cache_applied'],cache_unchanged=metric['cache_unchanged'],fact_age_p95=metric['fact_age_seconds_p95'],
        refresh_delivery_copies=sum(by_id[d['message_id']]['publication_reason']=='refresh' for d in deliveries),
        refresh_cache_applied=sum(d['applied'] and by_id[d['message_id']]['publication_reason']=='refresh' for d in deliveries),
        queue_delay_p95=metric['queue_delay_seconds_p95'],acquisition_origins=dict(origin_counts),reference_origins=dict(ref_counts),**network)


def check_tasks(report):
    base=ROOT/'simulation/outputs/E2-007/20261026-02-task'
    if not (base/'summary.json').exists(): report['pending'].append('18 task cases not produced');return
    summary,manifest=load(base/'summary.json'),load(base/'manifest.json')
    assert summary['planned']==manifest['full_task_episodes_planned']==18
    assert manifest['seconds_per_model_unit']==20 and manifest['meters_per_model_unit']==100
    assert file_sha(base/'WIRELESS_SERVICE_CONTRACT.md')==manifest['contract_sha256']
    for name,expected in manifest['source_hashes'].items():
        assert file_sha(base/'source'/name)==expected==file_sha(ROOT/'simulation'/name)
    for asset in manifest['assets']: assert file_sha(ROOT/'data/heteromrta/upstream'/asset['path'])==asset['sha256']
    for row in summary['cases']:
        try:
            assert row['executor_sha256']==manifest['source_hashes']['heteromrta_wireless_eval.py']
            report['task_cases'].append(check_task(base,row))
        except Exception as error:
            import traceback
            report['errors'].append(dict(scope='task',case=row['case_id'],error=repr(error),traceback=traceback.format_exc()))
    if len(summary['cases'])!=18: report['pending'].append(dict(task_recorded=len(summary['cases']),expected=18))


def check_diagnostics():
    p=ROOT/'simulation/outputs/E2-007/20261026-03-analysis/mechanism_trace_v2.json'
    if not p.exists(): return []
    output=[]
    for c in load(p)['comparisons']:
        sides={}
        for side,condition in [('left',c['left_condition']),('right',c['right_condition'])]:
            reference=c['sources'][condition];base=Path(reference['path'])
            for name,digest in reference['hashes'].items(): assert file_sha(base/(name+'.json'))==digest
            decisions=load(base/'decisions.json');events=load(base/'events.json');info=load(base/'information_ledger.json')
            messages=load(base/'messages.json');ledger=load(base/'service_ledger.json')
            saved=c[side];index=c['first'][side]['index'];d=decisions[index]
            assert saved['decision']['global_index']==index
            for name,value in d.items():
                if name!='observation': assert saved['decision'][name]==value
            assert saved['decision']['mask']==d['observation'][2][0]
            event=[e for e in events if e['kind']=='decision'][index]
            assert event['id']==saved['decision_event_id']
            previous=[e for e in events if e.get('actor')==d['actor'] and e['id']<event['id'] and e['kind'] in ('own_state','departure','arrival')]
            assert saved['recent_actor_physical_events']==previous[-4:]
            consultation=next(e for e in info if e['id']==saved['consultation_id'])
            refs=[e for e in consultation['references'] if e['object']=='self_state' and e['object_id'] in c['changed_source_versions']]
            assert refs==saved['cache_references']
            facts={e['id']:e for e in info};assert saved['cache_acquisition_records']==[facts[e['fact_id']] for e in refs if e['fact_id']]
            mid={e['message_id']:e for e in messages}
            for package in saved['state_messages']:
                m=mid[package['message_id']];assert json.loads(m['payload_utf8'])==package['body'] and m['enqueued_at']<=d['time']
                expected=[e for e in ledger if e.get('message_id')==m['message_id'] and e['time']<=d['time'] and e['event'] in ('tx_started','tx_completed','replaced','rejected','delivered') and (e['event']!='delivered' or e['recipient']==d['actor'])]
                assert expected==package['service_events']
            sides[side]=(decisions,index,d)
        aa,i,a=sides['left'];bb,j,b=sides['right']
        prefix=lambda seq:[(d['actor'],d['branch'],d['action']) for d in seq]
        assert prefix(aa[:i])==prefix(bb[:j]) and c['prior_global_action_sequence_equal']
        assert a['time']==b['time'] and c['first_decision_times_equal'] and a['action']!=b['action']
        assert c['changed_source_versions']==[int(k) for k in a['source_versions'] if a['source_versions'][k]!=b['source_versions'][k]]
        mask=[dict(action=k,left=x,right=y) for k,(x,y) in enumerate(zip(a['observation'][2][0],b['observation'][2][0])) if x!=y]
        assert mask==c['mask_differences']
        assert a['task_versions']==b['task_versions'] and c['task_versions_equal']
        own=lambda side: next(e['state'] for e in reversed(c[side]['recent_actor_physical_events']) if e['kind']=='own_state')
        assert own('left')==own('right')
        timed=lambda seq:[(d['time'],d['actor'],d['branch'],d['action']) for d in seq]
        output.append(dict(agents=c['agents'],tasks=c['tasks'],left=c['left_condition'],right=c['right_condition'],actor=a['actor'],time=a['time'],left_action=a['action'],right_action=b['action'],mask_differences=mask,changed_sources=c['changed_source_versions'],prior_timed_actions_equal=timed(aa[:i])==timed(bb[:j]),checks='pass'))
    assert len(output)==3
    return output


def check_analysis(report):
    base=ROOT/'simulation/outputs/E2-007/20261026-03-analysis'
    if not (base/'analysis.json').exists(): report['pending'].append('task analysis absent');return
    analysis=load(base/'analysis.json')
    assert file_sha(Path(analysis['input'])/'summary.json')==analysis['input_summary_sha256']
    checked={r['case']:r for r in report['task_cases']}
    rows=list(csv.DictReader(io.StringIO(raw(base/'cases.csv').decode('utf-8-sig'))))
    assert len(rows)==len(analysis['rows'])==18
    mapping=dict(demanded='demanded',delivered='delivered',collided='collided',dropped='dropped',replaced='replaced',coalesced='coalesced',
        pending='pending',recipient_delivered='recipient_delivered',airtime_attempt_us='airtime_attempt_us',channel_busy_us='channel_busy_us',
        cache_applied='cache_applied',cache_unchanged='cache_unchanged',generated_bytes='demand_application_bytes',makespan_model='makespan',
        ratio_instant='ratio_instant',queue_delay_seconds_p95='queue_delay_p95',fact_age_seconds_p95='fact_age_p95')
    for row in rows:
        c=checked[row['case_id']];assert row['status']==c['status']
        for name,key in mapping.items(): assert near(float(row[name]) if row[name] else None,c[key]),name
        assert near(float(row['airtime_us_per_completed_task']),c['airtime_attempt_us']/c['completed'])
    report['analysis_rows_checked']=18


def main():
    report=dict(scope='read-only saved evidence; no new simulation',load_preview=check_preview(),errors=[],pending=[],replay_cases=[],task_cases=[])
    try: report['service_fixtures']=check_micro()
    except Exception as error:
        import traceback
        report['errors'].append(dict(scope='service_fixtures',error=repr(error),traceback=traceback.format_exc()))
    check_replays(report)
    check_tasks(report)
    pre=ROOT/'simulation/outputs/E2-007/20261026-00-preflight'
    pf=load(pre/'preflight.json');freeze=load(pre/'source-freeze.json')
    assert freeze['tests_exit']==0
    assert file_sha(pf['contract_path'])==pf['contract_sha256'] and file_sha(pf['catalog_index_path'])==pf['catalog_index_sha256']
    for item in freeze['sources']: assert file_sha(ROOT/'simulation'/item['name'])==item['sha256']
    tests=raw(pre/'unit-tests.txt').decode();assert 'Ran 7 tests' in tests and '\nOK' in tests
    report['saved_test_counts']=dict(service_unique_tests=17,service_suite_calls=33,execution_micro_tests=7,auditor_test_runs=0)
    try:
        report['mechanism_diagnostics']=check_diagnostics()
        if len(report['task_cases'])==18:
            assert {(r['seed'],r['agents'],r['tasks'],r['condition']) for r in report['task_cases']}=={(s,n,t,c) for s in (5,6) for n,t in ((9,15),(18,30),(36,60)) for c in ('event_fifo','event_latest','refresh_latest')}
            check_analysis(report)
            report['task_totals']={k:sum(r[k] for r in report['task_cases']) for k in ('decisions','information_records','demanded','recipient_delivered','cache_applied','cache_unchanged','refresh_delivery_copies','refresh_cache_applied')}
    except Exception as error:
        import traceback
        report['errors'].append(dict(scope='analysis_or_diagnostics',error=repr(error),traceback=traceback.format_exc()))
    report['reviewed_documents']={}
    for name in ('WIRELESS_SERVICE_CONTRACT.md','WIRELESS_SERVICE_IMPLEMENTATION.md','WIRELESS_EXECUTION_IMPLEMENTATION.md','WIRELESS_EXECUTION_STAGE.md'):
        path=ROOT/'research/agent_native_network'/name
        if path.exists(): report['reviewed_documents'][name]=file_sha(path)
    file_sha(ROOT/'coordination/reviews/C-006-verification.py')
    report['verifier_sha256']=file_sha(__file__)
    report['input_sha256']=HASHES
    Path(__file__).with_suffix('.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(preview=len(report['load_preview']['rows']),fixtures=len(report.get('service_fixtures',[])),replays=len(report['replay_cases']),tasks=len(report['task_cases']),errors=report['errors'],pending=report['pending']),indent=2))
    return 1 if report['errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())
