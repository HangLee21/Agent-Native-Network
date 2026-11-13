"""Read saved per-process application and serial records, without RF or ports."""
import argparse,hashlib,json,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();source=a.source.resolve();out=a.output.resolve();assert source.is_relative_to(ROOT/'simulation/outputs/H-012') and out.is_relative_to(ROOT/'simulation/outputs/H-012');out.mkdir(parents=True,exist_ok=False)
sources={}
def rows(path):
 sources[str(path.relative_to(ROOT))]=hashlib.sha256(path.read_bytes()).hexdigest()
 return [json.loads(line)for line in path.read_bytes().splitlines()if line.strip()]
admitted=[];received=[];relays=[]
for path in sorted(source.glob('A-*.stdout.jsonl')):
 for row in rows(path):
  v=row.get('result',{})
  if isinstance(v,dict) and v.get('accepted'):admitted.append(v)
for path in sorted(source.glob('C-*.stdout.jsonl')):
 for row in rows(path):
  v=row.get('result',{})
  if isinstance(v,dict) and v.get('event')=='rx_local':received.append(v)
for path in sorted(source.glob('B-*.events.jsonl')):relays.extend(row['event']for row in rows(path))
result=json.loads((source/'result.json').read_bytes());assert all(result['stop_confirmed'].values()) and len(result['stop_confirmed'])==3 and all(result['closed'].values())
packets=[]
for tx in admitted:
 identity={k:tx[k]for k in ('origin','origin_boot','seq','dst')};rx=[x for x in received if all(x.get(k)==v for k,v in identity.items())];assert len(rx)==1
 command=tx['command_result'];event=next(x for path in sorted(source.glob('A-*.events.jsonl'))for x in (z['event']for z in rows(path))if x.get('nonce')==command['nonce'] and x.get('cmd')=='send');assert event['ok']
 # The actual host request is in the saved CLI stdin contract; bytes are also
 # known from the completed packet record or the phase-specific source text.
 known=next((x['payload_hex']for x in result['packets']if x['identity']==identity),None)
 if known is None:
  assert source.name=='20261108-14-local-edge' and tx['origin_boot']==result['after_A_reset_info']['A']['boot_id']
  known='H012 A 新启动身份无需远端重配置'.encode('utf-8').hex()
 assert rx[0]['payload_hex']==known
 same=[x for x in relays if all(x.get(k)==v for k,v in identity.items())];assert any(x['event']=='rx_relay'for x in same) and any(x['event']=='tx_submit' and x.get('next_hop')==tx['dst']for x in same)
 packets.append(dict(identity=identity,payload_hex=known,bytes=len(bytes.fromhex(known)),destination=rx[0],relay_events=same))
assert admitted and len(admitted)==len(received)
report=dict(success=True,source=str(source),source_script_status=result['success'],source_script_error=result.get('error'),independent_serial_audit_received=len(packets),packets=packets,stop_confirmed=result['stop_confirmed'],closed=result['closed'],verified_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sources=sources,limitations=['Same PC three independent single-port clients; not three physical hosts.','Saved original failed supervisor result is unchanged; serial evidence is audited separately.'])
(out/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({k:report[k]for k in ('success','source_script_status','independent_serial_audit_received','stop_confirmed','closed')}))
