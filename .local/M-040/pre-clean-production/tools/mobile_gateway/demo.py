"""One-command isolated demonstration using E2 GPS/node/agent and a labelled host transport."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

from .model import IDS

ROOT = Path(__file__).resolve().parents[2]


def request(base, path, body=None):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    req = urllib.request.Request(base+path, None if body is None else json.dumps(body).encode(), headers={'Content-Type':'application/json'})
    with opener.open(req, timeout=2) as response:
        return json.load(response)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, help='new evidence directory; default a unique H-016 output')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8790, help='0 selects an unused temporary port')
    p.add_argument('--open', action='store_true', help='open the printed map URL in the default browser')
    p.add_argument('--duration', type=float, default=70, help='real seconds; finite run, Ctrl+C stops early')
    p.add_argument('--time-scale', type=float, default=1, help='real seconds per scenario second (.1..10)')
    p.add_argument('--seed', type=int, default=30)
    p.add_argument('--stop-file', type=Path, help='optional external lifecycle file')
    p.add_argument('--center-lat', type=float, default=30)
    p.add_argument('--center-lon', type=float, default=120)
    p.add_argument('--width-m', type=float, default=600)
    p.add_argument('--height-m', type=float, default=400)
    p.add_argument('--speed-mps', type=float, default=1.4)
    args = p.parse_args(argv)
    if not .1 <= args.time_scale <= 10 or not 0 < args.duration <= 3600:
        p.error('time scale .1..10, duration 0..3600 required')
    output = (args.output or ROOT/'simulation/outputs/H-016'/('demo-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])).resolve()
    output.mkdir(parents=True, exist_ok=False)
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    children, lifecycle, files = [], [], []
    started_ms = int(time.time()*1000)
    source_files = list((ROOT/'tools/mobile_gateway').glob('*.py'))+list((ROOT/'tools/mobile_node').glob('*.py'))
    initial_hashes = {str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files}
    (output/'INPUT_HASHES.json').write_text(json.dumps(initial_hashes,indent=2),encoding='utf-8')
    commands = []
    def log(kind, **data):
        row = dict(kind=kind, host_ms=int(time.time()*1000), **data)
        lifecycle.append(row)
        with (output/'lifecycle.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps(row)+'\n')
        print(json.dumps(row), flush=True)
    def spawn(name, command):
        stdout = (output/(name+'.stdout.log')).open('x', encoding='utf-8')
        stderr = (output/(name+'.stderr.log')).open('x', encoding='utf-8')
        files.extend((stdout, stderr))
        proc = subprocess.Popen([sys.executable, '-X', 'utf8', *command], cwd=ROOT, stdout=stdout, stderr=stderr, env=dict(os.environ, PYTHONUNBUFFERED='1'))
        children.append((name, proc))
        commands.append(dict(name=name, pid=proc.pid, argv=[sys.executable,'-X','utf8',*command]))
        log('process_started', name=name, pid=proc.pid)
        return proc
    def ready(path, proc):
        end = time.monotonic()+15
        while time.monotonic()<end and not stop.is_set():
            if path.exists():
                return json.loads(path.read_text(encoding='utf-8'))
            if proc.poll() is not None:
                raise RuntimeError('child exited before readiness; inspect stderr logs')
            stop.wait(.05)
        raise TimeoutError('startup readiness timeout')
    def finish(proc, stopfile=None, timeout=6):
        if stopfile:
            stopfile.touch()
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                return proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                return proc.wait(timeout=3)
    result = dict(status='running', evidence_kind='host_model_not_RF', serial_opens=0, physical_boards=0, real_pi=0, real_gps=0, existing_services_changed=False)
    model = gateway = None
    try:
        # The gateway is a separate process from the model and every E2 client.
        gateway_stop = output/'gateway-stop'
        def start_gateway(port, resume=False):
            if gateway_stop.exists():
                gateway_stop.unlink()
            command = ['-m','tools.mobile_gateway','--host',args.host,'--port',str(port),'--output',str(output/'gateway'),'--offline-ms',str(max(500,int(2500*args.time_scale))),'--stale-ms',str(max(700,int(5000*args.time_scale))),'--stop-file',str(gateway_stop)]
            if resume:
                command.append('--resume')
            proc = spawn('gateway-reconnected' if resume else 'gateway', command)
            if resume:
                deadline = time.monotonic()+10
                while time.monotonic()<deadline:
                    try:
                        health = request(base, '/health')
                        if health['gateway_instance'] != initial_instance:
                            return proc, dict(port=port, gateway_instance=health['gateway_instance'])
                    except (OSError, ValueError):
                        pass
                    if proc.poll() is not None:
                        raise RuntimeError('gateway reconnect failed')
                    stop.wait(.05)
                raise TimeoutError('gateway reconnect')
            return proc, ready(output/'gateway/gateway.json', proc)
        gateway, meta = start_gateway(args.port)
        host_for_url = '127.0.0.1' if args.host in ('0.0.0.0','::') else args.host
        base = 'http://'+host_for_url+':'+str(meta['port'])
        initial_instance = meta['gateway_instance']
        log('map_ready', url=base+'/', mode='HOST MODEL; simulated GPS and radio; E2 node and agent are real processes')
        if args.open:
            webbrowser.open(base+'/')
        model_stop = output/'model-stop'
        model = spawn('model', ['-m','tools.mobile_gateway.model','--output',str(output/'model'),'--time-scale',str(args.time_scale),'--stop-file',str(model_stop)])
        model_meta = ready(output/'model/ready.json', model)
        epoch = time.monotonic()
        remaining = lambda: max(.5,args.duration-(time.monotonic()-epoch))
        launched = set()
        node_processes = {}
        snapshots = []
        gateway_down = gateway_restored = offline_sent = False
        rejoined = False
        def start_node(label, suffix='', duration=None):
            port = model_meta['ports'][label]
            duration = remaining() if duration is None else duration
            common = ['--edge-port',str(port),'--state',str(output/('node-'+label)), '--seed',str(args.seed), '--duration',str(duration),'--interval-min',str(max(.05,.8*args.time_scale)),'--interval-max',str(max(.08,1.7*args.time_scale))]
            for other in 'ABCDE':
                if other != label:
                    common += ['--dest',IDS[other]]
            node = spawn('node-'+label+suffix, ['-m','tools.mobile_node','node',*common,'--gateway',base,'--label',label,'--report-s',str(max(.1,.8*args.time_scale)),'--sample-s',str(max(.1,.5*args.time_scale)),'--center-lat',str(args.center_lat),'--center-lon',str(args.center_lon),'--width-m',str(args.width_m),'--height-m',str(args.height_m),'--speed-mps',str(args.speed_mps),'--no-position-injection'])
            agent_common = list(common)
            agent_common[agent_common.index('--state')+1] = str(output/('agent-'+label))
            agent = spawn('agent-'+label+suffix, ['-m','tools.mobile_node','agent',*agent_common])
            node_processes[label] = (node, agent)
            log('node_joined', label=label, simulated_id=IDS[label], edge_port=port, reporting_process=node.pid, business_process=agent.pid)
        checkpoints = [1,3.6,5,7.8,10,16,21,26,32,40,44,58,64]
        runtime_due = 0
        while not stop.is_set() and time.monotonic()-epoch < args.duration:
            if (output/'STUDIO_STOP').exists() or (args.stop_file and args.stop_file.exists()):
                stop.set()
                break
            t = (time.monotonic()-epoch)/args.time_scale
            if time.monotonic() >= runtime_due:
                runtime_due = time.monotonic()+.5
                runtime = dict(observed_ms=int(time.time()*1000),
                               agents={label:dict(node_pid=pair[0].pid,agent_pid=pair[1].pid,
                                                 running=pair[1].poll() is None)
                                       for label,pair in node_processes.items()})
                temporary = output/'RUNTIME.tmp'
                temporary.write_text(json.dumps(runtime),encoding='utf-8')
                temporary.replace(output/'RUNTIME.json')
            for label, when in [('C',0),('B',3),('A',7),('D',14),('E',18)]:
                if t >= when and label not in launched:
                    start_node(label, duration=max(.5,(28-t)*args.time_scale) if label=='E' else None)
                    launched.add(label)
            if t >= 28 and not any(x['kind']=='node_left' for x in lifecycle):
                log('node_left', label='E', radio_source='host_model')
            if t >= 38 and not rejoined:
                # Prior E reporters should exit normally on their duration timer.
                for proc in node_processes.get('E',()):
                    if proc.poll() is None:
                        finish(proc, timeout=2)
                start_node('E','-rejoined')
                rejoined = True
            if t >= 46 and not gateway_down:
                log('gateway_stop_requested', pid=gateway.pid)
                code = finish(gateway, gateway_stop)
                log('gateway_off', pid=gateway.pid, exit_code=code, model_pid=model.pid, model_running=model.poll() is None, clients_running={k:all(p.poll() is None for p in v) for k,v in node_processes.items()})
                gateway_down = True
                result['gateway_off_ms'] = int(time.time()*1000)
            if t >= 50 and gateway_down and not offline_sent:
                # A fresh explicit source request while the gateway OS process is absent.
                payload = ('Gateway offline; A to C continues. '+uuid.uuid4().hex).encode('ascii')
                identity = request('http://127.0.0.1:'+str(model_meta['ports']['A']), '/api/edge/send', dict(request_id='offline-'+uuid.uuid4().hex,dst=IDS['C'],payload_hex=payload.hex()))
                result['offline_packet'] = dict(receipt=identity,payload_hex=payload.hex(),input_ms=int(time.time()*1000),gateway_exited=gateway.poll() is not None,model_running=model.poll() is None)
                log('offline_business_input', **result['offline_packet'])
                offline_sent = True
            if t >= 56 and gateway_down and not gateway_restored:
                gateway, resumed = start_gateway(meta['port'], True)
                result['gateway_reconnected_ms'] = int(time.time()*1000)
                result['reconnected_instance'] = resumed['gateway_instance']
                gateway_restored = True
                log('gateway_reconnected', **resumed)
            for point in list(checkpoints):
                if t >= point:
                    if not gateway_down or gateway_restored:
                        try:
                            snap = request(base,'/api/v1/state')
                            name = 'state-'+str(point).replace('.','_')+'.json'
                            (output/name).write_text(json.dumps(snap,indent=2),encoding='utf-8')
                            snapshots.append(dict(scenario_s=point,path=name,labels=[n['label'] for n in snap['nodes']]))
                        except (OSError,ValueError) as exc:
                            log('snapshot_unavailable', error=str(exc))
                    checkpoints.remove(point)
            stop.wait(.05)
        if gateway and gateway.poll() is None:
            (output/'last-state.json').write_text(json.dumps(request(base,'/api/v1/state'),indent=2),encoding='utf-8')
            (output/'timeline.json').write_text(json.dumps(request(base,'/api/v1/timeline'),indent=2),encoding='utf-8')
        result.update(status='completed' if not stop.is_set() else 'stopped_early',url=base+'/',snapshots=snapshots,gateway_reconnected=gateway_restored)
    except Exception as exc:
        result.update(status='failed', error=repr(exc))
        raise
    finally:
        # Clients have bounded duration and stop before model teardown; no old service is touched.
        for name, proc in reversed(children):
            if name.startswith(('node-','agent-')):
                finish(proc, timeout=4 if not stop.is_set() else .5)
        if gateway and gateway.poll() is None:
            finish(gateway, output/'gateway-stop')
        if model and model.poll() is None:
            finish(model, output/'model-stop')
        for _, proc in children:
            if proc.poll() is None:
                finish(proc, timeout=.5)
        result['processes'] = [dict(name=name,pid=proc.pid,exit_code=proc.poll(),running=proc.poll() is None) for name,proc in children]
        for file in files:
            file.close()
        result['finished_ms'] = int(time.time()*1000)
        result['sources_unchanged_during_run'] = all((ROOT/path).is_file() and hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==sha for path,sha in initial_hashes.items())
        (output/'RESULT.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        sources = list((ROOT/'tools/mobile_gateway').glob('*.py'))+list((ROOT/'tools/mobile_node').glob('*.py'))
        manifest = dict(task_id='H-016',run_id=output.name,started_at=started_ms,finished_at=result['finished_ms'],timezone='Asia/Shanghai',worktree=str(ROOT),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty_files_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources},command=sys.argv,commands=commands,python_executable=sys.executable,dependency_snapshot='Python standard library; actual E2 mobile_node modules',upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=[args.seed],budget=dict(duration_s=args.duration,time_scale=args.time_scale),output_directory=str(output),process_id=os.getpid(),exit_code=0 if result['status'] in ('completed','stopped_early') else 1,status=result['status'],limitations=['Host transport model and BFS are synthetic, not board routing or RF measurements.','GPS is simulated through the actual E2 provider.','Single Windows PC; no real Pi, hotspot, LAN reach or GPS validation.'],review_reference=None)
        (output/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        print(json.dumps(dict(status=result['status'],output=str(output),all_children_stopped=all(not x['running'] for x in result['processes']))),flush=True)


if __name__ == '__main__':
    main()
