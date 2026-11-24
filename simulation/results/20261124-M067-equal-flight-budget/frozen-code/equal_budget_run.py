"""Paired C/D fixed-distance supplement; never alters the E1 mission engine.

Run only after the coordinate-only holdout is fixed. Flight segments have equal
length, and a run fails rather than reporting fabricated travel on infeasibility.
"""
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,os,pathlib,sys,time
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
import numpy as np
from scipy import stats
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE));sys.path.insert(0,str(ROOT))
from data_v2 import FieldV2
from sampling import sensor_noise,variance_scores
from analysis import reconstruct,score
from mission import initial_positions
from mission_transport import MissionTransport

REGION=(375.,375.,875.,875.);HEIGHTS=(2.,25.,50.,80.);DT=30.;STEPS=20;DIST=60.;SAFETY=5.;FLOOR=-240.96910013008056

def cell(x,y,h):
 return (int(math.floor(x/5+.5)),int(math.floor(y/5+.5)),float(h))

def holdouts(n,seed,initial):
 # Draw before either trajectory, only from coordinates. Do not inspect field values.
 occupied={cell(*p) for p in initial};result=[]
 for height in HEIGHTS:
  grid=[(float(x),float(y),height) for x in range(375,876,25) for y in range(375,876,25)]
  pool=[p for p in grid if cell(*p) not in occupied]
  rng=np.random.default_rng(np.random.SeedSequence([seed,n,74123,int(height)]));ids=rng.choice(len(pool),size=12,replace=False)
  result.extend(pool[i] for i in ids)
 return result

def candidates(p,old,chosen,index,blind):
 angles=np.arange(24)*2*np.pi/24.;ends=np.column_stack((p[0]+DIST*np.cos(angles),p[1]+DIST*np.sin(angles),np.full(24,p[2])))
 legal=(ends[:,0]>=REGION[0])&(ends[:,0]<=REGION[2])&(ends[:,1]>=REGION[1])&(ends[:,1]<=REGION[3]);legal &= np.array([cell(*q) not in blind for q in ends])
 others=np.arange(len(old))!=index;start=old[others];future=chosen[others]
 # Minimum synchronized separation between two linear flight segments.
 rel=p[None,None,:]-start[None,:,:];vel=(ends-p)[:,None,:]-(future-start)[None,:,:];v2=np.sum(vel*vel,axis=2);dot=np.sum(rel*vel,axis=2);u=np.divide(-dot,v2,out=np.zeros_like(dot),where=v2>1e-14);u=np.clip(u,0,1);mind=np.linalg.norm(rel+u[:,:,None]*vel,axis=2);legal &= np.all(mind>=SAFETY-1e-9,axis=1)
 return ends,legal

def region_id(p):
 # TASK_INTENT IDs refer to a shared fixed 5x5 grid, not local heading numbers.
 xs=np.linspace(REGION[0],REGION[2],5);ys=np.linspace(REGION[1],REGION[3],5)
 return int(np.argmin(abs(ys-p[1]))*5+np.argmin(abs(xs-p[0])))

