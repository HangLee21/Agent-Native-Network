"""Synthetic evidence only. Verify loss/empty-window/recovery accounting."""
import json,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tools/mid_baseline/validation/replacement'))
from contract import payload,decode,slots
import analysis
OUT=None
class ReplacementTests(unittest.TestCase):
 def fixture(self,arm,drop=(),reject=(),coverage=True,duplicate=False,unresolved=()):
  d=OUT/(self.id().split('.')[-1]+'-'+arm);d.mkdir();rows=[];t0=100000000000;A='02:00:00:00:00:01';B='02:00:00:00:00:02';ends=[A,B]
  ctx=dict(schema='mid.replacement.context.v1',run_id=arm,pair_id=1,arm=arm,schedule_t0_ns=t0,duration_s=60,planned_interval_ns=500000000,design_version='M019-E2-v1',initial_condition_id='pair1-common',evidence_kind='synthetic',endpoints=dict(A=A,B=B),boots={A:11,B:12},endpoint_coverage={A:coverage,B:True},shared_inputs=dict(model_sha256='m',initial_table_sha256='t',scenario_sha256='s',workload_id='v1',software_configuration_id='same-fixture-builds-and-bauds'))
  def record(ns,kind,**kw):rows.append(dict(host_monotonic_ns=ns,kind=kind,**kw))
  for p in slots(1,arm,t0):
   k=p['slot'];direction=p['direction'];src=ends[direction];dst=ends[1-direction];ns=p['planned_ns'];nonce=p['nonce'];identity=dict(origin=src,origin_boot=11+direction,seq=k+1,dst=dst)
   record(ns,'planned',direction=direction,slot=k,planned_ns=ns)
   record(ns,'host_tx',node_id=src,command=dict(cmd='send',nonce=nonce,dst=dst,payload_hex=p['payload_hex']))
   if k not in reject:
    record(ns+1000,'device_rx',event=dict(schema='mid.serial.v1',event='tx_queued',node_id=src,boot_id=11+direction,**identity))
   record(ns+2000,'device_rx',event=dict(schema='mid.serial.v1',event='command_result',node_id=src,boot_id=11+direction,cmd='invalid' if k in unresolved else 'send',nonce=None if k in unresolved else nonce,ok=False if k in unresolved else k not in reject,error='invalid_command' if k in unresolved else 'no_route' if k in reject else None))
   if k not in reject:
    record(ns+3000,'device_rx',event=dict(schema='mid.serial.v1',event='tx_submit',node_id=src,boot_id=11+direction,**identity))
    if k not in drop:
     e=dict(schema='mid.serial.v1',event='rx_local',node_id=dst,boot_id=12-direction,payload_hex=p['payload_hex'],**identity)
     record(ns+10000000,'device_rx',event=e)
     if duplicate:record(ns+11000000,'device_rx',event=e)
  record(t0+20000000000,'annotation',name='retire_effective',source='synthetic stop reply')
  rows.sort(key=lambda r:r['host_monotonic_ns']);log=d/'raw.jsonl';log.write_text('\n'.join(json.dumps(x) for x in rows)+'\n');c=d/'context.json';c.write_text(json.dumps(ctx));return analysis.analyze(c,[log])
 def test_paired_payload_and_order(self):
  self.assertEqual(payload(1,0,5),payload(1,0,5));self.assertEqual(decode(payload(5,1,119)),(5,1,119));self.assertEqual(len(list(slots(1,'fixed',0))),240)
 def test_empty_windows_and_fixed_right_censor(self):
  r=self.fixture('fixed',drop=set(range(40,120)));self.assertFalse(r['issues']);self.assertEqual(len(r['packets']),240);self.assertEqual(len(r['seconds']),120)
  self.assertEqual(r['directions'][0]['recovery']['status'],'right_censored');self.assertEqual(r['directions'][0]['missing']['packets'],80)
  self.assertTrue(all(x['goodput_bps']==0 for x in r['seconds'] if x['second']>=20))
 def test_recovery_three_windows_and_no_interruption(self):
  r=self.fixture('replan',drop=set(range(40,48)));self.assertEqual(r['directions'][0]['recovery']['recovery_s'],7)
  self.assertEqual(analysis.recovery([512]*60,20)['status'],'no_interruption');self.assertEqual(analysis.recovery([0]*60,20)['status'],'not_assessable')
 def test_rejected_sends_remain_planned(self):
  r=self.fixture('fixed',reject={45});d=r['directions'][0];self.assertEqual((d['planned'],d['dispatched'],d['accepted']),(120,120,119));self.assertEqual(sum(p['source_rejected'] for p in r['packets']),2)
 def test_unknown_coverage_is_not_zero_and_duplicates_dont_inflate(self):
  r=self.fixture('fixed',coverage=False,duplicate=True);self.assertTrue(all(x['goodput_bps'] is None for x in r['seconds']));self.assertEqual(r['directions'][0]['delivered_observed'],120);self.assertEqual(r['duplicate_endpoint_rows'],240)
 def test_pair_delta_and_mismatched_inputs(self):
  f=self.fixture('fixed',drop=set(range(40,120)));n=self.fixture('replan',drop=set(range(40,48)));r=analysis.pairs([f,n]);self.assertEqual(r['pairs'][0]['status'],'matched');self.assertEqual(r['summary'][0]['median'],18432)
  n['shared_inputs']['model_sha256']='other';self.assertEqual(analysis.pairs([f,n])['pairs'][0]['status'],'initial_condition_mismatch')
 def test_missing_nonce_reply_is_unknown_not_RF_loss(self):
  r=self.fixture('fixed',unresolved={119});self.assertIn('unresolved_send_response_not_RF_loss',r['issues']);self.assertEqual(sum(p['source_rejected'] for p in r['packets']),0);self.assertTrue(all(x['goodput_bps'] is None for x in r['seconds']))
 def test_incomplete_capture_does_not_report_missing_or_recovery(self):
  r=self.fixture('fixed',coverage=False,drop=set(range(10,120)));self.assertFalse(r['metrics_valid']);self.assertIsNone(r['directions'][0]['missing']['packets']);self.assertEqual(r['directions'][0]['recovery']['status'],'unknown');self.assertTrue(any(p['delivery_status']=='unknown_coverage' for p in r['packets']))
 def test_incomplete_pair_retained_without_difference(self):
  f=self.fixture('fixed',coverage=False);n=self.fixture('replan');p=analysis.pairs([f,n]);self.assertEqual(p['pairs'][0]['status'],'capture_incomplete');self.assertIsNone(p['pairs'][0]['directions'][0]['post_event_payload_bits_difference_replan_minus_fixed']);self.assertEqual(p['summary'][0]['valid_paired_differences'],0)
