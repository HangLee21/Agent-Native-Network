"""H014 one bounded late-join/aging/reboot pair; no static neighbor provisioning."""
import argparse,datetime,hashlib,json,os,secrets,sys,time
from pathlib import Path
import esptool
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_hardware/replacement'));sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from wire import Wire
from adapter import _cleanup
from lease import reservation

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build',required=True);p.add_argument('--group',type=int,default=270014);a=p.parse_args();assert 0<a.group<=0xffffffff
 out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-014');out.mkdir(parents=True,exist_ok=False);assert reservation()['owner']=='H014'
 registered=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];labels={k:registered[k]for k in 'AB'};A,B=labels['A'],labels['B'];wire=None;started=datetime.datetime.now(datetime.timezone.utc).isoformat();begin=time.monotonic();deadline=begin+120;tag='h014-'+secrets.token_hex(5)
 r=dict(started_at=started,group=a.group,channel=6,neighbor_addresses_provisioned=False,static_tables_provisioned=False,labels=labels,markers=[],packets=[],observations=[],Ubuntu_physical_hotplug_verified=False)
 def mark(name,**fields):
  item=dict(phase=name,elapsed_s=time.monotonic()-begin,**fields);saved=wire.record(dict(direction='H_phase',**item));item['host_monotonic_ns']=saved['host_monotonic_ns'];r['markers'].append(item);print(json.dumps(item),flush=True);return item
 def collect(seconds):
  end=min(time.monotonic()+seconds,deadline-7)
  while time.monotonic()<end:wire.poll();time.sleep(.004)
 def cmd(mac,name,**fields):
  if time.monotonic()>deadline-7:raise TimeoutError('bounded bench deadline')
  return wire.wait_command(mac,dict(cmd=name,nonce=tag+'-'+secrets.token_hex(5),**fields),seconds=3)
 def peers(mac):
  reply=cmd(mac,'neighbors');r['observations'].append(dict(observer=mac,host_monotonic_ns=time.monotonic_ns(),reply=reply));return reply['neighbors']
 def wait_pair(expected_b_boot,timeout=15):
  end=min(time.monotonic()+timeout,deadline-10);first=None
  while time.monotonic()<end:
   left=peers(A);right=peers(B);peer=next((x for x in left if x.get('node_id')==B and x.get('boot_id')==expected_b_boot),None)
   if peer and first is None:first=mark('A_observed_B',neighbor=peer)
   reverse=next((x for x in right if x.get('node_id')==A),None)
   if peer and peer['state']=='bidirectional' and reverse and reverse['state']=='bidirectional':return mark('pair_bidirectional',A_neighbor=peer,B_neighbor=reverse),peer
   collect(.45)
  raise TimeoutError('actual bidirectional neighbors not observed')
 def payload(text,destination):
  data=text.encode('utf-8');before=len(wire.events);reply=cmd(A,'send',dst=destination,payload_hex=data.hex());identity=dict(origin=A,origin_boot=reply['origin_boot'],seq=reply['packet_seq'],dst=destination);end=time.monotonic()+4
  while time.monotonic()<end:
   wire.poll();matches=[x for x in wire.events[before:]if x['event'].get('event')=='rx_local' and x['event'].get('node_id')==B and all(x['event'].get(k)==v for k,v in identity.items())]
   if matches:
    assert len(matches)==1 and matches[0]['event']['payload_hex']==data.hex();item=dict(text=text,payload_hex=data.hex(),identity=identity,command_result=reply,destination=matches[0]);r['packets'].append(item);mark('application_received',identity=identity,payload_bytes=len(data));return
   time.sleep(.004)
  raise TimeoutError('no original destination bytes; no automatic resend')
 try:
  wire=Wire(out,labels,owner='H014');wire.metadata=dict(task_id='H-014',run_id=out.name)
  r['initial_info']={k:cmd(mac,'info')for k,mac in labels.items()}
  for k,info in r['initial_info'].items():assert info['node_id']==labels[k] and info['build_id']==a.build and not info['radio'] and not info['deployment_saved'] and not info.get('discovery_saved') and not info.get('discovery_fault') and not info['locked_until_reset']
  r['A_config']=cmd(A,'discover_config',group=a.group,channel=6,autostart=True);mark('A_started_discovery')
  collect(4);r['A_before_B']=peers(A);assert not r['A_before_B'];assert cmd(B,'info')['radio'] is False
  r['B_config']=cmd(B,'discover_config',group=a.group,channel=6,autostart=True);mark('B_late_started');old_b=cmd(B,'info')['boot_id'];wait_pair(old_b)
  # Destination is taken from A's actual neighbor response after confirmation.
  selected=next(x for x in peers(A)if x['state']=='bidirectional');assert selected['node_id']==B;payload('H014 无预录邻居：A发现B后原文交付',selected['node_id'])
  r['before_off_stats']={k:cmd(mac,'stats')for k,mac in labels.items()};cmd(B,'stop');stop_stats=cmd(B,'stats');assert stop_stats['radio'] is False and stop_stats['queue_depth']==0;r['B_stop_stats']=stop_stats;mark('B_radio_stopped')
  end=time.monotonic()+17;seen_heard=False
  while time.monotonic()<end:
   current=next((x for x in peers(A)if x.get('node_id')==B),None);assert current
   if current['state']=='heard' and not seen_heard:mark('A_confirmation_expired',neighbor=current);seen_heard=True
   if current['state']=='lost':r['lost_neighbor']=current;mark('A_observed_B_lost',neighbor=current);break
   collect(.45)
  else:raise TimeoutError('B not aged to lost by bounded deadline')
  r['after_off_stats']={k:cmd(mac,'stats')for k,mac in labels.items()}
  port=wire.ports[B];port.baudrate=115200;esp=esptool.detect_chip(port,baud=115200,connect_mode='default_reset',trace_enabled=False,connect_attempts=1);actual=':'.join(f'{x:02x}'for x in esp.read_mac());assert actual==B and esp.CHIP_NAME=='ESP32-S3';r['B_reset_ROM_MAC']=actual
  wire.buffers[B].clear();port.baudrate=460800;mark('B_normal_reset_issued');esp.hard_reset();port.timeout=0;collect(1)
  r['B_after_reset_info']=cmd(B,'info');info=r['B_after_reset_info'];assert info['boot_id']!=old_b and info.get('discovery_saved') and info['radio'] and info['group']==a.group;r['new_B_boot']=info['boot_id'];wait_pair(info['boot_id']);payload('H014 B重启后再次发现：新boot原文交付',next(x for x in peers(A)if x.get('boot_id')==info['boot_id'] and x['state']=='bidirectional')['node_id'])
  r['final_discovery_stats']={k:cmd(mac,'stats')for k,mac in labels.items()}
  r['stopped_discovery_stats']={}
  for label,mac in labels.items():
   cmd(mac,'stop');stats=cmd(mac,'stats');assert stats['radio'] is False and stats['queue_depth']==0;r['stopped_discovery_stats'][label]=stats;cmd(mac,'discover_clear')
  r['final_info']={k:cmd(mac,'info')for k,mac in labels.items()}
  for info in r['final_info'].values():assert info['deployment_mode']=='mid' and not info['radio'] and not info['discovery_saved'] and info['channel']==6
  r['success']=True
 except Exception as exc:r.update(success=False,error=repr(exc))
 finally:
  if wire:
   stopped,errors=_cleanup(wire,tag,deadline);r.update(stop_confirmed=stopped,cleanup_errors=errors,all_ports_closed=all(not x.is_open for x in wire.ports.values()))
   if errors or len(stopped)!=2 or not all(stopped.values()) or not r['all_ports_closed']:r['success']=False
  r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['elapsed_s']=time.monotonic()-begin;(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
  m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes());m.update(template_only=False,task_id='H-014',run_id=out.name,started_at=started,finished_at=r['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),status='passed'if r.get('success')else'failed',exit_code=0 if r.get('success')else 1,budget=dict(wall_seconds=120,max_business_payloads=2,late_join_trials=1,aging_trials=1,reboot_trials=1),data_and_weights_sha256={'native.jsonl':hashlib.sha256((out/'native.jsonl').read_bytes()).hexdigest()}if(out/'native.jsonl').exists()else{},limitations=['Same Windows PC and two real RF boards, not two physical Ubuntu hosts.','Normal ROM reset, not physical power removal or USB hotplug.','Neighbor queries are local serial reads; delay estimates include bounded sampling and serial overhead.','Generated/submitted/received control counters are distinct; 41B frames exclude RF/MAC overhead.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps({k:r.get(k)for k in ('success','error','elapsed_s','stop_confirmed','cleanup_errors','all_ports_closed')},ensure_ascii=False),flush=True)
 return 0 if r.get('success')else 1
if __name__=='__main__':raise SystemExit(main())
