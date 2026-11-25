"""H-011 finite new measured-baseline checks, no solver/serial/network."""
import argparse,copy,datetime,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from simulation.mid_link_console.settings import measured as m
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-011');out.mkdir(parents=True,exist_ok=False);checks=[]
 def save(name,obj):
  with(out/name).open('x',encoding='utf-8')as f:json.dump(obj,f,ensure_ascii=False,indent=2);f.write('\n')
 def check(name,condition):assert condition,name;checks.append(dict(name=name,passed=True))
 snap=m.get_snapshot();d=m.get_defaults();normal=m.normalize_settings(d);s=m.compile_scenario(d)
 check('all_twenty_independent_directed_measurements',len(snap['edges'])==20 and len({(e['src'],e['dst'])for e in snap['edges']})==20)
 check('default_A_C_unlimited_no_intervention',d['src']=='A' and d['dst']=='C' and d['hops']is None and not s['events'])
 check('exact_measured_service_not_legacy_capacity',all(e['capacity_payload_bps']==2560 and e['pdr']==1 for e in m.state_at(s,0)['edges']))
 check('counts_and_timing_provenance',all(e['measured']['accepted']==e['measured']['destination_unique']==100 and e['measured']['window_samples']==10 and e['capture']['run_started_at_utc'] and e['capture']['host_monotonic_end_ns']>e['capture']['host_monotonic_start_ns'] for e in snap['edges']))
 check('unmeasured_delay_is_null_and_simulation_delay_is_marked',all(e['measured']['one_way_delay_ms']is None and e['defaults']['delay_ms']==10 and e['parameter_provenance']['delay_ms']=='unmeasured_editable_model_value' for e in snap['edges']))
 edit=copy.deepcopy(d)
 for e in edit['links']:
  if(e['src'],e['dst'])==('A','C'):e.update(fail=True)
  if(e['src'],e['dst'])==('D','C'):e.update(delay_ms=750,success_pct=75,capacity_kbps=1.28)
 edited=m.compile_scenario(edit)
 def edge(t,src,dst):return next(e for e in m.state_at(edited,t)['edges']if(e['src'],e['dst'])==(src,dst))
 check('two_edits_real_direction_and_window',edge(25,'A','C')['pdr']==0 and edge(25,'C','A')['pdr']==1 and edge(25,'D','C')['propagation_delay_s']==.75 and edge(25,'D','C')['pdr']==.75 and edge(25,'D','C')['capacity_payload_bps']==1280)
 check('restores_measured_values_before_and_after_window',all(edge(t,'D','C')['capacity_payload_bps']==2560 and edge(t,'D','C')['delay_ms']==10 and edge(t,'A','C')['pdr']==1 for t in [0,19.999999,40,60]))
 check('reset_clears_all_edits_and_snapshot_not_aliased',m.get_defaults()==d and m.get_snapshot()==snap)
 check('canonical_normalization',m.normalize_settings(normal)==normal and m.settings_hash(d)==m.settings_hash(normal))
 # Deliberately asymmetric fixture proves compilation never mirrors a direction.
 original=m.get_snapshot;fixture=copy.deepcopy(snap)
 for e in fixture['edges']:
  if(e['src'],e['dst'])==('A','B'):e['defaults'].update(success_pct=83,capacity_kbps=1.792)
 try:
  m.get_snapshot=lambda:copy.deepcopy(fixture);test=m.compile_scenario(m.get_defaults());state=m.state_at(test,0)
  ab=next(e for e in state['edges']if(e['src'],e['dst'])==('A','B'));ba=next(e for e in state['edges']if(e['src'],e['dst'])==('B','A'))
  check('synthetic_asymmetric_fixture_not_mirrored',ab['pdr']==.83 and ab['capacity_payload_bps']==1792 and ba['pdr']==1 and ba['capacity_payload_bps']==2560)
 finally:m.get_snapshot=original
 failures=0
 for raw in [dict(snapshot_id='other'),dict(schema='old'),dict(links=[dict(src='A',dst='C'),dict(src='A',dst='C')]),dict(links=[dict(src='A',dst='C',delay_ms=-1)]),dict(unrecognized=1)]:
  try:m.normalize_settings(raw)
  except m.SettingsError:failures+=1
 check('invalid_snapshot_direction_range_unknown_rejected',failures==5)
 check('short_duration_defaults_are_valid',m.normalize_settings(dict(duration_s=10))['fault_end_s']<10)
 save('defaults.json',d);save('two-edits.json',edit);save('compiled.json',edited);save('states.json',[m.state_at(edited,t)for t in[0,20,25,40,60]])
 result=dict(passed=True,checks=checks,scope='Historical source derivation and settings mapping only; asymmetric fixture is synthetic; no engine/browser/hardware run.',serial_ports_opened=0)
 save('result.json',result);manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text());manifest.update(template_only=False,task_id='H-011',run_id=out.name,started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=sys.argv,python_executable=sys.executable,output_directory=str(out),status='measured_contract_passed',exit_code=0,dirty_files_sha256={str(Path(m.__file__).relative_to(ROOT)):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest()},limitations=[result['scope']]);save('RUN_MANIFEST.json',manifest);print(json.dumps(result))
if __name__=='__main__':main()
