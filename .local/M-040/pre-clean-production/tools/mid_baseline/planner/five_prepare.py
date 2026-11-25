"""Five real nodes, two flows per scenario. Offline original SOCP, no serial."""
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):
    os.environ[key]='2'
import argparse,json,hashlib,itertools,datetime,sys
from pathlib import Path
from planner import solve
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bridge'))
from bridge import mac,pack


def prepare(bindings,out,provenance):
    labels='ABCDE';nodes=[bindings[x] for x in labels]
    if len({mac(n) for n in nodes})!=5:
        raise ValueError('five distinct real MACs required')
    out.mkdir(parents=True,exist_ok=False)
    scenarios=[(a+b,(a,b),None) for a,b in itertools.combinations(labels,2)]
    scenarios += [('chain_ABCDE',('A','E'),'ABCDE'),('chain_BADEC',('B','C'),'BADEC')]
    records=[]
    for name,pair,chain in scenarios:
        folder=out/name;folder.mkdir()
        allowed=set()
        if chain:
            for a,b in zip(chain,chain[1:]):
                allowed.add((labels.index(a),labels.index(b)))
                allowed.add((labels.index(b),labels.index(a)))
        mean=[[0 if i==j or (chain and (i,j) not in allowed) else .8 for j in range(5)] for i in range(5)]
        var=[[0 if i==j else (1 if chain and (i,j) not in allowed else .0001) for j in range(5)] for i in range(5)]
        a,b=pair
        problem=dict(nodes=nodes,flows=[dict(src=bindings[a],dst=bindings[b],rate=.05,qos=.9),dict(src=bindings[b],dst=bindings[a],rate=.05,qos=.9)],mean=mean,variance=var,
            channel_provenance='Explicit hypothetical dimensionless input; no RF calibration/QoS evidence. '+('Logical zero-capacity non-chain edges, finite variance penalty; NOT physical RF obstruction. Original SOCP must produce exact chain, no post-solve probability edits.' if chain else 'All model links available; do not infer actual packet path from online node count.'))
        (folder/'input.json').write_text(json.dumps(problem,indent=2)+'\n')
        answer=solve(problem)
        if answer['status']!='optimal':
            (folder/'failure.json').write_text(json.dumps(answer,indent=2));raise ValueError(name+': not optimal')
        update=answer['update'];expected=[]
        if chain:
            for route in (chain,chain[::-1]):
                src,dst=bindings[route[0]],bindings[route[-1]]
                for executor,gateway in zip(route,route[1:]):
                    row=next(r for r in update['routes'] if (r['node'],r['src'],r['dst'])==(bindings[executor],src,dst))
                    if len(row['gateways'])!=1 or row['gateways'][0]['node']!=bindings[gateway]:
                        (folder/'unexpected_solution.json').write_text(json.dumps(answer,indent=2));raise ValueError(name+': solver did not produce exact chain; rejected')
                expected.append([bindings[x] for x in route])
        (folder/'solution.json').write_text(json.dumps(answer,indent=2)+'\n')
        (folder/'network_update.json').write_text(json.dumps(update,indent=2)+'\n')
        frame=pack(update,nodes[0],1,1)
        assert len(frame)==160
        (folder/'OFFLINE_ONLY_boot1_seq1.bin').write_bytes(frame)
        records.append(dict(case=name,flow_labels=list(pair),flow_count=2,packets_per_direction=5,frame_bytes=len(frame),slack=answer['slack'],expected_chains=expected,files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}))
    index=dict(schema='mid.five.assets.v1',created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),bindings=bindings,binding_provenance=provenance,cases=records,case_count=12,total_source_packets=120,
        notes=['12 new scenarios, no repeat of first pair; all pairs 100 packets plus chains20','OFFLINE boot1/seq1 bytes MUST NOT deploy. H reads actual A boot and uses bridge.pack with fresh monotonic sequence','Original N5/K2/500ms remains unchanged. H/E2 materialize actual events/stop; no E1 physical access','Expected chains are solver outputs checked at each executor, NOT measured paths. Four-hop evidence needs every intermediate RX/TX and endpoint identity','No ACK, new routing algorithm, or probability post-edit'])
    (out/'INDEX.json').write_text(json.dumps(index,indent=2)+'\n');return index


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--labels',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    source=Path(a.labels);doc=json.loads(source.read_text(encoding='utf-8'));bindings={k:doc.get('bindings',doc.get('labels'))[k] for k in 'ABCDE'}
    prepare(bindings,Path(a.output),dict(path=str(source.resolve()),sha256=hashlib.sha256(source.read_bytes()).hexdigest()))


if __name__=='__main__':main()
