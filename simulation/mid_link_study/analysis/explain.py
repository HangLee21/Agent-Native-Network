"""Supplement cached E2 counts with raw failure/route/cost evidence; no rerun."""
import argparse,collections,datetime,hashlib,json,math,sys
from pathlib import Path
try:
    from . import metrics
except ImportError:
    import metrics

ROOT=Path(__file__).resolve().parents[3]
def read(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)


def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--output',required=True);args=p.parse_args()
    dataset=read(args.dataset);out=Path(args.output).resolve();assert out.is_relative_to(ROOT/'simulation/outputs/E2-019') and not out.exists();out.mkdir(parents=True)
    detail=[];all_runs=[];flow_summaries=[];costs=collections.defaultdict(collections.Counter)
    for ref in dataset['runs']:
        run=read(ref['path']);all_runs.append(run);source=run['source_files']['events.jsonl'];raw=Path(source['path']).read_bytes();assert hashlib.sha256(raw).hexdigest()==source['sha256']
        rows=[json.loads(x) for x in raw.splitlines()];by_packet=collections.defaultdict(list);route_draw_checks=0;bad_draws=[]
        for line,e in enumerate(rows,1):
            if 'packet_id'in e:by_packet[e['packet_id']].append((line,e))
            if e['event']=='route_selected':
                parts=[run['seed'],run['scenario_id'],'route',e['node'],e['epoch'],e['flow']];key=json.dumps(parts,separators=(',',':'));draw=int.from_bytes(hashlib.sha256(key.encode()).digest()[:8],'big')/2**64
                if not math.isclose(draw,e['draw'],abs_tol=1e-15) or e['epoch']!=int(round(e['t_s']*2)):bad_draws.append(line)
                route_draw_checks+=1
        assert not bad_draws
        packets=[];counts=collections.Counter();unavailable=collections.Counter();old_table=collections.Counter()
        for packet in run['packets']:
            history=by_packet[packet['packet_id']];links=[(line,e) for line,e in history if e['event']=='link_result' and e['kind']=='data'];last=links[-1] if links else None
            reason=packet['terminal_reason'];cls='delivered' if packet.get('delivered_in_window') else 'late_after_window' if packet['delivered'] else 'pending_at_end'
            if not packet['delivered']:
                if reason=='link_failure_or_zero_service':cls='zero_probability_or_service_link_attempt' if last and last[1]['p_success']==0 else 'positive_probability_link_failure'
                elif reason=='duplicate_64_cache':cls='loop_revisit_cache_drop' if len(set(packet['actual_received_path']))<len(packet['actual_received_path']) else 'duplicate_cache_drop'
                elif reason=='edge_unavailable_at_arrival':cls='edge_unavailable_during_propagation'
                elif reason=='no_installed_next_hop':cls='no_selected_next_hop'
                elif reason=='TTL':cls='TTL'
                elif reason:cls=reason
            counts[cls]+=1
            if not packet.get('delivered_in_window'):
                unavailable[str(packet.get('reachable_at_terminal'))]+=1
                old_table[str(any(a.get('behind_latest_published_table') is True for a in packet['attempts']))]+=1
            packets.append(dict(packet_id=packet['packet_id'],src=packet['src'],dst=packet['dst'],slot=packet['slot'],terminal_class=cls,
                actual_received_path=packet['actual_received_path'],reachable_at_generate=packet.get('reachable_at_generate'),reachable_at_terminal=packet.get('reachable_at_terminal'),
                any_attempt_behind_latest_published_table=any(a.get('behind_latest_published_table') is True for a in packet['attempts']),
                last_link_probability=last[1]['p_success'] if last else None,last_link_result_source=dict(path=source['path'],line=last[0]) if last else None,
                terminal_source=next((dict(path=source['path'],line=line) for line,e in reversed(history) if e['event'] in ['drop','queue_drop']),None)))
        recoveries=[]
        for direction in run['directions']:
            rec=direction['recovery'];after=rec.get('recovery_window_end_s');threshold=rec.get('threshold_bps')
            relapse=[s['second'] for s in run['seconds'] if s['direction']==direction['direction'] and after is not None and s['second']>=after and s['goodput_bps'] is not None and s['goodput_bps']<threshold]
            recoveries.append(dict(direction=direction['direction'],original_recovery=rec,subthreshold_seconds_after_first_confirmation=relapse,first_confirmation_is_not_permanent=bool(relapse)))
        cost=collections.Counter(publications=run['control']['publications'],control_tx_bytes=run['control']['tx_bytes'],initial_installs=sum(e.get('initial') is True for e in run['annotations'] if e['event']=='config_install'),dynamic_installs=sum(not e.get('initial') for e in run['annotations'] if e['event']=='config_install'))
        costs[run['scenario_id'],run['arm']].update(cost)
        detail.append(dict(run_id=run['run_id'],scenario_id=run['scenario_id'],seed=run['seed'],arm=run['arm'],source_events=source,route_random_checks=route_draw_checks,packet_details=packets,
            terminal_class_counts=dict(counts),undelivered_terminal_snapshot_reachability=dict(unavailable),
            undelivered_ever_behind_publication=dict(old_table),recovery_interpretation=recoveries,
            limitation='Behind-publication is exposure, not sole causal blame; control may not have reached node. Positive path does not guarantee capacity or delivery.'))
    aggregate=[]
    for sid in ['gradual_link','relay_exit','partition_restore']:
        chosen=[r for r in all_runs if r['scenario_id']==sid];arms={arm:[r for r in chosen if r['arm']==arm] for arm in ['fixed','adaptive']};pairs=[]
        for seed in [11,23,37,53,71]:
            pair={r['arm']:r for r in chosen if r['seed']==seed};f,n=pair['fixed'],pair['adaptive'];pairs.append(dict(seed=seed,fixed=sum(d['delivered_in_window'] for d in f['directions']),adaptive=sum(d['delivered_in_window'] for d in n['directions']),difference=sum(d['delivered_in_window'] for d in n['directions'])-sum(d['delivered_in_window'] for d in f['directions'])))
        summary=dict(scenario_id=sid,planned_per_arm=1200,received={a:sum(d['delivered_in_window'] for r in rs for d in r['directions']) for a,rs in arms.items()},
            pairs=pairs,delivery_difference_distribution=metrics.distribution([p['difference'] for p in pairs]),cost={a:dict(costs[sid,a]) for a in arms},
            terminal_classes={a:dict(sum((collections.Counter(d['terminal_class_counts']) for d in detail if d['scenario_id']==sid and d['arm']==a),collections.Counter())) for a in arms})
        aggregate.append(summary)
        for direction in [0,1]:
            flow_summaries.append(dict(scenario_id=sid,direction=direction,
                recovery={a:metrics.distribution([r['directions'][direction]['recovery'].get('recovery_s') for r in rs if r['directions'][direction]['recovery']['status'] in ['recovered','no_interruption']]) for a,rs in arms.items()},
                note='First three-window threshold confirmation may relapse; see per-run flags. Never mix directions into ten independent seeds.'))
    engine=sha(ROOT/'simulation/mid_link_study/engine/run.py');formal=read(ROOT/'simulation/outputs/E1-019/20261107-02-first-pair/INDEX.json');assert engine==formal['engine_sha256'];assert len(all_runs)==30 and sum(len(r['packets']) for r in all_runs)==7200
    write(out/'event-decomposition.json',dict(evidence_kind='software_simulation',runs=detail));write(out/'scenario-summary.json',aggregate);write(out/'recovery-summary.json',flow_summaries)
    copied=dict(dataset,event_decomposition=str(out/'event-decomposition.json'),scenario_summary=str(out/'scenario-summary.json'),recovery_summary=str(out/'recovery-summary.json'),source_core_dataset=dict(path=str(Path(args.dataset).resolve()),sha256=sha(Path(args.dataset))),formal_source_scope='E1-019/02-first-pair +03-rest-batch only; E1/01 and E2/04 excluded')
    write(out/'DATASET.json',copied)
    m=read(ROOT/'coordination/templates/RUN_MANIFEST.json');m.update(template_only=False,task_id='E2-019',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),python_executable=sys.executable,command=sys.argv,output_directory=str(out),status='formal_batch_explained',exit_code=0,budget=dict(new_raw_core_analysis=0,cached_runs=30,hardware_operations=0),dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__))},data_and_weights_sha256={str(Path(args.dataset).resolve()):sha(Path(args.dataset))},limitations=['Read raw events for additional loss evidence only; cached packet/second/pair counts not recomputed.','First threshold recovery may be temporary; relapse flags preserve this.','SOCP stochastic routes can loop despite PDR1; no generic stale-route attribution.']);write(out/'RUN_MANIFEST.json',m)
    print(json.dumps(aggregate))


if __name__=='__main__':main()
