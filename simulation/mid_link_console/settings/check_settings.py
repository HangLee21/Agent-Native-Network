"""Finite boundary/translation checks for H-009. No engine, HTTP or devices."""
import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from simulation.mid_link_study.scenarios import custom as c
from simulation.mid_link_study.scenarios.scenarios import path_witness


def save(path,value):
    with path.open('x',encoding='utf-8') as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False)
        handle.write('\n')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-009'):raise ValueError('outside H-009')
    out.mkdir(parents=True,exist_ok=False);started=datetime.datetime.now(datetime.timezone.utc).isoformat();checks=[]
    def passed(name):checks.append(dict(name=name,passed=True))
    defaults=c.get_defaults();fresh=copy.deepcopy(defaults)
    defaults['links'][0]['delay_ms']=999;defaults['offline_nodes'].append('D')
    assert c.get_defaults()==fresh;passed('fresh_defaults_have_no_draft_aliases')
    assert c.normalize_settings({})==c.normalize_settings(fresh);passed('complete_reset_returns_full_original_settings')
    assert c.normalize_settings(fresh)==fresh;passed('normalization_is_idempotent')
    reordered=copy.deepcopy(fresh);reordered['links'].reverse()
    assert c.settings_hash(reordered)==c.settings_hash(fresh);passed('canonical_directed_edge_order')
    assert c.compile_scenario(fresh)['events']==[];passed('normal_preset_has_no_intervention')
    for preset in c.PRESETS:
        assert len(c.normalize_settings(c.get_defaults(preset))['links'])==20
    passed('all_five_presets_compile_to_complete_settings')
    sample=c.get_defaults()
    for e in sample['links']:
        pair=frozenset((e['src'],e['dst']))
        if pair==frozenset('AC'):e['fail']=True
        if pair==frozenset('CD'):e['delay_ms']=750;e['success_pct']=75;e['capacity_kbps']=4.096
    before=copy.deepcopy(sample);scenario=c.compile_scenario(sample);assert sample==before
    def edge(t,a,b):return next(e for e in c.state_at(scenario,t)['edges'] if (e['src'],e['dst'])==(a,b))
    for t in (0,19.999999,40,59.999999,60):
        assert edge(t,'A','C')['pdr']==1 and edge(t,'C','D')['delay_ms']==10 and edge(t,'C','D')['capacity_payload_bps']==8192
    for t in (20,20.000001,39.999999):
        assert edge(t,'A','C')['pdr']==edge(t,'C','A')['pdr']==0
        assert edge(t,'C','D')['delay_ms']==edge(t,'D','C')['delay_ms']==750
        assert edge(t,'C','D')['pdr']==.75 and edge(t,'C','D')['capacity_payload_bps']==4096
    passed('two_bidirectional_edits_apply_and_restore_all_properties_at_exact_boundaries')
    assert c.state_at(scenario,20)['edges'][0]['propagation_delay_s']==.01
    assert edge(20,'C','D')['propagation_delay_s']==.75;passed('milliseconds_translate_to_seconds_once')
    one=c.compile_scenario(dict(links=[dict(src='A',dst='C',fail=True)]))
    assert next(e for e in c.state_at(one,25)['edges'] if (e['src'],e['dst'])==('A','C'))['pdr']==0
    assert next(e for e in c.state_at(one,25)['edges'] if (e['src'],e['dst'])==('C','A'))['pdr']==1
    passed('single_direction_never_silently_changes_reverse')
    offline=c.compile_scenario(c.get_defaults('relay_exit'))
    assert 'C' not in c.state_at(offline,20)['active_nodes'] and 'C' in c.state_at(offline,40)['active_nodes']
    passed('offline_relay_obeys_half_open_window')
    disconnected=c.get_defaults()
    for e in disconnected['links']:e['connected']=False
    state=c.state_at(c.compile_scenario(disconnected),0)
    assert path_witness(state,'A','B') is None;passed('all_disconnected_is_valid_unreachable_configuration')
    errors=[]
    invalid=[None,{'unknown':1},{'schema':'old'}, {'preset':[]}, {'duration_s':True},
        {'duration_s':121}, {'seed':0}, {'seed':10**1000}, {'fault_start_s':40,'fault_end_s':20},
        {'fault_end_s':61}, {'offline_nodes':['A']}, {'offline_nodes':['C','C']},
        {'links':[dict(src='A',dst='A')]}, {'links':[dict(src='A',dst='C'),dict(src='A',dst='C')]},
        {'links':[dict(src='A',dst='C',delay_ms=-1)]}, {'links':[dict(src='A',dst='C',delay_ms=2001)]},
        {'links':[dict(src='A',dst='C',delay_ms=float('nan'))]}, {'links':[dict(src='A',dst='C',success_pct=101)]},
        {'links':[dict(src='A',dst='C',connected=0)]}, {'links':[dict(src='A',dst='C',connected=False,fail=True)]},
        {'links':[dict(src='A',dst='C',capacity_kbps=0)]}, {'links':[dict(src='A',dst='C',path='x')]}]
    for index,value in enumerate(invalid):
        try:c.normalize_settings(value)
        except c.SettingsError as exc:errors.append(dict(case=index,**exc.as_dict()))
        else:raise AssertionError(f'invalid case accepted: {index}')
    passed('twenty_two_invalid_inputs_return_locatable_chinese_errors')
    minimum=c.compile_scenario(dict(duration_s=10))
    assert 0<minimum['custom_settings']['fault_start_s']<minimum['custom_settings']['fault_end_s']<10
    passed('short_duration_default_window_stays_inside_run')
    save(out/'catalog.json',c.catalog());save(out/'defaults.json',fresh)
    save(out/'two-link-settings.json',sample);save(out/'two-link-scenario.json',scenario)
    save(out/'sample-states.json',[c.state_at(scenario,t) for t in (0,19.999999,20,25,39.999999,40,60)])
    save(out/'invalid-inputs.json',errors)
    result=dict(passed=True,checks=checks,invalid_cases=len(errors),engine_runs=0,serial_ports_opened=0,RF_operations=0,
                scope='Settings/translation boundaries only; no actual packet propagation or browser validation claimed.')
    save(out/'result.json',result)
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    sources=[Path(c.__file__).resolve(),Path(__file__).resolve()]
    manifest.update(template_only=False,task_id='H-009',run_id=out.name,started_at=started,
        finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        dirty_files_sha256={str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in sources},
        command=sys.argv,python_executable=sys.executable,dependency_snapshot={'python':sys.version,'libraries':'stdlib'},
        config_file=str(out/'two-link-settings.json'),seeds=[11],budget={'cpu_jobs':1,'wall_seconds':30},
        output_directory=str(out),exit_code=0,status='settings_checks_passed',
        limitations=[result['scope'],'All coefficients and link delays are assumed software inputs.'])
    save(out/'RUN_MANIFEST.json',manifest);print(json.dumps(result))


if __name__=='__main__':main()
