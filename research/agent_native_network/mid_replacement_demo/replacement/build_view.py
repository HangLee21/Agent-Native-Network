"""Package existing E2 analysis into a standalone viewer; immutable inputs."""
from pathlib import Path
import argparse, json, hashlib, datetime, sys
from plot_service import generate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id',required=True)
    args=parser.parse_args()
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    output=ROOT/'simulation/outputs/D-016'/args.run_id
    output.mkdir(parents=True,exist_ok=False)
    sources=read(HERE/'sources.json')
    source_paths=[ROOT/sources['capture_index'],ROOT/sources['capture_summary'],*[ROOT/s for s in sources['analyses']]]
    data={'schema':'mid.replacement.viewer.v1','capture_index':read(source_paths[0]),'capture_summary':read(source_paths[1]),'runs':[],'plots':{},'sources':[]}
    for path in source_paths:
        data['sources'].append({'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':sha(path)})
    for path in source_paths[2:]:
        run=read(path)
        assert run['evidence_kind']=='hardware_measured'
        starts=[a for a in run['annotations'] if a['name']=='run_start']
        assert len(starts)==1
        run['display_t0_ns']=starts[0]['host_monotonic_ns']
        run['display_analysis_path']=str(path.relative_to(ROOT)).replace('\\','/')
        run['display_analysis_sha256']=sha(path)
        data['runs'].append(run)
    generate(data,output)
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    html=(HERE/'viewer.template.html').read_text(encoding='utf-8').replace('__DATA__',payload)
    (output/'index.html').write_text(html,encoding='utf-8')
    (output/'viewer-data.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    # Publish files only from this new, completed build directory.
    for name in ['index.html','viewer-data.json','paired-service.pdf','paired-service.svg','paired-service.png']:
        (HERE/name).write_bytes((output/name).read_bytes())
    profile={'runs':len(data['runs']),'packets':sum(len(r['packets']) for r in data['runs']),'per_second_rows':sum(len(r['seconds']) for r in data['runs']),'null_goodput_windows':sum(s['goodput_bps'] is None for r in data['runs'] for s in r['seconds']),'pairs_with_E2':sorted({r['pair_id'] for r in data['runs']}),'H_complete_pairs':data['capture_summary']['complete_pairs'],'E2_complete_pairs':[p for p in range(1,6) if len([r for r in data['runs'] if r['pair_id']==p and r.get('metrics_valid',not r['issues'])])==2]}
    (output/'DATA_PROFILE.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest=read(ROOT/'coordination/templates/RUN_MANIFEST.json')
    manifest.update(template_only=False,task_id='D-016',run_id=args.run_id,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),python_executable=sys.executable,command=sys.argv,output_directory=str(output),status='built_pending_browser_QA',data_and_weights_sha256={s['path']:s['sha256'] for s in data['sources']},dirty_files_sha256={str((HERE/n).relative_to(ROOT)):sha(HERE/n) for n in ['build_view.py','plot_service.py','viewer.template.html','sources.json']},limitations=['Uses existing E2 analysis only; no analyzer rerun or serial operations.','H capture overview is separate from E2 endpoint metrics.','Pair05 remains pending E2 until explicitly added to sources.json.','Unknown/null windows remain missing, never zero-filled.'])
    (output/'RUN_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(profile,ensure_ascii=False))

if __name__=='__main__':main()
