"""Read-only reconciliation of E2-045 published pair table and summaries."""
import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from scipy import stats


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--e2',required=True);ap.add_argument('--out',required=True);args=ap.parse_args()
    root=Path(args.e2); pairs=root/'pairs.csv'; summary=root/'summary.json'; manifest=root/'RUN_MANIFEST.json'
    with pairs.open(encoding='utf8',newline='') as f: rows=list(csv.DictReader(f))
    reports=json.loads(summary.read_text(encoding='utf8')); run=json.loads(manifest.read_text(encoding='utf8'))
    assert run['status']=='completed' and len(rows)==80
    result=[]
    for n in [5,10,20,30]:
        group=[r for r in rows if int(r['nodes'])==n]; assert len(group)==20
        assert {int(r['seed']) for r in group}==set(range(2000,2020)) and all(r['status']=='completed' for r in group)
        assert all(abs(float(r['distance_difference_m']))<1e-6 and int(r['sample_difference'])==0 and float(r['time_difference_s'])==0 for r in group)
        expected=next(s for s in reports if s['nodes']==n); metrics={}
        for col,expected_key in [('delta_offline_rmse','mean_D_minus_C_rmse'),('delta_floor_excluded_rmse','floor_excluded_mean_D_minus_C_rmse')]:
            x=[float(r[col]) for r in group];mean=statistics.mean(x);sd=statistics.stdev(x);margin=stats.t.ppf(.975,19)*sd/math.sqrt(20)
            assert abs(mean-expected[expected_key])<1e-10
            metrics[col]={'mean':mean,'sd':sd,'ci95':[mean-margin,mean+margin]}
        result.append({'nodes':n,'pairs':len(group),'max_abs_distance_difference_m':max(abs(float(r['distance_difference_m'])) for r in group),
                       'metrics':metrics})
    h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    data={'status':'pass_saved_pair_summary_checks','scope':'verify 80 saved pair rows, reported budgets and paired means; not an independent trajectory or model recomputation',
          'inputs_sha256':{p.name:h(p) for p in [pairs,summary,manifest]},'results':result}
    Path(args.out).write_text(json.dumps(data,indent=2),encoding='utf8')
    print(json.dumps(data,indent=2))

if __name__=='__main__':main()
