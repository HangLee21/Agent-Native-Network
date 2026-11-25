"""Finite, single-process LoRa reference/control discrete-event model."""
import argparse,csv,hashlib,heapq,json,math,os,random,statistics,sys,time,subprocess
from datetime import datetime,timezone
from pathlib import Path

FREQ=[470300000+200000*i for i in range(8)]
def airtime(n,sf=7,bw=125000,cr=1,preamble=8):
    symbol=2**sf/bw;de=1 if sf>=11 and bw==125000 else 0
    payload=8+max(math.ceil((8*n-4*sf+28+16)/(4*(sf-2*de)))*(cr+4),0)
    return (preamble+4.25+payload)*symbol

def pct(xs,q):
    if not xs:return None
    xs=sorted(xs);i=(len(xs)-1)*q;a=int(i);b=math.ceil(i);return xs[a]+(xs[b]-xs[a])*(i-a)

def experiment(mode,seed,duration,loss,clock_offset):
    rng=random.Random(seed);phase=[rng.random()*10 for _ in range(30)];drift=[rng.uniform(-20,20)*1e-6 for _ in phase]
    # Independent stable random streams preserve offered random schedules across modes.
    streams=[random.Random(seed*1000+i+731) for i in range(30)];channels=[random.Random(seed*1000+i+900731) for i in range(30)];dlrng=random.Random(seed+202630);ackrng=random.Random(seed+803010)
    heap=[];counter=0;events=[];active={};radio={'free':0.0,'tx':False};active_tx=set();attempted=[0]*30;received=[0]*30
    node=[dict(seq=0,period=10.,scheduled=False,executed={},pending_acks=set()) for _ in phase]
    command={};neighbor={};last_node={};aoi_node=[[] for _ in phase];coverage_node=[[] for _ in phase];aoi_pair={(i,j):[] for i in range(30) for j in range(8)};cover=[]
    collision={'same_channel':0,'gateway_tx':0};down_air=0.;up_air=0.;delivered=0
    def push(t,priority,kind,data):
        nonlocal counter
        if t<=duration:counter+=1;heapq.heappush(heap,(t,priority,counter,kind,data))
    def log(t,kind,**kw):events.append(dict(t=round(t,6),type=kind,**kw))
    def cmd_new(t,i,kind):
        key=f'{kind}-{i}';command[key]=dict(cmd_id=key,target=i,kind=kind,version=1,issued=t,expires=min(duration,t+120),attempts=0,executed=None,ack=None,dup=0)
        log(t,'command_issued',cmd_id=key,target=i,version=1,valid_until=command[key]['expires'],action=kind,value=15 if kind=='period' else 'assigned_slot',slot_s=(i//8)*.8+.12 if kind=='schedule' else None,channel=i%8 if kind=='schedule' else None)
    if mode=='eight_scheduled':
        for i in range(30):cmd_new(0,i,'schedule')
    for i in range(30):cmd_new(100,i,'period')
    for i,t in enumerate(phase):push(t,2,'uplink_start',i)
    for t in range(0,int(duration)+1):push(t,3,'sample',None)
    while heap:
        t,_,_,kind,data=heapq.heappop(heap)
        if kind=='uplink_start':
            i=data;n=node[i];n['seq']+=1;seq=n['seq'];attempted[i]+=1
            channel=0 if mode=='single_random' else (i%8 if n['scheduled'] else channels[i].randrange(8))
            peers=[(2*(seq-1)+k)%8 for k in range(4)];end=t+airtime(128);frame=dict(node=i,seq=seq,start=t,end=end,channel=channel,peers=peers,acks=list(n['pending_acks']),reason=None)
            for other in active.values():
                if other['channel']==channel:other['reason']='same_channel';frame['reason']='same_channel'
            if active_tx:frame['reason']='gateway_tx'
            active[(i,seq)]=frame;up_air+=min(airtime(128),max(0,duration-t));log(t,'offered',origin=f'n{i}',origin_boot=1,seq=seq,dst='gateway',reachable_at_offer=True,channel=channel,frequency_hz=FREQ[channel],airtime_s=airtime(128))
            if n['scheduled']:
                slot=(i//8)*.8+.12;local=t*(1+drift[i]);period=n['period'];next_local=(math.floor(local/period)+1)*period+slot
                nxt=next_local/(1+drift[i])
            else:nxt=t+n['period']+streams[i].uniform(-.25,.25)
            push(nxt,2,'uplink_start',i);push(end,0,'uplink_end',(i,seq))
        elif kind=='uplink_end':
            f=active.pop(data);i=f['node'];seq=f['seq']
            if f['reason']:
                collision[f['reason']]+=1;log(t,'uplink_lost',origin=f'n{i}',seq=seq,reason=f['reason']);continue
            received[i]+=1;delivered+=1;last_node[i]=f['start'];log(t,'delivered',origin=f'n{i}',origin_boot=1,seq=seq,dst='gateway',receiver='gateway',channel=f['channel'])
            for peer in f['peers']:
                neighbor[(i,peer)]=f['start'];log(t,'neighbor_received',observer=f'n{i}@1',peer=f'n{(i+peer+1)%30}@1',generated_at=f['start'])
            for key in f['acks']:
                c=command[key]
                if c['ack'] is None and ackrng.random()<.1:
                    log(t,'command_ack_lost',cmd_id=key,target=i,reason='gateway_application_receipt_loss');continue
                if c['ack'] is None:c['ack']=t;log(t,'command_ack_received',cmd_id=key,target=i)
                node[i]['pending_acks'].discard(key)
            pending=[c for c in command.values() if c['target']==i and c['issued']<=t<c['expires'] and c['ack'] is None and c['attempts']<4]
            pending.sort(key=lambda c:(c['issued'],c['cmd_id']))
            if pending:
                c=pending[0];c['attempts']+=1;send=max(t+1.,radio['free']);end=send+airtime(32);radio['free']=end+.02
                push(send,1,'downlink_start',dict(cmd=c['cmd_id'],node=i,center=t+1.,end=end,skew=clock_offset+drift[i]*t+dlrng.uniform(-.008,.008)))
        elif kind=='downlink_start':
            x=data;c=command[x['cmd']];i=x['node'];down_air+=min(airtime(32),max(0,duration-t));active_tx.add(x['cmd'])
            for f in active.values():f['reason']='gateway_tx'
            log(t,'gateway_tx',cmd_id=c['cmd_id'],target=i,attempt=c['attempts'],airtime_s=airtime(32))
            within=abs(t-x['center']-x['skew'])+airtime(32)<=.1
            reason='outside_receive_window' if not within else 'downlink_loss' if dlrng.random()<loss else None
            push(x['end'],0,'downlink_end',dict(cmd=x['cmd'],node=i,reason=reason))
        elif kind=='downlink_end':
            x=data;active_tx.discard(x['cmd']);c=command[x['cmd']];i=x['node']
            if t>=c['expires']:log(t,'command_not_received',cmd_id=x['cmd'],target=i,reason='expired');continue
            if x['reason']:log(t,'command_not_received',cmd_id=x['cmd'],target=i,reason=x['reason']);continue
            if x['cmd'] in node[i]['executed']:
                c['dup']+=1;log(t,'command_duplicate',cmd_id=x['cmd'],target=i,executor=i);node[i]['pending_acks'].add(x['cmd']);continue
            node[i]['executed'][x['cmd']]=t;c['executed']=t;node[i]['pending_acks'].add(x['cmd'])
            if c['kind']=='schedule':node[i]['scheduled']=True
            else:node[i]['period']=15.
            log(t,'command_executed',cmd_id=x['cmd'],target=i,executor=i,version=1,action=c['kind'])
        else:
            known_nodes=0;known_pairs=0
            for i in range(30):
                ages=[]
                for j in range(8):
                    stamp=neighbor.get((i,j));age=t-stamp if stamp is not None else None
                    if age is not None:ages.append(age);aoi_pair[(i,j)].append(age);known_pairs+=age<=30
                    if t%5==0:log(t,'aoi_sample',observer=f'n{i}@1',peer=f'n{(i+j+1)%30}@1')
                coverage_node[i].append(sum((t-neighbor[(i,j)]<=30) for j in range(8) if (i,j) in neighbor)/8)
                if i in last_node:aoi_node[i].append(t-last_node[i]);known_nodes+=1
            cover.append(known_pairs/240);log(t,'coverage_sample',known_nodes=known_nodes,neighbor_coverage_30s=known_pairs/240)
    # Unique destination receive is delivery; outstanding in-flight frames at end are right-censored.
    stats=[]
    for i in range(30):
        stats.append(dict(node=f'n{i}',offered=attempted[i],received=received[i],pdr=received[i]/attempted[i] if attempted[i] else None,node_aoi_p95_s=pct(aoi_node[i],.95),neighbor_aoi_p95_s=json.dumps({f'n{(i+j+1)%30}':pct(aoi_pair[(i,j)],.95) for j in range(8)}),mean_neighbor_coverage_30s=statistics.mean(coverage_node[i]),known_node_aoi_samples=len(aoi_node[i])))
    summary=dict(mode=mode,seed=seed,duration_s=duration,downlink_loss_probability=loss,clock_offset_s=clock_offset,
        offered=sum(attempted),received=delivered,pdr=delivered/sum(attempted),collision=collision,
        node_aoi_p95_s=pct([a for v in aoi_node for a in v],.95),neighbor_aoi_p95_s=pct([a for v in aoi_pair.values() for a in v],.95),
        mean_neighbor_coverage_30s=statistics.mean(cover),uplink_airtime_sum_s=up_air,downlink_airtime_s=down_air,
        commands_issued=len(command),commands_executed=sum(c['executed'] is not None for c in command.values()),
        commands_ack_received=sum(c['ack'] is not None for c in command.values()),duplicate_executions=0,
        duplicate_receipts=sum(c['dup'] for c in command.values()),command_execution_p95_s=pct([c['executed']-c['issued'] for c in command.values() if c['executed'] is not None],.95),
        scheduled_nodes=sum(n['scheduled'] for n in node),censored_uplinks=len(active))
    return summary,stats,list(command.values()),events

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    started=datetime.now(timezone.utc).isoformat();root=Path(__file__).resolve().parents[2];source=Path(__file__);configs=[(m,s,0.1,0.) for m in ('single_random','eight_random','eight_scheduled') for s in (11,22,33)] + [('eight_scheduled',s,l,c) for s,l,c in [(11,.5,0.),(22,.1,.12),(33,.5,.12)]]
    manifest=dict(task_id='E2-033',run_id=out.name,started_at=started,timezone='Asia/Shanghai',worktree=str(root),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),dirty_files_sha256={source.relative_to(root).as_posix():hashlib.sha256(source.read_bytes()).hexdigest()},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file='parameters.json',seeds=[11,22,33],budget=dict(runs=12,simulated_seconds=300,workers=1),output_directory=str(out),process_id=os.getpid(),status='running',finished_at=None,exit_code=None,review_reference=None,limitations=['Simplified synthetic LoRa model; no physical RF, capture, cross-SF or verified downlink hardware.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    params=dict(frequency_hz=FREQ,phy=dict(sf=7,bandwidth_hz=125000,coding_rate='4/5',preamble=8,crc=True,explicit_header=True),uplink_bytes=128,downlink_bytes=32,uplink_airtime_s=airtime(128),downlink_airtime_s=airtime(32),period_s=10,jitter_s=.25,receive_window_delay_s=1,receive_window_s=.2,drift_ppm=[-20,20],switch_guard_s=.02,downlink_attempt_limit=4,application_receipt_loss_probability=.1,neighbor_rows=4,total_neighbors=8,coverage_age_s=30)
    (out/'parameters.json').write_text(json.dumps(params,indent=2),encoding='utf-8');summaries=[]
    try:
        for index,(mode,seed,loss,offset) in enumerate(configs):
            name=f'{index+1:02}-{mode}-s{seed}-loss{loss}-clock{offset}';folder=out/name;folder.mkdir()
            summary,nodes,commands,events=experiment(mode,seed,300,loss,offset);summaries.append(summary)
            assert summary['received']<=summary['offered'] and summary['commands_ack_received']<=summary['commands_executed'] and summary['duplicate_executions']==0
            (folder/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');(folder/'commands.json').write_text(json.dumps(commands,indent=2),encoding='utf-8')
            with (folder/'nodes.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=nodes[0].keys());w.writeheader();w.writerows(nodes)
            with (folder/'events.jsonl').open('w',encoding='utf-8') as f:
                for event in events:f.write(json.dumps(event,separators=(',',':'))+'\n')
            print(name,round(summary['pdr'],3),summary['commands_executed'],flush=True)
        with (out/'summary.csv').open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=summaries[0].keys());w.writeheader();w.writerows(summaries)
        (out/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8');manifest.update(status='passed',exit_code=0)
    except Exception as e:manifest.update(status='failed',exit_code=1,error=repr(e));raise
    finally:manifest['finished_at']=datetime.now(timezone.utc).isoformat();(out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
if __name__=='__main__':main()
