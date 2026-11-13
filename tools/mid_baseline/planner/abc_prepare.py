"""Prepare actual-MAC three-node SOCP cases; offline only, no serial access."""
import argparse
import hashlib
import json
from pathlib import Path
import os
for name in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS'):
    os.environ[name] = '2'
from planner import solve
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bridge'))
from bridge import mac, pack


def cases(nodes):
    """Explicit synthetic channel assumptions, not measured calibration."""
    result = {}
    for name, s, d in [('AB', 0, 1), ('AC', 0, 2), ('BC', 1, 2), ('AC_controlled_two_hop', 0, 2)]:
        mean = [[0 if i == j else .8 for j in range(3)] for i in range(3)]
        var = [[0 if i == j else .0001 for j in range(3)] for i in range(3)]
        controlled = name.endswith('two_hop')
        if controlled:
            # Zero modeled direct-edge capacity. A finite uncertainty penalty also
            # prevents cost-free nonphysical alpha on the zero-mean edge. We never
            # edit a solver result to force a route; reject if thresholded output uses it.
            mean[0][2] = mean[2][0] = 0
            var[0][2] = var[2][0] = 1
        result[name] = dict(nodes=nodes, flows=[dict(src=nodes[s], dst=nodes[d], rate=.05, qos=.9),
                                              dict(src=nodes[d], dst=nodes[s], rate=.05, qos=.9)],
                            mean=mean, variance=var,
                            channel_provenance=('Explicit assumed dimensionless model, not calibrated RF. ' +
                            ('CONTROLLED LOGICAL zero-capacity A-C edge with finite variance penalty; verify actual solver output excludes A-C; not RF obstruction/coverage evidence.'
                             if controlled else 'All direct modeled links available; no claim that a selected path is multihop.')))
    return result


def prepare(nodes, out, binding_source, binding_sha):
    if len(nodes) != 3 or len({mac(n) for n in nodes}) != 3:
        raise ValueError('three distinct real unicast MACs required')
    out.mkdir(parents=True, exist_ok=False)
    records = []
    for name, problem in cases(nodes).items():
        folder = out / name
        folder.mkdir()
        (folder/'input.json').write_text(json.dumps(problem, indent=2)+'\n')
        answer = solve(problem)
        if answer['status'] != 'optimal':
            (folder/'failure.json').write_text(json.dumps(answer, indent=2))
            raise ValueError(name + ': SOCP not optimal')
        update = answer['update']
        if name.endswith('two_hop'):
            for row in update['routes']:
                if row['node'] in (nodes[0], nodes[2]):
                    other = nodes[2] if row['node'] == nodes[0] else nodes[0]
                    if any(g['node'] == other and g['weight'] > 0 for g in row['gateways']):
                        raise ValueError('controlled solve retained direct edge; no post-solve masking allowed')
            for src, dst in ((nodes[0], nodes[2]), (nodes[2], nodes[0])):
                for executor, gateway in ((src, nodes[1]), (nodes[1], dst)):
                    row = next(r for r in update['routes'] if (r['node'],r['src'],r['dst']) == (executor,src,dst))
                    if len(row['gateways']) != 1 or row['gateways'][0]['node'] != gateway:
                        raise ValueError('controlled solve did not yield the specified two-hop chain')
        (folder/'solution.json').write_text(json.dumps(answer, indent=2)+'\n')
        (folder/'network_update.json').write_text(json.dumps(update, indent=2)+'\n')
        # Encoding check only: boot1/seq1 is never a deployable publisher binding.
        frame = pack(update,nodes[0],1,1)
        (folder/'OFFLINE_ONLY_config_boot1_seq1.bin').write_bytes(frame)
        records.append(dict(case=name, frame_bytes=len(frame), slack=answer['slack'],
                            files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()},
                            deployment='H must use actual current A boot and new monotonic sequence with bridge.py'))
    index=dict(schema='mid.ABC.inputs.v1', nodes=nodes, binding_source=binding_source,
               binding_sha256=binding_sha, cases=records,
               firmware='unchanged package-01; third label ? with full MAC is intentional',
               scope='OFFLINE inputs/solutions only; E2/C must freeze finite scenario; H alone deploys. No RF/QoS/coverage measurement.')
    (out/'INDEX.json').write_text(json.dumps(index,indent=2)+'\n')
    return index


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--labels',required=True,help='H-frozen JSON with bindings A/B/C actual MACs')
    p.add_argument('--expected-sha256',required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    source=Path(a.labels);digest=hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != a.expected_sha256:
        raise ValueError('binding source hash mismatch')
    labels=json.loads(source.read_text(encoding='utf-8'))['bindings']
    prepare([labels[k] for k in ('A','B','C')],Path(a.output),str(source.resolve()),digest)


if __name__=='__main__':
    main()
