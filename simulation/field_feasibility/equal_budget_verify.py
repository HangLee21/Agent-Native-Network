"""Independent checks on fixed-budget paired mission output."""
import argparse,gzip,json,pathlib,sys
import numpy as np
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parents[1];sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from sampling import sensor_noise,segment_min_distance
from data_v2 import FieldV2
from equal_budget_run import cell
p=argparse.ArgumentParser();p.add_argument('--source',required=True,type=pathlib.Path);p.add_argument('--out',required=True,type=pathlib.Path);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);field=FieldV2(ROOT/'data/field_feasibility_v2');cases=[];pairs={}
for path in sorted(a.source.glob('n*-seed*-*.json.gz')):
 with gzip.open(path,'rt',encoding='utf8') as f:entry=json.load(f)
 run=entry['result'];n=run['nodes'];blind={cell(x,y,h) for x,y,h in entry['blind']};trajectory=run['trajectory'];samples=run['samples'];assert len(samples)==n*20 and len(trajectory)==n*20
 assert len(blind)==48 and all(sum(p[2]==height for p in blind)==12 for height in (2,25,50,80))
 for item in samples:
  assert cell(item['x_m'],item['y_m'],item['h_m']) not in blind
  expected=field.query(item['x_m'],item['y_m'],item['h_m'],item['t_s'])+sensor_noise(run['seed'],item['node_id'],item['step'],1.)
  assert abs(expected-item['value_dbm'])<1e-10
 positions=np.array([[s['x_m'],s['y_m'],s['h_m']] for s in trajectory]).reshape(20,n,3);positions=np.concatenate([positions,np.array(run['final_positions'])[None,:,:]],axis=0);lengths=np.linalg.norm(np.diff(positions,axis=0),axis=2);assert np.allclose(lengths,60,rtol=0,atol=1e-8)
 minimum=float('inf')
 for k in range(20):
  for i in range(n):
   for j in range(i):minimum=min(minimum,segment_min_distance(positions[k,i],positions[k+1,i],positions[k,j],positions[k+1,j]))
 assert minimum>=5-1e-9
 for e in run['events']:
  assert e['created_s']<=e['delivered_s'] and e['receiver']!=e['sender']
 deliveries={};task_deliveries={}
 samples_by_id={sample['sample_id']:sample for sample in samples}
 for e in run['events']:
  if e['kind']=='SAMPLE':
   sample=e['payload'];assert samples_by_id.get(sample['sample_id'])==sample
   key=(e['receiver'],sample['sample_id']);deliveries[key]=min(deliveries.get(key,float('inf')),e['delivered_s'])
  elif e['kind'] in ('TASK_INTENT','TASK_UPDATE','MAP_SUMMARY'):
   p=e['payload'];kind=e['kind'];region=p['target_index'] if kind=='TASK_INTENT' else p['region_id'];expiry=p['expires_s'] if kind=='TASK_INTENT' else p['expires_at']
   key=(e['receiver'],e['sender'],kind,region,p['height_m'],expiry);task_deliveries[key]=min(task_deliveries.get(key,float('inf')),e['delivered_s'])
 for decision in run['decisions']:
  assert all(deliveries.get((decision['node_id'],sid),float('inf'))<=decision['step']*30 for sid in decision['received_sample_ids'])
  local={s['sample_id'] for s in samples if s['node_id']==decision['node_id'] and s['step']<=decision['step']}
  assert set(decision['visible_sample_ids'])==local|set(decision['received_sample_ids'])
  for intent in decision['intents']:
   common=(decision['node_id'],intent['sender']);suffix=(intent['target_index'],intent['height_m'],intent['expires_s'])
   assert min(task_deliveries.get(common+(kind,)+suffix,float('inf')) for kind in ('TASK_INTENT','TASK_UPDATE'))<=decision['step']*30
  for summary in decision['summaries']:
   key=(decision['node_id'],summary['sender'],'MAP_SUMMARY',summary['target_index'],summary['height_m'],summary['expires_s'])
   assert task_deliveries.get(key,float('inf'))<=decision['step']*30
 pairs.setdefault((run['nodes'],run['seed']),{})[run['policy']]=entry
 cases.append({'file':path.name,'samples':len(samples),'min_separation_m':minimum,'max_segment_error_m':float(np.max(np.abs(lengths-60))),'events':len(run['events'])})
for key,pair in pairs.items():
 if set(pair)=={'C','D'}:
  c=pair['C'];d=pair['D'];assert c['blind']==d['blind']
  assert all(all(abs(a[k]-b[k])<1e-10 for k in ('x_m','y_m','h_m')) for a,b in zip(c['result']['samples'][:key[0]],d['result']['samples'][:key[0]]))
  for a_sample,b_sample in zip(c['result']['samples'],d['result']['samples']):
   assert (a_sample['node_id'],a_sample['step'],a_sample['t_s'])==(b_sample['node_id'],b_sample['step'],b_sample['t_s'])
   av=field.query(a_sample['x_m'],a_sample['y_m'],a_sample['h_m'],a_sample['t_s']);bv=field.query(b_sample['x_m'],b_sample['y_m'],b_sample['h_m'],b_sample['t_s'])
   assert abs((a_sample['value_dbm']-av)-(b_sample['value_dbm']-bv))<1e-10
assert cases;(a.out/'validation.json').write_text(json.dumps(cases,indent=2),encoding='utf8');print('validated runs',len(cases))
