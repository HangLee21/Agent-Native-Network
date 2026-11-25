"""Bounded real-process launcher checks, with isolated ports and no physical radios."""
from dataclasses import asdict, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import hashlib
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from .runtime import Bench, StartupError, ensure_runtime, read_json, wait_ready
from .server import ROOT
from tools.field_gateway.store import Store


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1',0))
        return s.getsockname()[1]


class Fixed(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        data=json.dumps(self.server.value).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sources=[Path(__file__),ROOT/'tools/mobile_gateway/runtime.py',ROOT/'tools/mobile_gateway/launch_studio.py',ROOT/'tools/mobile_gateway/ensure_hotspot.ps1']
    source_hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}
    (out/'SOURCES_AT_START.json').write_text(json.dumps(source_hashes,indent=2),encoding='utf-8')
    ports=set()
    while len(ports)<4: ports.add(free_port())
    pc,udp,studio,demo=ports
    bench=Bench(pc_port=pc,udp_port=udp,studio_port=studio,demo_port=demo,udp_host='127.0.0.1',
                state=str(out/'state'),fault=str(out/'fault.json'),maintenance=str(out/'maintenance.json'),manage_hotspot=False)
    config=out/'PROFILE.json';config.write_text(json.dumps(asdict(bench)),encoding='utf-8')
    checks=[];owned=[];fixtures=[]
    def ok(name,value):
        checks.append(dict(name=name,passed=bool(value)))
        if not value: raise AssertionError(name)
    def launch(name):
        target=out/name
        command=[sys.executable,'-X','utf8','-m','tools.mobile_gateway.launch_studio','--config',str(config),'--runtime-dir',str(out/'lock'),
                 '--output',str(target),'--no-open','--entry-wait','0']
        stdout=(out/(name+'.stdout.txt')).open('xb');stderr=(out/(name+'.stderr.txt')).open('xb')
        return subprocess.Popen(command,cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)),target,stdout,stderr
    def finish(item):
        proc,target,stdout,stderr=item
        code=proc.wait(timeout=30);stdout.close();stderr.close()
        row=json.loads((target/'RESULT.json').read_text());owned.extend(row['processes_started'])
        ok('launcher '+target.name+' exit0',code==0)
        return row
    def stop(role):
        for row in reversed(owned):
            if row['role']==role:
                Path(row['stop_file']).touch();break
        url=f'http://127.0.0.1:{bench.pc_port if role=="pc" else bench.studio_port}/'+('api/pc/status' if role=='pc' else 'api/studio/status')
        until=time.monotonic()+10
        while time.monotonic()<until:
            try:
                if read_json(url) is None:return
            except (StartupError, ConnectionResetError):
                pass # A resetting connection during our own graceful stop is transient.
            time.sleep(.1)
        raise TimeoutError('owned '+role+' did not stop')
    def conflict(name,changed,value):
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixed);server.value=value
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();fixtures.append((server,thread))
        cfg=replace(bench,**{changed:server.server_port})
        try:ensure_runtime(cfg,runtime_dir=out/'lock',output=out/name,entry_wait=0)
        except StartupError: pass
        else:raise AssertionError('conflict was accepted')
        saved=json.loads((out/name/'RESULT.json').read_text())
        ok(name+' no process replaced or created',saved['processes_started']==[] and read_json(f'http://127.0.0.1:{server.server_port}/')==value)
    try:
        first,second=launch('concurrent-A'),launch('concurrent-B')
        one,two=finish(first),finish(second)
        started=one['processes_started']+two['processes_started']
        ok('concurrent startup creates exactly one PC and one studio',sorted(x['role'] for x in started)==['pc','studio'])
        ok('concurrent callers see same PC identity/session',one['pc_instance_id']==two['pc_instance_id'] and one['pc_session']==two['pc_session'])
        repeated=finish(launch('repeat'))
        ok('repeat reuses both services',repeated['processes_started']==[] and repeated['pc_instance_id']==one['pc_instance_id'])
        with_state=Store(Path(bench.state)/'pc.sqlite3',pc_id=bench.pc_id)
        old,_=with_state.reserve('retained-request-01',{'dst':'02:00:00:00:00:02','payload_hex':'74657374'},{})
        with_state.close()
        studio_pid=next(x['pid'] for x in started if x['role']=='studio')
        stop('pc')
        repaired=finish(launch('existing-studio-missing-PC'))
        ok('existing studio repairs missing PC only',[x['role'] for x in repaired['processes_started']]==['pc'])
        ok('PC restart has new session, same ledger',repaired['pc_session']!=one['pc_session'] and read_json(f'http://127.0.0.1:{pc}/api/pc/requests/retained-request-01')['record']==old)
        status=read_json(f'http://127.0.0.1:{pc}/api/pc/status')
        ok('retained unknown request was never transmitted',status['wireless']['counters'].get('ip_send_sent',0)==0)
        stop('studio')
        repaired_studio=finish(launch('existing-PC-missing-studio'))
        ok('healthy PC preserved when studio missing',[x['role'] for x in repaired_studio['processes_started']]==['studio'] and repaired_studio['pc_instance_id']==repaired['pc_instance_id'])
        conflict('wrong-PC-id','pc_port',{'pc_id':1,'serial_access':False})
        conflict('occupied-studio','studio_port',{'other_service':True})
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as blocker:
            blocker.bind(('127.0.0.1',0));cfg=replace(bench,pc_port=free_port(),udp_port=blocker.getsockname()[1])
            try:ensure_runtime(cfg,runtime_dir=out/'lock',output=out/'UDP-occupied',entry_wait=0)
            except StartupError:pass
            else:raise AssertionError('UDP owner was not preserved')
            ok('occupied UDP does not start duplicate PC',json.loads((out/'UDP-occupied/RESULT.json').read_text())['processes_started']==[])
        delayed_port=free_port();holder={}
        def delayed():
            time.sleep(.5);s=ThreadingHTTPServer(('127.0.0.1',delayed_port),Fixed);s.value={'ready':True};holder['server']=s;s.serve_forever()
        t=threading.Thread(target=delayed,daemon=True);t.start();before=time.monotonic()
        got=wait_ready(f'http://127.0.0.1:{delayed_port}/',None,lambda x:x)
        ok('waits for delayed readiness instead of opening early',got['ready'] and time.monotonic()-before>=.4)
        holder['server'].shutdown();holder['server'].server_close();t.join(2)
    finally:
        for row in owned: Path(row['stop_file']).touch()
        until=time.monotonic()+10
        while owned and time.monotonic()<until:
            try:
                if read_json(f'http://127.0.0.1:{pc}/api/pc/status') is None and read_json(f'http://127.0.0.1:{studio}/api/studio/status') is None:break
            except StartupError: pass
            time.sleep(.1)
        for server,thread in fixtures:server.shutdown();server.server_close();thread.join(2)
        (out/'CHECK.json').write_text(json.dumps(dict(checks=checks,physical_boards=0,serial_opens=0,production_ports_changed=False,physical_business_sends=0,
                  source_hashes=source_hashes,sources_unchanged=all(hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==h for f,h in source_hashes.items())),indent=2),encoding='utf-8')
    print(json.dumps(dict(passed=all(x['passed'] for x in checks),checks=len(checks))))


if __name__=='__main__':main()
