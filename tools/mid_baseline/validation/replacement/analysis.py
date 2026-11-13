"""Per-packet/per-second analysis of paired replacement captures. No serial."""
from collections import defaultdict,deque
import argparse,hashlib,json,math
from pathlib import Path
from contract import decode,slots

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def strict(data):
 def pairs(items):
  r={}
  for k,v in items:
   if k in r:raise ValueError('duplicate JSON key')
   r[k]=v
  return r
 def bad(x):raise ValueError('nonfinite JSON')
 return json.loads(data,object_pairs_hook=pairs,parse_constant=bad)
def recovery(bits,event_s):
 if event_s is None:return dict(status='unknown',reason='retire_effective_not_observed')
 if not 0<=event_s<60:return dict(status='unknown',reason='event_outside_source_window')
 before=math.floor(event_s);start=math.ceil(event_s);pre=bits[max(0,before-10):before]
 if len(pre)!=10 or any(v is None for v in pre):return dict(status='unknown',reason='incomplete_pre_event_baseline')
 baseline=sum(pre)/10
 if baseline<=0:return dict(status='not_assessable',reason='zero_pre_event_service',baseline_bps=baseline)
 threshold=.8*baseline;after=bits[start:]
 if len(after)<3 or any(x is None for x in after):return dict(status='unknown',reason='incomplete_post_event_coverage',baseline_bps=baseline,threshold_bps=threshold)
 stable_pre=all(x>=threshold for x in pre[-3:])
 if stable_pre and all(x>=threshold for x in after):return dict(status='no_interruption',recovery_s=0,baseline_bps=baseline,threshold_bps=threshold)
 for i in range(len(after)-2):
  if all(x>=threshold for x in after[i:i+3]):return dict(status='recovered',recovery_s=start+i+3-event_s,recovery_window_end_s=start+i+3,baseline_bps=baseline,threshold_bps=threshold,pre_last_three_stable=stable_pre)
 return dict(status='right_censored',recovery_s=None,censor_s=60-event_s,baseline_bps=baseline,threshold_bps=threshold)
def longest_missing(packets):
 longest=length=0
 for p in packets:
  length=0 if p['delivered'] else length+1;longest=max(longest,length)
 return dict(packets=longest,planned_time_s=longest*.5,scope='missing_by_capture_end, planned slots not physical RF outage')

