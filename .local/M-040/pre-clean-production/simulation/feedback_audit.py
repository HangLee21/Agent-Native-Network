"""Audit whether online high-band feedback is needed by the current policy."""
import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
from simulation.route_pilot import episode, RouteConfig
from simulation.route_robustness import layouts, layout_for, write_csv
from simulation.validate_observation import prepare, patch_data, PATCHES, select_diverse, reconstruct, rmse


def preplan(remote, xy, initial_remote, layout, cfg):
    """Has no high-band truth or future-measurement parameter."""
    _, detail = episode(remote, xy, initial_remote, np.eye(remote.shape[1]),
                        lambda site: remote[site], 2, 'ideal', cfg, layout=layout)
    return detail


def same_routes(a, b):
    return a['nodes'] == b['nodes'] and a['sites'] == b['sites']


def score_plan(detail, initial, measured, test, evaluation, response):
    library = np.vstack([initial, measured[detail['sites']]])
    return rmse(reconstruct(test, library, response), evaluation)


def run(output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output must be empty')
    output.mkdir(parents=True, exist_ok=True)
    cube, response, qc = prepare(Path('data/cuprite/Cuprite_data_R188.mat'))
    dev, _, _ = patch_data(cube, PATCHES['development'])
    dr = dev @ response
    initial = dev[select_diverse(dr, dr.mean(axis=0, keepdims=True), 4)]
    oldpath = Path('simulation/results/2026-10-21-cuprite-geometry-v1/metrics.csv')
    with oldpath.open(encoding='utf8') as stream:
        old = {(r['patch'], r['layout'], float(r['factor']), float(r['noise_std']), int(r['seed'])):r
               for r in csv.DictReader(stream) if r['mode']=='ideal'}
    rows, plans = [], []
    for patch in ('A', 'B', 'C'):
        truth, evaluation, xy = patch_data(cube, PATCHES[patch])
        remote, test = truth @ response, evaluation @ response
        for axis, cut, reverse in layouts():
            name = f'{axis}-{cut}-' + ('reverse' if reverse else 'forward')
            layout = layout_for(xy, axis, cut, reverse)
            for factor in (1.5, 2.5):
                cfg = RouteConfig(factor=factor)
                plan = preplan(remote, xy, initial @ response, layout, cfg)
                plans.append(dict(patch=patch, layout=name, factor=factor, plan=plan))
                for noise in (0., .002):
                    for seed in range(12):
                        measured = np.maximum(truth + np.random.default_rng(seed).normal(0, noise, truth.shape), 0)
                        library, full = episode(remote, xy, initial, response, lambda site: measured[site],
                                                2, 'ideal', cfg, layout=layout)
                        _, compact = episode(remote, xy, initial @ response, np.eye(9),
                                             lambda site: measured[site] @ response,
                                             2, 'ideal', cfg, layout=layout)
                        full_error = rmse(reconstruct(test, library, response), evaluation)
                        prior = old[patch, name, factor, noise, seed]
                        assert abs(full_error-float(prior['rmse'])) < 1e-14
                        assert full['samples'] == int(prior['samples'])
                        for detail in (plan, full, compact):
                            for n in detail['nodes']:
                                assert n['finish_time'] <= n['budget'] + 1e-8
                                np.testing.assert_allclose(n['path'][-1], layout[2][n['node']])
                        static_error = score_plan(plan, initial, measured, test, evaluation, response)
                        compact_error = score_plan(compact, initial, measured, test, evaluation, response)
                        rows.append(dict(patch=patch, layout=name, factor=factor, noise_std=noise, seed=seed,
                                         full_rmse=full_error, compact_rmse=compact_error, preplanned_rmse=static_error,
                                         compact_same_route=same_routes(full, compact),
                                         preplanned_same_route=same_routes(full, plan),
                                         full_samples=full['samples'], preplanned_samples=plan['samples'],
                                         full_vs_preplanned_pct=100*(static_error-full_error)/static_error))
        print('Completed audit', patch, flush=True)
    write_csv(output/'metrics.csv', rows)
    summary = []
    for patch in ('A', 'B', 'C'):
        for factor in (1.5, 2.5):
            for noise in (0., .002):
                group = [r for r in rows if (r['patch'],r['factor'],r['noise_std'])==(patch,factor,noise)]
                vals = [np.mean([r['full_vs_preplanned_pct'] for r in group if r['layout']==name])
                        for name in sorted({r['layout'] for r in group})]
                summary.append(dict(patch=patch,factor=factor,noise_std=noise,records=len(group),
                                    compact_same_routes=sum(r['compact_same_route'] for r in group),
                                    preplanned_same_routes=sum(r['preplanned_same_route'] for r in group),
                                    mean_pct=float(np.mean(vals)), min_layout_pct=float(min(vals)),
                                    max_layout_pct=float(max(vals)),positive_layouts=sum(v>1e-8 for v in vals)))
    write_csv(output/'summary.csv',summary)
    (output/'preplans.json.gz').write_bytes(gzip.compress(json.dumps(plans).encode(),mtime=0))
    sources = ['simulation/feedback_audit.py','simulation/route_pilot.py','simulation/route_robustness.py',
               'simulation/validate_observation.py','simulation/FEEDBACK_AUDIT_PROTOCOL.md']
    metadata = dict(qc=qc,records=len(rows),preplans=len(plans),matched_previous=len(rows),
                    compact_same_routes=sum(r['compact_same_route'] for r in rows),
                    source_sha256={s:hashlib.sha256(Path(s).read_bytes()).hexdigest() for s in sources},
                    max_compact_rmse_delta=max(abs(r['full_rmse']-r['compact_rmse']) for r in rows),
                    scope='Deterministic timings; prior-only offline planning; no wireless simulation.')
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
