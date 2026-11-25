"""One existing local service owns USB. Configuration only when explicitly requested."""
import argparse
import json
from .local_api import LocalClient


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8780)
    p.add_argument('--role',choices=['off','rx','tx'])
    p.add_argument('--period-ms',type=int)
    p.add_argument('--start-on-boot',choices=['true','false'])
    p.add_argument('--send-to');p.add_argument('--text',default='hello from Raspberry Pi')
    a=p.parse_args();board=LocalClient(a.port)
    print(json.dumps(board.lora_status(),ensure_ascii=False))
    fields={}
    if a.role is not None:fields['role']=a.role
    if a.period_ms is not None:fields['report_period_ms']=a.period_ms
    if a.start_on_boot is not None:fields['start_on_boot']=a.start_on_boot=='true'
    if fields:print(json.dumps(board.lora_config(**fields),ensure_ascii=False))
    print(json.dumps(board.lora_events(after=0,wait=0),ensure_ascii=False))
    if a.send_to:print(json.dumps(board.send(a.send_to,a.text.encode()),ensure_ascii=False))


if __name__=='__main__':main()
