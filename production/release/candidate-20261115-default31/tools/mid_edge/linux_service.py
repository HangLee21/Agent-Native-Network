"""udev-owned single-board service. Probe only a registered candidate, once."""
import argparse
import datetime
import json
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid
from .client import Edge,EdgeError

class Rejected(RuntimeError):pass

def properties(device):
    if not re.fullmatch(r'/dev/tty(?:USB|ACM)[0-9]+',device):raise Rejected('udev tty USB/ACM device required')
    text=subprocess.check_output(['udevadm','info','--query=property','--name',device],text=True,timeout=5)
    return dict(line.split('=',1) for line in text.splitlines() if '=' in line)

def gate(config,props):
    for key,name in [('ID_PATH','id_path'),('ID_USB_INTERFACE_NUM','interface'),('ID_VENDOR_ID','vid'),('ID_MODEL_ID','pid')]:
        if not config.get(name) or props.get(key)!=config[name]:raise Rejected('candidate does not match registered '+key)

def run(config,device,*,get_properties=properties,edge_factory=Edge,stop=None,state=Path('/var/lib/mid-edge'),on_ready=None):
    # OS metadata first: unrelated serial interfaces are never opened.
    gate(config,get_properties(device));stop=stop or threading.Event();state=Path(state);state.mkdir(parents=True,exist_ok=True)
    from tools.mid_sim_console.local_edge import LocalEdge,ThreadingHTTPServer
    from .service_api import Handler
    edge=None;app=None;server=None;verified=False;manage_radio=False;cleanup=dict(verified_identity=False,stop_attempted=False,radio_stop_confirmed=False,serial_closed=False)
    try:
        edge=edge_factory(device,config['node_id'],config['baud'],log=str(state/(uuid.uuid4().hex+'.events.jsonl')))
        try:info=edge.identify()
        except Exception as exc:raise Rejected('candidate firmware/STA verification failed: '+str(exc)) from exc
        verified=True
        cleanup['verified_identity']=True
        if config['start_policy']=='saved':
            # Never install/clear a profile or bind a remote publisher at plug-in.
            if info.get('deployment_mode')=='autonomous' and info.get('discovery_saved') and not info.get('discovery_fault'):
                if info.get('radio') is not True:edge.command('route_start')
            elif info.get('discovery_saved') and not info.get('discovery_fault'):
                if info.get('radio') is not True:edge.command('discover_start')
            elif info.get('deployment_saved') and info.get('deployment_mode')=='offline_table':
                if info.get('radio') is not True:edge.command('local_start')
            else:raise Rejected('no saved supported local wireless profile; provision explicitly first with observe policy')
            manage_radio=True
        app=LocalEdge(edge,state/'requests.json');server=ThreadingHTTPServer(('127.0.0.1',config['http_port']),Handler);server.daemon_threads=True;server.app=app;server.timeout=.2
        if on_ready:on_ready(server.server_port)
        while not stop.is_set():
            edge.health();server.handle_request()
        return 0
    finally:
        if server:server.server_close()
        if app:app.stopping=True;app.thread.join(1)
        if edge:
            if verified and manage_radio:
                cleanup['stop_attempted']=True
                try:
                    edge.command('stop',timeout=1)
                    end=time.monotonic()+2
                    while time.monotonic()<end:
                        info=edge.info()
                        if not info.get('radio') and not info.get('stopping'):cleanup['radio_stop_confirmed']=True;break
                        time.sleep(.05)
                except Exception as exc:cleanup['stop_error']=str(exc)  # unplug: never reopen
            try:edge.close();cleanup['serial_closed']=True
            finally:
                (state/(uuid.uuid4().hex+'.shutdown.json')).write_text(json.dumps(cleanup,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--device',required=True);a=p.parse_args();config=json.loads(Path(a.config).read_bytes());stop=threading.Event()
    signal.signal(signal.SIGTERM,lambda *_:stop.set());signal.signal(signal.SIGINT,lambda *_:stop.set())
    try:return run(config,a.device,stop=stop)
    except Rejected as exc:print(json.dumps(dict(error=str(exc),host_wireless_start_issued=False)),flush=True);return 78
    except (EdgeError,OSError) as exc:print(json.dumps(dict(error=str(exc))),flush=True);return 1

if __name__=='__main__':raise SystemExit(main())
