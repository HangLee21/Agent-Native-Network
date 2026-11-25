"""Four independent single-board clients; routing runs entirely on ESP32 boards."""
import argparse,datetime,hashlib,json,os,queue,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from lease import HardwareLease,reservation

class Node:
 def __init__(self,label,binding,out,build,edge_source,edge_sha):
  self.label=label;self.q=queue.Queue();self.requests=(out/f'{label}.requests.jsonl').open('x',encoding='utf-8');self.errors=(out/f'{label}.stderr.txt').open('x',encoding='utf-8')
  self.argv=[sys.executable,str(ROOT/'tools/mid_hardware/adhoc_bench/node_client.py'),'--port',binding['port'],'--node-id',binding['node_id'],'--build',build,'--edge-source',str(edge_source),'--edge-sha256',edge_sha,'--log',str(out/f'{label}.events.jsonl')]
  self.process=subprocess.Popen(self.argv,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.errors,text=True,encoding='utf-8',bufsize=1,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  def read():
   with (out/f'{label}.stdout.jsonl').open('x',encoding='utf-8')as log:
    for line in self.process.stdout:
     log.write(line);log.flush()
     try:self.q.put(json.loads(line))
     except ValueError:pass
   self.q.put(dict(ok=False,error='local client process exited'))
  self.reader=threading.Thread(target=read,daemon=True);self.reader.start()
 def ready(self):
  r=self.q.get(timeout=12)
  if not r.get('ready'):raise RuntimeError((self.label,'ready',r))
  return r
 def ask(self,op,**fields):
  request=dict(op=op,**fields);self.requests.write(json.dumps(dict(request=request,host_monotonic_ns=time.monotonic_ns()))+'\n');self.requests.flush();self.process.stdin.write(json.dumps(request)+'\n');self.process.stdin.flush();r=self.q.get(timeout=12)
  if not r.get('ok'):raise RuntimeError((self.label,op,r))
  return r['result']
 def close(self):
  if not self.process.stdin.closed:self.process.stdin.close()
  try:self.process.wait(timeout=4)
  except subprocess.TimeoutExpired:self.process.terminate();self.process.wait(timeout=3)
  self.reader.join(timeout=3);self.requests.close();self.errors.close();assert self.process.returncode==0,(self.label,self.process.returncode)

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build',required=True);p.add_argument('--edge-source',type=Path,required=True);p.add_argument('--edge-sha256',required=True);p.add_argument('--group',type=int,default=290015);a=p.parse_args();assert 0<a.group<=0xffffffff
 out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-015');out.mkdir(parents=True,exist_ok=False);assert reservation()['owner']=='H015';source=a.edge_source.resolve();assert source.is_relative_to(ROOT/'.local/mid/H-015') and hashlib.sha256(source.read_bytes()).hexdigest()==a.edge_sha256
 labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_bytes())['bindings'];by={k:next(x for x in bindings if x['node_id']==labels[k])for k in 'ABCD'};reverse={v:k for k,v in labels.items()};heard={'A':['B','D'],'B':['A','C'],'C':['B','D'],'D':['A','C']};nodes={};start=time.monotonic();deadline=start+180
 r=dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),build_id=a.build,group=a.group,channel=6,topology_scope='volatile local frame hearability filters, not natural RF isolation',local_hearability_by_label=heard,host_installs_routes=False,host_forwards_payload=False,physical_hosts_verified=1,child_commands={},markers=[],packets=[],stop_confirmed={},closed={})
 def mark(name,**data):
  v=dict(phase=name,host_monotonic_ns=time.monotonic_ns(),elapsed_s=time.monotonic()-start,**data);r['markers'].append(v);print(json.dumps(v),flush=True);return v
 def check_deadline():
  if time.monotonic()>deadline-20:raise TimeoutError('bounded physical bench deadline')
 def events(label):check_deadline();return nodes[label].ask('events',after=0)
 def same(e,identity):return all(e.get(k)==v for k,v in identity.items())
 def send_packet(tag,data,receive_timeout=3):
  check_deadline();assert len(r['packets'])<8 and len(data)==160 and data.hex()not in [x['payload_hex']for x in r['packets']]
  entry=dict(tag=tag,payload_hex=data.hex(),bytes=len(data),submitted_host_ns=time.monotonic_ns(),destination_received=False);r['packets'].append(entry)
  tx=nodes['A'].ask('send',dst=labels['C'],payload_hex=data.hex());entry['source_admission']=tx;identity={k:tx[k]for k in ('origin','origin_boot','seq','dst')};assert identity['origin']==labels['A'] and identity['dst']==labels['C'];entry['identity']=identity
  receive_end=time.monotonic()+receive_timeout
  while time.monotonic()<receive_end:
   try:rx=nodes['C'].ask('recv',timeout=max(.05,receive_end-time.monotonic()))
   except RuntimeError as exc:
    if 'no endpoint delivery'not in str(exc):raise
    break
   target=next((old for old in r['packets']if old.get('identity') and same(rx,old['identity'])),None)
   if target is None:raise AssertionError('unmatched destination application identity')
   assert rx['application_payload_hex']==target['payload_hex'] and rx['payload_hex']==target['payload_hex']
   if target['destination_received']:raise AssertionError('duplicate application delivery')
   target.update(destination_received=True,destination=rx,received_host_ns=time.monotonic_ns())
   if target is entry:break
   target['late_observed_during']=tag
  if not entry['destination_received']:entry['observation_timeout']=True
  entry['source_events']=[e for e in events('A')if same(e,identity)];mark('business_observed',tag=tag,identity=identity,destination_received=entry['destination_received']);return entry
 def confirmed_diamond():
  snapshots={};end=time.monotonic()+18
  while time.monotonic()<end:
   check_deadline();snapshots={k:n.ask('neighbors')for k,n in nodes.items()}
   if all({x['node_id']for x in snapshots[k]['neighbors']if x['state']=='bidirectional'}=={labels[x]for x in heard[k]}for k in heard):return snapshots
   time.sleep(.45)
  raise TimeoutError('actual confirmed diamond did not form')
 def actual_selected_path():
  choices=[e for e in events('A')if e.get('event')=='route_selected' and e.get('origin')==labels['A'] and e.get('dst')==labels['C'] and len(e.get('path',[]))==3]
  if not choices:raise AssertionError('board route_selected event with a two-hop path is missing')
  return choices[-1]
 with HardwareLease('H015'):
  try:
   for k in 'ABCD':
    n=Node(k,by[k],out,a.build,source,a.edge_sha256);nodes[k]=n;r['child_commands'][k]=n.argv;r.setdefault('initial_ready',{})[k]=n.ready();info=r['initial_ready'][k]['info'];assert info['node_id']==labels[k] and not info['radio'] and not info.get('discovery_saved') and not info['deployment_saved']
   for k,n in nodes.items():r.setdefault('local_filter_results',{})[k]=n.ask('link_filter',allow=[labels[v]for v in heard[k]])
   for k,n in nodes.items():r.setdefault('mode_config_results',{})[k]=n.ask('route_config',group=a.group,channel=6,autostart=True)
   mark('local_protocols_started');r['confirmed_neighbors']=confirmed_diamond();r['initial_routes']={k:n.ask('routes')for k,n in nodes.items()};assert all(not x['routes']for x in r['initial_routes'].values());mark('empty_route_cache_and_diamond_confirmed')
   first=send_packet('cold_route_utf8',('自主多跳'*13+'ABCD').encode('utf-8'));assert first['destination_received'];r['initial_board_selection']=actual_selected_path();path=r['initial_board_selection']['path'];assert path[0]==labels['A'] and path[-1]==labels['C'] and path[1]in (labels['B'],labels['D'])
   second=send_packet('cache_binary',b'\x00\xff'+bytes(range(158)));assert second['destination_received'];r['before_fault_stats']={k:n.ask('stats')for k,n in nodes.items()}
   # Fault choice is the board's observed selection, not a host-computed route.
   selected=reverse[path[1]];alternate='D'if selected=='B'else'B';r['withdrawn_relay']=selected;r['alternate_relay']=alternate;nodes[selected].ask('stop');s=nodes[selected].ask('stats');assert not s['radio'] and s['queue_depth']==0;r['withdrawn_stats']=s;mark('actually_selected_relay_radio_stopped',relay=selected)
   recovered=None
   for i in range(6):
    prefix=f'H015 distinct recovery {i}|'.encode();data=(prefix+bytes((j+i)%256 for j in range(160)))[:160];entry=send_packet(f'after_fault_{i}',data,receive_timeout=3)
    if entry['destination_received']:
     received=actual_selected_path();newpath=received['path']
     if newpath==[labels['A'],labels[alternate],labels['C']]:recovered=entry;r['recovery_board_selection']=received;break
    time.sleep(.55)
   assert recovered,'no new message delivered through the other relay within the finite new-packet budget'
   assert r['recovery_board_selection']['request']!=r['initial_board_selection']['request'],'changed path without a new request round cannot be claimed as rediscovery'
   r['recovery_request_events']=[e for e in events('A')if e.get('event')=='route_request' and e.get('request')==r['recovery_board_selection']['request'] and e.get('dst')==labels['C']];assert r['recovery_request_events'],'new route request not observed'
   mark('alternate_new_message_delivered',identity=recovered['identity'],relay=alternate)
   r['final_active_stats']={k:n.ask('stats')for k,n in nodes.items()};r['final_route_views']={k:n.ask('routes')for k,n in nodes.items()};r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   for k,n in nodes.items():
    try:
     n.ask('stop');end=time.monotonic()+3
     while True:
      s=n.ask('stats')
      if not s['radio'] and not s['stopping'] and s['queue_depth']==0:break
      if time.monotonic()>end:raise TimeoutError('board did not drain')
      time.sleep(.03)
     r['stop_confirmed'][k]=True;r.setdefault('stopped_stats',{})[k]=s;n.ask('link_filter',clear=True);info=n.ask('info')
     if info.get('deployment_mode')=='autonomous':n.ask('route_clear')
     r.setdefault('final_info',{})[k]=n.ask('info');assert r['final_info'][k]['deployment_mode']=='mid' and not r['final_info'][k]['radio'] and not r['final_info'][k].get('link_filter_enabled');r.setdefault('final_events',{})[k]=n.ask('events',after=0)
    except Exception as exc:r.setdefault('cleanup_errors',[]).append(dict(board=k,error=repr(exc)))
    try:n.close();r['closed'][k]=True
    except Exception as exc:r['closed'][k]=False;r.setdefault('cleanup_errors',[]).append(dict(board=k,error=repr(exc)))
   r['success']=r.get('success',False) and len(r['stop_confirmed'])==4 and all(r['stop_confirmed'].values()) and all(r['closed'].values()) and not r.get('cleanup_errors');r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['elapsed_s']=time.monotonic()-start;(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
   sources={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in (ROOT/'tools/mid_hardware/adhoc_bench').glob('*.py')};m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes());m.update(template_only=False,task_id='H-015',run_id=out.name,started_at=r['started_at'],finished_at=r['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),dirty_files_sha256=sources,data_and_weights_sha256={str(source):a.edge_sha256},status='passed'if r['success']else'failed',exit_code=0 if r['success']else 1,budget=dict(controller_wall_seconds=180,max_distinct_business_messages=8,automatic_resends=0,relay_withdrawals=1),limitations=['Local per-frame hearability filters, not natural RF isolation.','Four independent single-port processes on one Windows host, not four Ubuntu hosts.','H does not install a route or choose the replacement route.','No endpoint ACK/RF retry/airtime claims from source callbacks.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps({k:r.get(k)for k in ('success','error','elapsed_s','withdrawn_relay','alternate_relay','stop_confirmed','closed','cleanup_errors')},ensure_ascii=False),flush=True)
 return 0 if r['success']else 1
if __name__=='__main__':raise SystemExit(main())
