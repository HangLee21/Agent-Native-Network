"""Audit saved local application/serial captures. No device or network imports."""
import argparse
import hashlib
import json
from pathlib import Path

KEYS=('origin','origin_boot','seq','dst')
A='90:da:72:48:a4:f8';B='90:da:72:48:a5:cc';C='90:da:72:48:a4:e0'

def audit(source,output,headless=False):
    source=Path(source);hashes={}
    def read(path):
        hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return [(line,json.loads(v)) for line,v in enumerate(path.read_bytes().splitlines(),1) if v.strip()]
    def rows(role,kind):
        return [(str(p),line,v) for p in sorted(source.glob(role+'-*.'+kind+'.jsonl')) for line,v in read(p)]
    result_path=source/'result.json';summary=json.loads(result_path.read_bytes());hashes[str(result_path)]=hashlib.sha256(result_path.read_bytes()).hexdigest()
    tx=[(p,l,v['result']) for p,l,v in rows('A','stdout') if isinstance(v.get('result'),dict) and v['result'].get('accepted')]
    rx=[(p,l,v['result']) for p,l,v in rows('C','stdout') if isinstance(v.get('result'),dict) and v['result'].get('event')=='rx_local']
    logs={role:[(p,l,v['event']) for p,l,v in rows(role,'events')] for role in 'ABC'}
    expected_texts=['H012 无屏端实际收件'] if headless else ['H012 独立本地应用 A 经 B 到 C','H012 B 单独重启后原本地配置转发','H012 A 新启动身份无需远端重配置']
    assert len(tx)==len(rx)==len(expected_texts)
    assert all(summary['stop_confirmed'][r] and summary['closed'][r] for r in 'ABC')
    assert summary['physical_hosts_verified']==1 and summary['host_forwarding'] is False
    packets=[]
    for (path,line,sent),text in zip(tx,expected_texts):
        identity={k:sent[k] for k in KEYS};assert identity['origin']==A and identity['dst']==C
        matches=[(p,l,e) for p,l,e in rx if all(e.get(k)==v for k,v in identity.items())];assert len(matches)==1
        rp,rl,received=matches[0];assert received['payload_hex']==text.encode().hex()
        assert sent['delivery_status']=='destination_unconfirmed' and received['delivery_status']=='destination_received'
        stages={}
        for role,event,next_hop in [('A','tx_queued',B),('A','tx_submit',B),('B','rx_relay',None),('B','tx_submit',C),('C','rx_local',None)]:
            found=[dict(path=p,line=l,event=e) for p,l,e in logs[role] if e.get('event')==event and e.get('node_id')==dict(A=A,B=B,C=C)[role] and all(e.get(k)==v for k,v in identity.items()) and (next_hop is None or e.get('next_hop')==next_hop)]
            assert found,(role,event,identity);stages[role+'_'+event]=found
        nonce=sent['command_result']['nonce'];assert any(e.get('nonce')==nonce and e.get('cmd')=='send' and e.get('ok') for _,_,e in logs['A'])
        packets.append(dict(identity=identity,text=text,payload_hex=received['payload_hex'],application_send=dict(path=path,line=line),application_receive=dict(path=rp,line=rl),stages=stages))
    commands=summary['child_commands']
    for name,command in commands.items():
        assert command.count('--port')==1 and command.count('--node-id')==1 and '--baud' in command
        assert command[command.index('--baud')+1]=='460800'
    reset_info={}
    if not headless:
        for role in ['A','B']:
            p=source/(role+'-2.stdout.jsonl');ready=read(p)[0][1]['info']
            assert ready['deployment_mode']=='offline_table' and ready['mode']=='active' and ready['deployment_saved'] and ready['autostart']
            initial=read(source/(role+'-1.stdout.jsonl'))[0][1]['info'];assert initial['boot_id']!=ready['boot_id']
            assert '--profile' not in commands[role+'-2']
            assert not any(e.get('cmd') in ['deploy','start','config'] for _,_,e in logs[role] if e.get('boot_id')==ready['boot_id'])
            reset=source/(role+'-reset/result.json');r=json.loads(reset.read_bytes());hashes[str(reset)]=hashlib.sha256(reset.read_bytes()).hexdigest();assert r['success'] and r['closed'] and r['flash_writes']==0
            reset_info[role]=dict(before_boot=initial['boot_id'],after_boot=ready['boot_id'],nvs_profile=ready['profile_id'],no_remote_rebind=True)
        assert packets[0]['identity']['origin_boot']==packets[1]['identity']['origin_boot']!=packets[2]['identity']['origin_boot']
        assert summary['success'] is False  # preserved supervisor snapshot race, not erased
    else:
        c=read(source/'C-1.stdout.jsonl')[0][1]['info'];assert c['display_enabled'] is False and c['display_api']==2
        assert summary['success'] is True and summary['initial_info']['C']['display_enabled'] is False
        for p in source.glob('*.requests.jsonl'):read(p)
    report=dict(status='passed',source=str(source),original_supervisor_success=summary['success'],original_error=summary.get('error'),packet_count=len(packets),packets=packets,resets=reset_info,headless_destination=headless,stop_confirmed=summary['stop_confirmed'],closed=summary['closed'],source_sha256=hashes,commands=commands,new_device_operations=0,limitations=['Same Windows PC, three independent single-board processes and real RF boards; no three physical hosts or Linux deployment verified.','H14 third payload expectation is the phase text in accept_local.py, with matching sender identity and C raw bytes; original supervisor failure retained.','No physical screen-pixel observation inferred.'])
    out=Path(output);out.mkdir(parents=True,exist_ok=False);(out/'checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--headless',action='store_true');a=p.parse_args();r=audit(a.source,a.output,a.headless);print(json.dumps(dict(status=r['status'],packet_count=r['packet_count'],resets=r['resets'],headless=r['headless_destination']),ensure_ascii=False))
