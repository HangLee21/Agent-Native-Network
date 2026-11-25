"""Five-node increment only: synthetic fixtures, no RF or old-suite reruns."""
import argparse,hashlib,json,os,sys,time,unittest
from datetime import datetime,timezone
from itertools import combinations
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/mid_baseline/validation'))
import five,native
OUT=None
def save(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
class FiveTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.labels={c:'02:00:00:00:00:'+f'{i+1:02x}' for i,c in enumerate('ABCDE')};cls.pkg=OUT/'fixture-package';cls.pkg.mkdir();save(cls.pkg/'PACKAGE_MANIFEST.json',dict(build_id='SYNTHETIC-FIVE-FIXTURE'))
  bridge=cls.pkg/'source/tools/mid_baseline/bridge/bridge.py';bridge.parent.mkdir(parents=True);bridge.write_bytes((ROOT/'tools/mid_baseline/bridge/bridge.py').read_bytes())
  cls.assets=OUT/'fixture-assets';cls.assets.mkdir();cases=[]
  for name in [''.join(x) for x in combinations('ABCDE',2)]+['chain_ABCDE','chain_BADEC']:
   path=list(name[6:]) if name.startswith('chain_') else list(name);paths=[path,list(reversed(path))];routes=[]
   for p in paths:
    for i in range(len(p)-1):routes.append(dict(node=cls.labels[p[i]],src=cls.labels[p[0]],dst=cls.labels[p[-1]],gateways=[dict(node=cls.labels[p[i+1]],weight=1)]))
   d=cls.assets/name;d.mkdir();save(d/'network_update.json',dict(schema='mid.network_update.v1',nodes=list(cls.labels.values()),flows=[dict(src=cls.labels[p[0]],dst=cls.labels[p[-1]]) for p in paths],routes=routes));save(d/'solution.json',dict(status='optimal',fixture_notice='Synthetic routes, not an actual SOCP run'))
   cases.append(dict(case=name))
  save(cls.assets/'INDEX.json',dict(cases=cases));cls.infos={c:dict(schema='mid.serial.v1',event='command_result',cmd='info',ok=True,node_id=m,boot_id=10+i,build_id='SYNTHETIC-FIVE-FIXTURE',firmware='mid-espnow',mode='idle',radio=False,stopping=False,locked_until_reset=False) for i,(c,m) in enumerate(cls.labels.items())}
 def test_twelve_actions_120_packets_and_real_boot_encoding(self):
  plans=[]
  for case in json.loads((self.assets/'INDEX.json').read_text())['cases']:
   p=five.materialize(self.pkg,self.assets,case['case'],self.infos,'fixture',{'labels':self.labels});self.assertEqual(len(p['info_boots']),5)
   commands=[x['command'] for x in p['actions'] if 'command'in x];self.assertEqual(sum(x['cmd']=='send' for x in commands),10)
   frames=[bytes.fromhex(x['frame_hex']) for x in commands if x['cmd']=='config'];self.assertEqual([len(x) for x in frames],[160]*3);self.assertTrue(all(int.from_bytes(x[14:18],'little')==10 for x in frames));plans.append(p)
  self.assertEqual(sum(p['user_packets'] for p in plans),120);save(OUT/'synthetic-plans.json',plans)
 def audit_fixture(self,name,missing=None):
  p=five.materialize(self.pkg,self.assets,name,self.infos,'fixture-'+name,self.labels);p['flows']=[dict(x,count=1) for x in p['flows']];folder=OUT/(name+'-'+str(missing).replace(':','_'));folder.mkdir();rows=[]
  def event(node,kind,**kw):return dict(schema='mid.serial.v1',build_id=p['build_id'],node_id=node,boot_id=p['info_boots'][node],event=kind,**kw)
  for mac in p['info_boots']:rows.append(event(mac,'command_result',cmd='stats',ok=True,nonce='e2-base-'+mac[-2:],tx_queued=0,rx_local=0))
  for path in p['paths']:
   ident=dict(origin=path[0],origin_boot=p['info_boots'][path[0]],seq=1,dst=path[-1]);rows.append(event(path[0],'tx_queued',**ident))
   for i,node in enumerate(path[:-1]):
    if i and missing!=('rx',node):rows.append(event(node,'rx_relay',**ident))
    if missing!=('tx',node):rows.append(event(node,'tx_submit',next_hop=path[i+1],**ident))
   rows.append(event(path[-1],'rx_local',payload_hex='00',**ident))
  for mac in p['info_boots']:rows.append(event(mac,'command_result',cmd='stats',ok=True,nonce='e2-final-'+mac[-2:],tx_queued=1 if mac in [p['paths'][0][0],p['paths'][0][-1]] else 2,rx_local=1 if mac in [p['paths'][0][0],p['paths'][0][-1]] else 0,radio=False,stopping=False,locked_until_reset=False))
  raw=folder/'counterfactual.jsonl';raw.write_text('\n'.join(json.dumps(dict(direction='device_rx',evidence_kind='hardware_serial',event=e,fixture_notice='SYNTHETIC predicate only')) for e in rows));pp=folder/'plan.json';save(pp,p);ctx=folder/'context.json';save(ctx,dict(task_id='H-005',run_id=p['run_id'],status='capture_complete',evidence_kind='hardware_measured',package_manifest_sha256=p['package_manifest_sha256'],log_sha256={str(raw.resolve()):five.sha(raw)},coverage={m:True for m in p['info_boots']},measurement_duration_us=1000000,duration_clock='host_monotonic_controlled_window',fixture_notice='not real measurements'))
  return five.audit(pp,[raw],ctx),p
 def test_both_chains_cover_all_internal_roles(self):
  roles=set()
  for name in ['chain_ABCDE','chain_BADEC']:
   result,p=self.audit_fixture(name);self.assertTrue(all(s['controlled_forwarding_verified'] for s in result['streams']));roles.update(p['paths'][0][1:-1])
  self.assertEqual(roles,set(self.labels.values()))
 def test_missing_each_source_or_intermediate_submit_or_receive_fails(self):
  path=five.path_map('ABCDE',self.labels)[0]
  for kind,node in [('tx',path[0])]+[(kind,node) for node in path[1:-1] for kind in ['rx','tx']]:
   result,_=self.audit_fixture('chain_ABCDE',(kind,node));self.assertFalse(result['streams'][0]['controlled_forwarding_verified'])
 def test_wrong_controlled_solution_not_silently_masked(self):
  with self.assertRaises(ValueError):five.materialize(self.pkg,self.assets,'AB',self.infos,'bad',self.labels,chain='ABCDE')
def main():
 global OUT
 a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();OUT=Path(args.output).resolve();assert not OUT.exists() and OUT.is_relative_to(ROOT/'simulation/outputs/E2-016');OUT.mkdir(parents=True);start=time.monotonic()
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text('utf-8-sig'));m.update(template_only=False,task_id='E2-016',run_id=OUT.name,started_at=datetime.now(timezone.utc).isoformat(),command=sys.argv,evidence_kind='synthetic',status='running',new_five_board_budget_seconds=3600,physical_operations=0,new_RF_runs=0,source_hashes={str(p.relative_to(ROOT)):five.sha(p) for p in [Path(__file__),ROOT/'tools/mid_baseline/validation/five.py']});save(OUT/'RUN_MANIFEST.started.json',m)
 with (OUT/'unittest.txt').open('w') as f:result=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FiveTests))
 elapsed=time.monotonic()-start;save(OUT/'result.json',dict(tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),successful=result.wasSuccessful(),evidence_kind='synthetic',physical_operations=0))
 m.update(finished_at=datetime.now(timezone.utc).isoformat(),elapsed_s=elapsed,exit_code=0 if result.wasSuccessful() else 1,status='passed' if result.wasSuccessful() else 'failed');save(OUT/'RUN_MANIFEST.json',m);print(json.dumps(dict(status=m['status'],elapsed_s=elapsed)));return m['exit_code']
if __name__=='__main__':raise SystemExit(main())