def run_one(field,n,seed,policy,blind):
 config={'range_m':400.,'bandwidth_bps':1000000.,'propagation_delay_s':0.,'loss_probability':0.}
 net=MissionTransport(config,seed) if policy=='D' else None
 pos=initial_positions(n,REGION,HEIGHTS,SAFETY,seed);own=[[] for _ in range(n)];received=[{} for _ in range(n)];intents=[{} for _ in range(n)];summaries=[{} for _ in range(n)];samples=[];decisions=[];traj=[];events=[];distance=np.zeros(n);rejected=0
 blind_cells={cell(*p) for p in blind}
 for step in range(STEPS):
  now=step*DT;incoming=net.advance(now,pos.copy()) if net else {};outgoing=[]
  for receiver,envelopes in incoming.items():
   for msg in envelopes:
    if msg['receiver']!=receiver or msg['created_s']>msg['delivered_s'] or msg['delivered_s']>now:raise ValueError('invalid causal network delivery')
    events.append(msg);sender=int(msg['sender']);p=msg['payload']
    if msg['kind']=='SAMPLE':
     if int(p['node_id'])!=sender or p['t_s']>msg['created_s'] or p['t_s']>now:raise ValueError('invalid or future sample')
     received[receiver][p['sample_id']]=p
    elif msg['kind']=='TASK_INTENT':intents[receiver][sender]=dict(p,sender=sender)
    elif msg['kind']=='TASK_UPDATE':
     if p['owner']!=sender:raise ValueError('invalid task owner')
     if p['status']=='active':intents[receiver][sender]={'target_index':p['region_id'],'expires_s':p['expires_at'],'height_m':p['height_m'],'sender':sender}
     else:intents[receiver].pop(sender,None)
    elif msg['kind']=='MAP_SUMMARY':summaries[receiver][sender]={'target_index':p['region_id'],'height_m':p['height_m'],'variance':p['variance'],'expires_s':p['expires_at'],'sender':sender}
  for i,p in enumerate(pos):
   if cell(*p) in blind_cells:raise ValueError('predeclared blind cell sampled')
   val=field.query(float(p[0]),float(p[1]),float(p[2]),now)+sensor_noise(seed,i,step,1.)
   sample={'sample_id':f'{i}:{step}','node_id':i,'step':step,'x_m':float(p[0]),'y_m':float(p[1]),'h_m':float(p[2]),'t_s':now,'value_dbm':float(val)};own[i].append(sample);samples.append(sample);traj.append({'node_id':i,'step':step,'t_s':now,'x_m':float(p[0]),'y_m':float(p[1]),'h_m':float(p[2])})
   if net:outgoing.append({'kind':'SAMPLE','sender':i,'created_s':now,'payload':sample})
  chosen=pos.copy()
  for i,p in enumerate(pos):
   endpoints,legal=candidates(p,pos,chosen,i,blind_cells);rejected+=int((~legal).sum())
   if not legal.any():raise RuntimeError(f'no legal fixed-length segment step={step} node={i}')
   local=own[i];history=sorted(local+list(received[i].values()),key=lambda o:(o['t_s'],o['node_id'],o['sample_id'])) if net else local
   base=variance_scores(p,endpoints,local,now);scores=variance_scores(p,endpoints,history,now) if net else base.copy();ids=np.array([region_id(q) for q in endpoints])
   active_intents=[];active_summaries=[]
   if net:
    for item in intents[i].values():
     if item['expires_s']>=now and item['height_m']==float(p[2]) and item['sender']<i:
      scores[ids==item['target_index']]-=2.;active_intents.append(item)
    for item in summaries[i].values():
     if item['expires_s']>=now and item['height_m']==float(p[2]):
      scores[ids==item['target_index']]+=.1*math.sqrt(max(0.,item['variance']))/10.;active_summaries.append(item)
   picked=int(np.argmax(np.where(legal,scores,-np.inf)));counter=int(np.argmax(np.where(legal,base,-np.inf)));target=endpoints[picked];chosen[i]=target
   decisions.append({'node_id':i,'step':step,'position':p.tolist(),'heading_index':picked,'region_id':int(ids[picked]),'counterfactual_heading':counter,'visible_sample_ids':[s['sample_id'] for s in history], 'received_sample_ids':sorted(received[i]),'intents':active_intents,'summaries':active_summaries})
   if net:
    mean,std=reconstruct(history,[[*target,now]]);region=int(ids[picked]);expiry=now+2*DT
    outgoing.extend([{'kind':'TASK_INTENT','sender':i,'created_s':now,'payload':{'target_index':region,'expires_s':expiry,'height_m':float(p[2]),'utility':float(scores[picked]),'eta_s':now+DT}}, {'kind':'MAP_SUMMARY','sender':i,'created_s':now,'payload':{'region_id':region,'mean':float(mean[0]),'variance':float(std[0]**2),'sample_count':len(history),'timestamp':now,'height_m':float(p[2]),'expires_at':expiry}}, {'kind':'TASK_UPDATE','sender':i,'created_s':now,'payload':{'region_id':region,'owner':i,'status':'active','expires_at':expiry,'height_m':float(p[2])}}])
  if net:net.send(now,pos.copy(),outgoing)
  lengths=np.linalg.norm(chosen-pos,axis=1)
  if not np.allclose(lengths,DIST,rtol=0,atol=1e-8):raise ValueError('unequal actual segment length')
  distance+=lengths;pos=chosen
 return {'policy':policy,'seed':seed,'nodes':n,'samples':samples,'decisions':decisions,'trajectory':traj,'events':events,'flight_distance_m':distance.tolist(),'final_positions':pos.tolist(),'candidate_rejections':rejected,'network':net.snapshot(STEPS*DT) if net else None}

