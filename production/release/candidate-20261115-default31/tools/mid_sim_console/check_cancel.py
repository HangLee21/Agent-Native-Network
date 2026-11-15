"""One isolated real worker cancellation. No production-state mutation or RF."""
import argparse,datetime,json,threading
from pathlib import Path
from unittest.mock import patch
import server

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args();out=Path(a.output).resolve();assert out.is_relative_to(server.ROOT/'simulation/outputs/E2-020') and not out.exists();out.mkdir(parents=True)
    done=threading.Event();started=threading.Event();processes=[]
    class TestApp(server.App):
        def execute(self,rid):
            try:super().execute(rid)
            finally:done.set()
    app=TestApp(out/'isolated-state.json');popen=server.subprocess.Popen
    def launch(*args,**kwargs):
        proc=popen(*args,**kwargs);processes.append(proc);started.set();return proc
    with patch.object(server.subprocess,'Popen',launch):
        job=app.submit(server.get_defaults());assert started.wait(5)
        try:app.submit(server.get_defaults())
        except server.Problem as e:assert e.status==409
        else:raise AssertionError('busy did not reject second run')
        app.cancel(job['run_id']);assert done.wait(15)
    result=app.get(job['run_id']);assert result['state']=='cancelled' and app.active is None and all(p.poll() is not None for p in processes)
    assert app.cancel(job['run_id'])['state']=='cancelled'
    (out/'result.json').write_text(json.dumps(dict(passed=True,run_id=job['run_id'],state='cancelled',worker_exited=True,busy_rejected=True,repeat_cancel_idempotent=True,production_state_untouched=True,hardware_operations=0),indent=2),encoding='utf-8')
    m=json.loads((server.ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E2-020',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),output_directory=str(out),status='passed',exit_code=0,budget=dict(cancelled_workers=1,complete_pair_experiments=0,hardware_operations=0),limitations=['Isolated real child cancelled; not included in two browser example results.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print((out/'result.json').read_text())

if __name__=='__main__':main()