def analyze(context_path,log_paths):
 ctx=strict(Path(context_path).read_bytes());pair,arm,t0=ctx['pair_id'],ctx['arm'],ctx['schedule_t0_ns']
 if ctx.get('schema')!='mid.replacement.context.v1' or arm not in ['fixed','replan'] or type(t0)is not int:raise ValueError('replacement context required')
 if ctx.get('duration_s')!=60 or ctx.get('planned_interval_ns')!=500000000:raise ValueError('workload differs from fixed design; label separate pilot')
 endpoints=ctx['endpoints'];ends=[endpoints['A'],endpoints['B']];issues=[];warnings=[];events=[];sources=[]
 if ctx.get('evidence_kind')=='hardware_measured' and (ctx.get('status')!='capture_complete' or any(ctx.get('stop_confirmed',{}).get(m)is not True for m in ends)):issues.append('capture_or_endpoint_stop_incomplete')
 for name in log_paths:
  p=Path(name).resolve();raw=p.read_bytes();digest=sha(p);sources.append(dict(path=str(p),sha256=digest))
  if ctx.get('evidence_kind')=='hardware_measured' and ctx.get('log_sha256',{}).get(str(p))!=digest:raise ValueError('original log hash does not match immutable context')
  for line_no,line in enumerate(raw.splitlines(),1):
   try:r=strict(line)
   except (ValueError,UnicodeError):issues.append('malformed_capture_JSON');continue
   if not isinstance(r,dict) or type(r.get('host_monotonic_ns'))is not int:issues.append('missing_host_timestamp');continue
   r=dict(r,_source=dict(path=str(p),line=line_no));events.append(r)
 events.sort(key=lambda r:r['host_monotonic_ns'])
 packets={(p['direction'],p['slot']):dict(p,planned=True,planned_logged=False,dispatched=False,command_response_observed=False,source_accepted=False,source_rejected=False,source_submitted=False,delivered=False,content_match=None,identity=None,sources={}) for p in slots(pair,arm,t0)}
 commands={};queued=defaultdict(deque);submitted={};received={};identity_owner={};annotations=[];duplicates=0;unmatched=0
 def identity(e):return (e.get('origin'),e.get('origin_boot'),e.get('seq'),e.get('dst'))
 for r in events:
  kind=r.get('kind',r.get('direction'));when=r['host_monotonic_ns'];ref=r['_source']
  if kind in ['annotation','planned','dispatch','undispatched']:
   if kind=='annotation':annotations.append(dict(r));continue
   key=(r.get('direction_id',r.get('flow_direction',r.get('direction'))),r.get('slot'))
   if key not in packets:issues.append('unknown_scheduler_slot');continue
   if kind=='planned':packets[key]['planned_logged']=True
   else:packets[key][kind+'_ns']=when;packets[key]['sources'][kind]=ref
   continue
  if kind=='host_tx':
   c=r.get('command',{})
   if c.get('cmd')!='send':continue
   try:p,d,s=decode(bytes.fromhex(c['payload_hex']))
   except (KeyError,ValueError):issues.append('send_payload_not_fixed_design');continue
   if p!=pair or r.get('node_id')!=ends[d] or c.get('dst')!=ends[1-d]:issues.append('send_pair_or_endpoint_mismatch');continue
   row=packets[(d,s)]
   if row['dispatched'] or c.get('nonce') in commands:issues.append('duplicate_slot_or_nonce')
   row.update(dispatched=True,dispatch_ns=when,dispatch_lateness_ns=when-row['planned_ns']);row['sources']['host_tx']=ref;commands[c['nonce']]=(d,s)
   continue
  if kind!='device_rx':continue
  if ctx.get('evidence_kind')=='hardware_measured' and r.get('evidence_kind')!='hardware_serial':issues.append('nonhardware_device_envelope')
  e=r.get('event',{});node=e.get('node_id');event=e.get('event')
  if e.get('schema')!='mid.serial.v1':continue
  expected_build=ctx.get('builds',{}).get(node,ctx.get('build_id'))
  if node in ends and ((ctx.get('boots') and e.get('boot_id')!=ctx['boots'].get(node)) or (expected_build and e.get('build_id')!=expected_build)):issues.append('endpoint_boot_or_build_changed')
  if node in ends and event in ['input_queue_overflow','callback_timeout','uart_rx_overflow']:issues.append('endpoint_capture_or_radio_fatal')
  if node in ends and any(type(e.get(k))is int and e[k]>0 for k in ['uart_fifo_overflows','uart_ring_overflows']):issues.append('endpoint_UART_overflow_counter_nonzero')
  if node in ends and ctx.get('uart_bauds',{}).get(node) and e.get('uart_baud') is not None and e['uart_baud']!=ctx['uart_bauds'][node]:issues.append('endpoint_UART_baud_mismatch')
  if event=='tx_queued' and e.get('origin')==node and node in ends:queued[node].append((identity(e),when,ref))
  elif event=='command_result' and e.get('cmd')=='send':
   key=commands.get(e.get('nonce'))
   if key is None:issues.append('unmatched_send_response');continue
   row=packets[key];row['sources']['send_response']=ref;row['command_response_observed']=True
   if e.get('ok') is True:
    if not queued[node]:issues.append('accepted_command_without_source_admission');continue
    wire,at,source=queued[node].popleft()
    if wire[0]!=ends[key[0]] or wire[-1]!=ends[1-key[0]] or type(wire[1])is not int or type(wire[2])is not int or (ctx.get('boots') and wire[1]!=ctx['boots'].get(node)):issues.append('source_identity_mismatch');continue
    if wire in identity_owner:issues.append('duplicate_wire_identity');continue
    identity_owner[wire]=key;row.update(source_accepted=True,accepted_ns=at,identity=list(wire));row['sources']['source_admission']=source
   else:row.update(source_rejected=True,reject_reason=e.get('error'))
  elif event=='tx_submit' and node in ends and e.get('origin')==node:submitted[identity(e)]=(when,ref)
  elif event=='rx_local' and node in ends and e.get('dst')==node:
   key=identity(e)
   if key in received:duplicates+=1;continue
   received[key]=(e,when,ref)
 for wire,key in identity_owner.items():
  row=packets[key]
  if wire in submitted:row.update(source_submitted=True,submitted_ns=submitted[wire][0]);row['sources']['tx_submit']=submitted[wire][1]
  if wire in received:
   e,when,ref=received[wire]
   try:valid=bytes.fromhex(e['payload_hex'])==bytes.fromhex(row['payload_hex'])
   except (KeyError,ValueError):valid=False
   row['content_match']=valid;row['sources']['endpoint']=ref
   if valid:row.update(delivered=True,received_ns=when,delivered_in_60s=t0<=when<t0+60000000000)
   else:issues.append('endpoint_content_mismatch')
 unmatched=len(set(received)-set(identity_owner))
 if any(p['dispatched'] and not p['command_response_observed'] for p in packets.values()):issues.append('unresolved_send_response_not_RF_loss')
 if unmatched:issues.append('unmatched_endpoint_identity')
 if any(queued.values()):issues.append('unmatched_source_admission')
 trigger=next((r for r in annotations if r.get('name')=='retire_effective'),None)
 event_s=(trigger.get('original_host_ns',trigger['host_monotonic_ns'])-t0)/1e9 if trigger else None
 results=[];seconds=[]
 for d in [0,1]:
  ps=[packets[(d,s)] for s in range(120)]
  known=all(ctx.get('endpoint_coverage',{}).get(m)is True for m in ends) and not issues
  for second in range(60):
   lo=t0+second*1000000000;hi=lo+1000000000;delivered=[p for p in ps if p['delivered'] and lo<=p['received_ns']<hi]
   seconds.append(dict(direction=d,second=second,planned_count=2,dispatch_count=sum(p['dispatched'] and lo<=p['dispatch_ns']<hi for p in ps),source_accepted=sum(p['source_accepted'] and lo<=p['accepted_ns']<hi for p in ps),source_submitted=sum(p['source_submitted'] and lo<=p['submitted_ns']<hi for p in ps),unique_delivered_observed=len(delivered),unique_delivered=len(delivered) if known else None,unique_payload_bits=len(delivered)*256 if known else None,goodput_bps=len(delivered)*256 if known else None,coverage_status='confirmed' if known else 'unknown'))
  bins=[x['goodput_bps'] for x in seconds if x['direction']==d]
  missing=longest_missing(ps) if known else dict(packets=None,planned_time_s=None,status='unknown',scope='incomplete coverage; unobserved slots are not RF loss')
  for row in ps:
   row['delivery_status']='destination_received' if row['delivered'] else 'not_observed_by_capture_end' if known else 'unknown_coverage'
   row['dispatch_status']='observed_full_host_write' if row['dispatched'] else 'recorded_undispatched' if 'undispatched_ns'in row else 'not_observed' if known else 'unknown_coverage'
  results.append(dict(direction=d,source=ends[d],destination=ends[1-d],planned=120,planned_logged=sum(p['planned_logged'] for p in ps),dispatched=sum(p['dispatched'] for p in ps),accepted=sum(p['source_accepted'] for p in ps),submitted=sum(p['source_submitted'] for p in ps),delivered_observed=sum(p['delivered'] for p in ps),late_after_window=sum(p['delivered'] and p['received_ns']>=t0+60000000000 for p in ps),missing=missing,recovery=recovery(bins,event_s) if known else dict(status='unknown',reason='incomplete_capture_coverage'),post_event_payload_bits=sum(v for i,v in enumerate(bins) if v is not None and event_s is not None and i>=math.ceil(event_s)) if known and event_s is not None else None))
 return dict(schema='mid.replacement.analysis.v1',metrics_valid=known,run_id=ctx['run_id'],pair_id=pair,arm=arm,design_version=ctx['design_version'],initial_condition_id=ctx['initial_condition_id'],shared_inputs=ctx.get('shared_inputs',{}),evidence_kind=ctx.get('evidence_kind','unknown'),issues=issues,warnings=warnings,packets=list(packets.values()),seconds=seconds,directions=results,annotations=annotations,duplicate_endpoint_rows=duplicates,unmatched_endpoint_identities=unmatched,source_logs=sources,source_context=dict(path=str(Path(context_path).resolve()),sha256=sha(context_path)),analyzer_sha256=sha(__file__),timing_scope='single host observation axis; not one-way RF latency; booleans are observed events, missing capture requires delivery_status/dispatch_status')

