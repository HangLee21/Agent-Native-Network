"""Prepare a reviewable state bundle. Does not stop or change the live service."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from server import Console, ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    source=Path(args.snapshot).resolve();out=Path(args.output).resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/E2-018') or out.exists():
        raise ValueError('new E2-018 migration bundle required')
    out.mkdir(parents=True)
    shutil.copyfile(source,out/'original-failed-run.json')
    app=Console(True,out/'state')
    app.restore_run(source)
    active=app.active
    imported=[]
    for folder in sorted((ROOT/'simulation/outputs/H-007').glob('*-console-*')):
        rid=folder.name.rsplit('-console-',1)[-1]
        result_path=folder/'result.json';plan_path=folder/'plan.json'
        if len(rid)!=24 or rid==active or not result_path.is_file():
            continue
        result=json.loads(result_path.read_bytes())
        plan=json.loads(plan_path.read_bytes()) if plan_path.is_file() else None
        pid=plan.get('plan_id') if plan else None
        participants=plan['network_update']['nodes'] if plan else list(result['model']['bindings'].values())
        safe=result.get('all_ports_closed') is True and all(result.get('stop_confirmed',{}).get(n) is True for n in participants)
        record=dict(ok=True,run_id=rid,plan_id=pid,state=result.get('status','failed') if safe else 'cleanup_unconfirmed',
            result=result,events=[],worker_running=False,participants=participants,cleanup_confirmed=safe,
            output_directory=str(folder),stop_event=__import__('threading').Event(),
            migration=dict(source_result=str(result_path),source_plan=str(plan_path) if plan else None,
                           original_service_timestamps_unavailable=True))
        if plan:
            record['plan_snapshot']=plan
            app.plans[pid]=dict(plan=plan,request={k:plan[k] for k in ['src','dst','mode','count']},run_id=rid,created=0)
        app.runs[rid]=record
        imported.append(dict(run_id=rid,plan_id=pid,result_path=str(result_path),result_sha256=hashlib.sha256(result_path.read_bytes()).hexdigest(),plan_path=str(plan_path) if plan else None))
    app.persist()
    report=dict(active_run_id=active,preserved_runs=len(app.runs),preserved_consumed_plans=len(app.plans),
        imports=imported,current_failed_selection=app.runs[active]['selection'],
        source_snapshot_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        state_sha256=hashlib.sha256((out/'state/state.json').read_bytes()).hexdigest(),
        live_service_unchanged=True,automatic_business_resend=False,
        limitation='Old service has no state export API. Unexecuted in-memory plans and full current failed table cannot be recovered via supported APIs. Original process retained for decision; known selection/failed plan ID and all on-disk executed histories preserved.')
    (out/'migration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='imports'}))


if __name__=='__main__':main()
