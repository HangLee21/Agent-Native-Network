"""Finite, read-only observation of native-IP mutual-neighbor refresh."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[3]
PAIR = {'90:da:72:48:a5:cc', '90:da:72:48:a4:e0'}


def get(port, path):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{port}{path}', timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--duration', type=float, default=30)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT/'simulation/outputs/H-018') or not 9 <= args.duration <= 60:
        parser.error('New H-018 output and 9..60 seconds required')
    output.mkdir(exist_ok=False)
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    points, errors = [], []
    end = time.monotonic()+args.duration
    with (output/'snapshots.jsonl').open('x', encoding='utf-8') as stream:
        while time.monotonic() < end:
            begin = time.monotonic()
            try:
                pc = get(8791, '/api/v1/state')
                studio = get(8794, '/api/v1/state')
                pair = [edge for edge in studio['edges'] if edge['from'] in PAIR and edge['to'] in PAIR]
                selected = [dict(direction=edge['from']+'>'+edge['to'], mutual=edge.get('mutual_confirmed'),
                    remaining_ms=edge.get('mutual_valid_for_ms'), proof=edge.get('direct_evidence')) for edge in pair]
                mutual = {tuple(sorted((edge['from'], edge['to']))) for edge in studio['edges'] if edge.get('mutual_confirmed')}
                point = dict(monotonic=time.monotonic(), utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    pair=selected, pair_mutual=len(pair)==2 and all(edge.get('mutual_confirmed') for edge in pair),
                    mutual_pairs=len(mutual), nodes=len(studio['nodes']),
                    pc_pair_mutual=sum(bool(e.get('mutual_confirmed')) for e in pc['edges'] if e['from'] in PAIR and e['to'] in PAIR)==2)
                points.append(point)
                stream.write(json.dumps(dict(point=point, pc=pc, studio=studio))+'\n')
                stream.flush()
            except Exception as exc:
                errors.append(dict(monotonic=time.monotonic(), error=repr(exc)))
            time.sleep(max(0, min(end-time.monotonic(), 1-(time.monotonic()-begin))))
    ages = [row['proof']['confirmation_age_upper_bound_ms'] for point in points for row in point['pair']
            if row.get('proof') and row['proof'].get('confirmation_age_upper_bound_ms') is not None]
    queries = {}
    for point in points:
        for row in point['pair']:
            if row.get('proof'):
                queries.setdefault(row['direction'], set()).add(row['proof']['query_id'])
    result = dict(samples=len(points), duration_observed_s=points[-1]['monotonic']-points[0]['monotonic'] if len(points)>1 else 0,
        errors=errors, pair_all_mutual=bool(points) and all(point['pair_mutual'] for point in points),
        pair_not_mutual_samples=[point for point in points if not point['pair_mutual']],
        max_confirmation_age_upper_bound_ms=max(ages) if ages else None,
        queries={key:sorted(values) for key,values in queries.items()},
        graph_mutual_pairs=[point['mutual_pairs'] for point in points],
        serial_opens=0, host_business_sends=0, ui_actions=0,
        finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
    (output/'RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    manifest=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text())
    manifest.update(template_only=False, task_id='H-018', run_id=output.name, started_at=started,
        finished_at=result['finished_at'], worktree=str(ROOT), command=[sys.executable,*sys.argv],
        python_executable=sys.executable, process_id=os.getpid(), output_directory=str(output),
        dirty_files_sha256={str(Path(__file__).relative_to(ROOT)):hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        status='passive_observation_saved', limitations=['Actual HTTP observations of native-IP requests; no host business or UI actions.',
            'Mutual connectivity evidence and RF frame ages remain separate; this is not a PDR or latency benchmark.'])
    (output/'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
