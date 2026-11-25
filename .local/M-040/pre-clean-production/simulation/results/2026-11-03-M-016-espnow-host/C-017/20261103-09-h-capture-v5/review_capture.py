"""C finite independent H-v5 checks, synthetic captures only; no serial enumeration."""
from datetime import datetime,timezone
import contextlib,copy,hashlib,importlib.util,io,json,shutil,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=HERE/'source'
E2=HERE.parent/'20261103-07-e2-comprehensive/source'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def now():return datetime.now(timezone.utc).isoformat()
assert not (HERE/'RUN_MANIFEST.start.json').exists(), 'Refuse replay into existing evidence'
hashes=read(HERE/'source_hashes.json')
for name,digest in hashes.items():assert sha(SOURCE/name)==digest,name
spec=importlib.util.spec_from_file_location('c017_h',SOURCE/'tools/espnow_hardware/__init__.py',submodule_search_locations=[str(SOURCE/'tools/espnow_hardware')])
package=importlib.util.module_from_spec(spec);sys.modules['c017_h']=package;spec.loader.exec_module(package)
from c017_h import hardware_tool as h,analysis_bridge as bridge
manifest=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
manifest.update(template_only=False,task_id='C-017',run_id=HERE.name,started_at=now(),worktree=str(ROOT),
 git_commit='d8325a230ce41943f43528c6a0c9552949e07abe',dirty_files_sha256={**hashes,'review_capture.py':sha(Path(__file__))},
 command=[sys.executable,'-B',str(Path(__file__))],python_executable=sys.executable,dependency_snapshot={'python':sys.version,'libraries':'stdlib only'},
 config_file=str(HERE/'source_hashes.json'),output_directory=str(HERE),status='running',evidence_kind='synthetic',
 budget={'command_timeout_s':120,'task_cap_s':600,'prior_charged_s':34,'output_cap_bytes':104857600},
 limitations=['Actual archived C trace passed through frozen H Capture and E2 API; no new C compilation or RF.',
 'Coverage counters/windows and every fixture are synthetic; no physical device enumeration/open, H-002 or hardware measurement.'])
write(HERE/'RUN_MANIFEST.start.json',manifest)
start=time.monotonic()

