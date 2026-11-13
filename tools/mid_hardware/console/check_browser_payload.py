"""Read saved browser/device evidence; never opens serial or sends packets."""
import argparse,datetime,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--hardware',type=Path,required=True);p.add_argument('--browser',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--expected-c-port');a=p.parse_args();out=a.output.resolve();assert out.is_relative_to(ROOT/'simulation/outputs/H-013');out.mkdir(parents=True,exist_ok=False);hardware=a.hardware.resolve();browser=a.browser.resolve();sources={}
def read(path):
 data=path.read_bytes();sources[str(path.relative_to(ROOT))]=hashlib.sha256(data).hexdigest();return json.loads(data)
r=read(hardware/'result.json');plan=read(hardware/'plan.json');before=read(browser/'BEFORE.json');after=read(browser/'AFTER.json');run=read(browser/'BROWSER_RUN.json');expected=after['message'].encode('utf-8').hex();assert before['message']==after['message']
assert r['status']=='completed' and r['requested']==1 and r['destination_unique_received']==1 and r['all_ports_closed'] and all(r['stop_confirmed'].values())
assert plan['src']=='A' and plan['dst']=='C' and plan['exact_hops']==2 and plan['node_set']==list('ABC') and plan['payload_hex']==expected and plan['request_id']
path=hardware/'native.jsonl';sources[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest();rows=[json.loads(line)for line in path.read_bytes().splitlines()];sends=[x for x in rows if x.get('direction')=='host_tx' and x.get('command',{}).get('cmd')=='send'];assert len(sends)==1 and sends[0]['command']['payload_hex']==expected
packet=r['packets'][0];identity=dict(zip(('origin','origin_boot','seq','dst'),packet['identity']));events=[x for x in rows if x.get('direction')=='device_rx' and all(x['event'].get(k)==v for k,v in identity.items())];labels=plan['bindings'];e=[x['event']for x in events]
for kind,node,next_hop in [('tx_queued','A',None),('tx_submit','A','B'),('rx_relay','B',None),('tx_submit','B','C'),('rx_local','C',None)]:assert any(x['event']==kind and x['node_id']==labels[node] and (next_hop is None or x.get('next_hop')==labels[next_hop])for x in e),(kind,node)
rx=[x for x in e if x['event']=='rx_local' and x['node_id']==labels['C']];assert len(rx)==1 and rx[0]['payload_hex']==expected
ports={k:sorted({x['port']for x in rows if x.get('direction')=='device_rx' and x['event'].get('node_id')==mac})for k,mac in labels.items()};assert all(len(x)==1 for x in ports.values())
if a.expected_c_port:assert ports['C']==[a.expected_c_port]
audit=dict(success=True,verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),request_id=plan['request_id'],plan_id=run['plan_id'],run_id=run['run_id'],text=after['message'],payload_hex=expected,payload_bytes=len(bytes.fromhex(expected)),identity=identity,actual_chain=list('ABC'),actual_events=events,stop_confirmed=r['stop_confirmed'],all_ports_closed=True,sources=sources,limitations=['Browser actions performed by D; H only audits saved original evidence.','Real RF bench on one PC; not physical multi-host deployment or pixel observation.','Original H007 manifests remain unchanged; H013 records this new interpretation.'])
audit['actual_ports']=ports
(out/'result.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:audit[k]for k in ('success','payload_bytes','identity','actual_chain','actual_ports','all_ports_closed')}))
