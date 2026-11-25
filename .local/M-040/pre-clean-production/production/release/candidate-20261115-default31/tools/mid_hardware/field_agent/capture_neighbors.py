"""Finite passive capture of actual PC native reports and the current studio graph."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.request

from tools.field_gateway.client import Client

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--duration',type=float,default=150)
    p.add_argument('--port',type=int,default=8791)
    p.add_argument('--studio-port',type=int,default=8794)
    a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-018') or not 0<a.duration<=600:p.error('new H-018 output and duration0..600 required')
    out.mkdir(parents=True,exist_ok=False)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    client=Client(a.port);cursor=0;instance=None;reports=[];errors=[];samples=0
    until=time.monotonic()+a.duration
    with (out/'snapshots.jsonl').open('x',encoding='utf-8') as journal:
        while time.monotonic()<until:
            try:
                status=client.status()
                if instance!=status['instance_id']:
                    instance=status['instance_id'];cursor=client.events(2**53-1)['cursor']
                events=client.events(cursor);cursor=events['cursor']
                pc_map=client.call('/api/v1/state')
                opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
                with opener.open(f'http://127.0.0.1:{a.studio_port}/api/v1/state',timeout=3) as r:studio=json.load(r)
                stamp=time.time()
                for event in events['events']:
                    if event['kind']=='wireless_report':
                        reports.append(event)
                        with (out/'native_reports.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
                journal.write(json.dumps(dict(captured_at=stamp,pc_status=status,events=events,pc_map=pc_map,studio=studio))+'\n');journal.flush();samples+=1
            except Exception as exc:errors.append(dict(at=time.time(),error=repr(exc)))
            time.sleep(min(1,max(0,until-time.monotonic())))
    summary=dict(samples=samples,native_reports=len(reports),errors=errors,serial_opens=0,business_sends=0,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (out/'RESULT.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text());manifest.update(template_only=False,task_id='H-018',run_id=out.name,started_at=started,finished_at=summary['finished_at'],worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,process_id=__import__('os').getpid(),output_directory=str(out),status='capture_saved',dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},limitations=['Actual IP observations; partial native rows and unknown transport ages remain explicit.','No serial telemetry, synthetic input or host business sends.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8');print(json.dumps(summary))


if __name__=='__main__':main()
