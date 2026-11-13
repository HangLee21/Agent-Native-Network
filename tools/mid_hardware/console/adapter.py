"""Bounded hardware backend for the localhost console; previews never call execute."""
import hashlib
import importlib.util
import json
import math
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lease import ROOT, status as lease_status

def _labels():
    return json.loads((ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json').read_text())['labels']

def _cleanup(wire,prefix,deadline):
    stopped,errors={},[]
    try:
        for mac in wire.ports:
            try:
                keep=[]
                for item in wire.tx[mac]:
                    if item['command']['cmd']=='send' and item['offset']==0:
                        wire.record(dict(direction='host_failure',nonce=item['nonce'],reason='operator_or_timeout_before_dispatch'))
                    else:keep.append(item)
                wire.tx[mac]=keep
                wire.submit(mac,dict(cmd='stop',nonce=prefix+'-stop-'+mac[-2:]))
            except Exception as exc:errors.append(dict(node=mac,stage='stop_submit',error=repr(exc)))
        end=min(deadline,time.monotonic()+4.5);queried=set()
        while time.monotonic()<end:
            try:wire.poll()
            except Exception as exc:errors.append(dict(stage='cleanup_poll',error=repr(exc)));break
            for mac in wire.ports:
                reply=wire.replies.get(prefix+'-stop-'+mac[-2:])
                if reply and mac not in queried:
                    queried.add(mac);wire.submit(mac,dict(cmd='stats',nonce=prefix+'-final-'+mac[-2:]))
                final=wire.replies.get(prefix+'-final-'+mac[-2:])
                if final:stopped[mac]=all(final.get(k)is False for k in ('radio','stopping','locked_until_reset')) and final.get('queue_depth')==0
            if len(stopped)==len(wire.ports) and all(stopped.values()):break
            time.sleep(.002)
    except Exception as exc:errors.append(dict(stage='cleanup',error=repr(exc)))
    finally:
        try:wire.close()
        except Exception as exc:
            errors.append(dict(stage='close',error=repr(exc)))
            for handle in [*wire.ports.values(),*wire.raw.values(),wire.log]:
                try:handle.close()
                except Exception as close_error:errors.append(dict(stage='independent_close',error=repr(close_error)))
            if wire.lease:
                try:wire.lease.__exit__();wire.lease=None
                except Exception as lease_error:errors.append(dict(stage='lease_release',error=repr(lease_error)))
    return stopped,errors

def status(publisher='A'):
    state = lease_status()
    bindings = json.loads((ROOT/'hardware/eora_hub_400tb/bindings.local.json').read_text())['bindings']
    labels = _labels()
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
    except ImportError:
        return dict(state, ready_nodes=[], run_available=False, reason='pyserial_unavailable_in_service_interpreter')
    ready, boots, versions, bauds = [], {}, {}, {}
    for label, mac in labels.items():
        b = next(x for x in bindings if x['node_id'] == mac)
        visible = any(p.device == b['port'] and p.vid == b['vid'] and p.pid == b['pid'] and p.location == b['location'] for p in ports)
        if visible and b.get('last_verified_boot_id') and b.get('verified_build_id'):
            ready.append(label)
            boots[label] = b['last_verified_boot_id']
            versions[label] = b['verified_build_id']
            bauds[label] = b.get('runtime_uart_baud', 115200)
    return dict(state, ready_nodes=ready, boots_by_label=boots, build_by_label=versions,
                uart_baud_by_label=bauds, publisher=publisher, publisher_boot=boots.get(publisher),
                run_available=not state['busy'] and publisher in ready,
                state_basis='USB presence and last verified info; execute rechecks live info under lease',
                live_info_recheck_required=True)

def execute(plan, output, stop_event, on_event=None, timeout=60):
    """Call in an E2 worker thread. stop_event is threading.Event, no second writer."""
    assert 0 < timeout <= 60
    assert plan.get('ok') is True
    labels = _labels()
    src, dst, count = plan['src'], plan['dst'], plan['count']
    user_payload = plan.get('payload_hex')
    if user_payload is not None:
        if not isinstance(user_payload,str) or len(user_payload)%2 or len(user_payload)>320 or any(c not in '0123456789abcdefABCDEF' for c in user_payload):
            raise ValueError('payload_hex must encode 0..160 bytes')
        user_payload=bytes.fromhex(user_payload).hex()
    assert src in labels and dst in labels and src != dst and type(count) is int and 1 <= count <= 10
    update = plan['network_update']
    assert update['schema'] == 'mid.network_update.v1'
    nodes = update['nodes']
    assert 2 <= len(nodes) <= 5 and len(set(nodes)) == len(nodes) and set(nodes) <= set(labels.values())
    assert update['flows'] == [dict(src=labels[src], dst=labels[dst])]
    for row in update['routes']:
        assert row['node'] in nodes and row['src'] == labels[src] and row['dst'] == labels[dst]
        for gateway in row['gateways']:
            assert gateway['node'] in nodes and gateway['node'] != row['node']
            assert type(gateway['weight']) in [int, float] and math.isfinite(gateway['weight']) and gateway['weight'] >= 0
    out = Path(output).resolve()
    assert any(out.is_relative_to(ROOT/'simulation/outputs'/task) for task in ('H-007','H-013'))
    out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(ROOT/'tools/mid_hardware/replacement'))
    from wire import Wire
    wire = None
    infos, stopped, packets = {}, {}, []
    result = dict(status='failed', run_id=out.name, evidence_kind='hardware_measured', requested=count,
                  mode=plan['mode'], model=plan.get('model'), expected_chain=plan.get('chain'))
    begin = time.monotonic()
    prefix = hashlib.sha256(out.name.encode()).hexdigest()[:12]
    deadline = begin+timeout
    data_start_ns = None
    def note(obj):
        if on_event:
            try:
                on_event(obj)
            except Exception:
                pass
    def wait(mac, command):
        if stop_event.is_set():
            raise RuntimeError('operator_stop')
        remaining = deadline-time.monotonic()-5
        if remaining <= 0:
            raise RuntimeError('execution_timeout')
        return wire.wait_command(mac, command, min(2, remaining))
    try:
        wire = Wire(out, {k:v for k,v in labels.items() if v in nodes}, owner='H007')
        wire.metadata = dict(run_id=out.name, task_id='H-007')
        for mac in nodes:
            info = wait(mac, dict(cmd='info', nonce=prefix+'-info-'+mac[-2:]))
            assert info['node_id'] == mac and info['mode'] == 'idle' and not any(info[k] for k in ['radio','stopping','locked_until_reset'])
            infos[mac] = info
        assert len({i['build_id'] for i in infos.values()}) == 1, 'mixed_firmware_versions'
        assert len({i.get('uart_baud',115200) for i in infos.values()}) == 1, 'mixed_application_baud'
        (out/'infos.json').write_text(json.dumps(infos, indent=2), encoding='utf-8')
        (out/'plan.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        publisher = labels[src]
        boot = infos[publisher]['boot_id']
        for mac in nodes:
            wait(mac, dict(cmd='start', nonce=prefix+'-start-'+mac[-2:], publisher=publisher, publisher_boot=boot))
        spec = importlib.util.spec_from_file_location('console_original_bridge',ROOT/'.local/mid/E1-016/package-03/source/tools/mid_baseline/bridge/bridge.py')
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
        frame = bridge.pack(update, publisher, boot, 1).hex()
        wait(publisher, dict(cmd='config', nonce=prefix+'-config', frame_hex=frame))
        gate = min(deadline-5, time.monotonic()+5)
        while time.monotonic() < gate:
            wire.poll()
            if stop_event.is_set():
                raise RuntimeError('operator_stop')
            if all(any(z['event'].get('event') == 'config_applied' and z['event'].get('node_id') == mac and z['event'].get('origin') == publisher and z['event'].get('seq') == 1 for z in wire.events) for mac in nodes):
                break
            time.sleep(.002)
        else:
            raise RuntimeError('configuration_not_observed_on_participants')
        data_start_ns = time.monotonic_ns()
        for i in range(count):
            target = data_start_ns/1e9+i*.5
            while time.monotonic() < target:
                wire.poll()
                if stop_event.is_set():
                    raise RuntimeError('operator_stop')
                time.sleep(.002)
            if time.monotonic() >= deadline-7 or stop_event.is_set():
                raise RuntimeError('operator_stop_or_execution_timeout')
            nonce = f'{prefix}-pkt-{i}'
            payload = user_payload if user_payload is not None else f'{out.name[-22:]}-{i:03d}'.ljust(32,'.').encode().hex()
            packets.append(dict(index=i, nonce=nonce, payload_hex=payload, identity=None, destination_received=False))
            wire.submit(publisher, dict(cmd='send', nonce=nonce, dst=labels[dst], payload_hex=payload), role='console_source')
            note(dict(kind='scheduled', index=i))
        drain = min(deadline-5, time.monotonic()+2)
        while time.monotonic() < drain:
            wire.poll()
            if stop_event.is_set():
                break
            time.sleep(.002)
        result['status'] = 'stopped' if stop_event.is_set() else 'completed'
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        if wire is not None:
            stopped,cleanup_errors=_cleanup(wire,prefix,deadline)
            if cleanup_errors:result.update(status='failed',cleanup_errors=cleanup_errors)
            events = [z['event'] for z in wire.events if data_start_ns is not None and z['host_monotonic_ns'] >= data_start_ns]
            queued = [e for e in events if e.get('event') == 'tx_queued' and e.get('node_id') == labels[src] and e.get('origin') == labels[src]]
            admission = iter(queued)
            for packet in packets:
                reply = wire.replies.get(packet['nonce'])
                packet['command_result'] = reply
                if reply and reply.get('ok'):
                    e = next(admission, None)
                    if e:
                        identity = [e.get(k) for k in ['origin','origin_boot','seq','dst']]
                        packet['identity'] = identity
                        same = [e for e in events if [e.get(k) for k in ['origin','origin_boot','seq','dst']] == identity]
                        packet['actual_edges'] = [dict(node=e['node_id'],next_hop=e['next_hop']) for e in same if e.get('event')=='tx_submit' and e.get('next_hop')]
                        packet['relays'] = [e['node_id'] for e in same if e.get('event') == 'rx_relay']
                        packet['destination_received'] = any(e.get('event')=='rx_local' and e.get('node_id')==labels[dst] and e.get('payload_hex')==packet['payload_hex'] for e in same)
                note(dict(kind='packet_result', **packet))
        result.update(packets=packets, destination_unique_received=sum(p['destination_received'] for p in packets),
                      stop_confirmed=stopped, all_ports_closed=wire is None or all(not p.is_open for p in wire.ports.values()),
                      elapsed_s=time.monotonic()-begin, actual_infos=infos,
                      limitations=['Model preview is not a link measurement.','Only destination rx_local proves receipt; actual_edges are logged transmissions, not intended paths.'])
        if out.joinpath('native.jsonl').exists():
            result['log_sha256'] = hashlib.sha256((out/'native.jsonl').read_bytes()).hexdigest()
        (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        manifest = json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
        manifest.update(template_only=False, task_id='H-007',run_id=out.name,output_directory=str(out),status=result['status'],budget={'max_seconds':timeout,'max_packets':10},limitations=result['limitations'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return result
