"""Finite real-board integration capture. Explicit recent identities required; no flashing or mode changes."""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import urllib.request
import uuid

from tools.mid_hardware.console.lease import HardwareLease, status
from tools.mobile_node.edge import MobileEdge
from tools.mobile_node.traffic import generate_payload
from .server import ROOT
from .demo import request


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--identities',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--port',type=int,default=8790)
    p.add_argument('--duration',type=float,default=80)
    p.add_argument('--gps',choices=['none','fake'],default='none')
    args=p.parse_args()
    if args.duration<40:
        p.error('at least 40 seconds required')
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'simulation/outputs/H-016'):
        p.error('H-016 output directory required')
    out.mkdir(parents=True,exist_ok=False)
    identity=json.loads(args.identities.read_text(encoding='utf-8'))
    boards=identity['boards']
    if len(boards)<2 or len({b['node_id'] for b in boards})!=len(boards):
        p.error('two or more distinct verified observers required')
    children=[]
    logs=[]
    stages=[]
    def note(kind,**data):
        row=dict(kind=kind,host_ms=int(time.time()*1000),**data)
        stages.append(row)
        with (out/'lifecycle.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')
        print(json.dumps(row),flush=True)
    def spawn(name,command):
        stdout=(out/(name+'.stdout.log')).open('x',encoding='utf-8')
        stderr=(out/(name+'.stderr.log')).open('x',encoding='utf-8')
        logs.extend((stdout,stderr))
        proc=subprocess.Popen([sys.executable,'-X','utf8',*command],cwd=ROOT,stdout=stdout,stderr=stderr,env=dict(os.environ,PYTHONUNBUFFERED='1'))
        children.append(dict(name=name,process=proc,command=[sys.executable,'-X','utf8',*command]))
        note('started',name=name,pid=proc.pid)
        return proc
    def wait_file(path,proc):
        until=time.monotonic()+15
        while time.monotonic()<until:
            if path.exists():
                return json.loads(path.read_text(encoding='utf-8'))
            if proc.poll() is not None:
                raise RuntimeError('child failed before readiness: '+str(path))
            threading.Event().wait(.05)
        raise TimeoutError('readiness: '+str(path))
    def finish(proc,stopfile=None,timeout=6):
        if stopfile:
            stopfile.touch()
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            return proc.wait(timeout=4)
    base='http://127.0.0.1:'+str(args.port)
    gate_stop=out/'gateway-stop'
    result=dict(status='running',evidence_kind='single_Windows_PC_multiple_real_ESP_NOW_boards',gps_source='simulated' if args.gps=='fake' else 'unavailable',rf_rssi_source='unavailable_on_existing_firmware',boards=len(boards),physical_Pis=0,flash_writes=0,radio_or_config_commands=0,lease_before=status())
    source_paths=list((ROOT/'tools/mobile_gateway').glob('*.py'))+list((ROOT/'tools/mobile_node').glob('*.py'))+[ROOT/'tools/mid_edge/client.py',ROOT/'tools/mid_sim_console/local_edge.py']
    inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    (out/'INPUT_HASHES.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    owners=[]
    gateway=None
    started_ms=int(time.time()*1000)
    lease=HardwareLease('H016')
    lease_held=False
    try:
        lease.__enter__()
        lease_held=True
        with contextlib.nullcontext():
            command=['-m','tools.mobile_gateway','--port',str(args.port),'--output',str(out/'gateway'),'--stop-file',str(gate_stop)]
            gateway=spawn('gateway',command)
            meta=wait_file(out/'gateway/gateway.json',gateway)
            empty=request(base,'/api/v1/state')
            assert not empty['nodes'] and not empty['edges']
            (out/'EMPTY_STATE.json').write_text(json.dumps(empty,indent=2),encoding='utf-8')
            note('map_ready',url=base+'/',initial_nodes=0,physical_capture=True)
            for board in boards:
                tag=board['label'] or board['node_id'].replace(':','')
                owner_stop=out/('owner-'+tag+'-stop')
                owner=spawn('owner-'+tag,['-m','tools.mobile_gateway.owned_edge','--serial-port',board['port'],'--node-id',board['node_id'],'--build',board['info']['build_id'],'--boot',str(board['info']['boot_id']),'--output',str(out/('owner-'+tag)),'--stop-file',str(owner_stop)])
                ready=wait_file(out/('owner-'+tag)/'ready.json',owner)
                owners.append(dict(board=board,tag=tag,process=owner,stop=owner_stop,port=ready['port']))
            # Every participant has its own real serial owner, observer and business process.
            for current in owners:
                tag=current['tag']
                duration=args.duration+2
                common=['--edge-port',str(current['port']),'--duration',str(duration),'--seed','16030']
                spawn('observer-'+tag,['-m','tools.mobile_node','node',*common,'--state',str(out/('observer-'+tag)),'--gateway',base,'--label',tag,'--gps',args.gps,'--report-s','1','--sample-s','1','--no-position-injection'])
                traffic=common+['--state',str(out/('agent-'+tag)),'--interval-min','1','--interval-max','2','--min-bytes','20','--max-bytes','160']
                for other in owners:
                    if other is not current:
                        traffic+=['--dest',other['board']['node_id']]
                spawn('agent-'+tag,['-m','tools.mobile_node','agent',*traffic])
            epoch=time.monotonic()
            off=args.duration*.38
            resume=args.duration*.60
            sent=False
            disconnected=False
            connected=False
            checkpoints={5:'early',args.duration*.30:'before-offline',args.duration*.75:'reconnected',args.duration-1:'final'}
            while time.monotonic()-epoch<args.duration:
                t=time.monotonic()-epoch
                if not disconnected and t>=off:
                    result['gateway_off_ms']=int(time.time()*1000)
                    code=finish(gateway,gate_stop)
                    assert code==0
                    result['gateway_off_ms']=int(time.time()*1000)
                    note('gateway_off',pid=gateway.pid,exit_code=code,owners_still_running=all(o['process'].poll() is None for o in owners))
                    disconnected=True
                if disconnected and not sent and t>=off+3:
                    # Reuse E2 application API and generator. No host route or control is sent.
                    import random
                    source,target=owners[0],owners[-1]
                    payload=generate_payload(random.Random(16030),67,67)
                    edge=MobileEdge(source['port'])
                    request_id='h016-offline-'+uuid.uuid4().hex
                    before=int(time.time()*1000)
                    receipt=edge.send(target['board']['node_id'],payload,request_id=request_id)
                    result['offline_packet']=dict(source=source['tag'],target=target['tag'],request_id=request_id,payload_hex=payload.hex(),input_ms=before,response=receipt,gateway_process_exited=gateway.poll() is not None)
                    note('new_business_while_gateway_off',**result['offline_packet'])
                    sent=True
                if disconnected and not connected and t>=resume:
                    gate_stop.unlink()
                    gateway=spawn('gateway-reconnected',command+['--resume'])
                    until=time.monotonic()+15
                    while time.monotonic()<until:
                        try:
                            health=request(base,'/health')
                            if health['gateway_instance']!=meta['gateway_instance']:
                                break
                        except OSError:
                            pass
                        threading.Event().wait(.1)
                    else:
                        raise TimeoutError('gateway reconnect')
                    result['gateway_reconnected_ms']=int(time.time()*1000)
                    note('gateway_reconnected',instance=health['gateway_instance'])
                    connected=True
                for when,name in list(checkpoints.items()):
                    if t>=when:
                        if not disconnected or connected:
                            (out/('STATE-'+name+'.json')).write_text(json.dumps(request(base,'/api/v1/state'),indent=2),encoding='utf-8')
                            (out/('TIMELINE-'+name+'.json')).write_text(json.dumps(request(base,'/api/v1/timeline'),indent=2),encoding='utf-8')
                        del checkpoints[when]
                for child in children:
                    if child['name'] not in ('gateway',) and child['process'].poll() is not None:
                        raise RuntimeError('unexpected child exit: '+child['name'])
                threading.Event().wait(.1)
            result['status']='completed'
            result['radio_final']={}
            for owner in owners:
                result['radio_final'][owner['tag']]=MobileEdge(owner['port']).status()['info']
    except Exception as exc:
        result.update(status='failed',error=repr(exc))
        raise
    finally:
        # Stop our observers/agents and owners, retaining each board's existing active radio mode.
        for child in reversed(children):
            if child['name'].startswith(('observer-','agent-')):
                finish(child['process'],timeout=5)
        for owner in owners:
            finish(owner['process'],owner['stop'])
        if gateway and gateway.poll() is None:
            finish(gateway,gate_stop)
        for child in children:
            if child['process'].poll() is None:
                finish(child['process'],timeout=.1)
        for f in logs:
            f.close()
        if lease_held:
            lease.__exit__(None,None,None)
        result['processes']=[dict(name=c['name'],pid=c['process'].pid,exit_code=c['process'].poll(),command=c['command']) for c in children]
        result['all_children_stopped']=all(c['process'].poll() is not None for c in children)
        result['lease_after']=status()
        result['finished_ms']=int(time.time()*1000)
        result['sources_unchanged_during_run']=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==sha for p,sha in inputs.items())
        (out/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        manifest=dict(task_id='H-016',run_id=out.name,started_at=started_ms,finished_at=result['finished_ms'],timezone='Asia/Shanghai',worktree=str(ROOT),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty_files_sha256=inputs,command=sys.argv,python_executable=sys.executable,dependency_snapshot='existing ESP-IDF Python environment, pyserial; E2 node/agent/local owner',upstream_commit=None,data_and_weights_sha256={str(args.identities):hashlib.sha256(args.identities.read_bytes()).hexdigest()},config_file=str(args.identities),seeds=[16030],budget=dict(duration_s=args.duration),output_directory=str(out),process_id=os.getpid(),exit_code=0 if result['status']=='completed' else 1,status=result['status'],limitations=['One Windows PC; no physical Pi or true GPS.','Existing board firmware does not provide RSSI; values stay null.','Unidentified USB-error port excluded; no firmware or radio configuration written.'],review_reference=None)
        (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(dict(status=result['status'],output=str(out),all_children_stopped=result['all_children_stopped'])),flush=True)


if __name__=='__main__':
    main()
