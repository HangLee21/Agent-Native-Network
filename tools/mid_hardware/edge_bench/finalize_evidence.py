"""Post-hoc provenance supplements; never changes raw results or old manifests."""
import argparse,datetime,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--task',choices=('H-012','H-013'),required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();base=ROOT/'simulation/outputs'/a.task;out=a.output.resolve();assert out.is_relative_to(base);out.mkdir(parents=True,exist_ok=False);now=datetime.datetime.now(datetime.timezone.utc).isoformat();template=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_bytes())
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
index=[]
for directory in sorted(base.iterdir()):
 if not directory.is_dir() or directory==out:continue
 files={str(x.relative_to(ROOT)):sha(x)for x in sorted(directory.rglob('*'))if x.is_file() and not x.name.startswith('RUN_MANIFEST') and x.suffix!='.exe'}
 result_path=directory/'result.json';result=json.loads(result_path.read_bytes())if result_path.exists()else None
 values=result if isinstance(result,list)else [result]if isinstance(result,dict)else []
 status='recorded';exit_code=None
 if values and all('success'in x for x in values):status='passed'if all(x['success']for x in values)else'failed';exit_code=0 if status=='passed'else 1
 m=dict(template);m.update(template_only=False,task_id=a.task,run_id=directory.name,worktree=str(ROOT),output_directory=str(directory),python_executable=sys.executable,started_at=next((x['started_at']for x in values if x.get('started_at')),None),finished_at=next((x['finished_at']for x in reversed(values)if x.get('finished_at')),None),data_and_weights_sha256=files,status=status,exit_code=exit_code,provenance_recorded_at=now,provenance_note='Post-hoc supplement from unchanged saved evidence; absent command/time/PID fields remain null.',limitations=['No additional device operation performed while writing this supplement.','Original failed supervisor/USB recovery results are retained; later audits do not overwrite their status.'],review_reference=f'coordination/tasks/{a.task}.md')
 target=directory/('RUN_MANIFEST_SUPPLEMENT.json'if (directory/'RUN_MANIFEST.json').exists()else'RUN_MANIFEST.json')
 if not target.exists():target.write_text(json.dumps(m,indent=2),encoding='utf-8')
 index.append(dict(directory=str(directory.relative_to(ROOT)),status=status,manifest=str(target.relative_to(ROOT)),sources=files))
sources={str(x.relative_to(ROOT)):sha(x)for x in sorted((ROOT/'tools/mid_hardware/edge_bench').glob('*.py'))}
if a.task=='H-013':sources.update({str(x.relative_to(ROOT)):sha(x)for x in (ROOT/'tools/mid_hardware/console').glob('*.py')})
(out/'INDEX.json').write_text(json.dumps(dict(task_id=a.task,recorded_at=now,runs=index,tool_sources=sources),indent=2),encoding='utf-8')
m=dict(template);m.update(template_only=False,task_id=a.task,run_id=out.name,started_at=now,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),output_directory=str(out),command=sys.argv,python_executable=sys.executable,dirty_files_sha256=sources,data_and_weights_sha256={'INDEX.json':sha(out/'INDEX.json')},status='completed',exit_code=0,limitations=['Evidence indexing only; no additional RF, flash, serial or simulation.'],review_reference=f'coordination/tasks/{a.task}.md');(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(dict(task_id=a.task,indexed_runs=len(index),output=str(out))))