class UartTests(unittest.TestCase):
 def test_different_arm_software_is_not_a_matched_pair(self):
  a=dict(pair_id=1,arm='fixed',initial_condition_id='common',design_version='v1',shared_inputs=dict(model_sha256='m',initial_table_sha256='t',scenario_sha256='s',workload_id='v1',software_configuration_id='old'),directions=[dict(post_event_payload_bits=0,recovery={},missing={}) for _ in range(2)])
  b=dict(a,arm='replan',shared_inputs=dict(a['shared_inputs'],software_configuration_id='new'))
  self.assertEqual(analysis.pairs([a,b])['pairs'][0]['status'],'initial_condition_mismatch')
 def inspect(self,event,**extra):
  d=OUT/self.id().split('.')[-1];d.mkdir(exist_ok=True);a='A-mac';b='B-mac'
  c=dict(schema='mid.replacement.context.v1',run_id='uart-fixture',pair_id=1,arm='fixed',schedule_t0_ns=0,duration_s=60,planned_interval_ns=500000000,design_version='v1',initial_condition_id='fixture',evidence_kind='synthetic',endpoints=dict(A=a,B=b),endpoint_coverage={a:True,b:True},builds={a:'old-app',b:'uart-app'},uart_bauds={a:115200,b:460800})
  e=dict(schema='mid.serial.v1',event=event,node_id=b,build_id='uart-app',**extra);log=d/'fixture.jsonl';log.write_text(json.dumps(dict(kind='device_rx',host_monotonic_ns=100,event=e))+'\n');cp=d/'context.json';cp.write_text(json.dumps(c));return analysis.analyze(cp,[log])
 def test_mixed_pilot_builds_and_bauds_do_not_invent_build_change(self):
  r=self.inspect('command_result',uart_baud=460800);self.assertNotIn('endpoint_boot_or_build_changed',r['issues']);self.assertNotIn('endpoint_UART_baud_mismatch',r['issues'])
 def test_uart_overflow_event_invalidates_coverage(self):
  r=self.inspect('uart_rx_overflow');self.assertIn('endpoint_capture_or_radio_fatal',r['issues']);self.assertTrue(all(s['goodput_bps'] is None for s in r['seconds']))
 def test_counter_and_wrong_application_baud_are_not_RF_loss(self):
  r=self.inspect('command_result',uart_fifo_overflows=1,uart_ring_overflows=0,uart_baud=115200);self.assertIn('endpoint_UART_overflow_counter_nonzero',r['issues']);self.assertIn('endpoint_UART_baud_mismatch',r['issues'])

if __name__=='__main__':
 import argparse,time,datetime
 ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--case',choices=['core','uart'],default='core');a=ap.parse_args();OUT=Path(a.output).resolve();assert not OUT.exists() and OUT.is_relative_to(ROOT/'simulation/outputs/E2-017');OUT.mkdir(parents=True);start=time.monotonic()
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text('utf-8-sig'));m.update(template_only=False,task_id='E2-017',run_id=OUT.name,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=sys.argv,evidence_kind='synthetic',physical_operations=0,source_hashes={str(p.relative_to(ROOT)):analysis.sha(p) for p in [Path(__file__),ROOT/'tools/mid_baseline/validation/replacement/analysis.py',ROOT/'tools/mid_baseline/validation/replacement/contract.py']});(OUT/'RUN_MANIFEST.started.json').write_text(json.dumps(m,indent=2))
 with (OUT/'unittest.txt').open('w') as f:r=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(UartTests if a.case=='uart' else ReplacementTests))
 result=dict(tests_run=r.testsRun,failures=len(r.failures),errors=len(r.errors),successful=r.wasSuccessful(),evidence_kind='synthetic',RF_runs=0);(OUT/'result.json').write_text(json.dumps(result,indent=2));m.update(status='passed' if r.wasSuccessful() else 'failed',elapsed_s=time.monotonic()-start,exit_code=0 if r.wasSuccessful() else 1);(OUT/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2));print(result);sys.exit(m['exit_code'])
