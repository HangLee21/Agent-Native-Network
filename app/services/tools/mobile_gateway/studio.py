"""Local AD-HOC observation service."""
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
from .fleet_registry import merged_fleet, read_nodes
from .remote import RemoteGateway
from .node_serial import SerialTopology

# Ethernet LoRa gateway source (tools/mid_baseline/gateway_probe/topology_server.py). Used
# only when the serial A reader is idle or empty, so the same page can show our EoRa
# topology whether it arrives over a serial board or over the RHF2S008 gateway.
GATEWAY_TOPOLOGY = 'http://127.0.0.1:8780/api/v1/lora/topology'
from tools.field_gateway.client import Client
from tools.mid_hardware.field_agent.wire_operator import Operator


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=2) as response:
        return json.load(response)


class Studio:
    def __init__(self, output, pc_port):
        self.output, self.pc_port = output, pc_port
        self.lock = threading.RLock()
        self.mode, self.fake_gps = 'live', False
        self.live = State(offline_ms=20000, stale_ms=30000)
        self.agent, self.positions, self.seq, self.boots, self.cursors = {}, {}, {}, {}, {}
        self.label_map = {}
        self.session = 'studio-' + uuid.uuid4().hex
        self.client, self.operator = Client(pc_port), Operator(pc_port)
        self.pc_status, self.error, self.last_ui = None, None, 0
        self.stop = threading.Event()
        self.journal = (output/'observations.jsonl').open('x', encoding='utf-8')
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
        return dict(mode='live', fake_gps=False, error=self.error,
                    live=dict(source='real_boards_USB_power',host_business_generator=False,serial_opens=0),
                    capabilities=dict(demo_control=False,fake_gps_toggle=False,lora_topology=True))

    def snapshot(self):
        self.touch()
        value=self.live.snapshot()
        value.update(view_mode='live',fake_gps=False,radio_source='actual_board_observation_only',business_source='board_field_agent',studio=self.status())
        return value

    def history(self, after):
        self.touch()
        return self.live.history(after)

    def close(self):
        self.stop.set()
        self.thread.join(8)
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
            value=self.server.state.status()
            if isinstance(self.server.remote,SerialTopology):
                value['live']['serial_opens']=1 if self.server.remote.serial_open else 0
                value['live']['source']='node_serial_lora'
            return self.reply(200,value)
        if path=='/api/v1/remote/health' and self.server.remote:
            self.server.remote.topology()
            return self.reply(200,self.server.remote.info)
        if path=='/api/v1/lora/topology':
            if self.server.remote:return self.reply(200,self.server.remote.topology())
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
        return self.reply(404, {'error':'控制入口未启用'})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--port',type=int,default=8794)
    p.add_argument('--pc-port',type=int,default=8791)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--production-output',action='store_true',help='allow a new explicit production run directory')
    p.add_argument('--fleet',type=Path,help='same validated fleet configuration passed by launcher')
    p.add_argument('--registry',type=Path,help='read-only runtime node registry')
    p.add_argument('--recovery-file',type=Path,help='read-only supervisor health state')
    p.add_argument('--topology-port',type=int,default=8780)
    p.add_argument('--gateway-mode',choices=['remote','legacy_local','node_serial'],default='legacy_local')
    p.add_argument('--gateway-eui')
    p.add_argument('--node-mac')
    p.add_argument('--serial-location')
    p.add_argument('--serial-port')
    p.add_argument('--serial-lease-dir')
    p.add_argument('--candidate-host',action='append',default=[])
    p.add_argument('--remote-http-port',type=int,default=8780)
    p.add_argument('--discovery-port',type=int,default=8781)
    p.add_argument('--stop-file',type=Path)
    args=p.parse_args()
    out=args.output.resolve()
    fleet_path=args.fleet or (ROOT/'data/fleet.json' if (ROOT/'data/fleet.json').is_file() else ROOT/'config/fleet.default.json')
    try:
        read_nodes(fleet_path)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        p.error('fleet configuration invalid: '+str(exc))
    out.mkdir(parents=True,exist_ok=False)
    state=Studio(out,args.pc_port)
    server=Gateway(('127.0.0.1',args.port),state,ROOT/'assets/mobile_gateway')
    server.RequestHandlerClass=StudioHandler
    server.fleet_path=fleet_path
    server.registry_path=args.registry or ROOT/'data/registry.json'
    server.recovery_path=args.recovery_file or ROOT/'data/studio-recovery.json'
    server.gateway_topology=f'http://127.0.0.1:{args.topology_port}/api/v1/lora/topology'
    if args.gateway_mode=='remote' and not args.gateway_eui:p.error('remote gateway EUI required')
    if args.gateway_mode=='node_serial' and not args.node_mac:p.error('节点1 MAC 必需')
    server.remote=RemoteGateway(args.gateway_eui,args.candidate_host,args.remote_http_port,args.discovery_port) if args.gateway_mode=='remote' else SerialTopology(args.node_mac,args.serial_location,args.serial_port,args.serial_lease_dir) if args.gateway_mode=='node_serial' else None
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
              lora_serial_owner='none; gateway UDP service owns reception',
              host_physical_business_generator=False)
    (out/'PROCESS.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    print(json.dumps(meta),flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    finally:
        done.set()
        server.server_close()
        if args.gateway_mode=='node_serial' and server.remote:server.remote.close()
        state.close()


if __name__=='__main__':
    main()
