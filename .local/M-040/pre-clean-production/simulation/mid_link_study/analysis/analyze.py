"""Identity-based statistics for normalized M-021 software simulation events.

The producer-specific adapter must retain original source references. This module
does not simulate packets, query future topology for a strategy, or run a solver.
"""
from collections import Counter, defaultdict
import math
try:
    from . import metrics
except ImportError:
    import metrics


def analyze(context,events,truth=None):
    if context.get('evidence_kind')!='software_simulation':
        raise ValueError('explicit software_simulation context required')
    if context['duration_s']!=60 or context['interval_s']!=.5 or context['payload_bytes']!=32:
        raise ValueError('separate non-M021 workload rather than mix the batch')
    issues=[];packets={};by_id={};annotations=[]
    flows=context['flows'];start=context.get('start_s',0);end=start+60
    for direction,flow in enumerate(flows):
        for slot in range(120):
            packets[(direction,slot)]=dict(direction=direction,src=flow['src'],dst=flow['dst'],slot=slot,
                planned_s=start+slot*.5,generated=False,packet_id=None,delivered=False,
                attempts=[],forwarding_events=[],receive_events=[],route_decisions=[],terminal_reason=None,source_refs=[])
    publications=[];installs=[];control=[]
    for event in sorted(events,key=lambda e:e['t_s']):
        t=event['t_s'];kind=event['event'];ref=event.get('source')
        if not isinstance(t,(int,float)) or not math.isfinite(t):
            issues.append('invalid_simulated_time');continue
        if kind in ('config_publish','config_install','control_tx','control_rx','solve_start','solve_end','detected','topology_change','observation','route_selected','keep_previous_table','control_drop','control_duplicate','control_not_member'):
            annotations.append(event)
            if kind=='config_publish':publications.append(event)
            elif kind=='config_install':installs.append(event)
            elif kind in ('control_tx','control_rx'):control.append(event)
            continue
        if kind=='generate':
            key=(event['direction'],event['slot'])
            if key not in packets:issues.append('source_outside_fixed_plan');continue
            row=packets[key];identity=(event['src'],event['dst'],str(event['packet_id']))
            if row['generated'] or identity in by_id:issues.append('duplicate_source_identity');continue
            if event['src']!=row['src'] or event['dst']!=row['dst'] or event.get('payload_bytes',32)!=32:
                issues.append('source_workload_mismatch');continue
            row.update(generated=True,generated_s=t,packet_id=str(event['packet_id']),payload_tag=event.get('payload_tag'))
            row['source_refs'].append(ref);by_id[identity]=key
            if truth:row['reachable_at_generate']=truth(t,row['src'],row['dst'])
            continue
        if kind not in ('tx_attempt','forward','relay_rx','destination_rx','drop','expire','queue_drop','source_admitted','forward_decision'):
            continue
        identity=(event['src'],event['dst'],str(event['packet_id']))
        key=by_id.get(identity)
        if key is None:issues.append('event_without_source_identity');continue
        row=packets[key];row['source_refs'].append(ref)
        if kind=='tx_attempt':
            attempt=dict(event)
            if truth:attempt['optimistic_path_exists']=truth(t,row['src'],row['dst'])
            published=[p for p in publications if p['t_s']<=t]
            attempt['behind_latest_published_table']=(event.get('route_version')!=published[-1].get('version')) if published and event.get('route_version') is not None else None
            row['attempts'].append(attempt)
        elif kind in ('forward','relay_rx'):
            row['forwarding_events'].append(event)
            if kind=='relay_rx':row['receive_events'].append(event)
        elif kind=='forward_decision':row['route_decisions'].append(event)
        elif kind=='source_admitted':row['source_admitted_s']=t
        elif kind=='destination_rx':
            if event.get('node')!=row['dst']:
                issues.append('receive_not_destination');continue
            if row.get('payload_tag') is not None and event.get('payload_tag')!=row['payload_tag']:
                issues.append('destination_payload_tag_mismatch');continue
            if row['delivered']:
                row['duplicate_destination_rows']=row.get('duplicate_destination_rows',0)+1
            else:
                row.update(delivered=True,received_s=t,delivered_in_window=start<=t<end)
        else:
            row.update(terminal_reason=event.get('reason',kind),terminal_s=t)
            if truth:row['reachable_at_terminal']=truth(t,row['src'],row['dst'])
    if sum(p['generated'] for p in packets.values())!=240:issues.append('source_schedule_incomplete')
    known=context.get('capture_complete') is True and not issues
    seconds=[];directions=[];evaluation=context.get('evaluation',{})
    for direction,flow in enumerate(flows):
        rows=[packets[(direction,s)] for s in range(120)]
        for second in range(60):
            low=start+second;high=low+1
            delivered=[p for p in rows if p['delivered'] and low<=p['received_s']<high]
            tx=[e for p in rows for e in p['attempts'] if low<=e['t_s']<high]
            seconds.append(dict(direction=direction,second=second,
                planned_count=2,generated_observed=sum(p['generated'] and low<=p['generated_s']<high for p in rows),
                attempts_observed=len(tx),unique_delivered_observed=len(delivered),
                unique_delivered=len(delivered) if known else None,
                goodput_bps=len(delivered)*256 if known else None,
                reachable_at_bin_start=truth(low,flow['src'],flow['dst']) if truth else None,
                coverage_status='confirmed_simulation' if known else 'unknown'))
        bins=[s['goodput_bps'] for s in seconds if s['direction']==direction]
        decomposition=Counter()
        for p in rows:
            p['delivery_status']='destination_received' if p['delivered'] else 'not_received_in_capture' if known else 'unknown_coverage'
            p['actual_received_path']=[p['src']]+[e['node'] for e in p['receive_events']]
            p['actual_path_complete']=p['delivered'] and p['actual_received_path'][-1]==p['dst']
            if not p.get('delivered_in_window',False):
                reason='late_after_window' if p['delivered'] else p['terminal_reason'] or 'pending_at_end'
                decomposition[(reason,p.get('reachable_at_generate'),p.get('reachable_at_terminal'))]+=1
        impact=evaluation.get('impact_start_s');anchor=evaluation.get('recovery_anchor_s')
        post=sum(v for i,v in enumerate(bins) if v is not None and impact is not None and i>=math.ceil(impact-start)) if known and impact is not None else None
        directions.append(dict(direction=direction,src=flow['src'],dst=flow['dst'],planned=120,
            generated_observed=sum(p['generated'] for p in rows),delivered_observed=sum(p['delivered'] for p in rows),
            delivered_in_window=sum(p.get('delivered_in_window',False) for p in rows),
            late_after_window=sum(p['delivered'] and p['received_s']>=end for p in rows),
            missing=metrics.longest_unreceived([dict(slot=p['slot'],delivered=p.get('delivered_in_window',False)) for p in rows],known),
            recovery=metrics.recovery(bins,impact-start if impact is not None else None,anchor-start if anchor is not None else None) if known else dict(status='unknown',reason='incomplete_capture'),
            post_impact_payload_bits=post,
            loss_observations=[dict(terminal_reason=k[0],reachable_at_generate=k[1],reachable_at_terminal=k[2],count=n) for k,n in sorted(decomposition.items(),key=lambda x:str(x[0]))]))
    layer=context.get('control_bytes_layer')
    for second in range(60):
        lo=start+second;hi=lo+1
        for direction in range(len(flows)):
            row=seconds[direction*60+second]
            row.update(config_publish_count=sum(lo<=e['t_s']<hi for e in publications),
                       config_install_count=sum(lo<=e['t_s']<hi for e in installs),
                       control_tx_bytes=sum(e['bytes'] for e in control if e['event']=='control_tx' and lo<=e['t_s']<hi) if layer else None,
                       control_bytes_layer=layer)
    return dict(schema='mid.link.analysis.v1',evidence_kind='software_simulation',run_id=context['run_id'],
        scenario_id=context['scenario_id'],seed=context['seed'],arm=context['arm'],metrics_valid=known,
        issues=sorted(set(issues)),shared_inputs=context.get('shared_inputs',{}),context=context,
        packets=list(packets.values()),seconds=seconds,directions=directions,annotations=annotations,
        control=dict(publications=len(publications),installs=len(installs),tx_bytes=sum(e['bytes'] for e in control if e['event']=='control_tx') if layer else None,bytes_layer=layer),
        limitations=['True topology is post-hoc optimistic reachability only, not policy input or causal blame.','Per-direction rows repeat global control counters; do not sum them across directions.','Software simulation, no measured RF or device clocks.'])


