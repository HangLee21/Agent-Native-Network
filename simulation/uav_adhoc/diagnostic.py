"""One bounded geometry diagnostic with provenance; no network simulation."""
import csv
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from motion import positions, graph, connected_pairs

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'simulation/outputs/E1-030/20261114-01-geometry-diagnostic'


def main():
    OUT.mkdir(parents=True, exist_ok=False)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    config = dict(nodes=30, seconds=20, sample_seconds=1, radius_m=150,
                  speeds_m_s=[5, 25, 50], modes=['formation', 'crossing', 'reorganize'], seed=0,
                  meaning='synthetic geometry diagnostic; no packets or radio')
    manifest = json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    manifest.update(template_only=False, task_id='E1-030', run_id=OUT.name, started_at=start,
                    worktree=str(ROOT), command=[sys.executable, *sys.argv], python_executable=sys.executable,
                    process_id=os.getpid(), output_directory=str(OUT), status='running', config=config,
                    seeds=[0], budget=dict(wall_seconds=120, processes=1),
                    source_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                   for p in [Path(__file__), Path(__file__).with_name('motion.py')]},
                    limitations=['Synthetic geometry only; no Wi-Fi, LoRa, or policy outcomes'])
    def save():
        (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    save()
    rows = []
    try:
        for mode in config['modes']:
            for speed in config['speeds_m_s']:
                prev_pos = prev_edges = None
                for t in range(config['seconds'] + 1):
                    pos = positions(mode, speed, 0, t)
                    edges = graph(pos, config['radius_m'])
                    rel = []
                    if prev_pos:
                        for i in range(30):
                            for j in range(i+1, 30):
                                rel.append(math.hypot((pos[i][0]-prev_pos[i][0])-(pos[j][0]-prev_pos[j][0]),
                                                      (pos[i][1]-prev_pos[i][1])-(pos[j][1]-prev_pos[j][1])))
                    rows.append(dict(mode=mode, speed_m_s=speed, time_s=t, edges=len(edges),
                                     connected_pairs=connected_pairs(30, edges),
                                     edge_changes=None if prev_edges is None else len(edges ^ prev_edges),
                                     mean_pair_relative_speed_m_s=None if not rel else sum(rel)/len(rel)))
                    prev_pos, prev_edges = pos, edges
        assert all(r['edge_changes'] == 0 for r in rows if r['mode'] == 'formation' and r['time_s'] > 0)
        assert any(r['edge_changes'] for r in rows if r['mode'] == 'crossing')
        with (OUT/'geometry.csv').open('w', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        (OUT/'config.json').write_text(json.dumps(config, indent=2)+'\n', encoding='utf-8')
        manifest.update(status='passed', exit_code=0, samples=len(rows))
    except Exception as exc:
        manifest.update(status='failed', exit_code=1, error=repr(exc)); raise
    finally:
        manifest['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat(); save()
    print(json.dumps(dict(status='passed', samples=len(rows), output=str(OUT))))


if __name__ == '__main__':
    main()
