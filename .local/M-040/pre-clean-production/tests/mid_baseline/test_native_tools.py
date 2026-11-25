import importlib.util,json,os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/mid_baseline/validation'))
import native as n
class NativeToolsTests(unittest.TestCase):
 def setUp(self):
  self.out=Path(os.environ['E2_MID_TEST_OUTPUT']);self.source=ROOT/'simulation/outputs/E2-016/20261106-06-native-package-corrected'
 def info(self,file):
  return next(json.loads(s) for s in file.read_text().splitlines() if s.startswith('{') and 'mid.serial.v1' in s and json.loads(s).get('cmd')=='info')
 def plan(self):return n.materialize(self.info(self.source/'native-A.stdout'),self.info(self.source/'native-1.stdout'),'host-native-test')
 def test_actual_native_info_materializes_ten_commands_fresh_boot(self):
  p=self.plan();sends=[a for a in p['actions'] if a.get('command',{}).get('cmd')=='send'];self.assertEqual(len(sends),10)
  self.assertTrue(all(len(bytes.fromhex(a['command']['payload_hex']))==16 for a in sends))
  configs=[a['command'] for a in p['actions'] if a.get('command',{}).get('cmd')=='config'];self.assertEqual(len(configs),3)
  self.assertEqual([int.from_bytes(bytes.fromhex(a['frame_hex'])[14:18],'little') for a in configs],[101]*3)
  (self.out/'synthetic-derived-AB-plan.json').write_text(json.dumps(p,indent=2))
 def test_actual_bound_ABC_assets_materialize_three_cases(self):
  a=self.info(self.source/'native-A.stdout');b=self.info(self.source/'native-1.stdout');c=dict(b,node_id='90:da:72:48:a4:e0',boot_id=305,device_label='?')
  for case,count in [('AC',4),('BC',4),('AC_controlled_two_hop',6)]:
   with self.subTest(case=case):
    p=n.materialize_abc(a,b,c,'synthetic-'+case,case)
    commands=[r['command'] for r in p['actions'] if 'command'in r];frames=[bytes.fromhex(q['frame_hex']) for q in commands if q['cmd']=='config']
    self.assertEqual([len(f) for f in frames],[84]*3);self.assertEqual(sum(q['cmd']=='send' for q in commands),count)
    self.assertTrue(all(int.from_bytes(f[14:18],'little')==101 for f in frames))
    (self.out/('synthetic-plan-'+case+'.json')).write_text(json.dumps(p,indent=2))
 def test_old_ANN_or_wrong_boot_or_busy_info_rejected(self):
  a=self.info(self.source/'native-A.stdout');b=self.info(self.source/'native-1.stdout')
  for change in [dict(build_id='ann-v1'),dict(boot_id=0),dict(radio=True),dict(mode='active'),dict(locked_until_reset=True)]:
   with self.subTest(change=change),self.assertRaises(ValueError):n.materialize(dict(a,**change),b,'bad')
 def test_actual_native_source_destination_audit_never_upgrades_host(self):
  pp=self.out/'plan-audit.json';pp.write_text(json.dumps(self.plan()))
  result=n.audit(pp,[self.source/'native-A.stdout',self.source/'native-1.stdout'])
  self.assertEqual(result['streams'][0]['source_queued_unique'],5);self.assertEqual(result['streams'][0]['endpoint_unique_observed'],5)
  self.assertTrue(all(x['pdr'] is None and x['goodput_bps'] is None and x['rtt_ms'] is None for x in result['streams']))
  (self.out/'synthetic-native-audit.json').write_text(json.dumps(result,indent=2))
  ctx=self.out/'fake-context.json';ctx.write_text(json.dumps(dict(task_id='H-005',run_id='host-native-test',status='capture_complete',evidence_kind='hardware_measured',package_manifest_sha256=n.PACKAGE_HASH)))
  with self.assertRaisesRegex(ValueError,'synthetic'):n.audit(pp,[self.source/'native-A.stdout'],ctx)
