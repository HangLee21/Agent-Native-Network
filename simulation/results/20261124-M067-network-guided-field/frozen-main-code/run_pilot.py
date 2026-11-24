"""Run the preregistered V2 frozen-frame pilot, only after Phase 0 release."""
from __future__ import annotations
import argparse
import csv
import gzip
import hashlib
import json
import os
import platform
import shutil
import sys
from datetime import datetime
from pathlib import Path

os.environ['OPENBLAS_NUM_THREADS']='1'
os.environ['OMP_NUM_THREADS']='1'
import numpy as np
import scipy
from mission import simulate
from mission_transport import MissionTransport
from analysis import observations_at,score,reconstruct
from analysis_stats import trajectory_distances


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,obj): p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf8')
def save_record(p,obj,compressed):
    if compressed:
        payload=json.dumps(obj,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf8')
        with (p.parent/(p.name+'.gz')).open('wb') as raw:
            with gzip.GzipFile(fileobj=raw,mode='wb',mtime=0,compresslevel=3) as f: f.write(payload)
    else: save(p,obj)
def dumpcsv(p,rows):
    if rows:
        with p.open('w',encoding='utf8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=rows[0]); w.writeheader(); w.writerows(rows)


def cell(x,y,h,grid):
    return (int(np.floor(x/grid+0.5)),int(np.floor(y/grid+0.5)),float(h))


class FrozenField:
    def __init__(self,field,frame): self.field=field; self.frame=frame
    def query(self,x,y,h,t): return self.field.query(x,y,h,self.frame)


def eval_points(cfg,t,results):
    xmin,ymin,xmax,ymax=cfg['region_m']; n=cfg['evaluation']['points_per_height']
    grid=cfg['evaluation']['grid_m']; spacing=cfg['evaluation']['candidate_spacing_m']
    visited={cell(s['x_m'],s['y_m'],s['h_m'],grid) for r in results.values() for s in r['samples'] if s['value_dbm'] is not None}
    output=[]
    for h in cfg['heights_m']:
        available=[(x,y) for x in range(int(xmin),int(xmax)+1,int(spacing))
                   for y in range(int(ymin),int(ymax)+1,int(spacing)) if cell(x,y,h,grid) not in visited]
        if len(available)<n: raise RuntimeError('not enough common unvisited evaluation cells')
        for i in np.rint(np.linspace(0,len(available)-1,n)).astype(int):
            x,y=available[i]; output.append([x,y,h,t])
    return output


def readiness(root):
    ready=root/'data_ready.json'; audit=Path('research/agent_native_network/field_feasibility/DATA_AUDIT.md')
    if not ready.is_file() or not audit.is_file(): raise RuntimeError('V2 audit/data_ready gate not passed')
    data=json.loads(ready.read_text(encoding='utf8'))
    if data.get('status')!='verified_source_and_arrays' or data.get('dataset_doi')!='10.17632/bn6n2639xh.2':
        raise RuntimeError('V2 readiness record does not assert verified source and arrays')
    if len(data.get('files',[]))<5 or any(not f.get('verified') for f in data['files']):
        raise RuntimeError('V2 source verification record incomplete')
    if not Path('simulation/field_feasibility/data_v2.py').is_file(): raise RuntimeError('audited V2 API unavailable')
    card=Path('coordination/tasks/D-045.md').read_text(encoding='utf8')
    if not any(s in card for s in ('状态 review','状态 closed','状态 done','状态 accepted','负责人 D，review')):
        raise RuntimeError('D-045 transport API has not been declared frozen/reviewed')
    return data


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--data',required=True); ap.add_argument('--config',required=True); ap.add_argument('--out',required=True)
    args=ap.parse_args(); root=Path(args.data).resolve(); out=Path(args.out).resolve(); config=Path(args.config).resolve()
    released=readiness(root)
    cfg=json.loads(config.read_text(encoding='utf8'))
    if cfg['phase'] not in (1,2,3,4) or cfg['field_mode'] not in ('frozen_dynamic','dynamic'):
        raise ValueError('entry requires phase 1–4 and explicit field mode')
    out.mkdir(parents=True,exist_ok=False)
    (out/'config.json').write_bytes(config.read_bytes())
    save(out/'data_ready_snapshot.json',released)
    started=datetime.now().astimezone().isoformat()
    files=['mission.py','sampling.py','analysis.py','analysis_stats.py','mission_transport.py','network.py','data_v2.py','run_pilot.py']
    hashes={name:sha(Path(__file__).parent/name) for name in files}
    snapshot=out/'code_snapshot'; snapshot.mkdir()
    for name in files: shutil.copyfile(Path(__file__).parent/name,snapshot/name)
    manifest={'status':'running','task_id':'E1-035','phase':1,'started_at':started,'timezone':'Asia/Shanghai',
              'config_sha256':sha(config),'data_ready_sha256':sha(root/'data_ready.json'),
              'dependency_snapshot':{'python':platform.python_version(),'numpy':np.__version__,'scipy':scipy.__version__},
              'python_executable':sys.executable,'code_sha256':hashes,'seeds':cfg['seeds'],
              'command':' '.join(sys.argv),'field_control':cfg['field_mode'],
              'source_directory':str(root),'output_directory':str(out),'process_id':os.getpid(),
              'intended_runs':len(cfg['policies'])*len(cfg['seeds']),'completed_runs':0}
    save(out/'RUN_MANIFEST.json',manifest)
    from data_v2 import FieldV2
    raw=FieldV2(root)
    field=FrozenField(raw,cfg['frozen_dynamic_frame_s']) if cfg['field_mode']=='frozen_dynamic' else raw
    rows=[]; height_rows=[]; temporal_rows=[]; distance_rows=[]
    for seed in cfg['seeds']:
        references={}; completed={}
        for policy in cfg['policies']:
            print('Phase',cfg['phase'],seed,policy,flush=True)
            is_frozen=policy.endswith('_frozen'); core=policy.removesuffix('_frozen')
            base='D' if core=='D_degraded' else core
            if base not in ('A','B','C','D','E'): raise ValueError('invalid pilot policy')
            selected_field=FrozenField(raw,cfg['frozen_dynamic_frame_s']) if is_frozen else field
            network_cfg=cfg['degraded_network'] if core=='D_degraded' else cfg['network']
            net=MissionTransport(network_cfg,seed+100000) if base in 'BD' else None
            result=simulate(selected_field,cfg,policy=base,seed=seed,transport=net)
            if base=='A': references[is_frozen]=result
            if base=='B':
                reference=references[is_frozen]
                assert result['samples']==reference['samples'] and result['trajectory']==reference['trajectory']
            completed[policy]=result
            folder=out/f'seed-{seed}'/policy; folder.mkdir(parents=True,exist_ok=False)
            save_record(folder/'mission.json',result,cfg.get('compress_records',False))
            if net:
                late=net.advance(cfg['duration_s'],np.asarray(result['final_positions']))
                network_snapshot=net.snapshot(cfg['duration_s']); network_snapshot['late_deliveries']=late
                save_record(folder/'network.json',network_snapshot,cfg.get('compress_records',False))
            manifest['completed_runs']+=1; save(out/'RUN_MANIFEST.json',manifest)
        expected=cfg['nodes']*int(np.ceil(cfg['duration_s']/cfg['dt_s']))
        if any(len(v['samples'])!=expected or any(s['value_dbm'] is None for s in v['samples']) for v in completed.values()):
            raise RuntimeError('missing or unequal observation budgets; pilot cannot be declared comparable')
        common=eval_points(cfg,0,completed)
        save(out/f'seed-{seed}'/'common_unvisited_points.json',common)
        trajectories={name:trajectory_distances(result['trajectory']) for name,result in completed.items()}
        shared_distance_ceiling=min(x[-1]['distance_m'] for x in trajectories.values())
        for policy,result in completed.items():
            distances={d['step']:d['distance_m'] for d in trajectories[policy]}
            previous=None
            for step in cfg['evaluation_steps']:
                t=step*cfg['dt_s']; qs=[[x,y,h,t] for x,y,h,_ in common]
                truth=[]
                score_field=FrozenField(raw,cfg['frozen_dynamic_frame_s']) if policy.endswith('_frozen') else field
                for x,y,h,qt in qs:
                    value=score_field.query(x,y,h,qt); truth.append(float(value) if value is not None else float('nan'))
                offline=score(qs,truth,observations_at(result,0,step,offline=True))
                floor_count=sum(v==cfg['repeated_floor_dbm'] for v in truth)
                masked_truth=[float('nan') if v==cfg['repeated_floor_dbm'] else v for v in truth]
                sensitivity=score(qs,masked_truth,observations_at(result,0,step,offline=True))
                online=[score(qs,truth,observations_at(result,i,step)) for i in range(cfg['nodes'])]
                values=[v['rmse_db'] for v in online if v['rmse_db'] is not None]
                rows.append({'seed':seed,'policy':policy,'step':step,'t_s':t,
                             'distance_m':distances[step],
                             'attempts':sum(s['t_s']<=t for s in result['samples']),
                             'successful_observations':sum(s['t_s']<=t and s['value_dbm'] is not None for s in result['samples']),
                             'offline_rmse_db':offline['rmse_db'],'offline_mae_db':offline['mae_db'],
                             'offline_p95_abs_error_db':offline['p95_abs_error_db'],
                             'online_mean_rmse_db':float(np.mean(values)) if values else None,'blind_support':offline['support'],
                             'blind_exact_floor_count':floor_count,'masked_blind_support':sensitivity['support'],
                             'masked_blind_rmse_db':sensitivity['rmse_db']})
                train=observations_at(result,0,step,offline=True)
                predicted,_=reconstruct(train,qs)
                for h in cfg['heights_m']:
                    indexes=[i for i,q in enumerate(qs) if q[2]==h]
                    per=score([qs[i] for i in indexes],[truth[i] for i in indexes],train)
                    height_rows.append({'seed':seed,'policy':policy,'step':step,'t_s':t,'height_m':h,
                                        'support':per['support'],'mae_db':per['mae_db'],'rmse_db':per['rmse_db'],
                                        'p95_abs_error_db':per['p95_abs_error_db']})
                current_truth=np.asarray(truth,float)
                if previous is not None:
                    old_t,old_truth,old_pred=previous
                    mask=np.isfinite(old_truth)&np.isfinite(current_truth)
                    delta=np.abs((predicted[mask]-old_pred[mask])-(current_truth[mask]-old_truth[mask]))
                    temporal_rows.append({'seed':seed,'policy':policy,'from_s':old_t,'to_s':t,'support':int(mask.sum()),
                                          'temporal_delta_mae_db':float(np.mean(delta)) if len(delta) else None})
                previous=(t,current_truth,predicted)
            for fraction in cfg.get('distance_checkpoint_fractions',[0.5,1.0]):
                requested=shared_distance_ceiling*fraction
                feasible=[x for x in trajectories[policy] if x['distance_m']<=requested+1e-9]
                if not feasible: continue
                mark=feasible[-1]; t=mark['t_s']; qs=[[x,y,h,t] for x,y,h,_ in common]
                score_field=FrozenField(raw,cfg['frozen_dynamic_frame_s']) if policy.endswith('_frozen') else field
                truth=[float(score_field.query(x,y,h,qt)) for x,y,h,qt in qs]
                metric=score(qs,truth,observations_at(result,0,mark['step'],offline=True))
                masked=score(qs,[float('nan') if v==cfg['repeated_floor_dbm'] else v for v in truth],
                             observations_at(result,0,mark['step'],offline=True))
                distance_rows.append({'seed':seed,'policy':policy,'fraction_of_shared_ceiling':fraction,
                                      'requested_team_m':requested,'observed_team_m':mark['distance_m'],
                                      'unused_distance_m':max(0.,requested-mark['distance_m']),'step':mark['step'],'t_s':t,
                                      'attempts':sum(s['t_s']<=t for s in result['samples']),
                                      'offline_rmse_db':metric['rmse_db'],'blind_support':metric['support'],
                                      'masked_blind_rmse_db':masked['rmse_db'],'masked_blind_support':masked['support']})
        dumpcsv(out/'checkpoints.csv',rows)
        dumpcsv(out/'checkpoints_height.csv',height_rows); dumpcsv(out/'temporal.csv',temporal_rows)
        dumpcsv(out/'distance_checkpoints.csv',distance_rows)
    dumpcsv(out/'checkpoints.csv',rows)
    dumpcsv(out/'checkpoints_height.csv',height_rows); dumpcsv(out/'temporal.csv',temporal_rows)
    dumpcsv(out/'distance_checkpoints.csv',distance_rows)
    manifest.update(status='completed',finished_at=datetime.now().astimezone().isoformat(),exit_code=0)
    save(out/'RUN_MANIFEST.json',manifest)

if __name__=='__main__': main()
