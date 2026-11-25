"""Small runnable application using the same single-board API as the GUI."""
import argparse
import json
from .client import Edge

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['send','recv','deploy']);p.add_argument('--port',required=True);p.add_argument('--node-id',required=True);p.add_argument('--baud',required=True,type=int);p.add_argument('--dst');p.add_argument('--text');p.add_argument('--hex');p.add_argument('--profile');p.add_argument('--timeout',type=float,default=30);p.add_argument('--log');a=p.parse_args()
    with Edge(a.port,a.node_id,a.baud,log=a.log) as edge:
        edge.info()  # actual board identity is checked by the single reader
        if a.action=='send':
            if not a.dst or (a.text is None)==(a.hex is None):p.error('send requires dst and exactly one of text/hex')
            payload=a.text.encode('utf-8') if a.text is not None else bytes.fromhex(a.hex)
            print(json.dumps(edge.send(a.dst,payload),ensure_ascii=False))
        elif a.action=='recv':
            item=edge.recv(a.timeout);payload=item.pop('payload');item['payload_hex']=payload.hex();print(json.dumps(item,ensure_ascii=False))
        else:
            if not a.profile:p.error('deploy requires profile')
            print(json.dumps(edge.deploy(json.load(open(a.profile,encoding='utf-8'))),ensure_ascii=False))

if __name__=='__main__':main()
