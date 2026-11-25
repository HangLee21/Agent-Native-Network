"""Run a H-compiled measured-baseline scenario WITHOUT legacy re-compilation."""
import argparse,copy,datetime,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from simulation.mid_link_console.runner.routing_pair import RoutingEngine
from simulation.mid_link_console.runner.pair import CustomEngine
from simulation.mid_link_study.engine.run import save,sha

ALGORITHMS=('fixed','latency_aware','compare_latency','mid','compare_mid')
class UnsupportedCombination(ValueError):pass

class MeasuredRoutingEngine(RoutingEngine):
 def environment(self,t=None):
  from simulation.mid_link_console.settings.measured import state_at
  return state_at(self.s,min(self.duration,max(0,self.t if t is None else t)))

class MeasuredMIDEngine(CustomEngine):
 def environment(self,t=None):
  from simulation.mid_link_console.settings.measured import state_at
  return state_at(self.s,min(self.duration,max(0,self.t if t is None else t)))

def validate_scenario(scenario,algorithm):
 if algorithm not in ALGORITHMS:raise UnsupportedCombination('请选择固定链、时延感知、两者配对、原MID或原MID配对。')
 if scenario.get('nodes')!=list('ABCDE') or not scenario.get('settings_sha256'):raise ValueError('需要H接口编译的完整五板场景与设置指纹。')
 if not scenario.get('edges') or any('delay_ms' not in e for e in scenario['edges']):raise ValueError('每方向的传播时延必须由H快照/模型值明确提供。')
 routing=scenario.get('routing',{})
 if algorithm in ('mid','compare_mid'):
  flows=scenario.get('traffic',{}).get('flows')
  if routing.get('hops') is not None or flows!=[dict(src='A',dst='B'),dict(src='B',dst='A')]:
   raise UnsupportedCombination('原MID当前入口仅支持A↔B双向、且不限跳数；不会把严格跳数或任意起终点伪装成原MID。请改选时延感知/固定链，或设A→B、反向开启、不限跳数。')
 elif not routing or routing.get('src')==routing.get('dst'):raise ValueError('需要有效的源目的/跳数routing字段。')
 return scenario

def execute_compiled(scenario,output_dir,*,algorithm='compare_latency',settings=None,source=None,cancel=None,progress=None):
 """Pure library boundary for E2: use exact H scenario, never normalize via old defaults."""
 scenario=copy.deepcopy(scenario);validate_scenario(scenario,algorithm)
 if algorithm in ('mid','compare_mid'):
  scenario['routing']['policy']='original_MID_SOCP'
  scenario['routing']['objective']='maximize common robust service margin; not propagation latency or exact hops'
 out=Path(output_dir);out.mkdir(parents=True,exist_ok=False);save(out/'settings.json',settings if settings is not None else scenario['custom_settings']);save(out/'scenario.json',scenario)
 arms={'fixed':['fixed'],'latency_aware':['latency_aware'],'compare_latency':['fixed','latency_aware'],'mid':['adaptive'],'compare_mid':['fixed','adaptive']}[algorithm]
 result=dict(schema='mid.workbench.result.v1',status='running',run_id=out.name,evidence_kind='software_simulation',algorithm=algorithm,selection_semantics='actual_arms_executed',execution_mode='paired_comparison' if len(arms)==2 else 'selected_strategy_only',executed_arms=arms,settings_sha256=scenario['settings_sha256'],runs=[],output_directory=str(out.resolve()),snapshot_source=source)
 save(out/'INDEX.json',result);started=time.monotonic()
 try:
  for arm in arms:
   # Existing environment evaluator accepts H's compiled edge baselines and
   # segments. No get_defaults()/compile_scenario() is called on the scenario.
   engine=MeasuredMIDEngine if algorithm in ('mid','compare_mid') else MeasuredRoutingEngine
   row=engine(scenario,scenario['custom_settings']['seed'],arm,out/arm,cancel,progress).run()
   context_path=out/arm/'context.json';ctx=json.loads(context_path.read_text());ctx.update(workbench_algorithm=algorithm,selection_semantics=result['selection_semantics'],snapshot_source=source,baseline_interpretation='Historical measured service/PDR baseline plus explicit model delay/capacity parameters; not current physical state or latency calibration');save(context_path,ctx)
   result['runs'].append(dict(row,path=arm,context=arm+'/context.json',events=arm+'/events.jsonl'))
   save(out/'INDEX.json',result)
   if row['status']=='cancelled':result['status']='cancelled';break
  else:result['status']='complete'
 except Exception as e:result.update(status='failed',error=repr(e))
 result['wall_s']=time.monotonic()-started;save(out/'INDEX.json',result)
 manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));manifest.update(template_only=False,task_id='E1-022',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=['execute_compiled',algorithm],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out.resolve()),config_file=str(out/'scenario.json'),status=result['status'],exit_code=0 if result['status']=='complete' else 1,seeds=[scenario['custom_settings']['seed']],dirty_files_sha256={'workbench.py':sha(Path(__file__))},limitations=['Software result only; no device access; source snapshot is historical, edited parameters are hypotheses']);save(out/'RUN_MANIFEST.json',manifest)
 return result

def run_pair(settings,output_dir,cancel=None,progress=None,*,algorithm=None):
 """H measured API is bound here once supplied; E2 may call execute_compiled now."""
 from simulation.mid_link_console.settings import measured
 normalized=measured.normalize_settings(settings)
 selected=algorithm or normalized.get('algorithm','compare_latency')
 return execute_compiled(measured.compile_scenario(normalized),output_dir,algorithm=selected,settings=normalized,source=dict(provider='simulation.mid_link_console.settings.measured',snapshot_id=normalized.get('snapshot_id'),source_kind='historical_measurement_plus_explicit_model_values'),cancel=cancel,progress=progress)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--settings',required=True);p.add_argument('--output',required=True);p.add_argument('--cancel-file');p.add_argument('--algorithm',choices=ALGORITHMS);p.add_argument('--compiled-scenario');a=p.parse_args();settings=json.loads(Path(a.settings).read_text(encoding='utf-8'));cancel=(lambda:Path(a.cancel_file).exists()) if a.cancel_file else None
 if a.compiled_scenario:r=execute_compiled(json.loads(Path(a.compiled_scenario).read_text(encoding='utf-8')),a.output,algorithm=a.algorithm or 'compare_latency',settings=settings,cancel=cancel)
 else:r=run_pair(settings,a.output,cancel,algorithm=a.algorithm)
 print(json.dumps(r));raise SystemExit(0 if r['status']=='complete' else 2)
