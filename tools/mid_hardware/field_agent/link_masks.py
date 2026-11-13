"""Explicit reversible ESP-NOW hearability fixture; never supplies board route vectors."""
import argparse
import json
from pathlib import Path

from tools.mid_edge.client import Edge
from tools.mid_hardware.console.lease import HardwareLease


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--flash-result',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--clear',action='store_true')
    a=p.parse_args()
    data=json.loads(a.flash_result.read_text())
    boards={b['label']:b['result'] for b in data['boards'] if b['result']['success']}
    peers=dict(A=['B'],B=['A','C'],C=['B','E'],D=['E'],E=['D','C'])
    out=a.output.resolve()
    root=Path(__file__).resolve().parents[3]
    if not out.is_relative_to(root/'simulation/outputs/H-017'):
        p.error('H-017 output required')
    out.mkdir(parents=True,exist_ok=False)
    results=[]
    try:
        with HardwareLease('H017'):
            for label in 'ABCDE':
                b=boards[label]
                with Edge(b['port'],b['mac'],460800) as edge:
                    info=edge.identify()
                    if info['build_id']!=data['target']:
                        raise RuntimeError('identity/build changed; no filter command')
                    fields={'clear':True} if a.clear else {'allow':[boards[n]['mac'] for n in peers[label]]}
                    response=edge.command('link_filter',**fields)
                    results.append(dict(label=label,node_id=b['mac'],port=b['port'],before_info=info,filter=fields,response=response))
    finally:
        (out/'RESULT.json').write_text(json.dumps(dict(action='clear' if a.clear else 'apply',results=results,all_ports_closed=True,evidence_kind='controlled_per_frame_RF_hearability_not_natural_coverage',route_vectors_supplied=False),indent=2),encoding='utf-8')
    print(json.dumps(dict(action='clear' if a.clear else 'apply',boards=len(results),ports_closed=True,route_vectors_supplied=False)))


if __name__=='__main__':
    main()
