"""Local dynamic AD-HOC viewer: real board observations and explicit isolated demo."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from urllib.parse import urlsplit

from .server import Gateway, Handler, ROOT
from .state import State
from .lora import LoRaTopology
from .fleet_registry import merged_fleet, read_nodes

# Ethernet LoRa gateway source (tools/mid_baseline/gateway_probe/topology_server.py). Used
# only when the serial A reader is idle or empty, so the same page can show our EoRa
# topology whether it arrives over a serial board or over the RHF2S008 gateway.
GATEWAY_TOPOLOGY = 'http://127.0.0.1:8780/api/v1/lora/topology'
from tools.field_gateway.client import Client
from tools.mid_hardware.field_agent.wire_operator import Operator
from tools.mobile_node.providers import fake_GPS_function


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=2) as response:
        return json.load(response)


class Studio:
    def __init__(self, output, demo_port, pc_port):
        self.output, self.demo_port, self.pc_port = output, demo_port, pc_port
        self.lock = threading.RLock()
        self.mode, self.fake_gps = 'live', False
        self.live = State(offline_ms=20000, stale_ms=30000)
        self.agent, self.positions, self.seq, self.boots, self.cursors = {}, {}, {}, {}, {}
        self.label_map = {}
        identity = ROOT/'simulation/outputs/H-017/20261109-13-five-flash/RESULT.json'
        if identity.is_file():
            self.label_map = {r['result']['mac']: r['label'] for r in json.loads(identity.read_text())['boards'] if r['result']['success']}
        self.session = 'studio-' + uuid.uuid4().hex
        self.client, self.operator = Client(pc_port), Operator(pc_port)
        self.pc_status, self.error, self.last_ui = None, None, 0
        self.demo, self.demo_dir, self.demo_started = None, None, None
        self.demo_files = []
        self.stop = threading.Event()
        self.journal = (output/'observations.jsonl').open('x', encoding='utf-8')
        self.lora = LoRaTopology(output, self.label_map)
        self.thread = threading.Thread(target=self.observe, daemon=True, name='wireless-read-only-observer')
        self.thread.start()

    def log(self, kind, **values):
        self.journal.write(json.dumps(dict(kind=kind, host_time=time.time(), **values))+'\n')
        self.journal.flush()

    def touch(self):
        self.last_ui = time.monotonic()

    def observe(self):
        index = 0
        while not self.stop.wait(.25):
            # No unattended finite experiment queue; observe while a visible page polls.
            if self.mode != 'live' or time.monotonic()-self.last_ui > 12:
                continue
            try:
                status = self.client.status()
                self.pc_status = status
                entries = [r for r in status['entries'] if r['connected']]
                if not entries:
                    self.error = '当前没有有效无线入口'
                    continue
                entry = entries[index % len(entries)]
                index += 1
                node = entry['node_id']
                response = self.operator.native(node, 'field_status', timeout=2)
                raw = response['reply']
                self.log('field_status', response=response)
                if self.boots.get(node) != raw['entry_boot']:
                    self.boots[node] = raw['entry_boot']
                    self.seq[node] = 0
                    self.cursors[node] = raw['latest_record_cursor']
                latest = raw['latest_record_cursor']
                previous = self.cursors[node]
                cursor = max(previous, latest-4)
                skipped = cursor-previous
                events = []
                for _ in range(4):
                    if cursor >= latest or self.stop.is_set():
                        break
                    item = self.operator.native(node, 'record', {'after': cursor}, timeout=2)
                    record = item['reply']
                    if record['event'] == 'record_idle':
                        break
                    cursor = record['record_cursor']
                    self.log('native_record', response=item)
                    names = {'source_admitted':'tx_queued', 'source_submitted':'tx_submit',
                             'relay_received':'rx_relay', 'relay_submitted':'tx_submit',
                             'destination_received':'rx_local'}
                    event = dict(record, event=names.get(record['kind'], record['kind']),
                                 node_id=node, observer_id=node, reporter=node,
                                 evidence_source='actual_board_RAM_over_IP',
                                 native_kind=record['kind'], raw=record)
                    # FG02 PC envelopes are not plain board application payloads.
                    if record.get('payload_hex', '').startswith('46473032'):
                        event['event'] = 'field_pc_envelope'
                    events.append(event)
                self.cursors[node] = max(previous, cursor)
                self.seq[node] += 1
                self.agent[node] = dict(running=raw['agent_running'], source='board_field_agent',
                                       counters={k:raw[k] for k in ('source_admitted','source_submitted','destination_received','relay_received','relay_submitted')},
                                       record_overwritten=raw['record_overwritten'], sampled_records_skipped=skipped,
                                       latest_record_cursor=latest, observed_at_ms=int(time.time()*1000))
                report = dict(schema_version=1, node_id=node, boot_id=raw['entry_boot'],
                              session_id=self.session+'-'+str(raw['entry_boot']), seq=self.seq[node],
                              label=self.label_map.get(node, node[-5:]), position=None,
                              neighbors=[], events=events, agent=self.agent[node],
                              source='actual_board_field_status', neighbor_observation='not_available_in_this_status',
                              counts=self.agent[node]['counters'])
                self.live.accept(report)
                self.error = None
            except Exception as exc:
                self.error = str(exc)
                self.log('observation_error', error=repr(exc))
                self.stop.wait(1)

    def status(self):
        self.touch()
        running = self.demo is not None and self.demo.poll() is None
        return dict(mode=self.mode, fake_gps=self.fake_gps, error=self.error if self.mode=='live' else None,
                    demo=dict(running=running, duration_s=120,
                              elapsed_s=round(time.monotonic()-self.demo_started, 1) if self.demo_started else 0,
                              exit_code=self.demo.poll() if self.demo else None,
                              output=str(self.demo_dir) if self.demo_dir else None,
                              source='host_model_not_RF', agent_source='actual_E2_fake_agent_function_processes',
                              gps_source='actual_E2_fake_GPS_function_simulated'),
                    live=dict(source='real_boards_USB_power', agent_source='board_field_agent',
                              host_business_generator=False, serial_opens=0,
                              connected_entries=len([r for r in (self.pc_status or {}).get('entries',[]) if r['connected']]),
                              agent=copy.deepcopy(self.agent)),
                    lora_receiver=self.lora.snapshot(touch=False)['receiver'],
                    capabilities=dict(demo_control=True, fake_gps_toggle=True, physical_agent_control=False, lora_topology=True),
                    endpoints=dict(mode='/api/studio/mode',demo='/api/studio/demo',gps='/api/studio/gps'))

    def start_demo(self):
        if self.demo and self.demo.poll() is None:
            return
        # Never stop another service or claim its occupied port.
        import socket
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', self.demo_port))
        directory=self.output/('demo-'+uuid.uuid4().hex[:8])
        stdout=(self.output/(directory.name+'.stdout.txt')).open('x',encoding='utf-8')
        stderr=(self.output/(directory.name+'.stderr.txt')).open('x',encoding='utf-8')
        self.demo_files.extend([stdout,stderr])
        command=[sys.executable,'-X','utf8','-m','tools.mobile_gateway.demo','--output',str(directory),
                 '--port',str(self.demo_port),'--duration','120','--seed','31','--speed-mps','5',
                 '--stop-file',str(self.output/(directory.name+'.STOP'))]
        self.demo=subprocess.Popen(command,cwd=ROOT,stdout=stdout,stderr=stderr,
                                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.demo_started, self.demo_dir = time.monotonic(), directory
        self.log('explicit_demo_started',pid=self.demo.pid,command=command)

    def stop_demo(self):
        if self.demo and self.demo.poll() is None:
            (self.output/(self.demo_dir.name+'.STOP')).touch()
            self.demo.wait(timeout=20)
            self.log('explicit_demo_stopped',exit_code=self.demo.returncode)

    def control(self, action, value):
        with self.lock:
            if action=='mode' and set(value)=={'mode'} and value['mode'] in ('live','demo'):
                self.mode=value['mode']
            elif action=='gps' and set(value)=={'enabled'} and type(value['enabled']) is bool:
                self.fake_gps=value['enabled']
            elif action=='demo' and set(value)=={'action'} and value['action'] in ('start','stop','restart'):
                if value['action'] in ('stop','restart'):
                    self.stop_demo()
                if value['action'] in ('start','restart'):
                    self.start_demo()
                    self.mode='demo'
                    self.fake_gps=True
            else:
                raise ValueError('unsupported studio action')
            return self.status()

    def snapshot(self):
        self.touch()
        if self.mode=='demo':
            if self.demo_dir is None:
                value=State().snapshot()
                value['gateway_instance']=self.empty_demo_instance()
                value['cursor']=0
                value['empty_reason']='点击开始组网演示；尚未启动任何模拟节点'
            else:
                try:
                    value=get_json(f'http://127.0.0.1:{self.demo_port}/api/v1/state')
                except OSError:
                    value=State().snapshot()
                    value['gateway_instance']=self.empty_demo_instance()
                    value['cursor']=0
                    value['empty_reason']='演示网关已关闭或正在重连；点击重播可重新开始'
            runtime = {}
            if self.demo_dir and (self.demo_dir/'RUNTIME.json').exists():
                runtime=json.loads((self.demo_dir/'RUNTIME.json').read_text())
            for node in value['nodes']:
                label=node['label']
                observed=runtime.get('agents',{}).get(label,{})
                running=observed.get('running') if self.demo and self.demo.poll() is None else False
                attempts,admitted,received=set(),set(),set()
                if self.demo_dir:
                    for journal in (self.demo_dir/('agent-'+label)).glob('agent-*.jsonl'):
                        for line in journal.read_text(encoding='utf-8').splitlines():
                            try:
                                row=json.loads(line)
                            except ValueError:
                                continue
                            if row['kind']=='send_attempt':
                                attempts.add(row['request_id'])
                            elif row['kind']=='send_receipt' and row['receipt'].get('accepted'):
                                admitted.add(row['request_id'])
                            elif row['kind']=='received':
                                p=row['packet']
                                received.add((p['origin'],p['boot'],p['seq'],p['dst']))
                node['agent']=dict(running=running,source='actual_E2_fake_agent_function_processes',
                                   process=observed,counters=dict(source_admitted=len(admitted),
                                   destination_received=len(received),send_attempts=len(attempts)))
                if not self.fake_gps:
                    node['position']=None
        else:
            value=self.live.snapshot()
            # Native IP summary reception is independent; keep its RF source/unknown age intact.
            try:
                native=get_json(f'http://127.0.0.1:{self.pc_port}/api/v1/state')
                actual={r['node_id']:r for r in native['nodes']}
                value['edges']=native['edges']
                for node in value['nodes']:
                    if node['node_id'] in actual:
                        node['neighbors']=actual[node['node_id']].get('neighbors',[])
            except OSError:
                pass
            for node in value['nodes']:
                if self.fake_gps:
                    provider=self.positions.setdefault(node['node_id'],fake_GPS_function(seed=int(hashlib.sha256(node['node_id'].encode()).hexdigest()[:8],16),speed_mps=5))
                    node['position']=dict(provider(),age_ms=0,stale=False,display_only=True)
                node['agent']=copy.deepcopy(self.agent.get(node['node_id']))
        value.update(view_mode=self.mode, fake_gps=self.fake_gps,
                     radio_source='host_model_simulated' if self.mode=='demo' else 'actual_board_observation_only',
                     business_source='E2_fake_agent_function_host_model' if self.mode=='demo' else 'board_field_agent',
                     studio=self.status())
        return value

    def history(self, after):
        self.touch()
        if self.mode=='live':
            return self.live.history(after)
        if self.demo_dir:
            try:
                return get_json(f'http://127.0.0.1:{self.demo_port}/api/v1/timeline?after={after}')
            except OSError:
                pass
        return dict(schema_version=1,gateway_instance=self.empty_demo_instance(),events=[],cursor=0,oldest_cursor=1,truncated=False)

    def empty_demo_instance(self):
        return self.session+'-demo-'+(self.demo_dir.name if self.demo_dir else 'not-started')

    def close(self):
        self.stop.set()
        self.lora.close()
        self.thread.join(8)
        self.stop_demo()
        for stream in self.demo_files:
            stream.close()
        self.journal.close()


class StudioHandler(Handler):
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/v1/recovery':
            try:
                value=json.loads(self.server.recovery_path.read_text(encoding='utf-8'))
                if value.get('schema')!='studio.recovery.v1' or value.get('state') not in ('connecting','recovering','online','recovered','unavailable') or time.time()-value['updated_at']>10:raise ValueError('recovery status stale or invalid')
                return self.reply(200,value)
            except (OSError,ValueError,TypeError,KeyError):
                return self.reply(503,{'schema':'studio.recovery.v1','state':'unknown','reason':'启动服务状态不可用'})
        if path=='/api/v1/fleet':
            try:
                return self.reply(200,merged_fleet(self.server.fleet_path,self.server.registry_path))
            except (ValueError,OSError) as exc:
                return self.reply(503,{'error':'节点编号配置不可用，请联系交付人员检查 fleet 和 registry：'+str(exc)})
        if path=='/api/studio/status':
            return self.reply(200,self.server.state.status())
        if path=='/api/v1/lora/topology':
            # The RHF2S008 gateway is now the only receiver: there is no serial fallback any
            # more, so an unreachable gateway is reported as such instead of silently
            # switching to a board's USB port.
            try:
                return self.reply(200,get_json(self.server.gateway_topology))
            except OSError as exc:
                return self.reply(200,{'schema':'lora.topology.v1','source':'gateway_udp_lrn1',
                                       'labels':{},'reports':[],
                                       'receiver':{'state':'unavailable','gateway_id':None,
                                                   'serial_open':False,'error':str(exc)},
                                       'evidence':'gateway source unreachable'})
        if path in ('/api/pc/status','/api/pc/inbox','/api/pc/events'):
            try:
                return self.reply(200,get_json(f'http://127.0.0.1:{self.server.state.pc_port}'+self.path))
            except OSError as exc:
                return self.reply(503,{'error':str(exc)})
        if path.startswith('/map/'):
            self.path='/' + self.path[len('/map/'):]
        return super().do_GET()

    def do_POST(self):
        path=urlsplit(self.path).path
        aliases={'/api/studio/demo/start':'start','/api/studio/demo/stop':'stop','/api/studio/demo/replay':'restart'}
        if path not in ('/api/studio/mode','/api/studio/demo','/api/studio/gps') and path not in aliases:
            return self.reply(404,{'error':'no physical business/control endpoint'})
        host=self.headers.get('Host')
        if host!=f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin')!='http://'+host:
            return self.reply(403,{'error':'same-origin loopback control required'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1024 or self.headers.get('Transfer-Encoding'):
                raise ValueError('small JSON body required')
            value=json.loads(self.rfile.read(size))
            if path in aliases:
                if value != {}:
                    raise ValueError('demo action path accepts empty JSON only')
                return self.reply(200,self.server.state.control('demo',{'action':aliases[path]}))
            return self.reply(200,self.server.state.control(path.rsplit('/',1)[1],value))
        except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
            return self.reply(400,{'error':str(exc)})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8794)
    p.add_argument('--demo-port',type=int,default=8795)
    p.add_argument('--pc-port',type=int,default=8791)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--production-output',action='store_true',help='allow a new explicit production run directory')
    p.add_argument('--fleet',type=Path,help='same validated fleet configuration passed by launcher')
    p.add_argument('--registry',type=Path,help='read-only runtime node registry')
    p.add_argument('--recovery-file',type=Path,help='read-only supervisor health state')
    p.add_argument('--topology-port',type=int,default=8780)
    p.add_argument('--stop-file',type=Path)
    args=p.parse_args()
    out=args.output.resolve()
    if not args.production_output and not any(out.is_relative_to(ROOT/'simulation/outputs'/task) for task in ('H-016','H-018','H-019','H-020')):
        p.error('new H-016, H-018, H-019 or H-020 output required')
    fleet_path=args.fleet or (ROOT/'production/local/fleet.json' if (ROOT/'production/local/fleet.json').is_file() else ROOT/'production/config/fleet.example.json')
    try:
        read_nodes(fleet_path)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        p.error('fleet configuration invalid: '+str(exc))
    out.mkdir(parents=True,exist_ok=False)
    state=Studio(out,args.demo_port,args.pc_port)
    server=Gateway(('127.0.0.1',args.port),state,ROOT/'research/agent_native_network/mobile_gateway')
    server.RequestHandlerClass=StudioHandler
    server.fleet_path=fleet_path
    server.registry_path=args.registry or ROOT/'production/local/registry.json'
    server.recovery_path=args.recovery_file or ROOT/'production/local/studio-recovery.json'
    server.gateway_topology=f'http://127.0.0.1:{args.topology_port}/api/v1/lora/topology'
    def halt(*_):
        threading.Thread(target=server.shutdown,daemon=True).start()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,halt)
    done=threading.Event()
    def watch():
        while not done.wait(.25):
            if args.stop_file and args.stop_file.exists():
                halt()
                return
    threading.Thread(target=watch,daemon=True).start()
    meta=dict(pid=__import__('os').getpid(),url=f'http://127.0.0.1:{args.port}/',serial_opens_at_start=0,
              lora_serial_owner='on-demand child H020-Studio-LoRa; see /api/studio/status lora_receiver',
              host_physical_business_generator=False)
    (out/'PROCESS.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta),flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        done.set()
        server.server_close()
        state.close()


if __name__=='__main__':
    main()
