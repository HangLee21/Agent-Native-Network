"""H fault wrapper around actual E2 PC serve; selectively withholds IP lease renewal.

Control JSON: {"withhold_lease_nodes":[canonical entry MACs]}. Empty list restores.
No WLAN change, RF control, business replay, routing override or administrator rights.
"""
import argparse
import json
from pathlib import Path
import re
import threading
import time

from tools.field_gateway import protocol
from tools.field_gateway.wireless import WirelessLink

MAC=re.compile(r'^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$')


class LeaseFaultLink(WirelessLink):
    def __init__(self,*args,fault_file,fault_log,maintenance_file=None,**kwargs):
        self.fault_file=Path(fault_file)
        self.fault_lock=threading.RLock()
        self.address_nodes={}
        self.withheld=set()
        self.fault_revision=None
        self.fault_counter=0
        self.maintenance_file=Path(maintenance_file) if maintenance_file else None
        self.maintenance_seen=set()
        self.maintenance_last=None
        self.maintenance_thread=None
        self.fault_log=Path(fault_log).open('x',encoding='utf-8')
        try:
            self.refresh_fault()
            super().__init__(*args,**kwargs)
        except BaseException:
            self.fault_log.close()
            raise

    def attach(self,callback,pc_id,pc_boot):
        super().attach(callback,pc_id,pc_boot)
        if self.maintenance_file:
            self.maintenance_thread=threading.Thread(target=self.maintenance_loop,name='H017-native-maintenance',daemon=True)
            self.maintenance_thread.start()

    def maintenance_loop(self):
        while not self.stop.wait(.05):
            if not self.maintenance_file.exists():
                continue
            try:
                value=json.loads(self.maintenance_file.read_text(encoding='utf-8'))
                action=value.get('action_id')
                if not self.claim_maintenance(action,value.get('op')):
                    continue
                if value.get('pc_session')!=self.pc_boot or not MAC.fullmatch(value.get('entry_id','')):
                    raise ValueError('maintenance session or entry mismatch')
                op,fields=value.get('op'),value.get('fields',{})
                if op=='field_status':
                    valid=fields=={}
                elif op=='record':
                    valid=set(fields)=={'after'} and type(fields['after']) is int and 0<=fields['after']<=2**53-1
                elif op=='agent':
                    valid=set(fields)=={'running'} and type(fields['running']) is bool
                elif op=='suspend':
                    valid=set(fields)=={'duration_ms'} and type(fields['duration_ms']) is int and 1000<=fields['duration_ms']<=300000
                else:
                    valid=False
                if not valid:
                    raise ValueError('unsupported bounded maintenance operation')
                row=next((r for r in self.registry.status()['entries'] if r['node_id']==value['entry_id'] and r['boot_id']==value.get('entry_boot') and r['connected']),None)
                if row is None:
                    raise ValueError('maintenance target has no matching current lease')
                self._send(row['address'],op,entry_boot=row['boot_id'],**fields)
                record=dict(event='maintenance_submitted',action_id=action,entry_id=row['node_id'],entry_boot=row['boot_id'],pc_session=self.pc_boot,op=op,fields=fields,host_time=time.time(),UDP_submit_only=True)
            except Exception as exc:
                record=dict(event='maintenance_error',action_id=locals().get('action'),host_time=time.time(),error=repr(exc),no_automatic_retry=True)
            with self.fault_lock:
                self.fault_log.write(json.dumps(record)+'\n')
                self.fault_log.flush()

    def claim_maintenance(self,action,op):
        """Claim each posted action once; continuous read queries do not fill write ledger."""
        if not isinstance(action,str) or not 1<=len(action)<=80 or action==self.maintenance_last or action in self.maintenance_seen:
            return False
        # Claim BEFORE validation/submission, so an unchanged file is never retried.
        self.maintenance_last=action
        if op in ('agent','suspend'):
            if len(self.maintenance_seen)>=4096:
                raise RuntimeError('maintenance write action capacity reached')
            self.maintenance_seen.add(action)
        return True

    def refresh_fault(self):
        with self.fault_lock:
            if not self.fault_file.exists():
                raw=b'{"withhold_lease_nodes":[]}'
            else:
                raw=self.fault_file.read_bytes()
            if raw==self.fault_revision:
                return
            value=json.loads(raw)
            nodes=value.get('withhold_lease_nodes')
            if set(value)!={'withhold_lease_nodes'} or not isinstance(nodes,list) or len(nodes)>5 or any(not isinstance(n,str) or not MAC.fullmatch(n) for n in nodes):
                raise ValueError('fault control requires at most five explicit canonical entry MACs')
            self.withheld=set(nodes)
            self.fault_revision=raw
            self.fault_log.write(json.dumps(dict(event='fault_control',host_time=time.time(),withhold_lease_nodes=sorted(self.withheld),mechanism='application_IP_lease_renewal_only',WLAN_changed=False,RF_commands=0))+'\n')
            self.fault_log.flush()

    def handle(self,raw,address):
        value=protocol.decode(raw)
        if value['event']=='register' and value['pc_id']==self.pc_id:
            with self.fault_lock:
                self.address_nodes[tuple(address)]=value['entry_id']
        return super().handle(raw,address)

    def _send(self,address,op,**fields):
        if op=='lease':
            self.refresh_fault()
            with self.fault_lock:
                node=self.address_nodes.get(tuple(address))
                if node in self.withheld:
                    self.fault_counter+=1
                    self.fault_log.write(json.dumps(dict(event='lease_renewal_withheld',host_time=time.time(),node_id=node,entry_boot=fields.get('entry_boot'),address=list(address),business_submitted=False))+'\n')
                    self.fault_log.flush()
                    return
        return super()._send(address,op,**fields)

    def status(self):
        result=super().status()
        with self.fault_lock:
            result['H017_fault']=dict(mechanism='application_IP_lease_renewal_only',withhold_lease_nodes=sorted(self.withheld),withheld_count=self.fault_counter,WLAN_changed=False,RF_commands=0)
        return result

    def close(self):
        try:
            return super().close()
        finally:
            if self.maintenance_thread:
                self.maintenance_thread.join(2)
            with self.fault_lock:
                if not self.fault_log.closed:
                    self.fault_log.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,add_help=False)
    p.add_argument('--fault-file',type=Path,required=True)
    p.add_argument('--fault-log',type=Path,required=True)
    p.add_argument('--maintenance-file',type=Path)
    options,remaining=p.parse_known_args(argv)
    if not remaining or remaining[0]!='serve':
        p.error('forward the actual E2 serve command after fault options')
    import tools.field_gateway.wireless as wireless
    from tools.field_gateway.__main__ import main as actual_main
    original=wireless.WirelessLink
    class OperatorLink(LeaseFaultLink):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,fault_file=options.fault_file,fault_log=options.fault_log,maintenance_file=options.maintenance_file,**kwargs)
    wireless.WirelessLink=OperatorLink
    try:
        return actual_main(remaining)
    finally:
        wireless.WirelessLink=original


if __name__=='__main__':
    main()