def paired(runs):
    groups=defaultdict(dict)
    for run in runs:
        key=(run['scenario_id'],run['seed'])
        if run['arm'] in groups[key]:raise ValueError('duplicate scenario/seed/arm')
        groups[key][run['arm']]=run
    pairs=[]
    for (scenario,seed),arms in sorted(groups.items()):
        if set(arms)!=set(('fixed','adaptive')):
            pairs.append(dict(scenario_id=scenario,seed=seed,status='missing_arm'));continue
        fixed,new=arms['fixed'],arms['adaptive']
        inputs=fixed['shared_inputs'];required={'scenario_sha256','source_plan_sha256','initial_table_sha256','channel_draw_index','delay_model'}
        matched=required<=set(inputs) and inputs==new['shared_inputs']
        valid=fixed['metrics_valid'] and new['metrics_valid']
        directions=[]
        for a,b in zip(fixed['directions'],new['directions']):
            directions.append(dict(direction=a['direction'],delivery_difference_adaptive_minus_fixed=b['delivered_in_window']-a['delivered_in_window'] if matched and valid else None,
                post_impact_payload_bits_difference=b['post_impact_payload_bits']-a['post_impact_payload_bits'] if matched and valid and a['post_impact_payload_bits'] is not None and b['post_impact_payload_bits'] is not None else None,
                fixed_recovery=a['recovery'],adaptive_recovery=b['recovery']))
        pairs.append(dict(scenario_id=scenario,seed=seed,status='matched' if matched and valid else 'capture_unknown' if not valid else 'shared_inputs_unknown_or_mismatch',directions=directions,
            control_publication_difference=new['control']['publications']-fixed['control']['publications'],
            control_tx_bytes_difference=new['control']['tx_bytes']-fixed['control']['tx_bytes'] if new['control']['tx_bytes'] is not None and fixed['control']['tx_bytes'] is not None else None))
    summary=[]
    for scenario in sorted({r['scenario_id'] for r in runs}):
        for direction in range(2):
            eligible=[p['directions'][direction] for p in pairs if p['scenario_id']==scenario and p['status']=='matched']
            summary.append(dict(scenario_id=scenario,direction=direction,delivery_difference=metrics.distribution([p['delivery_difference_adaptive_minus_fixed'] for p in eligible]),
                                post_impact_payload_bits_difference=metrics.distribution([p['post_impact_payload_bits_difference'] for p in eligible])))
    return dict(schema='mid.link.pairs.v1',evidence_kind='software_simulation',pairs=pairs,summary=summary)
