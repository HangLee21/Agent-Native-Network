"""Stop owned A/B discovery and clear only its saved cfg; no business sends."""
import argparse,datetime,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools/mid_hardware/console'))
from tools.mid_edge import Edge
from lease import HardwareLease,reservation
p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--build',required=True);a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-014');out.mkdir(parents=True,exist_ok=False);assert reservation()['owner']=='H014';started=datetime.datetime.now(datetime.timezone.utc).isoformat()
labels=json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_bytes())['labels'];bindings=json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_bytes())['bindings'];rows=[]
with HardwareLease('H014'):
 for label in 'AB':
  b=next(x for x in bindings if x['node_id']==labels[label]);r=dict(label=label,port=b['port']);edge=None
  try:
   edge=Edge(b['port'],labels[label],460800,log=str(out/f'{label}.events.jsonl'));r['before_info']=edge.info();assert r['before_info']['build_id']==a.build;r['stop']=edge.command('stop');r['stats']=edge.command('stats');assert r['stats']['radio'] is False and r['stats']['queue_depth']==0
   if r['before_info'].get('discovery_saved'):r['clear']=edge.command('discover_clear')
   r['after_info']=edge.info();assert r['after_info']['deployment_mode']=='mid' and not r['after_info'].get('discovery_saved') and not r['after_info']['radio'];r['success']=True
  except Exception as exc:r.update(success=False,error=repr(exc))
  finally:
   if edge:edge.close()
   r['closed']=True;rows.append(r);print(json.dumps(r),flush=True)
  if not r['success']:break
(out/'result.json').write_text(json.dumps(rows,indent=2),encoding='utf-8');good=len(rows)==2 and all(x['success']for x in rows);m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes());m.update(template_only=False,task_id='H-014',run_id=out.name,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=os.getpid(),output_directory=str(out),status='passed'if good else'failed',exit_code=0 if good else 1,limitations=['Owned local config cleanup; no business sends, flash or RF probes.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');raise SystemExit(not good)
