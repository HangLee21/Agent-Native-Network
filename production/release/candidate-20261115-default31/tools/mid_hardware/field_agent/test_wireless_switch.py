"""Finite real PC/board bidirectional test with remote IP suspension and selected lease loss."""
import argparse
import json
from pathlib import Path
import time
import uuid
import subprocess

from .wire_operator import Operator


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--remote',default='90:da:72:48:a4:e0')
    p.add_argument('--suspend-ms',type=int,default=120000)
    p.add_argument('--reuse-suspended-from',type=Path,help='prior owned run whose suspend ACK was lost but target is now observably offline')
    p.add_argument('--preexcluded-remote',action='store_true')
    p.add_argument('--base-withheld',action='append',default=[])
    p.add_argument('--entry-ip-suspend-ms',type=int,default=0)
    p.add_argument('--wait-remote-online',type=float,default=0)
    p.add_argument('--withdraw-upstream',action='store_true',help='withdraw the actually observed reverse-direction entry in its own round')
    a=p.parse_args()
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    operator=Operator()
    client=operator.client
    control=Path('.local/mid/H-017/formal-lease-control.json')
    history=[]
    def log(stage,**data):
        row=dict(stage=stage,host_time=time.time(),**data)
        history.append(row)
        with (out/'timeline.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
    def snapshot(name):
        value=client.status()
        (out/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
        return value
    def wait_entries(predicate,timeout=20):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            value=client.status()
            if predicate(value['entries']):
                return value
            time.sleep(.2)
        raise TimeoutError('entry condition; no new business sent')
    def send_new(phase):
        for attempt in range(1,4):
            payload=('H017 '+phase+' '+str(attempt)+' '+uuid.uuid4().hex).encode()
            request_id='h017-'+phase+'-'+uuid.uuid4().hex
            receipt=client.send(a.remote,payload,request_id)
            until=time.monotonic()+12
            while time.monotonic()<until:
                receipt=client.request(request_id)
                if receipt['record']['destination_received']:
                    break
                time.sleep(.1)
            record=receipt['record']
            log('PC_downlink',phase=phase,new_application_attempt=attempt,request_id=request_id,payload_hex=payload.hex(),record=record)
            if not record['destination_received']:
                continue  # Preserve unknown request; next measurement has a NEW ID and NEW bytes.
            if record['request']['payload_hex']!=payload.hex():
                raise RuntimeError('payload identity mismatch')
            if record['entry']['node_id']==a.remote or record['entry']['hops']<1:
                raise RuntimeError('remote gained IP direct path; cannot call this ESP-NOW transfer')
            return record
        raise RuntimeError('three distinct new measurements unconfirmed; no old-packet retry')
    def fresh_inbox_cursor():
        cursor=0
        for _ in range(16):
            page=client.inbox(cursor)
            if page['cursor']==cursor:
                return cursor
            cursor=page['cursor']
        raise RuntimeError('inbox pagination did not reach current end')
    def up_new(after,forbidden=(),timeout=90,not_before=0):
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            inbox=client.inbox(after)
            for row in inbox['records']:
                if row['origin']==a.remote and row['origin_boot']==result['remote_boot'] and row['received_at']>=not_before and row['entry_id'] not in set(forbidden)|{a.remote}:
                    log('remote_uplink_PC_received',record=row)
                    return row,inbox['cursor']
            after=inbox['cursor']
            time.sleep(.15)
        raise TimeoutError('no new remote-origin PC inbox via eligible alternative entry')
    result=dict(status='running',physical_supply='awaiting user confirmation; no serial business or control during this test',serial_opens=0,RF_link_filters=0,mechanisms=['formal remote IP suspend, radio/generator retained','selected application PC lease renewal withheld, WLAN not disconnected'])
    try:
        if a.wait_remote_online:
            log('waiting_for_remote_prior_suspend_to_finish',timeout_s=a.wait_remote_online)
            wait_entries(lambda rows:any(r['node_id']==a.remote and r['connected'] for r in rows) and sum(r['connected'] for r in rows)>=3,timeout=a.wait_remote_online)
        before=snapshot('INITIAL')
        if sum(r['connected'] for r in before['entries'])<(2 if a.preexcluded_remote or a.reuse_suspended_from else 3):
            raise RuntimeError('need remote plus at least two independent current entries')
        result['remote_boot']=next(r['boot_id'] for r in before['entries'] if r['node_id']==a.remote)
        cursor=fresh_inbox_cursor()
        if a.preexcluded_remote:
            if any(r['connected'] for r in before['entries'] if r['node_id']==a.remote):
                raise RuntimeError('remote still has a current PC lease')
            result['remote_status_before']=None
            suspended=dict(preexcluded_PC_lease=True,no_new_suspend_sent=True,base_withheld=a.base_withheld)
        elif a.reuse_suspended_from:
            prior=json.loads((a.reuse_suspended_from/'RESULT.json').read_text())
            if prior['remote_boot']!=result['remote_boot'] or any(r['connected'] for r in before['entries'] if r['node_id']==a.remote):
                raise RuntimeError('previous suspend is not confirmed by the same boot being IP-offline')
            result['remote_status_before']=prior['remote_status_before']
            suspended=dict(reused_observed_IP_loss=True,prior_run=str(a.reuse_suspended_from),ACK_unknown=True,no_new_suspend_sent=True)
        else:
            result['remote_status_before']=operator.native(a.remote,'field_status')
            try:
                suspended=operator.native(a.remote,'suspend',{'duration_ms':a.suspend_ms})
            except TimeoutError as exc:
                # Immediate STA disconnect can lose its final UDP acknowledgement.
                # Only continue if subsequent actual lease loss is observed below.
                suspended=dict(ACK_unknown=True,error=str(exc),no_retry=True)
        result['remote_suspend']=suspended
        log('remote_IP_suspend_observation',node=a.remote,duration_ms=a.suspend_ms,observation=suspended)
        wait_entries(lambda rows:all(not r['connected'] for r in rows if r['node_id']==a.remote) and sum(r['connected'] for r in rows)>=2)
        snapshot('REMOTE_NO_PC_ENTRY')
        before_phase=time.time()
        first=send_new('before')
        first_up,cursor=up_new(cursor,not_before=before_phase)
        result.update(before_down=first,before_up=first_up)
        lost=first_up['entry_id'] if a.withdraw_upstream else first['entry']['node_id']
        result['withdrawal_basis']='actual_upstream_entry' if a.withdraw_upstream else 'actual_downstream_entry'
        if a.entry_ip_suspend_ms:
            def association(name):
                command=['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File','tools/mid_hardware/field_agent/hotspot_clients.ps1','-FlashResult','simulation/outputs/H-017/20261109-13-five-flash/RESULT.json']
                value=json.loads(subprocess.check_output(command,text=True,encoding='utf-8-sig'))
                (out/(name+'.json')).write_text(json.dumps(value,indent=2),encoding='utf-8')
                return value
            result['entry_status_before_suspend']=operator.native(lost,'field_status')
            result['OS_association_before']=association('ASSOCIATIONS_BEFORE_ENTRY_LOSS')
            try:
                result['entry_IP_suspend']=operator.native(lost,'suspend',{'duration_ms':a.entry_ip_suspend_ms})
            except TimeoutError as exc:
                result['entry_IP_suspend']=dict(ACK_unknown=True,error=str(exc),no_retry=True)
            result['entry_IP_fault_duration_ms']=a.entry_ip_suspend_ms
            log('selected_entry_native_IP_suspend',node=lost,upstream_before=first_up['entry_id'],RF_disconnected=False,suspend=result['entry_IP_suspend'])
        else:
            temp=control.with_suffix('.tmp')
            temp.write_text(json.dumps({'withhold_lease_nodes':sorted(set(a.base_withheld)|{lost})}),encoding='utf-8')
            temp.replace(control)
            log('selected_entry_PC_lease_withheld',node=lost,upstream_before=first_up['entry_id'],RF_disconnected=False)
        wait_entries(lambda rows:all(not r['connected'] for r in rows if r['node_id'] in [lost,a.remote]) and any(r['connected'] for r in rows))
        snapshot('SELECTED_ENTRY_EXPIRED')
        if a.entry_ip_suspend_ms:
            result['OS_association_after']=association('ASSOCIATIONS_AFTER_ENTRY_LOSS')
            if any(r['node_id']==lost and r['associated'] for r in result['OS_association_after']['project_boards']):
                raise RuntimeError('Windows still reports selected entry associated; cannot claim actual AP disassociation')
        after_phase=time.time()
        after=send_new('after')
        after_up,cursor=up_new(cursor,forbidden=[lost],not_before=after_phase)
        if after['entry']['node_id']==lost:
            raise RuntimeError('new downlink still used expired entry')
        result.update(withdrawn_entry=lost,after_down=after,after_up=after_up,one_round_covers_both_directions=(first_up['entry_id']==lost and first['entry']['node_id']==lost))
        if a.entry_ip_suspend_ms:
            result['OS_association_after_delivery']=association('ASSOCIATIONS_AFTER_BIDIRECTIONAL_DELIVERY')
        result['status']='passed_real_bidirectional_first_round'
    except Exception as exc:
        result.update(status='failed',error=repr(exc))
        log('failure',error=repr(exc))
        raise
    finally:
        temp=control.with_suffix('.tmp')
        temp.write_text('{"withhold_lease_nodes":[]}',encoding='utf-8')
        temp.replace(control)
        result['lease_fault_cleared']=True
        result['remote_IP_resumes_automatically_after_ms']=a.suspend_ms
        result['final_PC_status']=client.status()
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        (out/'EVENTS.json').write_text(json.dumps(client.events(0),indent=2),encoding='utf-8')
        print(json.dumps(dict(status=result['status'],output=str(out),lease_fault_cleared=True)),flush=True)


if __name__=='__main__':
    main()
