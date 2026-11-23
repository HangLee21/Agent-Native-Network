"""Loopback client for the H-managed flight gateway."""
import argparse,json,secrets,urllib.request

def call(port,path,body=None):
 base=f'http://127.0.0.1:{port}';req=urllib.request.Request(base+path,None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':base})
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=5) as r:return json.load(r)
def main():
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8780);sub=p.add_subparsers(dest='cmd',required=True);sub.add_parser('status');q=sub.add_parser('send');q.add_argument('--target',required=True);q.add_argument('--boot',type=int,required=True);q.add_argument('--report-seq',type=int,required=True);q.add_argument('--operation',choices=['echo','status'],required=True);q.add_argument('--value',type=int,default=0);q.add_argument('--ttl-ms',type=int,default=30000);q.add_argument('--cmd-id',help='16 lowercase hex digits; reuse the same ID only for identical request')
 a=p.parse_args()
 if a.cmd=='status':value=call(a.port,'/api/v1/lora/topology')
 else:value=call(a.port,'/api/v1/commands',dict(cmd_id=a.cmd_id or secrets.token_hex(8),target=a.target,target_boot=a.boot,report_seq=a.report_seq,operation=a.operation,value=a.value,ttl_ms=a.ttl_ms))
 print(json.dumps(value,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
