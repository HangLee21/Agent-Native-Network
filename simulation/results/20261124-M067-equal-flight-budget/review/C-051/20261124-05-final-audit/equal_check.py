import os
os.environ['OPENBLAS_NUM_THREADS']='1'
import csv,gzip,json,math,hashlib
from pathlib import Path
from collections import Counter
import numpy as np
from scipy.stats import t,ttest_1samp
from scipy.spatial import cKDTree
root=Path('simulation/outputs/E2-045/20261124-06-four-height-main'); data=Path('data/field_feasibility_v2')
manifest=json.loads((root/'RUN_MANIFEST.json').read_text()); cfg=json.loads((root/'config.json').read_text())
with (root/'pairs.csv').open(newline='') as f: rows=list(csv.DictReader(f))
assert manifest['status']=='completed' and len(rows)==80 and all(r['status']=='completed' for r in rows)
for name,digest in manifest['source_sha256'].items():
 p=Path('simulation/field_feasibility')/name
 with p.open('rb') as f: assert hashlib.file_digest(f,'sha256').hexdigest()==digest,(name,'source drift')
arrays={h:np.load(data/f'dynamic_h{h}m_f64.npy',mmap_mode='r') for h in (2,25,50,80)}
scale=np.array([100.,100.,30.,120.]); totals=Counter();min_sep=float('inf');max_err=0.;examples={};score_examples=[]
def cell(p):return (int(math.floor(p[0]/5+.5)),int(math.floor(p[1]/5+.5)),int(p[2]))
def predict(samples,q):
 x=np.array([[s['x_m'],s['y_m'],s['h_m'],s['t_s']] for s in samples]);y=np.array([s['value_dbm'] for s in samples]);near=cKDTree(x/scale).query(q/scale,k=min(32,len(x)))[1]
 if near.ndim==1:near=near[:,None]
 vals=[]
 for pos,idx in zip(q,near):
  a=x[idx];k=100*np.exp(-.5*np.sum(((a[:,None]-a[None,:])/scale)**2,axis=2))+4*np.eye(len(a));v=100*np.exp(-.5*np.sum(((a-pos)/scale)**2,axis=1));vals.append(-65+v@np.linalg.solve(k,y[idx]+65))
 return np.array(vals)
