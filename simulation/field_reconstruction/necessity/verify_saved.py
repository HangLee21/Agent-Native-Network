"""Check saved E1-034 records and describe all preselected region masks; no replay."""
import csv
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from scipy.io import loadmat

out=Path('simulation/outputs/E1-034/20261124-01-necessity')
source=Path('simulation/outputs/E1-033/20261124-01-pilot/source')
cfg=json.loads((out/'config.json').read_text(encoding='utf8'))
field=np.stack([loadmat(source/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat')['rem'] for h in cfg['heights_m']])
valid=np.isfinite(field)&(field>-250)
gx,gy=np.indices((61,61)); blind=((gx//5+2*(gy//5))%5)==0
areas=[]
skipped={x['region'] for x in json.loads((out/'skipped_regions.json').read_text(encoding='utf8'))}
for n,(cx,cy) in enumerate(cfg['centers_index'],1):
    f=field[:,cx-30:cx+31,cy-30:cy+31]; v=valid[:,cx-30:cx+31,cy-30:cy+31]
    b=v&blind[None,:,:]
    areas.append({'region':n,'valid_count':int(v.sum()),'blind_valid_count':int(b.sum()),
                  'weak_blind_count':int((b&(f < -75)).sum()),
                  'status':'skipped fixed-scan eligibility' if n in skipped else 'completed'})
checked=[]
for folder in sorted(out.glob('region-*/*')):
    if not folder.is_dir(): continue
    with (folder/'samples.csv').open(newline='') as f: samples=list(csv.DictReader(f))
    with (folder/'trajectory.csv').open(newline='') as f: traj=list(csv.DictReader(f))
    decisions=json.loads((folder/'decisions.json').read_text(encoding='utf8'))
    metrics=json.loads((folder/'metrics.json').read_text(encoding='utf8'))
    reg=int(folder.parent.name.split('-')[1]); center=cfg['centers_index'][reg-1]
    assert len(samples)==96 and len(decisions)==12 and len(traj)==54
    for s in samples:
        i=int(s['aircraft']); x=int(s['x']); y=int(s['y']); rr=int(s['round'])
        assert valid[i,x,y] and not blind[x-center[0]+30,y-center[1]+30]
        assert float(s['dbm'])==float(field[i,x,y]) and 0<=rr<4
    for i in range(3):
        path=[(int(x['x']),int(x['y'])) for x in traj if int(x['aircraft'])==i]
        length=sum(5*math.hypot(b[0]-a[0],b[1]-a[1]) for a,b in zip(path,path[1:]))
        assert abs(length-1160)<1e-8 and abs(length-metrics['travel_m_per_aircraft'][i])<1e-8
    for d in decisions:
        r=d['round']; i=d['aircraft']
        for name,view in d['views'].items():
            expected=[s for s in samples if int(s['round'])<r and (int(s['aircraft'])==i or (name=='timely' and int(s['round'])<=r-1) or (name=='delayed' and int(s['round'])<=r-2))]
            assert view['sample_ids']==[s['sample_id'] for s in expected]
            ext=[r-1-int(s['round']) for s in expected if int(s['aircraft'])!=i]
            assert view['external_age_rounds']==ext
            if name=='delayed': assert all(age>=1 for age in ext)
            scores=d['scores'][name]
            best=min(scores,key=lambda k:(-scores[k],int(k)))
            assert d['counterfactual_ids'][name]==int(best)
    checked.append(str(folder))
result={'areas':areas,'checked_run_count':len(checked),'checked_runs':checked,
        'checks':'sample count, source values and blind mask, trajectory length, history visibility, ages and logged argmax; does not independently recompute model or metrics',
        'source_hashes':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('Static_REM_1.25km_h*m_2.45GHz_100s.mat') if p.name in {f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat' for h in cfg['heights_m']}}}
(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
