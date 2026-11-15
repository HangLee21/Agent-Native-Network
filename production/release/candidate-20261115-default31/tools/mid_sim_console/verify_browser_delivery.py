"""Read-only verification of D's one authorized browser run; never sends anything."""
import argparse
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def verify(run_id,prepared,output,binding_evidence=None):
    state=ROOT/'.local/mid/E2-018/service-8766/state.json'
    saved=json.loads(state.read_bytes());run=saved['runs'][run_id];entry=saved['plans'][run['plan_id']]
    plan=entry['plan'];request=entry['request'];expected=json.loads(Path(prepared).read_bytes());payload=expected['message'].encode('utf-8')
    assert payload.hex()==expected['payload_hex'] and len(payload)==expected['utf8_bytes']
    assert request['payload_hex']==plan['payload_hex']==payload.hex()
    assert request['src']==plan['src']=='A' and request['dst']==plan['dst']=='C'
    assert plan['mode']=='hops' and plan['exact_hops']==2 and plan['chain']==list('ABC')
    assert plan['node_set']==list('ABC') and plan['count']==1
    assert request['request_id']==plan['request_id'] and entry['run_id']==run_id
    result=run['result'];assert run['state']==result['status']=='completed'
    assert run['cleanup_confirmed'] and result['all_ports_closed']
    labels=plan['bindings'];assert all(result['stop_confirmed'][labels[n]] for n in 'ABC')
    assert len(result['packets'])==1 and result['destination_unique_received']==1
    packet=result['packets'][0];assert packet['destination_received'] and packet['payload_hex']==payload.hex()
    identity=packet['identity'];assert identity[0]==labels['A'] and identity[3]==labels['C']
    folder=Path(run['output_directory']);log=folder/'native.jsonl';rows=[];ports={}
    for line,raw in enumerate(log.read_bytes().splitlines(),1):
        r=json.loads(raw);e=r.get('event',{})
        if r.get('direction')=='device_rx' and [e.get(k) for k in ['origin','origin_boot','seq','dst']]==identity:
            rows.append((line,e));ports[line]=r.get('port')
    def proof(event,node,next_hop=None):
        hits=[dict(source_line=line,port=ports[line],event=e) for line,e in rows if e.get('event')==event and e['node_id']==labels[node] and (next_hop is None or e.get('next_hop')==labels[next_hop])]
        assert hits,(event,node,next_hop)
        return hits
    evidence=dict(source_admission=proof('tx_queued','A','B'),source_transmit=proof('tx_submit','A','B'),relay_receive=proof('rx_relay','B'),relay_transmit=proof('tx_submit','B','C'),destination=proof('rx_local','C'))
    assert len(evidence['destination'])==1 and evidence['destination'][0]['event']['payload_hex']==payload.hex()
    report=dict(status='passed',run_id=run_id,request_id=request['request_id'],message=expected['message'],payload_hex=payload.hex(),utf8_bytes=len(payload),identity=identity,actual_chain=list('ABC'),evidence=evidence,stop_confirmed=result['stop_confirmed'],all_ports_closed=True,inputs_sha256={str(log):sha(log),str(folder/'result.json'):sha(folder/'result.json'),str(Path(prepared)):sha(Path(prepared))},new_run_requests=0,limitations=['D browser procedure evidence is separate. This is one host controlling three real RF boards, not three physical edge hosts.','No screen-pixel observation or local offline/NVS restart verification inferred.'])
    if binding_evidence:
        path=Path(binding_evidence);by={r['node_id']:r for r in json.loads(path.read_bytes())['updates']}
        for hits in evidence.values():
            for hit in hits:
                expected_binding=by[hit['event']['node_id']]
                assert hit['port']==expected_binding['port'] and hit['event']['boot_id']==expected_binding['boot_id']
        assert identity[1]==by[labels['A']]['boot_id']
        report['binding_evidence']=dict(path=str(path),sha256=sha(path),all_actual_ports_and_logger_boots_matched=True)
        report['inputs_sha256'][str(path)]=sha(path)
    out=Path(output);out.mkdir(parents=True,exist_ok=False);(out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--prepared',required=True);p.add_argument('--output',required=True);p.add_argument('--bindings-evidence');a=p.parse_args();r=verify(a.run_id,a.prepared,a.output,a.bindings_evidence);print(json.dumps(dict(status=r['status'],run_id=r['run_id'],identity=r['identity'],utf8_bytes=r['utf8_bytes'],actual_chain=r['actual_chain']),ensure_ascii=False))
