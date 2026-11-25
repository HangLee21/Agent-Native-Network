"""Check bounded stress/long LoRa runs, identities, failure and resource bounds."""
import argparse,csv,hashlib,json,os,sys
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

def main():
 p=argparse.ArgumentParser();p.add_argument('--input',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);started=datetime.now(timezone.utc).isoformat();reports=[];sources={};external={}
 for base in a.input:
  base=base.resolve();manifest=json.loads((base/'RUN_MANIFEST.json').read_text());runs=list(x for x in base.iterdir() if x.is_dir());assert manifest['status']=='passed'
  for folder in sorted(runs):
   row=json.loads((folder/'summary.json').read_text());offers={};received=set();executed=set();reason=Counter();maxima=Counter()
   for line in (folder/'events.jsonl').open(encoding='utf-8'):
    e=json.loads(line);typ=e['type']
    if typ=='offered':
     key=(e['origin'],e['boot'],e['seq']);assert key not in offers;offers[key]=e['t']
    elif typ=='delivered':
     key=(e['origin'],e['boot'],e['seq']);assert key in offers and key not in received and e['receiver']=='gateway';received.add(key)
    elif typ=='command_executed':
     key=(e['cmd_id'],e['target']);assert key not in executed and e['executor']==e['target'];executed.add(key)
    elif typ=='command_duplicate':assert (e['cmd_id'],e['target']) in executed
    elif typ in ('uplink_lost','packet_rejected'):reason[e['reason']]+=1
    elif typ=='resource_sample':
     for field in ('pending_buffers','active_radios','pending_commands'):maxima[field]=max(maxima[field],e[field])
   assert len(offers)==row['offered'] and len(received)==row['received'] and len(executed)==row['executed'];assert dict(reason)==json.loads(row['packet_failure_reasons']);assert len(offers)-len(received)-sum(reason.values())==row['unresolved_at_end']>=0
   assert maxima['pending_buffers']<=30 and maxima['active_radios']<=30 and maxima['pending_commands']<=30
   if row['kind']=='capacity':
    key=(base.name,row['offered_period_s'],row['seed']);stream=sorted((k[0],k[1],k[2],t) for k,t in offers.items())
    if key in external:assert external[key]==stream
    else:external[key]=stream
   sources[str((folder/'events.jsonl').relative_to(base.parent))]=hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest()
   reports.append(dict(run=folder.name,suite=base.name,seed=row['seed'],period_s=row['offered_period_s'],mode=row['mode'],kind=row['kind'],offered=row['offered'],received=row['received'],pdr=row['pdr'],deadline_1s=row['deadline_1s'],max_buffers=maxima['pending_buffers'],max_radios=maxima['active_radios'],max_pending_commands=maxima['pending_commands'],status='passed'))
 with (out/'checks.csv').open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=reports[0]);w.writeheader();w.writerows(reports)
 summary=dict(runs=len(reports),equal_load_groups=len(external),max_pending_buffers=max(x['max_buffers'] for x in reports),max_active_radios=max(x['max_radios'] for x in reports),max_pending_commands=max(x['max_pending_commands'] for x in reports),limits='sampled each 60 s; Python model state counts are not target RAM',status='passed')
 (out/'summary.json').write_text(json.dumps(summary,indent=2));m=dict(task_id='E2-033',run_id=out.name,started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(Path.cwd()),git_commit=None,dirty_files_sha256={str(Path(__file__)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},command=sys.orig_argv,python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256=sources,config_file=None,seeds=[0,1,2],budget=dict(workers=1),output_directory=str(out),process_id=os.getpid(),status='passed',exit_code=0,review_reference=None,limitations=['Synthetic discrete event model; state occupancy is sampled and does not measure target memory or real radio.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2));print(json.dumps(summary))
if __name__=='__main__':main()