def pairs(runs):
 grouped=defaultdict(dict)
 for r in runs:
  if r['arm'] in grouped[r['pair_id']]:raise ValueError('multiple runs for same pair arm; label pilot separately')
  grouped[r['pair_id']][r['arm']]=r
 output=[]
 for pair,arms in sorted(grouped.items()):
  if set(arms)!={'fixed','replan'}:output.append(dict(pair_id=pair,status='missing_arm'));continue
  f,n=arms['fixed'],arms['replan'];required={'model_sha256','initial_table_sha256','scenario_sha256','workload_id','software_configuration_id'};complete=required<=set(f['shared_inputs']) and required<=set(n['shared_inputs']);matched=complete and f['shared_inputs']==n['shared_inputs'] and f['initial_condition_id']==n['initial_condition_id'] and f['design_version']==n['design_version']
  valid=all(r.get('metrics_valid',not r.get('issues') and all(s.get('coverage_status')=='confirmed' for s in r.get('seconds',[]))) for r in [f,n])
  ds=[]
  for d in [0,1]:
   a,b=f['directions'][d],n['directions'][d];delta=b['post_event_payload_bits']-a['post_event_payload_bits'] if matched and valid and a['post_event_payload_bits'] is not None and b['post_event_payload_bits'] is not None else None
   ds.append(dict(direction=d,post_event_payload_bits_difference_replan_minus_fixed=delta,fixed_recovery=a['recovery'],replan_recovery=b['recovery'],fixed_missing=a['missing'],replan_missing=b['missing']))
  output.append(dict(pair_id=pair,status='capture_incomplete' if not valid else 'matched' if matched else 'shared_input_fingerprints_missing' if not complete else 'initial_condition_mismatch',shared_inputs_match=matched,directions=ds))
 summaries=[]
 for d in [0,1]:
  values=[p['directions'][d]['post_event_payload_bits_difference_replan_minus_fixed'] for p in output if p['status']=='matched' and p['directions'][d]['post_event_payload_bits_difference_replan_minus_fixed'] is not None];values.sort()
  def percentile(q):
   if not values:return None
   i=(len(values)-1)*q;lo=math.floor(i);hi=math.ceil(i);return values[lo]+(values[hi]-values[lo])*(i-lo)
  summaries.append(dict(direction=d,valid_paired_differences=len(values),differences=values,median=percentile(.5),IQR=percentile(.75)-percentile(.25) if values else None,min=min(values) if values else None,max=max(values) if values else None))
 return dict(schema='mid.replacement.pairs.v1',pairs=output,summary=summaries,limitations=['show each pair; censored times are not observed means','paired inputs require shared model/table/scenario/workload fingerprints; no significance inference from five pairs'])

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--context',required=True);p.add_argument('--log',action='append',required=True);p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve();root=Path(__file__).resolve().parents[4]
 if out.exists() or not out.is_relative_to(root/'simulation/outputs/E2-017'):raise ValueError('new E2-017 output required')
 value=analyze(a.context,a.log);out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
if __name__=='__main__':main()