def evaluate(field,result,blind):
 now=(STEPS-1)*DT;q=np.array([[x,y,h,now] for x,y,h in blind]);truth=np.array([field.query(*p) for p in q]);all_samples=result['samples'];offline=score(q,truth,all_samples);mask=truth!=FLOOR;floor_score=score(q[mask],truth[mask],all_samples) if mask.any() else {'support':0,'rmse_db':None};online=[]
 for i in range(result['nodes']):
  ids=set(result['decisions'][-result['nodes']+i]['visible_sample_ids']);obs=[s for s in all_samples if s['sample_id'] in ids];online.append(score(q,truth,obs)['rmse_db'])
 per_height={}
 for height in HEIGHTS:
  selected=q[:,2]==height;filtered=selected&mask
  per_height[str(int(height))]={'raw':score(q[selected],truth[selected],all_samples),'floor_excluded':score(q[filtered],truth[filtered],all_samples) if filtered.any() else {'support':0,'rmse_db':None},'floor_count':int((selected&~mask).sum())}
 return {'offline':offline,'floor_excluded':floor_score,'per_height':per_height,'online_mean_rmse':float(np.mean(online)),'blind_truth_floor_count':int((~mask).sum())}

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=pathlib.Path);p.add_argument('--pilot',action='store_true');a=p.parse_args();out=a.out;out.mkdir(parents=True,exist_ok=False);field=FieldV2(ROOT/'data/field_feasibility_v2');ns=[5] if a.pilot else [5,10,20,30];seeds=[2000,2001] if a.pilot else list(range(2000,2020));started=time.time();summary=[];cfg={'nodes':ns,'seeds':seeds,'heights_m':HEIGHTS,'region_m':REGION,'dt_s':DT,'steps':STEPS,'speed_m_s':2,'distance_per_step_m':DIST,'heading_count':24,'min_separation_m':SAFETY,'blind_rule':'12 coordinate-only cells per height chosen before either mission; sampled endpoints prohibited','policy_difference':'common fixed-length heading planner, global region IDs for delivered intents; C local, D local plus delivered messages','noise_sigma_db':1,'network':{'range_m':400,'bandwidth_bps':1000000,'propagation_delay_s':0,'loss_probability':0}}
 (out/'config.json').write_text(json.dumps(cfg,indent=2),encoding='utf8')
 source_files=[pathlib.Path(__file__),HERE/'sampling.py',HERE/'analysis.py',HERE/'mission.py',HERE/'mission_transport.py',HERE/'network.py',HERE/'data_v2.py']
 source_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
 (out/'RUN_MANIFEST.json').write_text(json.dumps({'task_id':'E2-045','run_id':out.name,'status':'running','started_at':started,'timezone':'Asia/Shanghai','worktree':str(ROOT),'git_commit':None,'source_sha256':source_hashes,'dirty_files_sha256':source_hashes,'config':cfg,'config_file':str(out/'config.json'),'python_executable':sys.executable,'process_id':os.getpid(),'command':sys.argv,'output_directory':str(out)},indent=2),encoding='utf8')
 for n in ns:
  for seed in seeds:
   initial=initial_positions(n,REGION,HEIGHTS,SAFETY,seed);blind=holdouts(n,seed,initial);pair={};errors={}
   for policy in ('C','D'):
    try:
     result=run_one(field,n,seed,policy,blind);metrics=evaluate(field,result,blind);pair[policy]=(result,metrics)
     with gzip.open(out/f'n{n:02d}-seed{seed}-{policy}.json.gz','wt',encoding='utf8') as f:json.dump({'blind':blind,'result':result,'evaluation':metrics},f,separators=(',',':'))
    except (ValueError,RuntimeError) as exc:errors[policy]=str(exc)
   row={'nodes':n,'seed':seed,'status':'failed' if errors else 'completed','failure':json.dumps(errors,ensure_ascii=False),'blind_cells':len(blind)}
   if not errors:
    c,cm=pair['C'];d,dm=pair['D'];row.update(c_flight_m=sum(c['flight_distance_m']),d_flight_m=sum(d['flight_distance_m']),distance_difference_m=sum(d['flight_distance_m'])-sum(c['flight_distance_m']),time_difference_s=d['trajectory'][-1]['t_s']-c['trajectory'][-1]['t_s'],sample_difference=len(d['samples'])-len(c['samples']),c_offline_rmse=cm['offline']['rmse_db'],d_offline_rmse=dm['offline']['rmse_db'],delta_offline_rmse=dm['offline']['rmse_db']-cm['offline']['rmse_db'],c_online_rmse=cm['online_mean_rmse'],d_online_rmse=dm['online_mean_rmse'],c_floor_excluded_rmse=cm['floor_excluded']['rmse_db'],d_floor_excluded_rmse=dm['floor_excluded']['rmse_db'],delta_floor_excluded_rmse=dm['floor_excluded']['rmse_db']-cm['floor_excluded']['rmse_db'] if cm['floor_excluded']['rmse_db'] is not None else None,blind_floor_count=cm['blind_truth_floor_count'],c_rejections=c['candidate_rejections'],d_rejections=d['candidate_rejections'],delivered_events=len(d['events']),message_affected_decisions=sum(x['heading_index']!=x['counterfactual_heading'] for x in d['decisions']))
    assert abs(row['distance_difference_m'])<1e-6 and row['sample_difference']==0 and dm['blind_truth_floor_count']==cm['blind_truth_floor_count']
   summary.append(row);print('N',n,'seed',seed,row['status'],flush=True)
   with (out/'pairs.partial.jsonl').open('a',encoding='utf8') as partial:partial.write(json.dumps(row,ensure_ascii=False)+'\n')
 keys=sorted({k for r in summary for k in r});
 with (out/'pairs.csv').open('w',newline='',encoding='utf8') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(summary)
 aggregates=[]
 for n in ns:
  complete=[r for r in summary if r['nodes']==n and r['status']=='completed'];deltas=np.array([r['delta_offline_rmse'] for r in complete]);entry={'nodes':n,'attempted':len(seeds),'completed':len(complete),'failed':len(seeds)-len(complete)}
  if len(deltas):entry['mean_D_minus_C_rmse']=float(deltas.mean())
  if len(deltas)>1:
   sem=float(stats.sem(deltas));ci=stats.t.interval(.95,len(deltas)-1,loc=float(deltas.mean()),scale=sem) if sem else (float(deltas.mean()),)*2;entry.update(sd=float(deltas.std(ddof=1)),ci95=list(map(float,ci)),paired_t_pvalue=float(stats.ttest_1samp(deltas,0).pvalue) if sem else None)
  filtered=np.array([r['delta_floor_excluded_rmse'] for r in complete if r['delta_floor_excluded_rmse'] is not None])
  if len(filtered):entry['floor_excluded_mean_D_minus_C_rmse']=float(filtered.mean());entry['floor_excluded_pairs']=len(filtered)
  if len(filtered)>1:
   sem=float(stats.sem(filtered));ci=stats.t.interval(.95,len(filtered)-1,loc=float(filtered.mean()),scale=sem) if sem else (float(filtered.mean()),)*2
   entry.update(floor_excluded_sd=float(filtered.std(ddof=1)),floor_excluded_ci95=list(map(float,ci)),floor_excluded_pvalue=float(stats.ttest_1samp(filtered,0).pvalue) if sem else None)
  aggregates.append(entry)
 (out/'summary.json').write_text(json.dumps(aggregates,indent=2),encoding='utf8')
 unchanged=all(hashlib.sha256(p.read_bytes()).hexdigest()==source_hashes[p.name] for p in source_files)
 manifest={'template_only':False,'task_id':'E2-045','run_id':out.name,'status':'completed' if unchanged else 'invalid_source_changed','started_at':started,'finished_at':time.time(),'timezone':'Asia/Shanghai','worktree':str(ROOT),'git_commit':None,'upstream_commit':None,'dirty_files_sha256':source_hashes,'source_sha256':source_hashes,'config':cfg,'config_file':str(out/'config.json'),'python_executable':sys.executable,'process_id':os.getpid(),'command':sys.argv,'output_directory':str(out),'data_and_weights_sha256':{'data_ready.json':hashlib.sha256((ROOT/'data/field_feasibility_v2/data_ready.json').read_bytes()).hexdigest()},'seeds':seeds,'budget':{'nodes':ns,'strategies':['C','D'],'max_runs':2*len(ns)*len(seeds)},'dependency_snapshot':{'numpy':np.__version__},'exit_code':0 if unchanged else 1,'review_reference':'coordination/tasks/E2-045.md','limitations':['four fixed height planes and 500m region; no vertical transitions','coordinate-only fixed blind points exclude only sample endpoints','synchronous sequential geometric safety filter uses global positions and is not distributed collision avoidance','discrete 24 fixed-length headings change the original C/D motion planner','unclassified repeated floor retained; secondary score excludes exact floor only'],'outcomes':aggregates}
 (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
 if not unchanged:raise RuntimeError('source files changed during run; results not frozen')
if __name__=='__main__':main()
