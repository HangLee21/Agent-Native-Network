"""Live field gateway: starts empty; optional observers reuse existing local Edge owners.

No model, serial enumeration, flashing, radio commands, fixed identities or routes.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser

from .server import ROOT


def request(base,path):
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(base+path,timeout=3) as response:
        return json.load(response)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host',default='127.0.0.1')
    p.add_argument('--port',type=int,default=8790)
    p.add_argument('--output',type=Path)
    p.add_argument('--open',action='store_true')
    p.add_argument('--attach-edge',type=int,action='append',default=[],help='existing loopback owner port; repeat for any number of local observers')
    p.add_argument('--gps',choices=['none','fake'],default='none',help='fake positions are explicitly simulated; default unknown')
    p.add_argument('--seed',type=int,default=30)
    p.add_argument('--report-s',type=float,default=10)
    p.add_argument('--duration',type=float,default=0,help='0 runs until Ctrl+C, independent node owners/radios are not stopped')
    args=p.parse_args(argv)
    if len(set(args.attach_edge))!=len(args.attach_edge) or not .1<=args.report_s<=3600 or args.duration<0:
        p.error('unique edge ports, report-s .1..3600, duration >=0 required')
    output=(args.output or ROOT/'simulation/outputs/H-016'/('live-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    output.mkdir(parents=True,exist_ok=False)
    stop=threading.Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    children=[]
    files=[]
    def spawn(name,command):
        stdout=(output/(name+'.stdout.log')).open('x',encoding='utf-8')
        stderr=(output/(name+'.stderr.log')).open('x',encoding='utf-8')
        files.extend([stdout,stderr])
        proc=subprocess.Popen([sys.executable,'-X','utf8',*command],cwd=ROOT,stdout=stdout,stderr=stderr,env=dict(os.environ,PYTHONUNBUFFERED='1'))
        children.append(dict(name=name,process=proc,command=[sys.executable,'-X','utf8',*command]))
        return proc
    status='starting'
    error=None
    try:
        gateway=spawn('gateway',['-m','tools.mobile_gateway','--host',args.host,'--port',str(args.port),'--output',str(output/'gateway'),'--stop-file',str(output/'gateway-stop')])
        deadline=time.monotonic()+12
        while not (output/'gateway/gateway.json').exists():
            if gateway.poll() is not None or time.monotonic()>deadline:
                raise RuntimeError('gateway failed to bind/start; existing services were not stopped; inspect logs')
            stop.wait(.05)
        meta=json.loads((output/'gateway/gateway.json').read_text(encoding='utf-8'))
        hostname='127.0.0.1' if args.host in ('0.0.0.0','::') else args.host
        base='http://'+hostname+':'+str(meta['port'])
        empty=request(base,'/api/v1/state')
        if empty['nodes'] or empty['edges']:
            raise AssertionError('new live gateway must be empty')
        (output/'INITIAL_EMPTY_STATE.json').write_text(json.dumps(empty,indent=2),encoding='utf-8')
        print(json.dumps(dict(status='ready',url=base+'/',role='live_observation',initial_nodes=0,initial_edges=0,output=str(output),serial_opens=0)),flush=True)
        if args.open:
            webbrowser.open(base+'/')
        for port in args.attach_edge:
            # Read identity from this owner; never pass guessed inventory or configure its board.
            edge_status=request('http://127.0.0.1:'+str(port),'/api/edge/status')
            (output/('edge-'+str(port)+'-before.json')).write_text(json.dumps(edge_status,indent=2),encoding='utf-8')
            if edge_status.get('transport_source')=='host_model' or edge_status.get('wireless_mode')=='host_model':
                raise ValueError('live entry rejects explicitly simulated local owners; use isolated demo instead')
            common=['--edge-port',str(port),'--seed',str(args.seed)]
            if args.duration:
                common+=['--duration',str(args.duration)]
            spawn('observer-'+str(port),['-m','tools.mobile_node','node',*common,'--state',str(output/('observer-'+str(port))),'--gateway',base,'--gps',args.gps,'--report-s',str(args.report_s),'--no-position-injection'])
        status='running'
        until=time.monotonic()+args.duration if args.duration else float('inf')
        while not stop.wait(.2) and time.monotonic()<until:
            for child in children:
                if child['process'].poll() is not None:
                    raise RuntimeError(child['name']+' exited; inspect its logs')
        status='stopped'
        (output/'FINAL_STATE.json').write_text(json.dumps(request(base,'/api/v1/state'),indent=2),encoding='utf-8')
        (output/'FINAL_TIMELINE.json').write_text(json.dumps(request(base,'/api/v1/timeline'),indent=2),encoding='utf-8')
    except Exception as exc:
        status,error='failed',repr(exc)
        raise
    finally:
        for child in reversed(children):
            proc=child['process']
            if child['name']=='gateway':
                (output/'gateway-stop').touch()
            try:
                proc.wait(timeout=4 if args.duration or child['name']=='gateway' else .5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=4)
        for f in files:
            f.close()
        result=dict(status=status,error=error,existing_edge_owners_stopped=False,radio_commands=0,serial_opens=0,processes=[dict(name=c['name'],pid=c['process'].pid,exit_code=c['process'].poll(),command=c['command']) for c in children])
        (output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(dict(status=status,output=str(output),existing_edges_preserved=True)),flush=True)


if __name__=='__main__':
    main()
