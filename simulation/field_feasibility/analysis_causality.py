"""Check paired data isolation and message provenance for all saved runs."""
import argparse
import csv
import gzip
import json
import math
from pathlib import Path


def read(path):
    with gzip.open(path,'rt',encoding='utf8') as f:return json.load(f)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--analysis',default='analysis_v2');args=ap.parse_args()
    root=Path(args.root);cfg=json.loads((root/'config_main.json').read_text(encoding='utf8'));rows=[]
    for n in cfg['node_counts']:
        for seed in cfg['seeds']:
            base=root/f'n{n:02d}'/f'seed-{seed}'; runs={p:read(base/p/'mission.json.gz') for p in cfg['policies']}
            assert runs['A']['samples']==runs['B']['samples'] and runs['A']['trajectory']==runs['B']['trajectory']
            key=lambda x,y,h:(int(math.floor(x/5+.5)),int(math.floor(y/5+.5)),h)
            visited={key(s['x_m'],s['y_m'],s['h_m']) for r in runs.values() for s in r['samples']}
            common=json.loads((base/'common_unvisited_points.json').read_text(encoding='utf8'))
            assert len(common)==48 and all(key(x,y,h) not in visited for x,y,h,t in common)
            for policy,result in runs.items():
                samples={s['sample_id']:s for s in result['samples']}; delivered={}; intent_times={}; summary_times={}
                for event in result['events']:
                    if event['kind']=='SAFETY_FREEZE': continue
                    assert event['created_s']<=event['delivered_s']
                    r=event['receiver']; sender=event['sender']; p=event['payload']; t=event['delivered_s']
                    if event['kind']=='SAMPLE':
                        assert p['sample_id'] in samples and p==samples[p['sample_id']] and p['node_id']==sender and p['t_s']<=event['created_s']
                        k=(r,p['sample_id']);delivered[k]=min(t,delivered.get(k,float('inf')))
                    elif event['kind']=='TASK_INTENT':
                        k=(r,sender,p['target_index'],p['height_m'],p['expires_s']);intent_times[k]=min(t,intent_times.get(k,float('inf')))
                    elif event['kind']=='TASK_UPDATE' and p['status']=='active':
                        assert p['owner']==sender
                        k=(r,sender,p['region_id'],p['height_m'],p['expires_at']);intent_times[k]=min(t,intent_times.get(k,float('inf')))
                    elif event['kind']=='MAP_SUMMARY':
                        k=(r,sender,p['region_id'],p['height_m'],p['expires_at']);summary_times[k]=min(t,summary_times.get(k,float('inf')))
                for d in result['decisions']:
                    node=d['node_id']; now=d['t_s']; own={sid for sid,s in samples.items() if s['node_id']==node and s['t_s']<=now and s['value_dbm'] is not None}
                    seen=set(d['visible_sample_ids']);external=set(d['received_sample_ids'])
                    if policy in ('A','C'): assert seen==own and not external
                    if policy in ('B','D','D_degraded'):
                        assert seen==own|external
                        assert all(delivered.get((node,sid),float('inf'))<=now for sid in external)
                    if policy=='E': assert seen=={sid for sid,s in samples.items() if s['t_s']<=now and s['value_dbm'] is not None}
                    for p in d.get('received_intents',[]) if policy in ('D','D_degraded') else []:
                        k=(node,p['sender'],p['target_index'],p['height_m'],p['expires_s']);assert intent_times.get(k,float('inf'))<=now
                    for p in d.get('received_summaries',[]):
                        k=(node,p['sender'],p['target_index'],p['height_m'],p['expires_s']);assert summary_times.get(k,float('inf'))<=now
                rows.append({'nodes':n,'seed':seed,'policy':policy,'sample_count':len(samples),
                             'decision_count':len(result['decisions']),'delivered_sample_recipients':len(delivered),
                             'common_unvisited_count':len(common),'causal_checks':'pass'})
        print('causality checked N=',n,flush=True)
    with (root/args.analysis/'causality_all_runs.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print('causality checked',len(rows),'runs')

if __name__=='__main__':main()
