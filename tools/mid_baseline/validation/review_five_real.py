"""One finite, read-only review of the twelve H-005 five-board real captures. No device code."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import argparse,hashlib,json,time
from pathlib import Path
from unittest.mock import patch
import native
import five
ROOT=Path(__file__).resolve().parents[3]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,v):
 with p.open('x',encoding='utf-8') as f:json.dump(v,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
def key(e):return (e['origin'],e['origin_boot'],e['seq'],e['dst'])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);args=ap.parse_args();out=Path(args.output).resolve()
 if out.exists() or not out.is_relative_to((ROOT/'simulation/outputs/E2-016').resolve()):raise ValueError('new E2-016 output required')
 out.mkdir(parents=True);start=time.monotonic();now=lambda:datetime.now(timezone.utc).isoformat()
 template=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text('utf-8-sig'))
 template.update(template_only=False,task_id='E2-016',run_id=out.name,started_at=now(),worktree=str(ROOT),command=['review_five_real.py','--output',str(out)],evidence_kind='hardware_log_analysis',status='running',physical_operations=0,new_RF_runs=0,dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),str(Path(native.__file__).relative_to(ROOT)):sha(Path(native.__file__))},limitations=['Only existing H actual logs; no device runs or unchanged-package revalidation','Twelve small functional cases; no statistical reliability or coverage/QoS claim','Unmeasured RTT/RF retries/PHY airtime and full physical OLED verification remain unknown'])
 save(out/'RUN_MANIFEST.started.json',template);ledger=ROOT/'tests/mid_baseline/five_execution_budget.jsonl'
 with ledger.open('a') as f:f.write(json.dumps(dict(event='reserved',run_id=out.name,timeout_s=120,scope='five_existing_hardware_log_analysis'))+'\n')
 summaries=[];identities=[];inputs={};error=None
 try:
  h=ROOT/'simulation/outputs/H-005';index_path=h/'20261107-18-five-results/EVIDENCE_INDEX.json';index=json.loads(index_path.read_text())
  index={str(Path(r['path']).resolve()):r for r in index};inputs[str(index_path.relative_to(ROOT))]=sha(index_path)
  for case in json.loads((h/'20261107-18-five-results/result.json').read_text())['cases']:
   run=Path(case['run']).name
   folder=h/run;plan_path=folder/'plan.json';log=folder/'native.jsonl';context=folder/'context.json'
   for p in [plan_path,log,context,folder/'result.json']+list(folder.glob('*.raw.bin')):
    digest=sha(p);rel=str(p.relative_to(ROOT)).replace('\\','/');entry=index[str(p.resolve())];assert digest==entry['sha256'] and p.stat().st_size==entry['bytes'],rel;inputs[rel]=digest
   plan=json.loads(plan_path.read_text());rows=[];host=defaultdict(list);reply=defaultdict(list);captured=defaultdict(Counter)
   for number,line in enumerate(log.read_text('utf-8').splitlines(),1):
    wrapper=native.strict(line)
    if wrapper.get('direction')=='host_tx':
     command=wrapper.get('command',{})
     if command.get('cmd')=='send':host[(wrapper['node_id'],command['dst'])].append(dict(command=command,line=number))
    if wrapper.get('direction')=='device_rx':
     e=wrapper['event'];canonical=json.dumps(e,sort_keys=True,separators=(',',':'));captured[e['node_id']][canonical]+=1
     rows.append((number,e))
     if e.get('event')=='command_result':reply[(e['node_id'],e.get('nonce'))].append(e)
   # Reconcile actual captured JSON with per-board original UART bytes.
   raw_counts={}
   for p in folder.glob('*.raw.bin'):
    raw=Counter()
    for line in p.read_bytes().splitlines():
     try:e=native.strict(line)
     except (ValueError,UnicodeError):continue
     if isinstance(e,dict) and e.get('schema')=='mid.serial.v1':raw[json.dumps(e,sort_keys=True,separators=(',',':'))]+=1
    mac=next(json.loads(s)['node_id'] for s in raw)
    assert raw==captured[mac],str(p)+' UART/native capture mismatch';raw_counts[mac]=sum(raw.values())
   # Only the unchanged package metadata check is excluded, per latest user instruction.
   audit=five.audit(plan_path,[log],context)
   assert not audit['issues'],audit['issues'];save(out/(run+'-audit.json'),audit)
   source_count=endpoint_count=chains=0
   for flow in plan['flows']:
    src,dst,count=flow['source'],flow['destination'],flow['count'];generated={};received={}
    for line,e in rows:
     if e.get('origin')==src and e.get('dst')==dst:
      if e.get('event')=='tx_queued' and e['node_id']==src:
       assert key(e) not in generated;generated[key(e)]=(line,e)
      if e.get('event')=='rx_local' and e['node_id']==dst:
       assert key(e) not in received;received[key(e)]=(line,e)
    assert len(generated)==count and set(generated)==set(received)
    commands=host[(src,dst)];assert len(commands)==count
    for (identity,(line,e)),command in zip(generated.items(),commands):
     destination_line,rx=received[identity];payload=bytes.fromhex(command['command']['payload_hex']);assert payload==bytes.fromhex(rx['payload_hex'])
     answers=reply[(src,command['command']['nonce'])];assert len(answers)==1 and answers[0].get('ok') is True
     submissions=[n for n,x in rows if x.get('event')=='tx_submit' and x.get('node_id')==src and all(x.get(k)==e[k] for k in ['origin','origin_boot','seq','dst'])]
     assert submissions,'Missing source tx_submit'
     record=dict(run_id=run,identity=list(identity),host_send_line=command['line'],host_nonce=command['command']['nonce'],source_queued_line=line,source_tx_submit_lines=submissions,destination_rx_local_line=destination_line,payload_hex=rx['payload_hex'],payload_matches_command=True,source_file=str(log))
     path=next((path for path in plan.get('paths',[]) if path[0]==src and path[-1]==dst),None)
     if path:
      hops=[]
      for i,node in enumerate(path[:-1]):
       tx=[n for n,x in rows if x.get('event')=='tx_submit' and x.get('node_id')==node and x.get('next_hop')==path[i+1] and all(x.get(k)==e[k] for k in ['origin','origin_boot','seq','dst'])]
       rx_relay=[n for n,x in rows if x.get('event')=='rx_relay' and x.get('node_id')==node and all(x.get(k)==e[k] for k in ['origin','origin_boot','seq','dst'])] if i else []
       assert tx and (not i or rx_relay),'Incomplete actual hop'
       hops.append(dict(node=node,next_hop=path[i+1],tx_submit_lines=tx,rx_relay_lines=rx_relay))
      record.update(path=path,hops=hops);chains+=1
     identities.append(record)
    source_count+=len(generated);endpoint_count+=len(received)
   assert all(s['pdr']==1.0 for s in audit['streams'])
   if plan.get('paths'):assert all(s['controlled_forwarding_verified'] is True for s in audit['streams'])
   cleanup=json.loads((folder/'result.json').read_text());assert cleanup['all_ports_closed'] and all(cleanup['stop_confirmed'].values())
   summaries.append(dict(run_id=run,source_unique=source_count,destination_unique=endpoint_count,matching_payloads=endpoint_count,complete_controlled_chains=chains,stop_confirmed=cleanup['stop_confirmed'],ports_closed_reported_by_H=cleanup['all_ports_closed'],UART_native_JSON_reconciled=raw_counts,streams=audit['streams'],host_window_seconds=json.loads(context.read_text())['measurement_duration_us']/1e6))
  assert sum(x['destination_unique'] for x in summaries)==120 and sum(x['complete_controlled_chains'] for x in summaries)==20
  save(out/'identities.json',dict(schema='E2-016.five.real.identity-evidence/1',evidence_kind='hardware_log_analysis',identities=identities))
  save(out/'summary.json',dict(status='passed',evidence_kind='hardware_log_analysis',cases=summaries,matched_endpoint_packets=120,matched_controlled_four_hop_chains=20,total_host_window_seconds=sum(x['host_window_seconds'] for x in summaries),RTT_ms=None,RF_retries=None,PHY_airtime_us=None,physical_OLED_pixels_PRG='not_verified_by_E2',limitations=template['limitations']))
 except Exception as exc:error=repr(exc)
 finally:
  elapsed=time.monotonic()-start;template.update(finished_at=now(),elapsed_s=elapsed,status='analysis_passed' if error is None else 'analysis_failed',exit_code=0 if error is None else 1,error=error,data_and_weights_sha256=inputs)
  save(out/'RUN_MANIFEST.json',template)
  with ledger.open('a') as f:f.write(json.dumps(dict(event='finished',run_id=out.name,elapsed_s=elapsed,exit_code=template['exit_code'],protection_stopped=False))+'\n')
 print(json.dumps(dict(status=template['status'],error=error,elapsed_s=elapsed)))
 return template['exit_code']
if __name__=='__main__':raise SystemExit(main())
