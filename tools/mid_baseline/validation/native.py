"""Package-pinned offline AB command materializer and native log audit. No serial."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
from analyze import strict
ROOT=Path(__file__).resolve().parents[3]
PACKAGE=ROOT/'.local/mid/E1-016/package-01'
PACKAGE_HASH='d69533ff29318c5600d24300fa05d28ee673f9ffeec6437f9cc76eb7d148a683'
BUILD='mid-v1-99e77eba7e472bd687ea18321d6ac566e9e8b21d764431e1b42ec7fee945c2f3'
A='90:da:72:48:a4:f8';B='90:da:72:48:a5:cc'
UPDATE=ROOT/'simulation/outputs/E1-016/20261106-08-AB-planner/network_update.json'
UPDATE_HASH='db11092bb00a3b80ef76dbf30eea15cb9d5755836a7bd58b52e8d8d2944e79c2'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def verify():
 if sha(PACKAGE/'PACKAGE_MANIFEST.json')!=PACKAGE_HASH:raise ValueError('package anchor mismatch')
 m=strict((PACKAGE/'PACKAGE_MANIFEST.json').read_bytes())
 for x in m['files']:
  p=(PACKAGE/x['path']).resolve()
  if not p.is_relative_to(PACKAGE.resolve()) or p.stat().st_size!=x['bytes'] or sha(p)!=x['sha256']:raise ValueError('package file drift')
 if sha(UPDATE)!=UPDATE_HASH:raise ValueError('Planner update drift')
 return m
def materialize(info_a,info_b,run_id):
 verify();infos={A:info_a,B:info_b}
 for mac,r in infos.items():
  if (r.get('schema')!='mid.serial.v1' or r.get('event')!='command_result' or r.get('cmd')!='info' or r.get('ok') is not True or r.get('node_id')!=mac or r.get('build_id')!=BUILD or r.get('firmware')!='mid-espnow' or r.get('chip')!='esp32s3' or r.get('mode')!='idle' or any(r.get(k) is not False for k in ['radio','stopping','locked_until_reset']) or type(r.get('boot_id')) is not int or not 1<=r['boot_id']<=0xffffffff):raise ValueError('fresh bound MID idle info required')
 spec=importlib.util.spec_from_file_location('frozen_mid_bridge',PACKAGE/'source/tools/mid_baseline/bridge/bridge.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
 actions=[]
 def action(board,command,**kw):actions.append(dict(board=board,command=command,**kw))
 for mac in [A,B]:action(mac,dict(cmd='start',nonce='e2-start-'+mac[-2:],publisher=A,publisher_boot=info_a['boot_id']),require_reply_ok=True)
 for seq in [1,2,3]:action(A,dict(cmd='config',nonce='e2-config-'+str(seq),frame_hex=bridge.pack(strict(UPDATE.read_bytes()),A,info_a['boot_id'],seq).hex()),at_config_seconds=seq-1,require_reply_ok=True)
 actions.append(dict(gate='both config_applied seq>=3 and correct route_selected (A flow0->B, B flow1->A)',timeout_seconds=5,abort_on_timeout=True))
 for mac in [A,B]:action(mac,dict(cmd='stats',nonce='e2-base-'+mac[-2:]),require_reply_ok=True)
 for source,dest,flow in [(A,B,'AB'),(B,A,'BA')]:
  for i in range(5):action(source,dict(cmd='send',nonce=f'e2-{flow}-{i+1}',dst=dest,payload_hex=(f'{flow}-{i+1:02d}'.ljust(16,'.')).encode().hex()),interval_ms=500,require_reply_ok=True)
  actions.append(dict(gate='bounded drain',seconds=1.5))
 for mac in [A,B]:action(mac,dict(cmd='stop',nonce='e2-stop-'+mac[-2:]),require_reply_ok=True)
 actions.append(dict(gate='both radio=false stopping=false locked_until_reset=false; repeat read-only stats within 2s if drain pending',timeout_seconds=2,abort_on_timeout=True))
 for mac in [A,B]:action(mac,dict(cmd='stats',nonce='e2-final-'+mac[-2:]),require_reply_ok=True)
 return dict(schema='mid.native.execution_plan.v1',run_id=run_id,package_manifest_sha256=PACKAGE_HASH,build_id=BUILD,network_update_sha256=UPDATE_HASH,channel=6,info_boots={k:v['boot_id'] for k,v in infos.items()},max_wall_seconds=24,RF_runs=1,user_packets=10,flows=[dict(source=A,destination=B,count=5),dict(source=B,destination=A,count=5)],physical_owner='H-005',actions=actions,finally_actions=[dict(board=k,command=dict(cmd='stop',nonce='e2-finally-'+k[-2:])) for k in [A,B]],preconditions=['C readiness for exact package and plan','H checks fresh MAC/USB and full backups, consumes remaining RF budget','H owns both persistent handles and captures ALL host_tx/device_rx; do not use a second publisher process','No data retry, ACK, automatic reset or extra run on failure'],capture_context_contract={'task_id':'H-005','run_id':run_id,'status':'capture_complete','evidence_kind':'hardware_measured','package_manifest_sha256':PACKAGE_HASH,'log_sha256':'absolute native log path -> SHA256','coverage':'MAC -> bool after stats/stop/boot/overflow checks','measurement_duration_us':'actual host window, not count*interval'},limitations=['assumed dimensionless channel; not calibrated QoS','two-board functionality; no multihop claim'])

def materialize_abc(info_a,info_b,info_c,run_id,case):
 plan=materialize(info_a,info_b,run_id);c='90:da:72:48:a4:e0'
 if (info_c.get('schema')!='mid.serial.v1' or info_c.get('cmd')!='info' or info_c.get('ok') is not True or info_c.get('node_id')!=c or info_c.get('build_id')!=BUILD or info_c.get('firmware')!='mid-espnow' or info_c.get('chip')!='esp32s3' or info_c.get('mode')!='idle' or type(info_c.get('boot_id')) is not int or not 1<=info_c['boot_id']<=0xffffffff or any(info_c.get(k) is not False for k in ['radio','stopping','locked_until_reset'])):raise ValueError('fresh C MID info required')
 folder=ROOT/'simulation/outputs/E1-016/20261106-10-ABC-real/cases';index=folder/'INDEX.json'
 if sha(index)!='37d879827f6e50bd940737dccdee6ca82a79d410b4ac2957a06dc39826ff1f57':raise ValueError('ABC index drift')
 entry=next((r for r in strict(index.read_bytes())['cases'] if r['case']==case),None)
 if not entry:raise ValueError('unknown ABC case')
 for name,h in entry['files'].items():
  if sha(folder/case/name)!=h:raise ValueError('ABC asset drift')
 update=strict((folder/case/'network_update.json').read_bytes());solution=strict((folder/case/'solution.json').read_bytes())
 if update['nodes']!=[A,B,c] or solution.get('status')!='optimal':raise ValueError('ABC solution/node mismatch')
 spec=importlib.util.spec_from_file_location('fixed_bridge_abc',PACKAGE/'source/tools/mid_baseline/bridge/bridge.py');bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
 controlled=case=='AC_controlled_two_hop';count=3 if controlled else 2;start={'AC':101,'BC':201,'AC_controlled_two_hop':301}[case]
 rows=update['routes']
 if controlled:
  expected={(A,A,c):B,(B,A,c):c,(c,c,A):B,(B,c,A):A}
  if len(rows)!=4 or any(len(row['gateways'])!=1 or row['gateways'][0]['node']!=expected.get((row['node'],row['src'],row['dst'])) for row in rows):raise ValueError('SOCP did not produce controlled two-hop paths')
 actions=[]
 for mac in [A,B,c]:actions.append(dict(board=mac,command=dict(cmd='start',nonce='e2-start-'+mac[-2:],publisher=A,publisher_boot=info_a['boot_id']),require_reply_ok=True))
 for seq in range(start,start+3):actions.append(dict(board=A,command=dict(cmd='config',nonce='e2-config-'+str(seq),frame_hex=bridge.pack(update,A,info_a['boot_id'],seq).hex()),at_config_seconds=seq-start,require_reply_ok=True))
 actions.append(dict(gate='all config_applied seq>='+str(start+2)+' and all available routes selected from required_routes',required_routes=rows,timeout_seconds=5,abort_on_timeout=True))
 for mac in [A,B,c]:actions.append(dict(board=mac,command=dict(cmd='stats',nonce='e2-base-'+mac[-2:]),require_reply_ok=True))
 for f in update['flows']:
  for i in range(count):actions.append(dict(board=f['src'],command=dict(cmd='send',nonce='e2-'+case+'-'+f['src'][-2:]+'-'+str(i),dst=f['dst'],payload_hex=(case[:8]+str(i)).ljust(16,'.').encode().hex()),interval_ms=500,require_reply_ok=True))
  actions.append(dict(gate='bounded drain',seconds=1.5))
 for mac in [A,B,c]:actions.append(dict(board=mac,command=dict(cmd='stop',nonce='e2-stop-'+mac[-2:]),require_reply_ok=True))
 actions.append(dict(gate='all radio=false stopping=false locked_until_reset=false',timeout_seconds=2,abort_on_timeout=True))
 for mac in [A,B,c]:actions.append(dict(board=mac,command=dict(cmd='stats',nonce='e2-final-'+mac[-2:]),require_reply_ok=True))
 plan.update(case=case,info_boots={A:info_a['boot_id'],B:info_b['boot_id'],c:info_c['boot_id']},actions=actions,flows=[dict(source=f['src'],destination=f['dst'],count=count) for f in update['flows']],network_update_sha256=entry['files']['network_update.json'],ABC_index_sha256=sha(index),max_wall_seconds=20 if controlled else 15,user_packets=count*2,required_relay=B if controlled else None,finally_actions=[dict(board=k,command=dict(cmd='stop',nonce='e2-finally-'+k[-2:])) for k in [A,B,c]],limitations=['assumed channel, not calibrated QoS','controlled A-C logical edge restriction; not observed RF disconnection','B relay in this case only; nodes remain peers'])
 return plan

def audit(plan_path,log_paths,context_path=None):
 plan=strict(Path(plan_path).read_bytes());verify();issues=[];events=[];sources=[];synthetic=False
 if plan.get('package_manifest_sha256')!=PACKAGE_HASH:raise ValueError('plan package mismatch')
 for name in log_paths:
  p=Path(name).resolve();sources.append(dict(path=str(p),sha256=sha(p)))
  for number,line in enumerate(p.read_bytes().splitlines(),1):
   try:r=strict(line)
   except (ValueError,UnicodeError):
    if line.lstrip().startswith(b'{'):issues.append('malformed device/capture JSON')
    continue
   if not isinstance(r,dict):continue
   outer=None
   if 'direction'in r:
    if r['direction'] not in ['device_rx','rx']:continue
    outer=r.get('evidence_kind');raw=r.get('event')
    if raw is None:
     try:raw=strict(r.get('line',r.get('raw','')))
     except (ValueError,TypeError):issues.append('malformed captured native row');continue
    r=raw
   if not isinstance(r,dict) or r.get('schema')!='mid.serial.v1':continue
   synthetic=synthetic or outer!='hardware_serial' or r.get('evidence_kind')=='synthetic'
   if r.get('build_id')!=BUILD or r.get('node_id') not in plan['info_boots'] or r.get('boot_id')!=plan['info_boots'].get(r.get('node_id')):issues.append('build/node/boot changed')
   if r.get('destination_confirmed') is True:issues.append('unexpected MID endpoint confirmation')
   if r.get('event') in ['input_queue_overflow','callback_timeout','input_queue_alloc_failed','uart_task_failed']:issues.append('capture or radio fatal event')
   r=dict(r,source=dict(path=str(p),line=number));events.append(r)
 context=strict(Path(context_path).read_bytes()) if context_path else None
 hardware=False
 if context:
  if any(context.get(k)!=v for k,v in dict(task_id='H-005',run_id=plan['run_id'],status='capture_complete',evidence_kind='hardware_measured',package_manifest_sha256=PACKAGE_HASH).items()):raise ValueError('capture context mismatch')
  if synthetic:raise ValueError('synthetic or untagged log cannot become hardware')
  if any(context.get('log_sha256',{}).get(s['path'])!=s['sha256'] for s in sources):raise ValueError('native capture hash mismatch')
  hardware=True
 results=[]
 for flow in plan.get('flows',[dict(source=A,destination=B,count=5),dict(source=B,destination=A,count=5)]):
  source,dest,expected=flow['source'],flow['destination'],flow['count']
  generated={};received={};dup=0
  for e in events:
   if e.get('origin')!=source or e.get('dst')!=dest:continue
   key=(source,e.get('origin_boot'),e.get('seq'),dest)
   if type(key[1]) is not int or type(key[2]) is not int:issues.append('bad data identity');continue
   if key[1]!=plan['info_boots'].get(source):issues.append('origin boot does not match bound source')
   if e.get('event')=='tx_queued' and e['node_id']==source:
    if key in generated:issues.append('duplicate source admission')
    generated[key]=e
   if e.get('event')=='rx_local' and e['node_id']==dest:
    if key in received:dup+=1
    try:payload=bytes.fromhex(e['payload_hex'])
    except (KeyError,TypeError,ValueError):issues.append('invalid received payload');continue
    received[key]=(e,len(payload))
  base={};final={}
  for mac in plan['info_boots']:
   for e in events:
    if e.get('node_id')==mac and e.get('cmd')=='stats' and e.get('ok') is True:
     if e.get('nonce')=='e2-base-'+mac[-2:]:base[mac]=e
     if e.get('nonce')=='e2-final-'+mac[-2:]:final[mac]=e
  complete=bool(hardware and not issues and all(context.get('coverage',{}).get(m) is True for m in plan['info_boots']) and all(m in base and m in final for m in plan['info_boots']))
  if complete:
   complete=all(final[m].get('radio') is False and final[m].get('stopping') is False and final[m].get('locked_until_reset') is False for m in plan['info_boots'])
   if complete:
    try:complete=all(type(v) is int for v in [final[source]['tx_queued'],base[source]['tx_queued'],final[dest]['rx_local'],base[dest]['rx_local']]) and final[source]['tx_queued']-base[source]['tx_queued']==len(generated) and final[dest]['rx_local']-base[dest]['rx_local']==len(received)
    except (KeyError,TypeError):complete=False
  known=complete and len(generated)==expected and not(set(received)-set(generated))
  window=context.get('measurement_duration_us') if context else None
  valid_window=type(window)is int and window>0 and context.get('duration_clock')=='host_monotonic_controlled_window'
  relay=plan.get('required_relay');relay_matches={}
  if relay:
   for key in received:
    source_tx=[e['source'] for e in events if e.get('node_id')==source and e.get('event')=='tx_submit' and e.get('next_hop')==relay and (e.get('origin'),e.get('origin_boot'),e.get('seq'),e.get('dst'))==key]
    rx=[e['source'] for e in events if e.get('node_id')==relay and e.get('event')=='rx_relay' and (e.get('origin'),e.get('origin_boot'),e.get('seq'),e.get('dst'))==key]
    tx=[e['source'] for e in events if e.get('node_id')==relay and e.get('event')=='tx_submit' and e.get('next_hop')==dest and (e.get('origin'),e.get('origin_boot'),e.get('seq'),e.get('dst'))==key]
    if source_tx and rx and tx:relay_matches[str(key)]=dict(source_tx_submit=source_tx,rx_relay=rx,tx_submit=tx)
  results.append(dict(source=source,destination=dest,source_queued_unique=len(generated),endpoint_unique_observed=len(received),duplicate_rx_log_rows=dup,pdr=len(received)/expected if known else None,goodput_bps=sum(x[1] for x in received.values())*8e6/window if known and valid_window else None,rtt_ms=None,reason=None if known else 'no_complete_hardware_context_or_counts',controlled_forwarding_verified=bool(known and received and len(relay_matches)==len(received)) if relay else None,relay_evidence=relay_matches,identity_evidence=[dict(identity=list(k),source=v['source'],endpoint=received[k][0]['source'] if k in received else None) for k,v in generated.items()]))
 if issues:
  for s in results:s.update(pdr=None,goodput_bps=None,controlled_forwarding_verified=False if plan.get('required_relay') else None,reason='log_integrity_issue')
 return dict(schema='mid.native.audit.v1',run_id=plan['run_id'],evidence_kind='hardware_measured' if hardware else 'synthetic_or_unverified',streams=results,issues=issues,source_logs=sources,source_plan_sha256=sha(plan_path),source_context_sha256=sha(context_path) if context_path else None,analyzer_sha256=sha(__file__),rx_duplicate_event_count=sum(e.get('event')=='rx_duplicate' for e in events),control_tx_submit_count=sum(e.get('event')=='tx_submit' and 'dst' not in e for e in events),control_submitted_bytes=None,rf_retry_count=None,airtime_us=None,limitations=['source tx_queued is admission, callback is not delivery','no source-clock endpoint echo; RTT unavailable','native protocol has no measured RF retry/airtime fields','context required for hardware metrics; raw host probe is never RF evidence'])

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='cmd',required=True)
 m=sub.add_parser('materialize');m.add_argument('--info-a',required=True);m.add_argument('--info-b',required=True);m.add_argument('--run-id',required=True);m.add_argument('--case',choices=['AB','AC','BC','AC_controlled_two_hop'],default='AB');m.add_argument('--info-c')
 a=sub.add_parser('audit');a.add_argument('--plan',required=True);a.add_argument('--log',action='append',required=True);a.add_argument('--context')
 for q in [m,a]:q.add_argument('--output',required=True)
 x=p.parse_args();target=Path(x.output).resolve()
 if target.exists() or not any(target.is_relative_to((ROOT/'simulation/outputs'/task).resolve()) for task in ['E2-016','H-005']):raise ValueError('new owner task output required')
 result=(materialize(strict(Path(x.info_a).read_bytes()),strict(Path(x.info_b).read_bytes()),x.run_id) if x.case=='AB' else materialize_abc(strict(Path(x.info_a).read_bytes()),strict(Path(x.info_b).read_bytes()),strict(Path(x.info_c).read_bytes()) if x.info_c else {},x.run_id,x.case)) if x.cmd=='materialize' else audit(x.plan,x.log,x.context)
 target.parent.mkdir(parents=True,exist_ok=True)
 with target.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
if __name__=='__main__':main()
