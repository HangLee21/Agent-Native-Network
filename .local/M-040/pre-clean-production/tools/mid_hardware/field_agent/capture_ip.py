"""Finite read-only capture of the actual E2 PC endpoint; no USB, routes or send retries."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

from tools.field_gateway.client import Client

ROOT=Path(__file__).resolve().parents[3]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8791)
    p.add_argument('--duration',type=float,default=60)
    p.add_argument('--interval',type=float,default=.5)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if not 0<a.duration<=3600 or not .1<=a.interval<=10:
        p.error('duration 0..3600, interval .1..10 required')
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-017'):
        p.error('H-017 output required')
    out.mkdir(parents=True,exist_ok=False)
    client=Client(a.port)
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    until=time.monotonic()+a.duration
    inbox_cursor=event_cursor=0
    instance=None
    count=errors=0
    with (out/'observations.jsonl').open('x',encoding='utf-8') as log:
        while time.monotonic()<until:
            stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            try:
                status=client.status()
                if status.get('serial_access') is not False:
                    raise ValueError('PC endpoint did not declare serial_access=false')
                if instance!=status.get('instance_id'):
                    inbox_cursor=event_cursor=0
                    instance=status.get('instance_id')
                inbox=client.inbox(inbox_cursor)
                events=client.events(event_cursor)
                inbox_cursor=inbox.get('cursor',inbox_cursor)
                event_cursor=events.get('cursor',event_cursor)
                value=dict(captured_at=stamp,status=status,inbox=inbox,events=events)
                count+=1
            except Exception as exc:
                value=dict(captured_at=stamp,error=repr(exc))
                errors+=1
            log.write(json.dumps(value)+'\n')
            log.flush()
            time.sleep(min(a.interval,max(0,until-time.monotonic())))
    result=dict(status='completed_with_errors' if errors else 'completed',snapshots=count,errors=errors,serial_opens=0,business_sends=0,route_installs=0)
    (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    m.update(template_only=False,task_id='H-017',run_id=out.name,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(ROOT),command=[sys.executable,*sys.argv],python_executable=sys.executable,dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},dependency_snapshot='actual E2 tools.field_gateway.client.Client, Python standard library',output_directory=str(out),process_id=__import__('os').getpid(),status=result['status'],exit_code=0 if not errors else 1,budget=dict(duration_s=a.duration,serial_opens=0,business_sends=0),limitations=['HTTP snapshots alone do not establish power supply, zero-USB wiring or RF delivery.','Reads existing endpoint only; no fixture or substitute transport is created.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
    print(json.dumps(result))
    if not count:
        raise SystemExit(1)


if __name__=='__main__':
    main()
