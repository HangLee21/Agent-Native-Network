"""Audit equal-load runs and summarize paired seed differences."""
import argparse,csv,hashlib,json,random,statistics,sys
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter

def interval(values):
 rng=random.Random(20261114);n=len(values);draws=sorted(sum(rng.choice(values) for _ in range(n))/n for __ in range(5000))
 return dict(n=n,mean=statistics.mean(values),min=min(values),max=max(values),bootstrap95=[draws[int(.025*len(draws))],draws[int(.975*len(draws))-1]],resampling_unit='seed')

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();src=a.input.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);start=datetime.now(timezone.utc).isoformat();runs=[];capacity={};totals=Counter();source_hashes={};h=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
 for folder in sorted(x for x in src.iterdir() if x.is_dir()):
  row=json.loads((folder/'summary.json').read_text());commands=json.loads((folder/'commands.json').read_text());events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
  offers={};deliveries={};executed=set();acks=set();dup=0;reasons=Counter()
  for e in events:
   typ=e['type']
   if typ=='offered':
    k=(e['origin'],e['boot'],e['seq']);assert k not in offers;offers[k]=e['t']
   elif typ=='delivered':
    k=(e['origin'],e['boot'],e['seq']);assert k in offers and k not in deliveries and e['receiver']=='gateway';deliveries[k]=e['t']
   elif typ=='command_executed':
    k=(e['cmd_id'],e['target']);assert k not in executed and e['executor']==e['target'];executed.add(k)
   elif typ=='command_duplicate':assert (e['cmd_id'],e['target']) in executed;dup+=1
   elif typ=='command_receipt':assert (e['cmd_id'],e['target']) in executed;acks.add((e['cmd_id'],e['target']))
   elif typ in ('uplink_lost','packet_rejected'):reasons[e['reason']]+=1
  assert len(offers)==row['offered'] and len(deliveries)==row['received'];assert len(executed)==row['executed'] and len(acks)==row['receipts'];assert dup==row['duplicates_received'] and row['duplicate_executions']==0
  for d,field in ((.5,'deadline_0_5s'),(1,'deadline_1s'),(2,'deadline_2s')):
   definite=sum(t-offers[k]<=d-1.1e-6 for k,t in deliveries.items());possible=sum(t-offers[k]<=d+1.1e-6 for k,t in deliveries.items())
   assert definite<=row[field]<=possible
  assert json.loads(row['packet_failure_reasons'])==dict(reasons);assert row['offered']-row['received']-sum(reasons.values())==row['unresolved_at_end']>=0
  assert sum(c['executed'] is not None for c in commands)==row['executed'] and len(commands)==row['commands']
  if row['kind']=='capacity':
   key=row['seed'];external=sorted((k[0],k[1],k[2],t) for k,t in offers.items())
   if key in capacity:assert external==capacity[key]
   else:capacity[key]=external
  source_hashes[str((folder/'events.jsonl').relative_to(src))]=h(folder/'events.jsonl');runs.append(row);totals.update(reasons)
 assert len(runs)==220 and len(capacity)==20
 comparisons=[]
 def compare(name,find_a,find_b,measure):
  one={r['seed']:r for r in runs if find_a(r)};two={r['seed']:r for r in runs if find_b(r)};assert set(one)==set(two)==set(range(20))
  values=[measure(two[i])-measure(one[i]) for i in sorted(one)]
  comparisons.append(dict(comparison=name,**interval(values)))
 cap=lambda mode:lambda r:r['kind']=='capacity' and r['mode']==mode
 compare('capacity eight_random minus single_random PDR',cap('single_random'),cap('eight_random'),lambda r:r['pdr'])
 compare('capacity eight_scheduled minus eight_random PDR',cap('eight_random'),cap('eight_scheduled'),lambda r:r['pdr'])
 compare('capacity eight_scheduled minus eight_random 1s/on offered',cap('eight_random'),cap('eight_scheduled'),lambda r:r['deadline_1s']/r['offered'])
 cmd=lambda window,kind:lambda r:r['kind']==kind and r['window']==window and r['dl_loss']==.1 and r['clock_offset_s']==0 and not r['reboot']
 for kind in ('command','single_command'):
  for deadline in (1,2,5):compare(f'{kind} periodic minus uplink executed within {deadline}s',cmd('uplink',kind),cmd('periodic',kind),lambda r,d=deadline:r[f'command_at_{d}s']/r['commands'])
 (out/'paired.json').write_text(json.dumps(comparisons,indent=2),encoding='utf-8')
 with (out/'paired.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=comparisons[0]);w.writeheader();w.writerows(comparisons)
 report=dict(runs=len(runs),capacity_paired_seeds=len(capacity),packet_failure_reasons=dict(totals),duplicates_received=sum(x['duplicates_received'] for x in runs),duplicate_executions=sum(x['duplicate_executions'] for x in runs),reboot_dedup_exercised=sum(x['reboot_dedup_checked'] for x in runs),reboot_cases=sum(x['reboot'] for x in runs),comparison='paired by seed, intervals bootstrap 5000 seed-level samples',limitations=['Synthetic radio model; no target RAM measurement.','Counterfactual command execution may change generation periods and offered traffic; separate from fixed-load capacity.','Injected stale-command replay tests persisted idempotence as a modeling assumption, not a physical reboot test.','1/2/5-second command completion counts node execution; gateway receipt counted separately.','Raw event times are rounded to microseconds; packet deadline counts are verified within the resulting two-timestamp uncertainty interval.'])
 (out/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8');m=dict(task_id='E2-033',run_id=out.name,started_at=start,finished_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(Path.cwd()),git_commit=None,dirty_files_sha256={str(Path(__file__)):h(Path(__file__))},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256=source_hashes,config_file=None,seeds=list(range(20)),budget=dict(runs=220,workers=1,bootstrap_replicates=5000),output_directory=str(out),process_id=None,status='passed',exit_code=0,review_reference=None,limitations=report['limitations']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(report));print(json.dumps(comparisons,indent=2))
if __name__=='__main__':main()
