"""Re-score saved node-visible histories, raw and blind-floor-excluded."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import numpy as np
from analysis import observations_at,score
from analysis_stats import paired_summary
from data_v2 import FieldV2


def write(path,rows):
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--data',required=True);ap.add_argument('--analysis',default='analysis_v2');args=ap.parse_args()
    root=Path(args.root);out=root/args.analysis;cfg=json.loads((root/'config_main.json').read_text(encoding='utf8'))
    field=FieldV2(args.data); step=cfg['evaluation_steps'][-1]; t=step*cfg['dt_s']; rows=[]; differences=[]
    for n in cfg['node_counts']:
        for seed in cfg['seeds']:
            base=root/f'n{n:02d}'/f'seed-{seed}'
            common=json.loads((base/'common_unvisited_points.json').read_text(encoding='utf8'))
            queries=[[x,y,h,t] for x,y,h,_ in common]; truth=[field.query(*q) for q in queries]
            masked=[float('nan') if v==cfg['repeated_floor_dbm'] else v for v in truth]
            for policy in cfg['policies']:
                with gzip.open(base/policy/'mission.json.gz','rt',encoding='utf8') as f:r=json.load(f)
                raw=[];sens=[]
                for node in range(n):
                    obs=observations_at(r,node,step)
                    raw.append(score(queries,truth,obs)['rmse_db']);sens.append(score(queries,masked,obs)['rmse_db'])
                rows.append({'nodes':n,'seed':seed,'policy':policy,'t_s':t,'blind_support':len(truth),
                             'excluded_floor_count':len(truth)-sum(np.isfinite(masked)),
                             'raw_online_mean_rmse_db':float(np.mean(raw)),
                             'masked_online_mean_rmse_db':float(np.mean(sens)) if all(v is not None for v in sens) else None})
        for a,b in [('D','C'),('B','A'),('D_degraded','D')]:
            for metric in ['raw_online_mean_rmse_db','masked_online_mean_rmse_db']:
                aa={r['seed']:r[metric] for r in rows if r['nodes']==n and r['policy']==a}
                bb={r['seed']:r[metric] for r in rows if r['nodes']==n and r['policy']==b}
                s=paired_summary(aa,bb)
                differences.append({'nodes':n,'comparison':a+' minus '+b,'metric':metric,'seed_count':s['n'],
                                    'mean_difference':s['mean_difference'],'sd_difference':s['sd_difference'],
                                    'ci95_low':s['ci95'][0] if s['ci95'] else None,'ci95_high':s['ci95'][1] if s['ci95'] else None,
                                    'paired_t_p':s['paired_t_p']})
        print('scored N=',n,flush=True)
    write(out/'online_floor_sensitivity.csv',rows);write(out/'online_floor_paired.csv',differences)

if __name__=='__main__':main()
