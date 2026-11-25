"""Held-out return-period sensitivity for the rescue reporting pilot."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from simulation.rescue_reporting import Config, episode, write_csv


def run(output):
    if output.exists() and any(output.iterdir()):raise ValueError('Output must be empty')
    output.mkdir(parents=True,exist_ok=True)
    previous=Path('simulation/results/2026-10-21-rescue-reporting-v1/metrics.csv')
    with previous.open() as f:old=list(csv.DictReader(f))
    key=lambda r:(int(r['reach']),int(r['rate']),int(r['evidence']),int(r['horizon']),r['policy'],int(r['seed']))
    oldmap={key(r):r for r in old};rows=[];selected=[];matches=0
    for reach in (3,6,99):
        for rate in (4000,64000):
            for evidence in (0,65536,524288):
                for horizon in (600,900):
                    for policy in ('return','relay_return'):
                        group=[]
                        for period in (60,120,240):
                            for seed in range(24):
                                row,_=episode(Config(horizon=horizon,reach=reach,rate=rate,evidence=evidence,return_period=period),policy,seed)
                                group.append(row);rows.append(row)
                                if period==120:
                                    prior=oldmap[key(row)]
                                    for k in ('report_auc','discovered','received','distance','contact_wait','after_contact_wait'):
                                        assert abs(row[k]-float(prior[k]))<1e-10
                                    matches+=1
                        scores={period:np.mean([r['report_auc'] for r in group if r['return_period']==period and r['seed']<8]) for period in (60,120,240)}
                        chosen=max(scores,key=lambda p:(scores[p],p))
                        test=[r for r in group if r['return_period']==chosen and r['seed']>=8]
                        control='priority' if policy=='return' else 'relay'
                        controls=[oldmap[reach,rate,evidence,horizon,control,s] for s in range(8,24)]
                        selected.append(dict(reach=reach,rate=rate,evidence=evidence,horizon=horizon,policy=policy,
                                             selected_period=chosen,development_auc=float(scores[chosen]),
                                             heldout_auc=float(np.mean([r['report_auc'] for r in test])),
                                             heldout_discovered=float(np.mean([r['discovered'] for r in test])),
                                             heldout_received=float(np.mean([r['received'] for r in test])),
                                             no_return_policy=control,no_return_auc=float(np.mean([float(r['report_auc']) for r in controls])),
                                             no_return_discovered=float(np.mean([float(r['discovered']) for r in controls])),
                                             heldout_auc_delta=float(np.mean([r['report_auc']-float(c['report_auc']) for r,c in zip(test,controls)]))))
        print('Completed return sensitivity',reach,flush=True)
    write_csv(output/'metrics.csv',rows);write_csv(output/'selected.csv',selected)
    sources=['simulation/rescue_return_sensitivity.py','simulation/rescue_reporting.py','simulation/RESCUE_RETURN_PROTOCOL.md']
    (output/'metadata.json').write_text(json.dumps(dict(records=len(rows),matched_previous=matches,development_seeds=list(range(8)),
        heldout_seeds=list(range(8,24)),source_sha256={s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources}),indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
