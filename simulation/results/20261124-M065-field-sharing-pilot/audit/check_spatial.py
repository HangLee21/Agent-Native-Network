"""Summarize saved samples against same-height blind weak points; no policy run."""
import csv,json,os
from pathlib import Path
os.environ['OPENBLAS_NUM_THREADS']='1'
import numpy as np
from scipy.io import loadmat
from scipy.spatial import cKDTree
root=Path.cwd()/'simulation/outputs/E1-033/20261124-01-pilot';out=Path(__file__).resolve().parent
field=np.stack([loadmat(root/'source'/f'Static_REM_1.25km_h{h}m_2.45GHz_100s.mat')['rem'] for h in (20,30,40)])
x,y=np.indices((250,250));blind=((x//10+2*(y//10))%5)==0;weak=(np.isfinite(field)&(field>-250)&(field<-75)&blind)
result=[]
for group in range(1,5):
 for policy in ('partition','local','shared'):
  with (root/'results'/f'group-{group:02d}'/policy/'samples.csv').open(newline='') as stream:samples=list(csv.DictReader(stream))
  distances=[]
  for z,h in enumerate((20,30,40)):
   points=np.argwhere(weak[z])*5;measured=np.array([[int(a['x'])*5,int(a['y'])*5] for a in samples if int(a['height_m'])==h]);distances.extend(cKDTree(measured).query(points)[0])
  d=np.array(distances);result.append({'group':group,'policy':policy,'weak_count':len(d),'min_m':float(d.min()),'median_m':float(np.median(d)),'within_75_m':int((d<=75).sum()),'within_150_m':int((d<=150).sum()),'within_300_m':int((d<=300).sum())})
(out/'SPATIAL.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print('saved',len(result),'distance summaries')
