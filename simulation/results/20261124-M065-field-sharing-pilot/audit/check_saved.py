"""Read-only recomputation from E1-033 saved samples; no policy run."""
import csv, hashlib, json, os
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1'; os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy.io import loadmat
from scipy.linalg import cho_factor,cho_solve
from scipy.spatial import cKDTree

ROOT=Path.cwd(); run=ROOT/'simulation/outputs/E1-033/20261124-01-pilot'; saved=run/'results'; out=Path(__file__).resolve().parent
heights=np.array([20,30,40]); files=[run/'source'/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat' for h in heights]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((saved/'RUN_MANIFEST.json').read_text(encoding='utf8'))
assert sha(ROOT/'simulation/field_reconstruction/pilot.py')==next(iter(manifest['dirty_files_sha256'].values()))
for p in files: assert sha(p)==manifest['data_and_weights_sha256'][p.name]
field=np.stack([loadmat(p)['rem'].astype(float) for p in files]); valid=np.isfinite(field)&(field>-250)
xx,yy=np.indices((250,250)); blind=((xx//10+2*(yy//10))%5)==0; mask=valid & blind[None,:,:]
idx=np.argwhere(mask); q=idx[:,[1,2]]*5.; query=np.column_stack((q,heights[idx[:,0]])); actual=field[tuple(idx.T)]; truth=actual < -75
length=np.array([150.,150.,20.])
def K(a,b):
 d=(a[:,None,:]-b[None,:,:])/length
 return 100*np.exp(-np.sum(d*d,axis=2)/2)
def predict(obs,query):
 x=np.array([[5*s['x'],5*s['y'],s['height_m']] for s in obs],float); v=np.array([s['dbm'] for s in obs]); k=K(x,x);k.flat[::len(k)+1]+=1
 factor=cho_factor(k,lower=True);return -65+K(x,query).T@cho_solve(factor,v+65)
vectors=[(15,0),(12,9),(9,12),(0,15),(-9,12),(-12,9),(-15,0),(-12,-9),(-9,-12),(0,-15),(9,-12),(12,-9)]
def score_candidates(base,z,history):
 x=np.array([[5*s['x'],5*s['y'],s['height_m']] for s in history],float);v=np.array([s['dbm'] for s in history]);k=K(x,x);k.flat[::len(k)+1]+=1;factor=cho_factor(k,lower=True)
 scores={}
 for n,(dx,dy) in enumerate(vectors):
  cells=[]
  for step in range(1,16):
   a=base[0]+round(dx*step/15);b=base[1]+round(dy*step/15)
   if (a,b) not in cells and valid[z,a,b] and not blind[a,b]:cells.append((a,b))
  if len(cells)<6:continue
  q=np.array([[a*5,b*5,heights[z]] for a,b in cells[:6]]);cross=K(x,q);sol=cho_solve(factor,cross);mu=-65+cross.T@cho_solve(factor,v+65);sd=np.sqrt(np.maximum(100-np.sum(cross*sol,axis=0),0));scores[str(n)]=float(np.mean(sd+12*np.exp(-.5*((mu+75)/np.sqrt(sd*sd+4))**2)))
 return scores
def boundary(m,c,h):
 pts=[]
 for axis in (0,1):
  a=[slice(None),slice(None)];b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
  v=np.argwhere(m[a]&m[b]&(c[a]!=c[b]));pts.extend([[5*(x+.5*(axis==0)),5*(y+.5*(axis==1)),h] for x,y in v])
 return pts
tb=[]
for z,h in enumerate(heights):tb+=boundary(mask[z],field[z]<-75,h)
allrows=[]; shared_decisions=[]; violations=[]
for group in range(1,5):
 for policy in ('partition','local','shared'):
  folder=saved/f'group-{group:02d}'/policy
  with (folder/'samples.csv').open(encoding='utf8',newline='') as f: rows=list(csv.DictReader(f))
  obs=[{k:(float(v) if k=='dbm' else int(v)) for k,v in r.items()} for r in rows]
  assert len(obs)==75
  for s in obs:
   z=list(heights).index(s['height_m']); x,y=s['x'],s['y']
   if not valid[z,x,y] or blind[x,y] or not np.isclose(s['dbm'],field[z,x,y],atol=1e-7): violations.append([group,policy,s])
  predicted=np.concatenate([predict(obs,query[i:i+1500]) for i in range(0,len(query),1500)])
  pred=predicted < -75; fn=int(np.sum(truth&~pred));fp=int(np.sum(~truth&pred));rmse=float(np.sqrt(np.mean((actual-predicted)**2)))
  grid=np.zeros_like(mask);grid[tuple(idx.T)]=pred;pb=[]
  for z,h in enumerate(heights):pb+=boundary(mask[z],grid[z],h)
  boundary_dist=None if not pb or not tb else float((cKDTree(pb).query(tb)[0].mean()+cKDTree(tb).query(pb)[0].mean())/2)
  m=json.loads((folder/'metrics.json').read_text(encoding='utf8'))
  assert fn==m['fn'] and fp==m['fp'] and len(idx)==m['blind_count'] and np.isclose(rmse,m['rmse_db'],atol=1e-9)
  assert (boundary_dist is None and m['boundary_symmetric_distance_m'] is None) or np.isclose(boundary_dist,m['boundary_symmetric_distance_m'],atol=1e-9)
  with (folder/'trajectory.csv').open(encoding='utf8',newline='') as f: traj=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
  distance={str(i):sum(np.hypot((b['x']-a['x'])*5,(b['y']-a['y'])*5) for rnd in range(4) for line in [[v for v in traj if v['aircraft']==i and v['round']==rnd]] for a,b in zip(line,line[1:])) for i in range(3)}
  assert all(np.isclose(v,600) for v in distance.values())
  per=[]
  for z,h in enumerate(heights):
   s=[v for v in obs if v['height_m']==h];p=np.array([[v['x']*5,v['y']*5] for v in s]); blind_pts=np.argwhere(mask[z])*5; d=cKDTree(p).query(blind_pts)[0]
   weak=field[z][mask[z]] < -75
   per.append({'height_m':int(h),'blind_points':int(len(d)),'blind_within_75m':int(np.sum(d<=75)),'blind_weak':int(np.sum(weak)),'blind_weak_within_75m':int(np.sum(d[weak]<=75)),'sample_weak_occurrences':sum(v['dbm'] < -75 for v in s),'unique_samples':len({(v['x'],v['y']) for v in s}),'max_sample_distance_from_base_m':float(max(np.hypot((v['x']-s[0]['x'])*5,(v['y']-s[0]['y'])*5) for v in s))})
  decisions=json.loads((folder/'decisions.json').read_text(encoding='utf8'))
  assert len(decisions)==12
  if policy=='shared':
   for d in decisions:
    assert d['local_history_count']==1+6*d['round'] and d['pooled_history_count']==3+18*d['round']
    assert d['changed_from_local']==(d['selected']!=d['local_counterfactual'])
    history=[s for s in obs if s['round']<d['round']];local=[s for s in history if s['aircraft']==d['aircraft']]
    for given,calculated in ((d['local_scores'],score_candidates(d['base'],d['aircraft'],local)),(d['shared_scores'],score_candidates(d['base'],d['aircraft'],history))):
     assert given.keys()==calculated.keys() and all(np.isclose(given[k],calculated[k],atol=1e-9) for k in given)
    assert int(max(d['local_scores'],key=lambda k:(d['local_scores'][k],-int(k))))==d['local_counterfactual']
    assert int(max(d['shared_scores'],key=lambda k:(d['shared_scores'][k],-int(k))))==d['selected']
   shared_decisions += [{'group':group,**d} for d in decisions if d['changed_from_local']]
  allrows.append({'group':group,'policy':policy,'fn':fn,'fp':fp,'rmse_db':rmse,'boundary_m':boundary_dist,'pred_boundary_edges':len(pb),'unique':len({(s['height_m'],s['x'],s['y']) for s in obs}),'distances_m':distance,'per_layer':per,'selected_by_aircraft':[[d['selected'] for d in decisions if d['aircraft']==i] for i in range(3)]})
assert not violations,violations
saved_changes=json.loads((saved/'changed_examples.json').read_text(encoding='utf8'))
assert [(d['group'],d['round'],d['aircraft'],d['selected'],d['local_counterfactual']) for d in shared_decisions]==[(d['group'],d['round'],d['aircraft'],d['selected'],d['local_counterfactual']) for d in saved_changes]
paired=[]
for g in range(1,5):
 a=next(r for r in allrows if r['group']==g and r['policy']=='shared'); b=next(r for r in allrows if r['group']==g and r['policy']=='local')
 paired.append({'group':g,'delta_fn':a['fn']-b['fn'],'delta_fnr':(a['fn']-b['fn'])/int(truth.sum()),'delta_fp':a['fp']-b['fp'],'delta_fpr':(a['fp']-b['fp'])/int((~truth).sum()),'delta_rmse_db':a['rmse_db']-b['rmse_db']})
result={'source_sha256':{p.name:sha(p) for p in files},'pilot_sha256':sha(ROOT/'simulation/field_reconstruction/pilot.py'),'mask_counts':{'valid':int(valid.sum()),'excluded':int((~valid).sum()),'blind':len(idx),'weak':int(truth.sum()),'nonweak':int((~truth).sum()),'true_boundary_edges':len(tb)},'runs':allrows,'shared_changes':{'count':len(shared_decisions),'by_group':[sum(d['group']==g for d in shared_decisions) for g in range(1,5)],'first':shared_decisions[0]},'paired_shared_minus_local':paired,'sample_violations':len(violations)}
(out/'RESULT.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({'status':'passed','runs':len(allrows),'mask':result['mask_counts'],'shared_changes':result['shared_changes']['by_group'],'paired':paired},ensure_ascii=False))
