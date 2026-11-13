"""One H015 process, one frozen Edge client, one local serial owner. No routing."""
import argparse,hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def main():
 p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--node-id',required=True);p.add_argument('--build',required=True);p.add_argument('--edge-source',type=Path,required=True);p.add_argument('--edge-sha256',required=True);p.add_argument('--log',type=Path,required=True);a=p.parse_args();source=a.edge_source.resolve();assert source.is_relative_to(ROOT/'.local/mid/H-015') and hashlib.sha256(source.read_bytes()).hexdigest()==a.edge_sha256
 spec=importlib.util.spec_from_file_location('h015_frozen_edge',source);module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
 allowed={'info':set(),'stats':set(),'neighbors':set(),'routes':set(),'stop':set(),'route_config':{'group','channel','autostart'},'route_start':set(),'route_clear':set(),'link_filter':{'allow','clear'}}
 with module.Edge(a.port,a.node_id,460800,log=str(a.log))as edge:
  info=edge.identify();assert info['build_id']==a.build;print(json.dumps(dict(ready=True,info=info,port=a.port,edge_source_sha256=a.edge_sha256)),flush=True)
  for line in sys.stdin:
   try:
    q=json.loads(line);op=q.pop('op')
    if op=='send':
     assert set(q)=={'dst','payload_hex'};result=edge.send(q['dst'],bytes.fromhex(q['payload_hex']))
    elif op=='recv':
     assert set(q)<= {'timeout'};result=edge.recv(q.get('timeout',3));payload=result.pop('payload');assert result['payload_hex']==payload.hex();result['application_payload_hex']=payload.hex()
    elif op=='events':
     assert set(q)<= {'after'};result=edge.events(q.get('after',0))
    elif op in allowed:
     assert set(q)<=allowed[op];result=edge.command(op,**q)
    else:raise ValueError('unsupported local operation; route installation/host forwarding are not implemented')
    print(json.dumps(dict(ok=True,result=result)),flush=True)
   except Exception as exc:print(json.dumps(dict(ok=False,error=repr(exc))),flush=True)
if __name__=='__main__':main()
