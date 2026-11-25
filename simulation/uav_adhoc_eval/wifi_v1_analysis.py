"""Independent deadlines for frozen E1 v1 JSONL; no event-to-packet failure guess."""
import argparse,csv,hashlib,json,math,os,statistics,sys
from pathlib import Path
from datetime import datetime,timezone

def quantile(x,q):
 x=sorted(x)
 if not x:return None
 k=(len(x)-1)*q;a=int(k);b=math.ceil(k);return x[a]+(x[b]-x[a])*(k-a)

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.input.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=datetime.now(timezone.utc).isoformat()
 manifest=json.loads((source/'RUN_MANIFEST.json').read_text());cfg=json.loads((source/'config.json').read_text());duration=cfg['seconds']*1000
 h=lambda path:hashlib.sha256(path.read_bytes()).hexdigest();inputs=[source/'RUN_MANIFEST.json',source/'config.json',source/'summary.json']+sorted(source.glob('*.jsonl'))+sorted(p for p in (source/'source').glob('*') if p.is_file())
 provenance={x.relative_to(source).as_posix():h(x) for x in inputs};(out/'SOURCE_HASHES.json').write_text(json.dumps(provenance,indent=2),encoding='utf-8')
 summaries=json.loads((source/'summary.json').read_text()); index={(x['mode'],x['speed_m_s'],x['seed'],x['policy']):x for x in summaries};results=[];packets_out=(out/'packets.csv').open('w',newline='',encoding='utf-8');fields=['run','origin','origin_boot','seq','dst','offered_ms','admitted','received_ms','geometric_4hop_at_submit','end_status','deadline_0_5','deadline_1','deadline_2'];w=csv.DictWriter(packets_out,fieldnames=fields);w.writeheader()
 try:
  for path in sorted(source.glob('*.jsonl')):
   stem=path.stem;motion,speed,seed,policy=stem.split('-',3);seed=int(seed.removeprefix('seed'));speed=int(speed);expected=index[(motion,speed,seed,policy)];packets={};event_counts={}
   for line in path.open(encoding='utf-8'):
    e=json.loads(line);name=e['event'];event_counts[name]=event_counts.get(name,0)+1
    if name not in ('offered','admitted','submission_rejected','destination_received'):continue
    key=(e['origin_id'],e['origin_boot_id'],e['seq'],e['dst_id']);t=e['time_ms']
    if name=='offered':
     if key in packets:raise ValueError('duplicate offered '+str(key))
     packets[key]=dict(t=t,reachable=e['geometric_4hop_at_submit'],admitted=False,received=None,rejected=False)
    else:
     if key not in packets:raise ValueError('missing offer '+str(key))
     row=packets[key]
     if name=='admitted':row['admitted']=True
     elif name=='submission_rejected':row['rejected']=True
     else:
      if e.get('bytes_match') is not True or row['received'] is not None:raise ValueError('invalid or duplicate destination')
      row['received']=t
   delivered=[v for v in packets.values() if v['received'] is not None];reachable=[v for v in packets.values() if v['reachable']];latencies=[v['received']-v['t'] for v in delivered];metrics={}
   assert len(packets)==expected['offered'] and len(delivered)==expected['delivered']
   for deadline in (500,1000,2000):
    eligible=[v for v in packets.values() if v['t']+deadline<=duration];timely=[v for v in eligible if v['received'] is not None and v['received']-v['t']<=deadline]
    metrics[f'd{deadline}_eligible']=len(eligible);metrics[f'd{deadline}_delivered']=len(timely);metrics[f'd{deadline}_censored']=len(packets)-len(eligible);metrics[f'd{deadline}_ratio']=len(timely)/len(eligible) if eligible else None
   for key,v in packets.items():
    status='destination_received' if v['received'] is not None else 'submission_rejected' if v['rejected'] else 'unreceived_no_unique_cause'
    row=dict(zip(['origin','origin_boot','seq','dst'],key));row.update(run=stem,offered_ms=v['t'],admitted=v['admitted'],received_ms=v['received'],geometric_4hop_at_submit=v['reachable'],end_status=status)
    for deadline,label in ((500,'0_5'),(1000,'1'),(2000,'2')):row['deadline_'+label]='censored' if v['t']+deadline>duration and (v['received'] is None or v['received']-v['t']>deadline) else 'delivered' if v['received'] is not None and v['received']-v['t']<=deadline else 'not_delivered'
    w.writerow(row)
   pernode={i:[v for (origin,_,_,_),v in packets.items() if origin==i] for i in range(30)};rates=[sum(x['received'] is not None for x in values)/len(values) for values in pernode.values() if values]
   results.append(dict(run=stem,motion=motion,speed_m_s=speed,seed=seed,policy=policy,offered=len(packets),admitted=sum(v['admitted'] for v in packets.values()),delivered=len(delivered),pdr=len(delivered)/len(packets),reachable_offered=len(reachable),reachable_delivered=sum(v['received'] is not None for v in reachable),latency_count=len(latencies),p95_ms=quantile(latencies,.95),p99_ms=quantile(latencies,.99),worst_origin_pdr=min(rates),submission_rejected=sum(v['rejected'] for v in packets.values()),unreceived_no_unique_cause=sum(v['received'] is None and not v['rejected'] for v in packets.values()),**metrics))
 finally:packets_out.close()
 with (out/'runs.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=results[0]);w.writeheader();w.writerows(results)
 pairs=[]
 for key,r in index.items():
  motion,speed,seed,policy=key
  if policy!='baseline':continue
  b=next(x for x in results if (x['motion'],x['speed_m_s'],x['seed'],x['policy'])==key);c=next(x for x in results if (x['motion'],x['speed_m_s'],x['seed'],x['policy'])==(motion,speed,seed,'local_cache_2s'))
  assert b['offered']==c['offered'];pairs.append(dict(motion=motion,speed_m_s=speed,seed=seed,delta_pdr=c['pdr']-b['pdr'],delta_deadline_1s=c['d1000_ratio']-b['d1000_ratio']))
 with (out/'paired.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=pairs[0]);w.writeheader();w.writerows(pairs)
 overall=dict(runs=len(results),pairs=len(pairs),offered=sum(x['offered'] for x in results),delivered=sum(x['delivered'] for x in results),unreceived_no_unique_cause=sum(x['unreceived_no_unique_cause'] for x in results),pdr_range=[min(x['pdr'] for x in results),max(x['pdr'] for x in results)],deadline_1s_paired_delta_range=[min(x['delta_deadline_1s'] for x in pairs),max(x['delta_deadline_1s'] for x in pairs)],limitations=['E1 25ms MAC model is uncalibrated; no physical RF claim.','Deadline denominators exclude offers whose entire deadline exceeds simulation end; packet table preserves observed early delivery and censored cases.','Control route event sequence is a request sequence and is not reliably attributable as a business-packet terminal cause.','Sampled-at-submit geometric <=4 hop is not path persistence or guaranteed delivery.','Three seeds are not sufficient to establish an engineering confidence interval.'])
 (out/'summary.json').write_text(json.dumps(overall,indent=2),encoding='utf-8');sourcefile=Path(__file__).resolve();m=dict(task_id='E2-033',run_id=out.name,started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(Path.cwd()),git_commit=manifest.get('git_commit'),dirty_files_sha256={str(sourcefile):h(sourcefile)},upstream_commit=manifest.get('upstream_commit'),data_and_weights_sha256=provenance,config_file=str(source/'config.json'),seeds=manifest['seeds'],budget={'input_runs':54,'workers':1},output_directory=str(out),process_id=os.getpid(),command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,status='passed',exit_code=0,review_reference=None,limitations=overall['limitations']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(overall))
if __name__=='__main__':main()