class CaptureReview(unittest.TestCase):
 def setUp(self):
  self.root=HERE/'fixtures'/self._testMethodName;self.root.mkdir(parents=True)
  self.out=self.root/'capture';self.out.mkdir()
  e2hash=read(HERE.parent/'20261103-07-e2-comprehensive/source_hashes.json')
  frozen={n:e2hash[n] for n in ['tests/espnow/analyze_logs.py','tests/espnow/ANALYZER_API.md','tests/espnow/README.md','tests/espnow/ANALYZER_FREEZE.json']}
  for name,digest in frozen.items():
   target=self.root/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(E2/name,target);self.assertEqual(sha(target),digest)
  registry=self.root/'coordination/reviews/M-016-verification.json';registry.parent.mkdir(parents=True)
  write(registry,{'active_freezes':{'E2_analyzer':'E2_analyzer_v2'},'frozen':{'E2_analyzer_v2':frozen}})
  self.capture=h.Capture(self.out,evidence_kind='synthetic')
  raw=ROOT/'simulation/results/2026-11-03-M-016-espnow-host/E2-015/20261103-13-final-core-contract/telemetry.jsonl'
  self.boots={};self.by_id={}
  for line in raw.read_bytes().splitlines():
   event=h.parse_event(line)
   if event:
    device='board'+str(int(event['node_id'].split(':')[-1],16))
    self.capture.record(device,'device_rx',line)
    self.boots[device]=event['boot_id'];self.by_id[device]={'node_id':event['node_id']}
  self.capture.close()
  self.plan={'run_id':'E2-echo','device_ids':sorted(self.by_id),'sender_id':'board1','receiver_id':'board5','count':1}
  self.result={'status':'hardware_capture_unanalyzed','probes':[{'id':k,'info':{'boot_id':v,'chip':'host-synthetic'}} for k,v in self.boots.items()],
   'stop_attempts':[{'id':k,'acknowledged':True} for k in self.by_id],'cleanup_errors':[]}
  base={k:{'boot_id':v,'event_overflow':0,'queue_overflow':0,'delivered':0} for k,v in self.boots.items()}
  final={k:{**v,'delivered':len(self.capture.unique_rx.get(k,set()))} for k,v in base.items()}
  self.runtime={'baseline_stats':base,'final_stats':final,'window_start_ns':1000000000,'window_end_ns':2000000000}
  write(self.out/'measurements.json',h.measurement_ledger())
 def context(self):return bridge.capture_context(self.plan,self.result,self.capture,self.by_id,self.runtime)
 def finalize(self):return bridge.finalize_capture(self.root,self.out,self.plan,self.result,self.capture,self.by_id,self.runtime)
 def test_actual_C_capture_pipeline_stays_synthetic(self):
  before=sha(self.out/'measurements.json');status=self.finalize();a=read(Path(status['analysis']))
  self.assertEqual(a['pdr'],1);self.assertEqual(a['successful_same_boot_rtt_count'],1)
  self.assertEqual(a['evidence_kind'],'synthetic');self.assertTrue(self.context()['receiver_log_complete'])
  self.assertEqual(a['source_manifests'][0]['sha256'],sha(self.out/'capture_context.json'))
  self.assertEqual(a['source_logs'][0]['sha256'],sha(self.capture.path))
  self.assertEqual(sha(self.out/'measurements.json'),before);self.assertFalse((self.out/'measurement_updates.jsonl').exists())
 def test_coverage_faults_never_admit_metrics(self):
  baseline=copy.deepcopy(self.runtime)
  for fault in ['overflow','boot','regressed','counter_mismatch','missing_stats','partial','malformed']:
   with self.subTest(fault=fault):
    self.runtime=copy.deepcopy(baseline);self.capture.pending={};self.capture.malformed_devices=set()
    if fault=='overflow':self.runtime['final_stats']['board5']['event_overflow']=1
    if fault=='boot':self.runtime['final_stats']['board5']['boot_id']='changed'
    if fault=='regressed':self.runtime['final_stats']['board5']['queue_overflow']=-1
    if fault=='counter_mismatch':self.runtime['final_stats']['board5']['delivered']+=1
    if fault=='missing_stats':del self.runtime['final_stats']['board5']
    if fault=='partial':self.capture.pending['board5']=b'{unfinished'
    if fault=='malformed':self.capture.malformed_devices.add('board5')
    context=self.context();self.assertFalse(context['receiver_log_complete']);self.assertTrue(context['coverage_reasons'])
 def test_stop_unconfirmed_saves_context_without_analysis(self):
  self.result['status']='stop_unconfirmed';self.result['stop_attempts'][0]['acknowledged']=False
  status=self.finalize();self.assertEqual(status['status'],'capture_failed_not_analyzed')
  self.assertFalse((self.out/'synthetic').exists());self.assertFalse((self.out/'measurement_updates.jsonl').exists())
  self.assertFalse(read(self.out/'capture_context.json')['receiver_log_complete'])
 def test_input_mutation_detected_before_publishing_analysis(self):
  real_load=bridge.load_analyzer
  def wrapped(root):
   module,frozen=real_load(root);real=module.analyze_files
   def mutate(config,*args,**kwargs):
    analysis=real(config,*args,**kwargs)
    with Path(config).open('a',encoding='utf-8') as stream:stream.write(' ')
    return analysis
   module.analyze_files=mutate;return module,frozen
  with patch.object(bridge,'load_analyzer',side_effect=wrapped):
   with self.assertRaisesRegex(ValueError,'input changed'):self.finalize()
  self.assertFalse((self.out/'synthetic/analysis.json').exists());self.assertFalse((self.out/'measurement_updates.jsonl').exists())
 def test_unknown_analyzer_version_rejected(self):
  registry=self.root/'coordination/reviews/M-016-verification.json';v=read(registry);v['active_freezes']['E2_analyzer']='unknown';write(registry,v)
  with self.assertRaisesRegex(ValueError,'unknown or unapproved'):self.finalize()
  self.assertFalse((self.out/'measurement_updates.jsonl').exists())
 def test_default_once_never_opens_with_empty_bindings(self):
  cfg=self.root/'bindings.json';write(cfg,{'schema':'ann.hardware.bindings.v1','bindings':[]})
  template=self.root/'coordination/templates/RUN_MANIFEST.json';template.parent.mkdir(parents=True);write(template,{})
  output=self.root/'simulation/outputs/H-001/default-check'
  with patch.object(h,'ROOT',self.root),patch.object(h,'source_hashes',return_value={}),patch.object(h,'enumerate_ports',return_value={'status':'enumerated','ports':[]}) as enum,patch.object(h,'open_bound',side_effect=AssertionError('physical open forbidden')) as op,contextlib.redirect_stdout(io.StringIO()):
   self.assertEqual(h.main(['--once','--bindings',str(cfg),'--output',str(output)]),0)
  enum.assert_called_once();op.assert_not_called();self.assertEqual(read(output/'check.json')['status'],'waiting_hardware')
  self.assertTrue(all(v['value'] is None for v in read(output/'measurements.json')['metrics'].values()))
 def test_finite_plan_rejects_unarmed_overflow_and_extra_runs(self):
  bindings=[{'id':k,'allow_probe':True} for k in self.by_id]
  valid={**self.plan,'schema':'ann.hardware.bench.v1','armed':True,'count':1,'interval_ms':100,'frame_bytes':128,'echo':True,'max_runs':1,'capture_seconds':2}
  h.validate_plan(valid,bindings)
  for mutation in [{'armed':False},{'count':1001},{'max_runs':2},{'capture_seconds':46},{'frame_bytes':119},{'count':100,'interval_ms':100}]:
   with self.subTest(mutation=mutation),self.assertRaises(ValueError):h.validate_plan({**valid,**mutation},bindings)

with (HERE/'unittest.txt').open('w',encoding='utf-8') as stream:
 result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CaptureReview))
summary={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'elapsed_s':time.monotonic()-start,
 'evidence_kind':'synthetic','physical_ports_opened':0,'real_OS_enumerations':0,'wireless_runs':0,
 'source_copies_unchanged':all(sha(SOURCE/n)==d for n,d in hashes.items())}
write(HERE/'summary.json',summary)
manifest.update(finished_at=now(),exit_code=0 if result.wasSuccessful() else 1,status='passed' if result.wasSuccessful() else 'failed',execution_elapsed_s=summary['elapsed_s'])
write(HERE/'RUN_MANIFEST.json',manifest)
print(json.dumps(summary));sys.exit(manifest['exit_code'])
