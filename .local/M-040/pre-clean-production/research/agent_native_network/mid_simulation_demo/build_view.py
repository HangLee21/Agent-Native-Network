"""Read explicit software-simulation sources and package an offline viewer.

No engine runs, solver calls, device access, network calls or history scans.
"""
from pathlib import Path
import argparse, datetime, hashlib, importlib.util, json, sys, gzip, base64

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LABELS={'gradual_link':'单条在用链路渐弱','relay_exit':'在役中继退出 / 替代路保留','partition_restore':'完全分区后恢复'}

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def source_record(path,role):
    rel=path.resolve().relative_to(ROOT).as_posix()
    return {'path':rel,'role':role,'sha256':sha(path),'href':'../../../'+rel}

def load_scenarios(config,data):
    module_path=ROOT/'simulation/mid_link_study/scenarios/scenarios.py'
    spec=importlib.util.spec_from_file_location('d018_readonly_scenario',module_path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    data['sources'].append(source_record(module_path,'H场景状态求值函数（只读调用）'))
    for name in config['scenario_files']:
        path=ROOT/name;s=read(path);data['sources'].append(source_record(path,'H场景输入假设'))
        snapshots=[]
        for tick in range(int(s['duration_s']*20)+1):
            t=tick/20;state=model.state_at(s,t)
            snapshots.append({'t_s':t,'active_nodes':state['active_nodes'],'edges':[{'src':e['src'],'dst':e['dst'],'capacity_bps':e['capacity_payload_bps'],'pdr':e['pdr']} for e in state['edges']]})
        truth_path=ROOT/config['truth_files'][s['id']]
        truth=read(truth_path)
        data['sources'].append(source_record(truth_path,'H独立可达性真值（仅用于解释）'))
        partitions=[]
        for interval in truth['intervals']:
            for direction,flow in enumerate(interval['flows']):
                if not flow['reachable']:partitions.append({'direction':direction,'start_s':interval['start_s'],'end_s':interval['end_s']})
        data['scenarios'].append({'id':s['id'],'label':LABELS.get(s['id'],s['description']),'seeds':s['seeds'],'duration_s':s['duration_s'],'topology':snapshots,'partitions':partitions,'assumptions':s['assumptions'],'raw_source':name})

def load_analysis(config,data):
    from import_sources import append_engine_indexes
    append_engine_indexes(ROOT,config.get('engine_indexes',[]),data,source_record)
    if config.get('analysis_datasets'):
        from import_analysis import append_datasets
        append_datasets(ROOT,config['analysis_datasets'],data,source_record)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run-id',required=True);args=p.parse_args()
    output=ROOT/'simulation/outputs/D-018'/args.run_id;output.mkdir(parents=True,exist_ok=False)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();config=read(HERE/'sources.json')
    data={'schema':'mid.simulation.viewer.v1','evidence_kind':'software_simulation','scenarios':[],'runs':[],'pairs':[],'plots':{},'sources':[],'exports':[],'planned_seeds':[11,23,37,53,71]}
    load_scenarios(config,data);load_analysis(config,data)
    # Rendering only; all numerical curves require real E2 output.
    if data['runs']:
        from plot_results import generate
        generate(data,output)
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    packed=base64.b64encode(gzip.compress(payload.encode('utf-8'),mtime=0)).decode('ascii')
    html=(HERE/'viewer.template.html').read_text(encoding='utf-8').replace('__DATA__',packed)
    (output/'index.html').write_text(html,encoding='utf-8')
    (output/'viewer-data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    for name in ['index.html','viewer-data.json',*[e['path'] for e in data['exports']]]:
        (HERE/name).write_bytes((output/name).read_bytes())
    profile={'scenarios':len(data['scenarios']),'actual_simulation_runs':len(data['runs']),'actual_simulation_packets':sum(len(r['packets']) for r in data['runs']),'paired_analyses':len(data['pairs']),'planned_runs':30,'planned_packets':7200,'topology_snapshot_resolution_s':.05,'source_note':'H pure environment evaluation for display; no packet simulation or solver'}
    (output/'DATA_PROFILE.json').write_text(json.dumps(profile,indent=2),encoding='utf-8')
    manifest=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
    files=['build_view.py','import_sources.py','import_analysis.py','plot_results.py','sources.json','viewer.template.html']
    manifest.update(template_only=False,task_id='D-018',run_id=args.run_id,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),python_executable=sys.executable,command=sys.argv,output_directory=str(output),status='built_pending_browser_QA',data_and_weights_sha256={s['path']:s['sha256'] for s in data['sources']},dirty_files_sha256={str((HERE/n).relative_to(ROOT)):sha(HERE/n) for n in files if (HERE/n).exists()},limitations=['Software assumptions and actual simulator output only, never RF measurements.','No engine/solver/device runs; upstream sources read only.','If no E2 analysis delivered, performance plots remain empty; raw E1 event replay remains available.','Topology sampled every 0.05 simulated seconds using H pure state function.'])
    (output/'RUN_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(profile,ensure_ascii=False))

if __name__=='__main__':main()
