"""Equal-exogenous-load LoRa capacity and separate command-window experiments."""
import argparse,csv,hashlib,heapq,json,math,os,random,sys,time,statistics
from datetime import datetime,timezone
from pathlib import Path
from run import airtime,pct,FREQ

def rand(seed,*keys):return random.Random('|'.join(map(str,(seed,*keys)))).random()

def experiment(seed,mode,kind,duration,window,dl_loss,ack_loss,clock_offset,reboot,base_period):
 heap=[];serial=0;events=[];nodes=[dict(seq=0,period=base_period,grant=False,pending=None,boot=1,executed={},ack=None,received=0,offered=0,deadline=0,deadline05=0,deadline1=0,eligible=0,delay=[],aoi=[],rx_s=0.) for _ in range(30)]
 active={};tx_active=False;gateway_free=0.;sent=0;received=0;collision=0;tx_s=0.;ul_s=0.;rx_s=0.;commands={};issued=set();reboot_dedup_checked=False
 def push(t,priority,typ,data):
  nonlocal serial
  if t<=duration:serial+=1;heapq.heappush(heap,(t,priority,serial,typ,data))
 def emit(t,typ,**fields):events.append(dict(t=round(t,6),type=typ,**fields))
 def issue(t,i,action):
  key=f'{action}-{i}';c=dict(id=key,target=i,action=action,version=1,issued=t,expires=t+60,attempts=0,executed=None,receipt=None,duplicates=0,applied_boot=None)
  commands[key]=c;emit(t,'command_issued',cmd_id=key,target=i,version=1,expires=c['expires'],action=action,value=15 if action=='period' else 'microframe_slot')
  if window=='periodic':plan(t,c)
 def plan(t,c):
  nonlocal gateway_free
  if c['receipt'] is not None or c['attempts']>=4 or t>=c['expires']:return
  phase=(c['target']%8)*.02
  if window=='periodic':
   t=max(t,gateway_free);predicted=math.floor(t)+phase
   if predicted<t:predicted+=1
  else:predicted=t
  start=max(predicted,gateway_free);end=start+airtime(32);gateway_free=end+.02
  c['attempts']+=1;push(start,1,'dl_start',dict(id=c['id'],predicted=predicted,end=end,attempt=c['attempts']))
 for i in range(30):
  phase=rand(seed,'phase',i)*base_period;push(phase,2,'generate',i)
  if kind=='capacity' and mode=='eight_scheduled':push(0,1,'issue',(i,'grant'))
  if kind=='command' or kind=='single_command' and i==0:push(100+i*.05,1,'issue',(i,'period'))
 if reboot:push(103,0,'reboot',0);push(104,1,'replay_inject',0)
 for t in range(int(duration)+1):push(t,4,'sample',None)
 while heap:
  t,_,_,typ,data=heapq.heappop(heap)
  if typ=='issue':issue(t,*data)
  elif typ=='reboot':
   n=nodes[data];n['boot']+=1;n['seq']=0;n['ack']=None;n['pending']=None
   for u in active.values():
    if u['node']==data:u['reason']='node_reboot'
   emit(t,'node_reboot',node=data,boot=n['boot'],persisted_commands=list(n['executed']))
  elif typ=='replay_inject':
   i=data;n=nodes[i];key=f'period-{i}'
   if key in n['executed']:
    reboot_dedup_checked=True;commands[key]['duplicates']+=1;n['ack']=key;emit(t,'command_duplicate',cmd_id=key,target=i,executor=i,fault_injected=True,boot=n['boot'])
   else:emit(t,'fault_not_exercised',node=i,reason='no_prior_execution')
  elif typ=='sample':
   for n in nodes:
    if n['received'] and 'last' in n:n['aoi'].append(t-n['last'])
   if t%60==0:emit(t,'resource_sample',pending_buffers=sum(n['pending'] is not None for n in nodes),active_radios=len(active),pending_commands=sum(c['receipt'] is None and t<c['expires'] for c in commands.values()),nodes_known=sum('last' in n for n in nodes))
   if window=='periodic' and t<duration:
    for n in nodes:n['rx_s']+=.2
  elif typ=='generate':
   i=data;n=nodes[i];n['seq']+=1;seq=n['seq'];n['offered']+=1;n['eligible']+=int(t+2<=duration);sent+=1
   emit(t,'offered',origin=i,boot=n['boot'],seq=seq,dst='gateway',deadline_s=2)
   next_t=t+n['period']+(rand(seed,'jitter',i,seq)-.5)*min(.5,base_period*.1);push(next_t,2,'generate',i)
   if n['pending'] is not None:emit(t,'packet_rejected',origin=i,boot=n['boot'],seq=seq,reason='one_slot_full');continue
   if mode=='eight_scheduled' and n['grant']:
    slot=(i//8)*.25;local=t*(1+20e-6*(rand(seed,'drift',i)-.5)*2);target=math.floor(local)+slot
    if target<local:target+=1
    start=target/(1+20e-6*(rand(seed,'drift',i)-.5)*2);ch=i%8
   else:start=t;ch=0 if mode=='single_random' else int(rand(seed,'channel',i,seq)*8)
   n['pending']=(n['boot'],seq,t);push(start,2,'ul_start',dict(node=i,boot=n['boot'],seq=seq,generated=t,ch=ch))
  elif typ=='ul_start':
   x=data;i=x['node']
   if x['boot']!=nodes[i]['boot']:emit(t,'uplink_lost',origin=i,boot=x['boot'],seq=x['seq'],reason='node_reboot');continue
   end=t+airtime(128);x['end']=end;x['reason']=None;ul_s+=min(airtime(128),duration-t)
   for other in active.values():
    if other['ch']==x['ch']:other['reason']='same_channel';x['reason']='same_channel'
   if tx_active:x['reason']='gateway_tx'
   active[(i,x['boot'],x['seq'])]=x;emit(t,'uplink_start',origin=i,boot=x['boot'],seq=x['seq'],channel=x['ch'],frequency_hz=FREQ[x['ch']]);push(end,0,'ul_end',x)
  elif typ=='ul_end':
   x=data;i=x['node'];n=nodes[i];active.pop((i,x['boot'],x['seq']),None)
   if n['pending'] and n['pending'][:2]==(x['boot'],x['seq']):n['pending']=None
   if window=='uplink' and x['reason']!='node_reboot':n['rx_s']+=min(.2,max(0.,duration-t-1))
   if x['reason']:collision+=1;emit(t,'uplink_lost',origin=i,boot=x['boot'],seq=x['seq'],reason=x['reason']);continue
   received+=1;n['received']+=1;n['last']=x['generated'];n['deadline']+=t-x['generated']<=2;n['deadline05']+=t-x['generated']<=.5;n['deadline1']+=t-x['generated']<=1;n['delay'].append(t-x['generated'])
   emit(t,'delivered',origin=i,boot=x['boot'],seq=x['seq'],dst='gateway',receiver='gateway',delay_s=t-x['generated'])
   if n['ack']:
    c=commands[n['ack']]
    if rand(seed,'ack',i,c['id'],c['attempts'])>=ack_loss:
     c['receipt']=t;emit(t,'command_receipt',cmd_id=c['id'],target=i);n['ack']=None
    else:emit(t,'receipt_lost',cmd_id=c['id'],target=i)
   if window=='uplink':
    pending=[c for c in commands.values() if c['target']==i and c['receipt'] is None and c['issued']<=t<c['expires'] and c['attempts']<4]
    if pending:plan(t+1,pending[0])
  elif typ=='dl_start':
   x=data;c=commands[x['id']];i=c['target']
   if c['receipt'] is not None or t>=c['expires']:emit(t,'gateway_tx_cancelled',cmd_id=c['id'],target=i,reason='acknowledged_or_expired');continue
   node_transmitting=any(u['node']==i for u in active.values());tx_active=True;tx_s+=airtime(32)
   for u in active.values():u['reason']='gateway_tx'
   emit(t,'gateway_tx',cmd_id=c['id'],target=i,attempt=x['attempt'],predicted_window=x['predicted'])
   actual=x['predicted']+clock_offset+(rand(seed,'clock',i)-.5)*40e-6*t
   miss=abs(t-actual)+airtime(32)>.1
   lost=rand(seed,'downlink',i,c['id'],x['attempt'])<dl_loss
   push(x['end'],0,'dl_end',dict(id=c['id'],reason='node_transmitting' if node_transmitting else 'window_miss' if miss else 'downlink_loss' if lost else None))
  elif typ=='dl_end':
   tx_active=False;c=commands[data['id']];i=c['target'];n=nodes[i]
   if data['reason'] or t>c['expires']:
    emit(t,'command_missed',cmd_id=c['id'],target=i,reason=data['reason'] or 'expired')
   elif c['id'] in n['executed']:
    c['duplicates']+=1;n['ack']=c['id'];emit(t,'command_duplicate',cmd_id=c['id'],target=i,executor=i)
   else:
    n['executed'][c['id']]=c['version'];c['executed']=t;c['applied_boot']=n['boot'];n['ack']=c['id']
    if c['action']=='grant':n['grant']=True
    else:n['period']=15.
    emit(t,'command_executed',cmd_id=c['id'],target=i,executor=i,boot=n['boot'],version=1)
   if window=='periodic' and c['receipt'] is None:plan(t+1,c)
 lat=[c['executed']-c['issued'] for c in commands.values() if c['executed'] is not None];receipt=[c['receipt']-c['issued'] for c in commands.values() if c['receipt'] is not None]
 rows=[dict(node=i,offered=n['offered'],received=n['received'],deadline_0_5s=n['deadline05'],deadline_1s=n['deadline1'],deadline_2s=n['deadline'],deadline_eligible_2s=n['eligible'],pdr=n['received']/n['offered'] if n['offered'] else None,aoi_p95_s=pct(n['aoi'],.95),aoi_p99_s=pct(n['aoi'],.99),known_aoi_samples=len(n['aoi']),receive_listen_s=n['rx_s']) for i,n in enumerate(nodes)]
 summary=dict(seed=seed,mode=mode,kind=kind,window=window,offered_period_s=base_period,dl_loss=dl_loss,ack_loss=ack_loss,clock_offset_s=clock_offset,reboot=reboot,offered=sent,received=received,pdr=received/sent if sent else None,deadline_0_5s=sum(n['deadline05'] for n in nodes),deadline_1s=sum(n['deadline1'] for n in nodes),deadline_2s=sum(n['deadline'] for n in nodes),collision=collision,inflight=len(active),deadline_eligible_2s=sum(n['eligible'] for n in nodes),p95_delivery_delay_s=pct([v for n in nodes for v in n['delay']],.95),p99_delivery_delay_s=pct([v for n in nodes for v in n['delay']],.99),delivery_latency_n=sum(len(n['delay']) for n in nodes),gateway_uplink_airtime_sum_s=ul_s,reboot_dedup_checked=reboot_dedup_checked,worst_node_pdr=min(r['pdr'] for r in rows if r['pdr'] is not None),worst_node_aoi_p95_s=max((r['aoi_p95_s'] for r in rows if r['aoi_p95_s'] is not None),default=None),worst_node_aoi_p99_s=max((r['aoi_p99_s'] for r in rows if r['aoi_p99_s'] is not None),default=None),gateway_tx_s=tx_s,total_node_rx_s=sum(n['rx_s'] for n in nodes),commands=len(commands),executed=len(lat),receipts=len(receipt),command_execution_p95_s=pct(lat,.95),command_execution_p99_s=pct(lat,.99),command_receipt_p95_s=pct(receipt,.95),command_execution_latency_n=len(lat),command_at_1s=sum(x<=1 for x in lat),command_at_2s=sum(x<=2 for x in lat),command_at_5s=sum(x<=5 for x in lat),duplicates_received=sum(c['duplicates'] for c in commands.values()),duplicate_executions=0)
 reasons={}
 for e in events:
  if e['type'] in ('uplink_lost','packet_rejected'):
   key=e['reason'];reasons[key]=reasons.get(key,0)+1
 summary['packet_failure_reasons']=json.dumps(reasons,sort_keys=True)
 summary['unresolved_at_end']=sent-received-sum(reasons.values())
 return summary,rows,list(commands.values()),events

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);p.add_argument('--seeds',type=int,default=20);p.add_argument('--duration',type=int,default=300);p.add_argument('--suite',choices=['core','pressure','long'],default='core');a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=datetime.now(timezone.utc).isoformat();results=[]
 config=[('single_random','capacity','periodic',.1,.1,0.,False),('eight_random','capacity','periodic',.1,.1,0.,False),('eight_scheduled','capacity','periodic',.1,.1,0.,False),('eight_random','command','uplink',.1,.1,0.,False),('eight_random','command','periodic',.1,.1,0.,False),('eight_random','command','periodic',.5,.5,0.,False),('eight_random','command','periodic',.1,.1,.08,False),('eight_random','command','periodic',.1,.9,0.,True),('eight_random','command','periodic',.5,.5,.08,True),('eight_random','single_command','uplink',.1,.1,0.,False),('eight_random','single_command','periodic',.1,.1,0.,False)]
 if a.suite=='pressure':config=[(m,'capacity','periodic',.1,.1,0.,False,period) for period in (5.,1.,.5,.2) for m in ('eight_random','eight_scheduled')]
 elif a.suite=='long':config=[('eight_random','capacity','periodic',.1,.1,0.,False,10.),('eight_scheduled','capacity','periodic',.1,.1,0.,False,10.),('eight_random','command','periodic',.1,.1,0.,False,10.)]
 else:config=[tuple(x)+(10.,) for x in config]
 source=Path(__file__).resolve();root=source.parents[2];inputs=[source,source.with_name('run.py')]
 manifest=dict(task_id='E2-033',run_id=out.name,started_at=start,finished_at=None,timezone='Asia/Shanghai',worktree=str(root),git_commit=None,dirty_files_sha256={str(x.relative_to(root)):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=list(range(a.seeds)),budget=dict(simulated_seconds=a.duration,workers=1,wall_seconds_limit=1200),output_directory=str(out),process_id=os.getpid(),status='running',exit_code=None,review_reference=None,limitations=['Synthetic standalone fixed 10s offered load, simplified RF/window assumptions, not ESP target resource measurement.'])
 (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');end=time.monotonic()+1200
 try:
  for j,params in enumerate(config):
   for seed in range(a.seeds):
    if time.monotonic()>end:raise TimeoutError('finite 20 minute batch deadline')
    m,k,w,l,ack,c,r,period=params;row,nodes,commands,events=experiment(seed,m,k,a.duration,w,l,ack,c,r,period);results.append(row)
    folder=out/f'{j+1:02}-{k}-{m}-{w}-period{period:g}-seed{seed:02}';folder.mkdir()
    (folder/'summary.json').write_text(json.dumps(row,indent=2),encoding='utf-8');(folder/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
    with (folder/'nodes.csv').open('w',newline='',encoding='utf-8') as f:wr=csv.DictWriter(f,fieldnames=nodes[0]);wr.writeheader();wr.writerows(nodes)
    with (folder/'events.jsonl').open('w',encoding='utf-8') as f:
     for e in events:f.write(json.dumps(e,separators=(',',':'))+'\n')
   print(k,m,w,'completed',a.seeds,flush=True)
  with (out/'runs.csv').open('w',newline='',encoding='utf-8') as f:wr=csv.DictWriter(f,fieldnames=results[0]);wr.writeheader();wr.writerows(results)
  (out/'runs.json').write_text(json.dumps(results,indent=2),encoding='utf-8');manifest.update(status='passed',exit_code=0)
 except Exception as exc:manifest.update(status='failed',exit_code=1,error=repr(exc));raise
 finally:manifest['finished_at']=datetime.now(timezone.utc).isoformat();(out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
if __name__=='__main__':main()
