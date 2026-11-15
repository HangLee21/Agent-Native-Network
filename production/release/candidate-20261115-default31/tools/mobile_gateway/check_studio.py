"""Isolated real-process checks for source-session isolation and explicit demo cleanup."""
import argparse
import json
from pathlib import Path
import socket
import threading
import time
import urllib.error
import urllib.request

from .server import Gateway, ROOT
from .studio import Studio, StudioHandler


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    with socket.socket() as unused:
        unused.bind(('127.0.0.1',0))
        demo_port=unused.getsockname()[1]
    with socket.socket() as unavailable:
        unavailable.bind(('127.0.0.1',0))
        pc_port=unavailable.getsockname()[1]
        state=Studio(out,demo_port,pc_port) # No production endpoint, radio or serial.
        server=Gateway(('127.0.0.1',0),state,ROOT/'research/agent_native_network/mobile_gateway')
        server.RequestHandlerClass=StudioHandler
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        checks=[]
        def call(path,body=None):
            request=urllib.request.Request(base+path,None if body is None else json.dumps(body).encode(),
                         headers={'Content-Type':'application/json','Origin':base})
            with urllib.request.urlopen(request,timeout=25) as response:
                return json.load(response)
        def ok(name,value):
            checks.append(dict(name=name,passed=bool(value)))
            if not value:
                raise AssertionError(name)
        def empty_pair():
            snapshot=call('/api/v1/state')
            history=call('/api/v1/timeline?after=500')
            ok('empty snapshot/history same instance',snapshot['gateway_instance']==history['gateway_instance'])
            ok('empty snapshot and cursor stay empty',snapshot['nodes']==[] and snapshot['edges']==[] and snapshot['cursor']==0 and history['events']==[] and history['cursor']==0)
            return snapshot['gateway_instance']
        try:
            call('/api/studio/mode',{'mode':'demo'})
            first=empty_pair()
            ok('changing mode never auto-starts agents',not call('/api/studio/status')['demo']['running'])
            call('/api/studio/demo/start',{})
            first_dir=state.demo_dir
            until=time.monotonic()+15
            while time.monotonic()<until:
                snapshot=call('/api/v1/state')
                if snapshot['nodes'] and all(n['agent']['running'] is True for n in snapshot['nodes']):
                    break
                time.sleep(.1)
            ok('actual E2 model processes produced reports',bool(snapshot['nodes']) and all(n['position']['source']=='simulated' for n in snapshot['nodes']))
            ok('demo radio is explicitly simulated',snapshot['radio_source']=='host_model_simulated')
            ok('demo agent runtime comes from owned process status',all(n['agent']['source']=='actual_E2_fake_agent_function_processes' and n['agent']['process']['agent_pid']>0 for n in snapshot['nodes']))
            call('/api/studio/demo/stop',{})
            stopped=empty_pair()
            saved=json.loads((first_dir/'RESULT.json').read_text())
            ok('all first-demo children stopped',all(not p['running'] for p in saved['processes']))
            call('/api/studio/demo/replay',{})
            second_dir=state.demo_dir
            ok('replay uses a fresh output/session',second_dir!=first_dir)
            # Immediate stop also covers creation-before-directory startup race.
            call('/api/studio/demo/stop',{})
            second=empty_pair()
            ok('previous demo session never reused',first!=stopped and stopped!=second)
            saved2=json.loads((second_dir/'RESULT.json').read_text())
            ok('all replay children stopped',all(not p['running'] for p in saved2['processes']))
            call('/api/studio/mode',{'mode':'live'})
            current=call('/api/v1/state')
            ok('return to live has no synthetic nodes',current['nodes']==[] and current['gateway_instance']==state.live.instance and current['view_mode']=='live')
        finally:
            server.shutdown()
            thread.join(3)
            server.server_close()
            state.close()
            (out/'CHECK.json').write_text(json.dumps(dict(checks=checks,serial_opens=0,physical_boards=0,production_services_changed=False),indent=2),encoding='utf-8')
        print(json.dumps(dict(checks=len(checks),passed=all(c['passed'] for c in checks),physical_boards=0)))


if __name__=='__main__':
    main()
