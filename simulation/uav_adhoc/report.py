"""Check saved endpoints and produce a small traceable matrix summary."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(sys.argv[1])
rows = json.loads((root / 'summary.json').read_text(encoding='utf-8'))
assert len(rows) == 54
groups = collections.defaultdict(list)
pairs = {}
for row in rows:
    name = f"{row['mode']}-{row['speed_m_s']}-seed{row['seed']}-{row['policy']}"
    offered, received = {}, set()
    with (root / (name + '.jsonl')).open(encoding='utf-8') as stream:
        for line in stream:
            event = json.loads(line)
            key = (event['origin_id'], event['origin_boot_id'], event['seq'])
            if event['event'] == 'offered':
                assert key not in offered
                offered[key] = event['dst_id']
            elif event['event'] == 'destination_received':
                assert key in offered and key not in received
                assert offered[key] == event['dst_id'] and event['bytes_match']
                received.add(key)
    assert (len(offered), len(received)) == (row['offered'], row['delivered'])
    groups[(row['mode'], row['speed_m_s'], row['policy'])].append(row)
    pairs.setdefault((row['mode'], row['speed_m_s'], row['seed']), {})[row['policy']] = row

assert len(pairs) == 27
for pair in pairs.values():
    assert set(pair) == {'baseline', 'local_cache_2s'}
    assert pair['baseline']['offered'] == pair['local_cache_2s']['offered']

summaries = []
for (mode, speed, policy), group in sorted(groups.items()):
    assert len(group) == 3
    offered, delivered = sum(x['offered'] for x in group), sum(x['delivered'] for x in group)
    summaries.append(dict(mode=mode, speed_m_s=speed, policy=policy, seeds=3,
                          offered=offered, delivered=delivered, pdr=delivered/offered,
                          candidate_count=sum(x['candidate_count'] for x in group),
                          no_route_events=sum(x['no_route_events'] for x in group),
                          nd_queue_expired=sum(x['nd_queue_expired'] for x in group),
                          mac_collisions=sum(x['mac_collisions'] for x in group)))
with (root / 'grouped_summary.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=summaries[0].keys())
    writer.writeheader(); writer.writerows(summaries)
fig, ax = plt.subplots(figsize=(7, 4))
for mode in ('formation', 'crossing', 'reorganize'):
    data = sorted((r for r in summaries if r['mode'] == mode and r['policy'] == 'baseline'),
                  key=lambda r: r['speed_m_s'])
    ax.plot([r['speed_m_s'] for r in data], [100*r['pdr'] for r in data], marker='o', label=mode)
ax.set(xlabel='Speed (m/s)', ylabel='Delivered / offered (%)',
       title='Synthetic model, 3 seeds; baseline (candidate identical)')
ax.set_xticks([5, 25, 50]); ax.legend(); ax.grid(alpha=.3); fig.tight_layout()
fig.savefig(root / 'pdr_by_motion.svg'); plt.close(fig)
audit = dict(cases=len(rows), paired_cases=len(pairs), endpoint_accounting='passed',
             pairs_equal_delivery=sum(p['baseline']['delivered'] == p['local_cache_2s']['delivered'] for p in pairs.values()),
             paired_traffic_equal=True, limitations='Model results only; counters are not unique loss attribution.',
             summary_sha256=hashlib.sha256((root/'summary.json').read_bytes()).hexdigest(),
             report_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
(root / 'accounting_audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
print(json.dumps(audit))
