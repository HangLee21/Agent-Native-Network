"""NATIVE-01 only. Counterfactual labels test a predicate, never hardware data."""
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/mid_baseline/validation'))
import native as n

class Native01Tests(unittest.TestCase):
 def fixture(self,name,omit=None,change=None):
  out=Path(os.environ['E2_MID_TEST_OUTPUT'])/name;out.mkdir();c='90:da:72:48:a4:e0';boots={n.A:101,n.B:203,c:305}
  plan=dict(run_id='NATIVE01-counterfactual',package_manifest_sha256=n.PACKAGE_HASH,info_boots=boots,required_relay=n.B,flows=[dict(source=n.A,destination=c,count=1)])
  rows=[]
  def event(mac,kind,**kw):return dict(schema='mid.serial.v1',build_id=n.BUILD,node_id=mac,boot_id=boots[mac],event=kind,**kw)
  for mac in boots:rows.append(event(mac,'command_result',cmd='stats',ok=True,nonce='e2-base-'+mac[-2:],tx_queued=0,rx_local=0))
  identity=dict(origin=n.A,origin_boot=101,seq=1,dst=c)
  chain=[event(n.A,'tx_queued',**identity),event(n.A,'tx_submit',next_hop=n.B,**identity),event(n.B,'rx_relay',**identity),event(n.B,'tx_submit',next_hop=c,**identity),event(c,'rx_local',payload_hex='00',**identity)]
  for i,row in enumerate(chain):
   if i==omit:continue
   if change and i==change[0]:row.update(change[1])
   rows.append(row)
  for mac in boots:rows.append(event(mac,'command_result',cmd='stats',ok=True,nonce='e2-final-'+mac[-2:],tx_queued=0 if mac==c else 1,rx_local=1 if mac==c else 0,radio=False,stopping=False,locked_until_reset=False))
  raw=out/'counterfactual.jsonl';raw.write_text('\n'.join(json.dumps(dict(direction='device_rx',evidence_kind='hardware_serial',event=r,fixture_notice='SYNTHETIC predicate test, no physical observations')) for r in rows)+'\n')
  context=dict(task_id='H-005',run_id=plan['run_id'],status='capture_complete',evidence_kind='hardware_measured',package_manifest_sha256=n.PACKAGE_HASH,log_sha256={str(raw.resolve()):n.sha(raw)},coverage={mac:True for mac in boots},measurement_duration_us=1000000,duration_clock='host_monotonic_controlled_window',fixture_notice='SYNTHETIC/OFFLINE_ONLY test labels; never append measurement')
  pp=out/'plan.json';pp.write_text(json.dumps(plan));cp=out/'context.json';cp.write_text(json.dumps(context))
  # Existing package validation is unchanged and deliberately excluded here.
  with patch.object(n,'verify',return_value=None):value=n.audit(pp,[raw],cp)
  return value['streams'][0]
 def test_complete_chain_keeps_source_submit_lineage(self):
  result=self.fixture('complete');self.assertTrue(result['controlled_forwarding_verified'])
  evidence=next(iter(result['relay_evidence'].values()))
  self.assertEqual(evidence['source_tx_submit'][0]['line'],5)
 def test_each_missing_link_cannot_verify_chain(self):
  for i in [1,2,3,4]:
   with self.subTest(omitted=i):self.assertFalse(self.fixture('missing-'+str(i),omit=i)['controlled_forwarding_verified'])
 def test_source_submit_identity_and_next_hop_must_match(self):
  for name,change in [('seq',dict(seq=2)),('boot',dict(origin_boot=102)),('destination',dict(dst=n.B)),('next',dict(next_hop='90:da:72:48:a4:e0'))]:
   with self.subTest(change=name):self.assertFalse(self.fixture('mismatch-'+name,change=(1,change))['controlled_forwarding_verified'])
