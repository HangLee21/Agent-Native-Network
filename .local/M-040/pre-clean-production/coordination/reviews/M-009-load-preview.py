"""Read 008 task traces and compute offered frame time before wireless results."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'simulation/results/2026-10-26-E1-006-execution/20261026-03-scale'


def read(path):
    if not path.exists():
        path = path.with_name(path.name + '.gz')
    raw = path.read_bytes()
    data = gzip.decompress(raw) if path.suffix == '.gz' else raw
    return json.loads(data), dict(path=path.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(raw).hexdigest())


def main():
    rows, inputs = [], []
    for case in sorted(BASE.glob('seed-*')):
        messages, provenance = read(case / 'messages.json')
        inputs.append(provenance)
        result, provenance = read(case / 'result.json')
        inputs.append(provenance)
        batches = collections.defaultdict(list)
        total_us = 0
        for msg in messages:
            size = len(msg['payload_utf8'].encode('utf-8'))
            assert size == msg['bytes']
            total_us += 20 + 4 * math.ceil((16 + 8 * (size + 64) + 6) / 24)
            batches[math.ceil(msg['generated_at'] * 20_000_000)].append(msg)
        seconds = result['makespan_return'] * 20
        rows.append(dict(case=case.name, agents=result['agents'], tasks=result['tasks'],
                         application_bytes=sum(m['bytes'] for m in messages),
                         messages=len(messages), duration_seconds=seconds,
                         payload_max_bytes=max(m['bytes'] for m in messages),
                         offered_tx_seconds=total_us / 1e6,
                         offered_tx_time_fraction=total_us / 1e6 / seconds,
                         peak_same_us_messages=max(map(len, batches.values())),
                         peak_same_us_sources=max(len({m['source'] for m in v}) for v in batches.values()),
                         multi_source_batches=sum(len({m['source'] for m in v}) > 1 for v in batches.values())))
    output = dict(scope='008 frozen instant traces; offered airtime sum, not measured busy fraction',
                  mapping_seconds_per_unit=20, wireless_result_used=False, cases=rows, inputs=inputs,
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    dest = Path(__file__).with_suffix('.json')
    assert not dest.exists(), 'preserve existing preview'
    dest.write_text(json.dumps(output, indent=2) + '\n', encoding='utf-8', newline='\n')
    for row in rows:
        print(row['case'], 'offered airtime %', round(100 * row['offered_tx_time_fraction'], 4),
              'simultaneous sources', row['peak_same_us_sources'], 'max payload', row['payload_max_bytes'])


if __name__ == '__main__':
    main()