for row in rows:
 n,seed=int(row['nodes']),int(row['seed']); loaded=[]
 for policy in ('C','D'):
  with gzip.open(root/f'n{n:02}-seed{seed}-{policy}.json.gz','rt') as f: obj=json.load(f)
  r=obj['result'];samples=r['samples'];traj=r['trajectory'];dec=r['decisions'];assert len(samples)==len(traj)==len(dec)==20*n
  coords=np.array([[x['x_m'],x['y_m'],x['h_m']] for x in traj]).reshape(20,n,3);positions=np.concatenate([coords,np.asarray(r['final_positions'])[None,:,:]])
  dist=np.linalg.norm(np.diff(positions,axis=0),axis=2);max_err=max(max_err,float(np.max(np.abs(dist-60.))));assert np.allclose(dist,60,rtol=0,atol=1e-8)
  assert np.allclose(np.sum(dist,axis=0),r['flight_distance_m'],atol=1e-8) and all(375-1e-8<=x<=875+1e-8 for x in positions[:,:,:2].flat)
  for k in range(20):
   old=positions[k];v=positions[k+1]-old;ii,jj=np.triu_indices(n,1);d=old[ii]-old[jj];dv=v[ii]-v[jj];vv=np.sum(dv*dv,axis=1);u=np.divide(-np.sum(d*dv,axis=1),vv,out=np.zeros_like(vv),where=vv>1e-14);u=np.clip(u,0,1);sd=np.linalg.norm(d+u[:,None]*dv,axis=1);min_sep=min(min_sep,float(sd.min()));assert np.all(sd>=5-1e-8)
  assert all(s['step']==i//n and s['node_id']==i%n and s['t_s']==30*(i//n) and np.allclose([s['x_m'],s['y_m'],s['h_m']],coords[i//n,i%n]) for i,s in enumerate(samples))
  blind={cell(b) for b in obj['blind']};assert len(blind)==48 and all(cell([s['x_m'],s['y_m'],s['h_m']]) not in blind for s in samples)
  occupied={cell(p) for p in positions[0]};expected=[]
  for h in (2,25,50,80):
   pool=[(float(x),float(y),float(h)) for x in range(375,876,25) for y in range(375,876,25) if cell((x,y,h)) not in occupied]
   rng=np.random.default_rng(np.random.SeedSequence([seed,n,74123,h]));expected.extend(pool[i] for i in rng.choice(len(pool),size=12,replace=False))
  assert [tuple(z) for z in obj['blind']]==expected
  for s in samples:
   x,y,h=cell([s['x_m'],s['y_m'],s['h_m']]);z=float(arrays[h][x,y,s['step']*30]);noise=float(np.random.default_rng(np.random.SeedSequence([seed,s['node_id'],s['step']])).normal(0,1));assert abs(s['value_dbm']-z-noise)<1e-10
  if policy=='D':
   net=r['network'];outcomes={(e['message_id'],e['destination']):e for e in net['outcomes']}; delivered_events=r['events'];assert len(delivered_events)==int(row['delivered_events'])
   for e in delivered_events:
    o=outcomes[(e['network_message_id'],e['receiver'])];assert o['status']=='delivered' and o['source']==e['sender'] and o['completed_at']==e['delivered_s'] and e['created_s']<=e['delivered_s']
   samplemap={s['sample_id']:s for s in samples}; recv={}
   for e in delivered_events:
    if e['kind']=='SAMPLE': assert samplemap[e['payload']['sample_id']]==e['payload'];recv.setdefault(e['receiver'],[]).append(e)
   for d in dec:
    i,step=d['node_id'],d['step'];now=step*30
    ids={e['payload']['sample_id'] for e in recv.get(i,[]) if e['delivered_s']<=now};local={f'{i}:{j}' for j in range(step+1)}
    assert set(d['received_sample_ids'])==ids and set(d['visible_sample_ids'])==ids|local
    if d['heading_index']!=d['counterfactual_heading']:
     totals['changed_decisions']+=1
     if n not in examples and step<19 and ids:examples[n]={'seed':seed,'node':i,'step':step,'heading':d['heading_index'],'counterfactual':d['counterfactual_heading'],'visible_received':len(ids),'position':d['position'],'next_position':positions[step+1,i].tolist()}
   assert sum(d['heading_index']!=d['counterfactual_heading'] for d in dec)==int(row['message_affected_decisions'])
   totals['delivered_events']+=len(delivered_events)
  if seed==2000:
   q=np.array([[*x,570.] for x in obj['blind']]);truth=np.array([arrays[int(h)][int(x/5),int(y/5),570] for x,y,h in obj['blind']]);pred=predict(samples,q);err=pred-truth;raw=float(np.sqrt(np.mean(err**2)));mask=truth!=-240.96910013008056;masked=float(np.sqrt(np.mean(err[mask]**2)))
   assert np.isclose(raw,obj['evaluation']['offline']['rmse_db'],atol=1e-8) and np.isclose(masked,obj['evaluation']['floor_excluded']['rmse_db'],atol=1e-8)
   score_examples.append({'nodes':n,'seed':seed,'policy':policy,'raw':raw,'floor_excluded':masked})
  loaded.append(obj)
 assert loaded[0]['blind']==loaded[1]['blind'] and np.allclose(np.array(loaded[0]['result']['trajectory'][:n][0]['x_m']),np.array(loaded[1]['result']['trajectory'][:n][0]['x_m']))
 assert all(np.allclose([a['x_m'],a['y_m'],a['h_m']],[b['x_m'],b['y_m'],b['h_m']]) for a,b in zip(loaded[0]['result']['trajectory'][:n],loaded[1]['result']['trajectory'][:n]))
 cm,dm=(x['evaluation'] for x in loaded)
 for col,val in [('c_offline_rmse',cm['offline']['rmse_db']),('d_offline_rmse',dm['offline']['rmse_db']),('c_floor_excluded_rmse',cm['floor_excluded']['rmse_db']),('d_floor_excluded_rmse',dm['floor_excluded']['rmse_db'])]: assert np.isclose(float(row[col]),val,atol=1e-9)
 assert abs(float(row['distance_difference_m']))<1e-6 and float(row['time_difference_s'])==0 and int(row['sample_difference'])==0
 totals['pairs']+=1
aggregate=[]
for n in (5,10,20,30):
 r=[x for x in rows if int(x['nodes'])==n];entry={'nodes':n}
 for col,label in [('delta_offline_rmse','raw'),('delta_floor_excluded_rmse','masked')]:
  x=np.array([float(z[col]) for z in r]);mean=float(x.mean());sd=float(x.std(ddof=1));margin=float(t.ppf(.975,len(x)-1)*sd/np.sqrt(len(x)));entry[label]={'n':len(x),'mean':mean,'sd':sd,'ci95':[mean-margin,mean+margin],'p':float(ttest_1samp(x,0).pvalue)}
  expected=next(x for x in manifest['outcomes'] if x['nodes']==n);key='mean_D_minus_C_rmse' if label=='raw' else 'floor_excluded_mean_D_minus_C_rmse';assert np.isclose(mean,expected[key],atol=1e-9)
  ci=expected['ci95' if label=='raw' else 'floor_excluded_ci95'];assert np.allclose(entry[label]['ci95'],ci,atol=1e-9)
 aggregate.append(entry)
out={'pairs':totals['pairs'],'changed_decisions':totals['changed_decisions'],'delivered_events':totals['delivered_events'],'minimum_simultaneous_distance_m':min_sep,'max_segment_length_error_m':max_err,'aggregate':aggregate,'motion_examples':examples,'independent_score_examples':score_examples,'limitations':'common geometrical safety uses global state; blind forbids measured endpoints only; equal 60 m steps changes original motion policy; no actual RF or flight'}
Path('simulation/outputs/C-051/20261124-05-final-audit/equal_result.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out,indent=2))
