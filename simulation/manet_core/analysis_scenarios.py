"""Summarize within-scenario paired seeds; no pooling scenarios as replicates."""
import json,math,pathlib,statistics,sys
root=pathlib.Path(sys.argv[1]);out=pathlib.Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False);m=json.loads((root/'campaign.json').read_text());
def ci(v):
 mean=statistics.mean(v);radius=2.776*statistics.stdev(v)/math.sqrt(len(v)) if len(v)==5 else None
 return {'mean':mean,'t95_low':mean-radius if radius is not None else None,'t95_high':mean+radius if radius is not None else None,'n':len(v)}
records=[]
for c in m['results']:
 a=c['audited_pairs'];
 if len(a)!=5:continue
 records.append({'scenario':c['name'],'base':ci([x['base'] for x in a]),'candidate':ci([x['candidate'] for x in a]),'paired_rate_difference':ci([x['delta'] for x in a]),'paired_control_ratio_minus1':ci([x['candidate_control']/x['base_control']-1 for x in a]),'worst_destination_difference':ci([x['worst_candidate_destination']-x['worst_base_destination'] for x in a])})
x={'source':str(root),'campaign_status':m['status'],'scenarios':records,'limits':['t intervals describe only five seeds within each scenario; geometry/model choice fixed and uncalibrated','formation speeds share relative topology; do not treat scenarios as independent replicates','worst-node values can refer to different nodes between strategies']};(out/'scenarios.json').write_text(json.dumps(x,indent=2));print('scenarios',len(records))
