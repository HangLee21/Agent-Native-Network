"""Finite read-only capture for H's actual wireless switching runs."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from .client import Client


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port', type=int, default=8791)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--duration', type=float, default=90)
    p.add_argument('--interval', type=float, default=.5)
    a = p.parse_args(argv)
    if not 0 < a.duration <= 3600 or not .1 <= a.interval <= 10:
        p.error('finite duration 0..3600 and interval .1..10 required')
    a.output.mkdir(parents=True, exist_ok=False)
    client = Client(a.port)
    cursor = inbox_cursor = 0
    instance = None
    maximum = 0
    received = set()
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic()+a.duration
    errors, changes, rows = [], [], 0
    previous = None
    try:
        with (a.output/'observations.jsonl').open('x', encoding='utf-8') as stream:
            while time.monotonic() < deadline:
                try:
                    status = client.status()
                    if instance is not None and status['instance_id'] != instance:
                        cursor = 0
                    instance = status['instance_id']
                    events, inbox = client.events(cursor), client.inbox(inbox_cursor)
                    cursor, inbox_cursor = events['cursor'], inbox['cursor']
                    online = sorted(e['node_id'] for e in status['entries'] if e['connected'])
                    maximum = max(maximum, len(online))
                    if online != previous:
                        changes.append(dict(elapsed_s=a.duration-max(0,deadline-time.monotonic()), online=online))
                        previous = online
                    for record in inbox['records']:
                        received.add((record['origin'],record['origin_boot'],record['transaction_id']))
                    row = dict(observed_at=datetime.now(timezone.utc).isoformat(), status=status,
                               events=events, inbox=inbox)
                    stream.write(json.dumps(row, ensure_ascii=False)+'\n')
                    stream.flush()
                    rows += 1
                except Exception as exc:
                    errors.append(dict(at=datetime.now(timezone.utc).isoformat(), error=str(exc)))
                    stream.write(json.dumps(dict(api_error=errors[-1]))+'\n')
                    stream.flush()
                time.sleep(min(a.interval,max(0,deadline-time.monotonic())))
    except KeyboardInterrupt:
        pass
    summary = dict(started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                   rows=rows, max_simultaneous_entries=maximum, entry_changes=changes,
                   unique_pc_receives=len(received), api_errors=errors,
                   business_sends_by_capture=0, serial_access=False,
                   evidence_scope='local_API_observations; power/WiFi/RF conditions must be recorded independently by H')
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)


if __name__ == '__main__':main()
