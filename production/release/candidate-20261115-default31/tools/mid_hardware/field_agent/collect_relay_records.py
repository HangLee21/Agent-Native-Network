"""Read real powered relay RAM journals after a finite switching run; preserve gaps."""
import argparse
import json
from pathlib import Path
import time

from .wire_operator import Operator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--wait',type=float,default=300)
    a=p.parse_args()
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    until=time.monotonic()+a.wait
    while not (a.run/'RESULT.json').exists() and time.monotonic()<until:
        time.sleep(.1)
    if not (a.run/'RESULT.json').exists():
        raise TimeoutError('switch run result not available')
    result=json.loads((a.run/'RESULT.json').read_text())
    operator=Operator()
    targets=['90:da:72:48:a5:cc','90:da:72:48:a6:98']
    snapshots={}
    for node in targets:
        until=time.monotonic()+15
        while not any(r['node_id']==node and r['connected'] for r in operator.client.status()['entries']):
            if time.monotonic()>until:
                break
            time.sleep(.1)
        rows=[]
        running=False
        try:
            status=operator.native(node,'field_status')
            latest=status['reply']['latest_record_cursor']
            running=status['reply']['agent_running']
            if running:
                operator.native(node,'agent',{'running':False})
            cursor=0
            for _ in range(128):
                row=operator.native(node,'record',{'after':cursor})
                raw=row['reply']
                rows.append(row)
                if raw['event']=='record_idle':
                    break
                cursor=raw['record_cursor']
                if cursor>=latest:
                    break
            snapshots[node]=dict(status=status,records=rows,initial_latest_cursor=latest)
        except Exception as exc:
            snapshots[node]=dict(error=repr(exc),records=rows)
        finally:
            if running:
                try:
                    operator.native(node,'agent',{'running':True})
                except Exception as exc:
                    snapshots[node]['resume_error']=repr(exc)
        (out/(node.replace(':','')+'.json')).write_text(json.dumps(snapshots[node],indent=2),encoding='utf-8')
    summary=dict(switch_run=str(a.run),switch_status=result['status'],relays={n:dict(records=len(s['records']),error=s.get('error'),overwritten=s.get('status',{}).get('reply',{}).get('record_overwritten')) for n,s in snapshots.items()},serial_opens=0,transport='formal field.ip.v2 record operation over real PC UDP owner',retention='128 RAM rows per board; overwritten history is not reconstructed')
    (out/'RESULT.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    main()
