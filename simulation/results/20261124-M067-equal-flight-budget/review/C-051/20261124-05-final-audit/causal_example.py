import gzip,json,math
from pathlib import Path
import numpy as np
p=Path('simulation/outputs/E2-045/20261124-06-four-height-main/n05-seed2000-D.json.gz')
with gzip.open(p,'rt') as f:o=json.load(f)
r=o['result'];d=next(x for x in r['decisions'] if x['node_id']==0 and x['step']==1);now=30.;pos=np.array(d['position']);samples={s['sample_id']:s for s in r['samples']};local=[s for s in r['samples'] if s['node_id']==0 and s['step']<=1];history=sorted([samples[i] for i in d['visible_sample_ids']],key=lambda s:(s['t_s'],s['node_id'],s['sample_id']));angles=np.arange(24)*2*np.pi/24;ends=np.column_stack((pos[0]+60*np.cos(angles),pos[1]+60*np.sin(angles),np.full(24,pos[2])));blind={(round(x/5),round(y/5),h) for x,y,h in o['blind']};old=np.array([[s['x_m'],s['y_m'],s['h_m']] for s in r['trajectory'] if s['step']==1]);legal=[]
for e in ends:
 ok=375<=e[0]<=875 and 375<=e[1]<=875 and (math.floor(e[0]/5+.5),math.floor(e[1]/5+.5),e[2]) not in blind
 for other in old[1:]:
  diff=pos-other;v=e-pos;v2=v@v;u=min(1,max(0,-diff@v/v2));ok &= np.linalg.norm(diff+u*v)>=5-1e-9
 legal.append(ok)
def scores(hist):
 x=np.array([[s['x_m'],s['y_m'],s['h_m'],s['t_s']] for s in hist[-32:]]);q=np.column_stack((ends,np.full(24,now)));sc=np.array([100.,100.,30.,120.]);K=np.exp(-.5*np.sum(((x[:,None]-x[None,:])/sc)**2,axis=2))+.04*np.eye(len(x));v=np.exp(-.5*np.sum(((x[:,None]-q[None,:])/sc)**2,axis=2));var=np.maximum(0,1-np.sum(v*np.linalg.solve(K,v),axis=0));return var/(1+np.linalg.norm(ends[:,:2]-pos[:2],axis=1)/100)
base=scores(local);actual=scores(history);axes=np.linspace(375,875,5);ids=np.array([int(np.argmin(abs(axes-e[1]))*5+np.argmin(abs(axes-e[0]))) for e in ends])
for s in d['summaries']:
 matches=[e for e in r['events'] if e['receiver']==0 and e['kind']=='MAP_SUMMARY' and e['sender']==s['sender'] and e['delivered_s']<=now and e['payload']['region_id']==s['target_index'] and e['payload']['variance']==s['variance']];assert matches
 actual[ids==s['target_index']]+=.1*math.sqrt(max(0,s['variance']))/10
assert not d['intents']; selected=int(np.argmax(np.where(legal,actual,-np.inf)));counter=int(np.argmax(np.where(legal,base,-np.inf)));assert (selected,counter)==(d['heading_index'],d['counterfactual_heading'])==(14,13)
nextpos=next(x for x in r['trajectory'] if x['node_id']==0 and x['step']==2);assert np.allclose(ends[selected],[nextpos['x_m'],nextpos['y_m'],nextpos['h_m']])
out={'seed':2000,'nodes':5,'node':0,'step':1,'received_ids':d['received_sample_ids'],'summary':d['summaries'],'selected':selected,'local_counterfactual':counter,'actual_next':ends[selected].tolist(),'local_next_if_same_legal_set':ends[counter].tolist()};Path('simulation/outputs/C-051/20261124-05-final-audit/causal_example.json').write_text(json.dumps(out,indent=2),encoding='utf8');print(json.dumps(out,indent=2))
