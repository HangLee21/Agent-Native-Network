"""Reproducible seed-level aggregation of completed M-067 phase-4 records."""
from __future__ import annotations
import argparse
import csv
import gzip
import json
import math
from pathlib import Path
import numpy as np
from scipy import stats
from analysis_stats import paired_summary


def readrecord(path):
    compressed=path.parent/(path.name+'.gz')
    if compressed.exists():
        with gzip.open(compressed,'rt',encoding='utf8') as f: return json.load(f)
    return json.loads(path.read_text(encoding='utf8'))


def writecsv(path,rows):
    if not rows: return
    with path.open('w',encoding='utf8',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys()); writer.writeheader(); writer.writerows(rows)


def estimate(values):
    a=np.array([float(x) for x in values if x is not None and x!=''],float)
    if not len(a): return (0,None,None,None,None)
    mean=float(a.mean())
    if len(a)==1: return (1,mean,None,None,None)
    sd=float(a.std(ddof=1)); margin=float(stats.t.ppf(.975,len(a)-1)*sd/math.sqrt(len(a)))
    return (len(a),mean,sd,mean-margin,mean+margin)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--out',default='analysis'); args=ap.parse_args()
    root=Path(args.root); manifest=json.loads((root/'RUN_MANIFEST.json').read_text(encoding='utf8'))
    if manifest['status']!='completed': raise RuntimeError('main matrix is not complete')
    cfg=json.loads((root/'config_main.json').read_text(encoding='utf8'))
    seedrows=[]; summaries=[]; pairs=[]; checkpoint_rows=[]; time_pairs=[]; distance_pairs=[]; height_pairs=[]; temporal_pairs=[]
    for n in cfg['node_counts']:
        nr=root/f'n{n:02d}'
        with (nr/'checkpoints.csv').open(encoding='utf8',newline='') as f: checkpoints=list(csv.DictReader(f))
        with (nr/'distance_checkpoints.csv').open(encoding='utf8',newline='') as f: drows=list(csv.DictReader(f))
        with (nr/'checkpoints_height.csv').open(encoding='utf8',newline='') as f: hrows=list(csv.DictReader(f))
        with (nr/'temporal.csv').open(encoding='utf8',newline='') as f: trows=list(csv.DictReader(f))
        for row in checkpoints: checkpoint_rows.append({'nodes':n,**row})
        for seed in cfg['seeds']:
            independent=readrecord(nr/f'seed-{seed}'/'C'/'mission.json')
            for policy in cfg['policies']:
                folder=nr/f'seed-{seed}'/policy; mission=readrecord(folder/'mission.json')
                samples=[s for s in mission['samples'] if s['value_dbm'] is not None]
                cells=[(int(math.floor(s['x_m']/5+.5)),int(math.floor(s['y_m']/5+.5)),s['h_m']) for s in samples]
                cells_t=[(*cell,s['t_s']) for cell,s in zip(cells,samples)]
                xmin,ymin,xmax,ymax=cfg['region_m']; grid=cfg['evaluation']['grid_m']
                spatial_cells=(int((xmax-xmin)/grid)+1)*(int((ymax-ymin)/grid)+1)
                time_steps=int(math.ceil(cfg['duration_s']/cfg['dt_s']))
                cadence_support=spatial_cells*len(cfg['heights_m'])*time_steps
                network=readrecord(folder/'network.json')['metrics'] if policy in ('B','D','D_degraded') else None
                net=network['total'] if network else None
                main=[r for r in checkpoints if int(r['seed'])==seed and r['policy']==policy and int(r['step'])==cfg['evaluation_steps'][-1]][0]
                decisions=[d for d in mission['decisions'] if d['selected_target_index'] is not None]
                row={'nodes':n,'seed':seed,'policy':policy,'sample_count':len(samples),
                     'distinct_spatial_cells':len(set(cells)),
                     'distinct_space_time_cells':len(set(cells_t)),
                     'cadence_domain_space_time_cells':cadence_support,
                     'unique_cadence_domain_fraction':len(set(cells_t))/cadence_support,
                     'spatial_revisit_fraction':(len(cells)-len(set(cells)))/len(cells) if cells else None,
                     'space_time_duplicate_fraction':(len(cells_t)-len(set(cells_t)))/len(cells_t) if cells_t else None,
                     'flight_distance_m':sum(mission['flight_distance_m']),
                     'safety_freeze_steps':sum(e['kind']=='SAFETY_FREEZE' for e in mission['events']),
                     'decision_count':len(decisions),
                     'changed_from_no_messages':sum(d['selected_target_index']!=d['local_counterfactual_index'] for d in decisions),
                     'position_steps_changed_vs_C':sum(any(abs(r[k]-c[k])>1e-9 for k in ('x_m','y_m','h_m'))
                                                       for r,c in zip(mission['trajectory'],independent['trajectory'])) if policy in ('D','D_degraded') else None,
                     'sent_bytes':net['tx_bytes'] if net else 0,
                     'received_bytes':net['rx_bytes'] if net else 0,
                     'mission_duration_s':cfg['duration_s'],
                     'last_sample_time_s':max(s['t_s'] for s in samples) if samples else None,
                     'network_pdr':net['pdr'] if net else None,'network_delivered':net['delivered'] if net else 0,
                     'network_dropped':net['dropped'] if net else 0,'network_pending':net['pending'] if net else 0,
                     'network_mean_latency_s':net['mean_latency_s'] if net else None,
                     'network_connectivity_ratio':network['connectivity_ratio'] if network else None,
                     'network_partition_duration_s':network['partition_duration_s'] if network else None,
                     'network_mean_degree':network['average_node_degree'] if network else None,
                     'offline_rmse_db':float(main['offline_rmse_db']) if main['offline_rmse_db'] else None,
                     'masked_blind_rmse_db':float(main['masked_blind_rmse_db']) if main['masked_blind_rmse_db'] else None,
                     'online_mean_rmse_db':float(main['online_mean_rmse_db']) if main['online_mean_rmse_db'] else None,
                     'blind_exact_floor_count':int(main['blind_exact_floor_count'])}
                seedrows.append(row)
        subset=[r for r in seedrows if r['nodes']==n]
        for policy in cfg['policies']:
            subsetp=[r for r in subset if r['policy']==policy]
            for metric in ['offline_rmse_db','masked_blind_rmse_db','online_mean_rmse_db','unique_cadence_domain_fraction','spatial_revisit_fraction',
                           'space_time_duplicate_fraction','flight_distance_m','sent_bytes','received_bytes','network_pdr',
                           'network_mean_latency_s','network_connectivity_ratio','network_partition_duration_s','network_mean_degree',
                           'safety_freeze_steps','changed_from_no_messages','position_steps_changed_vs_C']:
                count,mean,sd,lo,hi=estimate([r[metric] for r in subsetp])
                summaries.append({'nodes':n,'policy':policy,'metric':metric,'seed_count':count,'mean':mean,'sd':sd,'ci95_low':lo,'ci95_high':hi})
        for a,b in [('D','C'),('B','A'),('D','E'),('D_degraded','D')]:
            for metric in ['offline_rmse_db','masked_blind_rmse_db','online_mean_rmse_db','spatial_revisit_fraction','flight_distance_m','sent_bytes']:
                aa={r['seed']:r[metric] for r in subset if r['policy']==a}; bb={r['seed']:r[metric] for r in subset if r['policy']==b}
                s=paired_summary(aa,bb)
                pairs.append({'nodes':n,'comparison':a+' minus '+b,'metric':metric,'seed_count':s['n'],
                              'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                              'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                              'paired_t_p':s['paired_t_p']})
        for fraction in [.5,1.]:
            for a,b in [('D','C'),('D_degraded','D')]:
                for metric in ['offline_rmse_db','masked_blind_rmse_db','unused_distance_m','t_s']:
                    aa={int(r['seed']):float(r[metric]) for r in drows if r['policy']==a and float(r['fraction_of_shared_ceiling'])==fraction and r[metric]}
                    bb={int(r['seed']):float(r[metric]) for r in drows if r['policy']==b and float(r['fraction_of_shared_ceiling'])==fraction and r[metric]}
                    s=paired_summary(aa,bb)
                    distance_pairs.append({'nodes':n,'fraction_of_common_ceiling':fraction,'comparison':a+' minus '+b,'metric':metric,
                                           'seed_count':s['n'],'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                                           'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                                           'paired_t_p':s['paired_t_p']})
        for step in cfg['evaluation_steps']:
            for a,b in [('D','C'),('B','A'),('D_degraded','D')]:
                for metric in ['offline_rmse_db','masked_blind_rmse_db','online_mean_rmse_db','distance_m']:
                    aa={int(r['seed']):float(r[metric]) for r in checkpoints if r['policy']==a and int(r['step'])==step and r[metric]}
                    bb={int(r['seed']):float(r[metric]) for r in checkpoints if r['policy']==b and int(r['step'])==step and r[metric]}
                    s=paired_summary(aa,bb)
                    time_pairs.append({'nodes':n,'step':step,'t_s':step*cfg['dt_s'],'comparison':a+' minus '+b,'metric':metric,
                                       'seed_count':s['n'],'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                                       'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                                       'paired_t_p':s['paired_t_p']})
        for h in cfg['heights_m']:
            for a,b in [('D','C'),('D_degraded','D')]:
                aa={int(r['seed']):float(r['rmse_db']) for r in hrows if r['policy']==a and float(r['height_m'])==h and int(r['step'])==cfg['evaluation_steps'][-1] and r['rmse_db']}
                bb={int(r['seed']):float(r['rmse_db']) for r in hrows if r['policy']==b and float(r['height_m'])==h and int(r['step'])==cfg['evaluation_steps'][-1] and r['rmse_db']}
                s=paired_summary(aa,bb)
                height_pairs.append({'nodes':n,'height_m':h,'comparison':a+' minus '+b,'metric':'offline_rmse_db',
                                     'seed_count':s['n'],'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                                     'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                                     'paired_t_p':s['paired_t_p']})
        for a,b in [('D','C'),('D_degraded','D')]:
            for from_step,to_step in zip(cfg['evaluation_steps'],cfg['evaluation_steps'][1:]):
                start=from_step*cfg['dt_s']; end=to_step*cfg['dt_s']
                aa={int(r['seed']):float(r['temporal_delta_mae_db']) for r in trows if r['policy']==a and float(r['from_s'])==start and float(r['to_s'])==end and r['temporal_delta_mae_db']}
                bb={int(r['seed']):float(r['temporal_delta_mae_db']) for r in trows if r['policy']==b and float(r['from_s'])==start and float(r['to_s'])==end and r['temporal_delta_mae_db']}
                s=paired_summary(aa,bb)
                temporal_pairs.append({'nodes':n,'from_s':start,'to_s':end,'comparison':a+' minus '+b,
                                       'seed_count':s['n'],'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                                       'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                                       'paired_t_p':s['paired_t_p']})
    target=root/args.out; target.mkdir(exist_ok=False)
    for name,data in [('per_seed.csv',seedrows),('summary.csv',summaries),('paired.csv',pairs),
                      ('paired_time.csv',time_pairs),('paired_distance.csv',distance_pairs),('paired_height.csv',height_pairs),
                      ('paired_temporal.csv',temporal_pairs),('all_checkpoints.csv',checkpoint_rows)]: writecsv(target/name,data)
    print('Analyzed',len(seedrows),'runs; comparisons are seed-level; no multiplicity correction')

if __name__=='__main__': main()
