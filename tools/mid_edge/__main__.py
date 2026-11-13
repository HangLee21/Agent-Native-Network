"""JSONL stdin/stdout application adapter; exactly one local serial owner."""
import argparse
import json
import sys
from .client import Edge

def encode(value):
    if isinstance(value,bytes): return value.hex()
    raise TypeError(type(value).__name__)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--config',help='Local JSON with port,node_id,baud; no remote host or publisher_boot')
    p.add_argument('--port')
    p.add_argument('--node-id')
    p.add_argument('--profile',help='Provision an inactive board once; subsequent starts read its NVS without this flag')
    p.add_argument('--baud',type=int,help='Use actual firmware UART baud (existing boards have also used460800)')
    p.add_argument('--log')
    a=p.parse_args()
    if a.config:
        cfg=json.load(open(a.config,encoding='utf-8'))
        a.port=a.port or cfg['port'];a.node_id=a.node_id or cfg['node_id'];a.baud=a.baud or cfg['baud']
    if not a.port or not a.node_id or not a.baud:p.error('port/node-id/baud required, explicitly or via config')
    with Edge(a.port,a.node_id,a.baud,log=a.log) as edge:
        info=edge.info()
        if a.profile: edge.deploy(json.load(open(a.profile,encoding='utf-8')))
        print(json.dumps(dict(ready=True,info=info)),flush=True)
        for line in sys.stdin:
            try:
                q=json.loads(line);op=q['op']
                if op=='send': result=edge.send(q['dst'],bytes.fromhex(q['payload_hex']))
                elif op=='recv':
                    result=edge.recv(q.get('timeout',30));result.pop('payload');result['delivery_status']='destination_received'
                elif op=='events': result=edge.events(q.get('after',0))
                elif op in ['packet_status','wait_packet']:
                    identity={k:q[k] for k in ['origin','origin_boot','seq','dst']}
                    result=edge.packet_status(**identity) if op=='packet_status' else edge.wait_packet(**identity,timeout=q.get('timeout',10))
                elif op=='neighbors':result=edge.neighbors()
                elif op=='lora_status':result=edge.lora_status()
                elif op=='lora_config':result=edge.lora_config(**{k:v for k,v in q.items() if k!='op'})
                elif op=='lora_events':result=edge.lora_events(q.get('after',0),q.get('wait',0))
                elif op=='neighbor':result=edge.node_status(q['node_id'])
                elif op=='neighbor_probe':result=edge.neighbor_probe(q['node_id'])
                elif op=='discover_config':result=edge.discover_config(q['group'],q['channel'],q.get('autostart',True))
                elif op=='route_config':result=edge.route_config(q['group'],q['channel'],q.get('autostart',True))
                elif op=='routes':result=edge.routes()
                elif op=='route_start':result=edge.route_start()
                elif op=='route_clear':result=edge.route_clear()
                elif op in ['info','stats','stop','local_start','deployment_clear','discover_start','discover_clear']: result=edge.command(op)
                else: raise ValueError('op must be send/recv/events/info/stats/stop')
                print(json.dumps(dict(ok=True,result=result),default=encode),flush=True)
            except Exception as exc:
                print(json.dumps(dict(ok=False,error=str(exc))),flush=True)

if __name__=='__main__': main()
