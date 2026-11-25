import argparse,csv,json,hashlib,os,sys,time
from collections import Counter
from pathlib import Path
from datetime import datetime,timezone

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False);started=datetime.now(timezone.utc).isoformat();root=Path.cwd();cases=[]
 for d in sorted((root/'simulation/outputs/E1-030/20261114-84-core-resume/batch-0512-0541').glob('case-*')):
  if d.is_dir():cases.append(('unaudited30',d,600))
 for i in range(3):cases.append(('long',root/f'simulation/outputs/E1-030/20261114-{81+i}-long-seed{i}/case-0000',21600))
 assert len(cases)==33;rows=[];sources={};limit=time.monotonic()+1200
 for category,d,seconds in cases:
  if time.monotonic()>limit:raise TimeoutError('batch 20-minute cap')
  summary=json.loads((d/'summary.json').read_text());assert summary.get('event_recording_complete') is True
  offers={};receipts={};reject=set();outcomes={};h=hashlib.sha256()
  with (d/'events.jsonl').open('rb') as f:
   for raw in f:
    h.update(raw)
    if not any(tag in raw for tag in (b'"offered"',b'"submission_rejected"',b'"destination_received"',b'"deadline_outcome"')):continue
    e=json.loads(raw);kind=e['event'];key=(e['origin_id'],e['origin_boot_id'],e['seq'])
    if kind=='offered':assert key not in offers;offers[key]=(e['time_us'],e['dst_id'],e['geometric_4hop_at_submit'])
    elif kind=='submission_rejected':reject.add(key)
    elif kind=='destination_received':
     assert key in offers and key not in receipts and offers[key][1]==e['dst_id'] and e['bytes_match'] is True;receipts[key]=e['time_us']
    else:assert key not in outcomes;outcomes[key]=e
  assert len(offers)==summary['offered'] and len(receipts)==summary['delivered'] and len(outcomes)==len(offers)
  end=seconds*1000000;counts=Counter()
  for key,(sent,dst,geo) in offers.items():
   for limit_us,label in ((500000,'status_500ms'),(1000000,'status_1s'),(2000000,'status_2s')):
    status='submission_rejected' if key in reject else 'received_on_time' if key in receipts and receipts[key]-sent<=limit_us else 'right_censored' if sent+limit_us>end else 'no_endpoint_receipt_by_deadline'
    assert outcomes[key][label]==status
   if sent+1000000<=end:
    group='geom' if geo else 'nongeom';counts[group+'_eligible']+=1;counts[group+'_received_1s']+=int(key in receipts and receipts[key]-sent<=1000000)
  rows.append(dict(category=category,case=str(d),offered=len(offers),delivered=len(receipts),rejected=len(reject),**counts))
  sources[str(d/'events.jsonl')]=h.hexdigest();print(category,d.name,len(offers),flush=True)
 with (o/'cases.csv').open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=['category','case','offered','delivered','rejected','geom_eligible','geom_received_1s','nongeom_eligible','nongeom_received_1s']);w.writeheader();w.writerows(rows)
 result=dict(status='passed',cases=len(rows),unaudited30=30,long=3,limitations=['Geom is ideal <=4-hop at offer only; nongeometric is not permanent partition.','bytes_match is producer boolean; destination bytes absent in saved event.','Recorded absence is not a unique packet failure cause.']);(o/'summary.json').write_text(json.dumps(result,indent=2));m=dict(task_id='E2-034',run_id=o.name,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(root),git_commit=None,dirty_files_sha256={str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256=sources,config_file=None,seeds=[],budget=dict(workers=1,wall_seconds=1200,cases=33),output_directory=str(o),process_id=os.getpid(),status='passed',exit_code=0,review_reference=None,limitations=result['limitations']);(o/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2));print(json.dumps(result))
if __name__=='__main__':main()
