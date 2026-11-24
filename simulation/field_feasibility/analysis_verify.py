"""Independent consistency checks on a representative seed at each scale."""
import argparse
import gzip
import json
import math
from pathlib import Path
import numpy as np
from data_v2 import FieldV2
from sampling import sensor_noise,segment_min_distance


def read(path):
    with gzip.open(str(path)+'.gz','rt',encoding='utf8') as f:return json.load(f)


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); ap.add_argument('--data',required=True); ap.add_argument('--analysis',default='analysis')
    args=ap.parse_args(); root=Path(args.root); cfg=json.loads((root/'config_main.json').read_text(encoding='utf8'))
    world=FieldV2(args.data); reports=[]; seed=cfg['seeds'][0]
    for n in cfg['node_counts']:
        base=root/f'n{n:02d}'/f'seed-{seed}'; paired={p:read(base/p/'mission.json') for p in cfg['policies']}
        assert paired['A']['samples']==paired['B']['samples'] and paired['A']['trajectory']==paired['B']['trajectory']
        common=json.loads((base/'common_unvisited_points.json').read_text(encoding='utf8'))
        grid=cfg['evaluation']['grid_m']
        key=lambda x,y,h:(int(math.floor(x/grid+.5)),int(math.floor(y/grid+.5)),float(h))
        visited={key(s['x_m'],s['y_m'],s['h_m']) for r in paired.values() for s in r['samples'] if s['value_dbm'] is not None}
        assert not any(key(x,y,h) in visited for x,y,h,t in common)
        sample_checks=trajectory_segments=0; min_distance=float('inf')
        for name,result in paired.items():
            assert len(result['samples'])==n*20
            for s in result['samples']:
                truth=world.query(s['x_m'],s['y_m'],s['h_m'],s['t_s'])
                expected=truth+sensor_noise(seed,s['node_id'],s['step'],cfg['noise_sigma_db'])
                assert math.isclose(s['value_dbm'],expected,rel_tol=0,abs_tol=1e-10)
                sample_checks+=1
            by_step={step:sorted([p for p in result['trajectory'] if p['step']==step],key=lambda v:v['node_id']) for step in range(20)}
            for step in range(20):
                start=by_step[step]; end=by_step[step+1] if step<19 else [{'x_m':v[0],'y_m':v[1],'h_m':v[2]} for v in result['final_positions']]
                for i in range(n):
                    a=[start[i]['x_m'],start[i]['y_m'],start[i]['h_m']]; b=[end[i]['x_m'],end[i]['y_m'],end[i]['h_m']]
                    assert math.dist(a,b)<=cfg['speed_m_s']*cfg['dt_s']+1e-8
                    trajectory_segments+=1
                    for j in range(i):
                        c=[start[j]['x_m'],start[j]['y_m'],start[j]['h_m']]; d=[end[j]['x_m'],end[j]['y_m'],end[j]['h_m']]
                        distance=segment_min_distance(a,b,c,d); min_distance=min(min_distance,distance)
                        assert distance>=cfg['min_separation_m']-1e-8
            sample_index={s['sample_id']:s for s in result['samples']}
            delivered_time={(e['payload']['sample_id'],e['receiver']):e['delivered_s'] for e in result['events'] if e['kind']=='SAMPLE'}
            for dec in result['decisions']:
                assert all(sample_index[i]['t_s']<=dec['t_s'] for i in dec['visible_sample_ids'])
                if name in ('B','D','D_degraded'):
                    assert all(delivered_time.get((sample_id,dec['node_id']),float('inf'))<=dec['t_s']
                               for sample_id in dec['received_sample_ids'])
        reports.append({'nodes':n,'seed':seed,'policies_checked':list(paired),'sample_value_checks':sample_checks,
                        'trajectory_segments_checked':trajectory_segments,'min_continuous_separation_m':min_distance,
                        'common_unvisited_count':len(common),'ab_samples_and_trajectory_equal':True})
    (root/args.analysis/'representative_verification.json').write_text(json.dumps(reports,indent=2),encoding='utf8')
    print(json.dumps(reports,indent=2))

if __name__=='__main__':main()
