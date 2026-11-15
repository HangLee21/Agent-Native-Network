"""Bounded operations through the actual PC UDP owner's formal maintenance channel."""
import json
from pathlib import Path
import time
import uuid

from tools.field_gateway.client import Client


class Operator:
    def __init__(self,port=8791,control=Path('.local/mid/H-017/maintenance-control.json')):
        self.client=Client(port)
        self.control=Path(control)

    def native(self,node,op,fields=None,timeout=5):
        status=self.client.status()
        row=next(r for r in status['entries'] if r['node_id']==node and r['connected'])
        # Ask for cursor metadata without downloading the full retained journal
        # before every status/record query on a continuously open map.
        cursor=self.client.events(2**53-1)['cursor']
        action=dict(action_id=uuid.uuid4().hex,pc_session=status['pc_session'],entry_id=node,entry_boot=row['boot_id'],op=op,fields=fields or {})
        temp=self.control.with_suffix('.tmp')
        temp.write_text(json.dumps(action),encoding='utf-8')
        temp.replace(self.control)
        end=time.monotonic()+timeout
        expected={'record':{'record','record_idle'},'field_status':{'field_status'},'agent':{'agent'},'suspend':{'ip_suspending'}}[op]
        while time.monotonic()<end:
            events=self.client.events(cursor)
            for item in events['events']:
                event=item.get('raw',{})
                if event.get('type')!='wireless_status':
                    continue
                raw=event.get('raw',{})
                if raw.get('entry_id')==node and raw.get('entry_boot')==row['boot_id'] and raw.get('event') in expected:
                    return dict(action=action,reply=raw,received_at=item['received_at'],cursor=item['cursor'])
            cursor=events['cursor']
            time.sleep(.05)
        raise TimeoutError('maintenance '+op+' response unknown; no automatic command retry')

    def records(self,node,after=0,limit=128):
        rows=[]
        for _ in range(limit):
            item=self.native(node,'record',{'after':after})
            raw=item['reply']
            if raw['event']=='record_idle':
                break
            if raw['record_cursor']<=after:
                raise ValueError('non-increasing native record cursor')
            after=raw['record_cursor']
            rows.append(item)
        return rows
