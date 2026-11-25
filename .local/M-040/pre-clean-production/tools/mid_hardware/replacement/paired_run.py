"""One 60-second arm. Source deadlines continue through solve/configuration."""
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path
from wire import ROOT, Wire
sys.path.insert(0, str(ROOT/'tools/mid_baseline/validation/replacement'))
from contract import slots

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def main():
    ap = argparse.ArgumentParser()
    for key in ['initial', 'scenario', 'model', 'output']:
        ap.add_argument('--'+key, type=Path, required=True)
    ap.add_argument('--pair', type=int, choices=range(1, 6), required=True)
    ap.add_argument('--arm', choices=['fixed', 'replan'], required=True)
    x = ap.parse_args()
    out = x.output.resolve()
    assert out.is_relative_to(ROOT/'simulation/outputs/H-006')
    out.mkdir(parents=True, exist_ok=False)
    labels = load(ROOT/'hardware/mid_baseline/BOARD_LABELS_20261107_ABCDE.json')['labels']
    scenario = load(x.scenario)
    assert scenario['duration_s'] == 60 and scenario['trigger_target_s'] == 20
    initial_result = load(x.initial/'result.json')
    assert initial_result['status'] == 'optimal'
    initial = load(x.initial/'command.json')
    result = dict(started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), pair=x.pair,
                  arm=x.arm, success=False, source_plan_count=240, radio_reset=False)
    wire = None
    worker = None
    logs = []
    rf_start = None
    start_ns = None
    try:
        wire = Wire(out, labels)
        wire.metadata = dict(run_id=out.name, pair_id=x.pair, arm=x.arm)
        infos = {}
        for label, mac in labels.items():
            i = wire.wait_command(mac, dict(cmd='info', nonce='info-'+label))
            assert i['node_id'] == mac and i['device_label'] == label and i['mode'] == 'idle'
            assert not any(i[k] for k in ['radio', 'stopping', 'locked_until_reset'])
            infos[label] = i
        assert len({i['build_id'] for i in infos.values()}) == 1
        boot = infos['A']['boot_id']
        assert initial_result['request']['publisher_boot'] == boot
        (out/'infos.json').write_text(json.dumps(infos, indent=2))
        rf_start = time.monotonic()
        for label in 'ABCD':
            wire.wait_command(labels[label], dict(cmd='start', nonce='start-'+label,
                              publisher=labels['A'], publisher_boot=boot))
        wire.wait_command(labels['A'], initial)
        end = time.monotonic()+5
        while time.monotonic() < end:
            wire.poll()
            if all(any(z['event'].get('event') == 'config_applied' and z['event'].get('node_id') == labels[k] and z['event'].get('origin')==labels['A'] and z['event'].get('origin_boot')==boot and z['event'].get('seq')==initial_result['request']['seq']
                       for z in wire.events) for k in 'ABCD'):
                break
            time.sleep(.002)
        else:
            raise RuntimeError('Initial configuration not observed on ABCD')
        jobs = []
        for item in slots(x.pair, x.arm, 0):
            d = item['direction']
            jobs.append(dict(at_s=item['slot']*.5, source='AB'[d], destination='BA'[d],
                             direction_id=d, slot=item['slot'], nonce=item['nonce'], payload_hex=item['payload_hex']))
        (out/'source_plan.json').write_text(json.dumps(jobs, indent=2))
        start_ns = time.monotonic_ns()
        start = start_ns/1e9
        wire.record(dict(kind='annotation', name='run_start', direction='host_marker', event='business_start', pair=x.pair, arm=x.arm,
                         duration_s=60, target_packets_per_direction_per_second=2))
        next_job = 0
        triggered = False
        requested = False
        worker_done = False
        event_ready = False
        c_stats_requested = False
        trigger_time = None
        processed_events = 0
        first_spare = False
        while time.monotonic()-start < 60:
            now = time.monotonic()
            wire.poll()
            while processed_events < len(wire.events):
                captured = wire.events[processed_events]
                processed_events += 1
                event = captured['event']
                ref = dict(path=str(out/'native.jsonl'), line=captured['capture_line'])
                if event.get('event') == 'config_applied':
                    wire.record(dict(kind='annotation', name='config_applied', node_id=event['node_id'],
                                     raw_source=ref, original_host_ns=captured['host_monotonic_ns'],
                                     publisher=event.get('origin'), seq=event.get('seq')))
                if triggered and not first_spare and event.get('node_id') == labels['E'] and event.get('event') == 'rx_relay':
                    first_spare = True
                    wire.record(dict(kind='annotation', name='spare_first_relay', raw_source=ref,
                                     original_host_ns=captured['host_monotonic_ns'], identity={k:event.get(k) for k in ['origin','origin_boot','seq','dst']}))
            # No command result, solver, route gate or log operation advances this plan.
            while next_job < len(jobs) and jobs[next_job]['at_s'] <= now-start:
                job = jobs[next_job]
                nonce = job['nonce']
                wire.record(dict(kind='planned', direction='source_schedule',
                                 planned_ns=start_ns+int(job['at_s']*1e9), **job))
                wire.submit(labels[job['source']], dict(cmd='send', nonce=nonce,
                            dst=labels[job['destination']], payload_hex=job['payload_hex']), role='source')
                next_job += 1
            if not triggered and now-start >= 20:
                triggered = True
                trigger_time = now
                activity = {k: any(e['event'].get('node_id') == labels[k] and
                                   e['event'].get('event') == 'rx_relay' for e in wire.events) for k in 'CD'}
                result['pretrigger_relay_observed'] = activity
                wire.record(dict(kind='annotation', name='trigger_requested', direction='host_marker', event='external_event_requested',
                                 relay_observed=activity, target_s=20))
                wire.record(dict(kind='annotation', name='retire_requested', direction='host_marker', node_id=labels['C']))
                wire.submit(labels['C'], dict(cmd='stop', nonce='event-C-stop'))
                wire.record(dict(kind='annotation', name='spare_start_requested', direction='host_marker', node_id=labels['E']))
                wire.submit(labels['E'], dict(cmd='start', nonce='event-E-start',
                            publisher=labels['A'], publisher_boot=boot))
            c = wire.replies.get('event-C-stats', wire.replies.get('event-C-stop', {}))
            e = wire.replies.get('event-E-start', {})
            stopped = c.get('ok') and all(c.get(k) is False for k in ['radio', 'stopping', 'locked_until_reset'])
            if triggered and not stopped and c.get('ok') and not c_stats_requested:
                wire.submit(labels['C'], dict(cmd='stats', nonce='event-C-stats'))
                c_stats_requested = True
            if triggered and stopped and e.get('ok') and e.get('radio') is True and not event_ready:
                event_ready = True
                cn = 'event-C-stats' if 'event-C-stats' in wire.replies else 'event-C-stop'
                wire.record(dict(kind='annotation', name='retire_effective', direction='host_marker',
                                 raw_source=wire.reply_sources[cn], original_host_ns=wire.reply_sources[cn]['original_host_ns']))
                wire.record(dict(kind='annotation', name='spare_active', direction='host_marker',
                                 raw_source=wire.reply_sources['event-E-start'], original_host_ns=wire.reply_sources['event-E-start']['original_host_ns']))
                wire.record(dict(direction='host_marker', event='external_event_confirmed',
                                 exited='C', replacement='E', members=list('ABDE')))
            if x.arm == 'replan' and event_ready and not requested:
                requested = True
                request = dict(scenario=str(x.scenario.resolve()), model=str(x.model.resolve()), phase='after',
                               members=list('ABDE'), arm='replan', demand=512, qos=.9, publisher_boot=boot,
                               seq=x.pair*10000+100, nonce=f'p{x.pair}-after')
                (out/'solve-request.json').write_text(json.dumps(request, indent=2))
                command = [str(ROOT/'.local/mid/E1-016/venv/Scripts/python.exe'),
                           str(ROOT/'tools/mid_baseline/planner/replacement/online.py'), 'solve',
                           '--request', str(out/'solve-request.json'), '--output', str(out/'after-solve')]
                logs = [(out/'solve.stdout.txt').open('xb'), (out/'solve.stderr.txt').open('xb')]
                wire.record(dict(kind='annotation', name='solve_start', direction='host_marker', event='solve_process_start', request=request))
                worker = subprocess.Popen(command, cwd=ROOT, stdout=logs[0], stderr=logs[1])
                worker_started = now
            if worker is not None and not worker_done:
                code = worker.poll()
                if code is None and now-worker_started > 15:
                    worker.kill()
                    wire.record(dict(direction='host_marker', event='solve_timeout'))
                    worker_done = True
                elif code is not None:
                    worker_done = True
                    wire.record(dict(kind='annotation', name='solve_end', direction='host_marker', event='solve_process_end', exit_code=code))
                    if code == 0:
                        wire.record(dict(kind='annotation', name='config_publish_start', direction='host_marker', source_file=str(out/'after-solve/command.json')))
                        wire.submit(labels['A'], load(out/'after-solve/command.json'))
            time.sleep(.002)
        result['source_schedule_emitted'] = next_job
        result['external_event_confirmed'] = event_ready
        result['trigger_actual_s'] = trigger_time-start if trigger_time else None
        wire.record(dict(kind='annotation', name='run_end', direction='host_marker', event='business_end', scheduled=next_job))
        drain = time.monotonic()+1
        while time.monotonic() < drain:
            wire.poll()
            time.sleep(.002)
        result['success'] = next_job == 240 and event_ready
    except Exception as exc:
        result['error'] = repr(exc)
    finally:
        if worker is not None:
            if worker.poll() is None:
                worker.kill()
            worker.wait(timeout=3)
        for f in logs:
            f.close()
        stopped = {}
        if wire is not None:
            queried = set()
            for label, mac in labels.items():
                try:
                    wire.submit(mac, dict(cmd='stop', nonce='cleanup-'+label))
                except Exception:
                    stopped[label] = False
            cleanup_end = min(time.monotonic()+10, rf_start+80 if rf_start is not None else time.monotonic()+4)
            try:
                while time.monotonic() < cleanup_end:
                    wire.poll(ignore_port_errors=True)
                    for label, mac in labels.items():
                        reply = wire.replies.get('cleanup-'+label)
                        if reply and label not in queried:
                            queried.add(label)
                            wire.submit(mac, dict(cmd='stats',nonce='cleanup-stats-'+label))
                        state = wire.replies.get('cleanup-stats-'+label)
                        if state:
                            stopped[label] = all(state.get(k) is False for k in ['radio','stopping','locked_until_reset'])
                    if all(stopped.get(k,False) for k,m in labels.items() if wire.ports[m].is_open):
                        break
                    time.sleep(.002)
            except Exception as exc:
                result['cleanup_error'] = repr(exc)
            # Reopen only lost handles once for safety cleanup, never resend data.
            for label, mac in labels.items():
                if wire.ports[mac].is_open or mac not in wire.port_errors:
                    continue
                try:
                    if rf_start is not None and time.monotonic() >= rf_start+78:
                        break
                    for item in wire.tx[mac]:
                        wire.record(dict(direction='host_failure',node_id=mac,nonce=item['nonce'],reason='disconnected_port_no_data_retry'))
                    wire.tx[mac]=[]
                    wire.buffers[mac].clear()
                    wire.ports[mac].open()
                    i=wire.wait_command(mac,dict(cmd='info',nonce='reopen-info-'+label),.8)
                    assert i['node_id']==mac
                    wire.wait_command(mac,dict(cmd='stop',nonce='reopen-stop-'+label),.8)
                    state=wire.wait_command(mac,dict(cmd='stats',nonce='reopen-stats-'+label),.8)
                    stopped[label]=all(state.get(k)is False for k in ['radio','stopping','locked_until_reset'])
                except Exception as exc:
                    result.setdefault('reopen_cleanup_errors',{})[label]=repr(exc)
            for label in labels:
                stopped.setdefault(label,False)
            wire.close()
        result.update(stop_confirmed=stopped, all_ports_closed=wire is None or all(not p.is_open for p in wire.ports.values()),
                      RF_host_window_seconds=time.monotonic()-rf_start if rf_start else 0,
                      finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        (out/'result.json').write_text(json.dumps(result, indent=2))
        if wire is not None and start_ns is not None:
            log = out/'native.jsonl'
            ctx = dict(schema='mid.replacement.context.v1', run_id=out.name, pair_id=x.pair, arm=x.arm,
                       design_version='M019-E2-v1', schedule_t0_ns=start_ns, duration_s=60,
                       planned_interval_ns=500000000, measurement_clock='host_monotonic',
                       evidence_kind='hardware_measured', build_id=infos['A']['build_id'],
                       endpoints={k:labels[k] for k in 'AB'}, boots={labels[k]:i['boot_id'] for k,i in infos.items()},
                       status='capture_complete' if result['success'] and all(stopped.values()) else 'capture_incomplete',
                       endpoint_coverage={labels[k]:result['success'] and stopped.get(k,False) for k in 'AB'},
                       stop_confirmed={labels[k]:v for k,v in stopped.items()}, all_ports_closed=result['all_ports_closed'],
                       log_sha256={str(log):sha(log)}, initial_condition_id=f'pair-{x.pair:02d}-common-initial',
                       shared_inputs=dict(model_sha256=sha(x.model), initial_table_sha256=sha(x.initial/'network_update.json'),
                                          scenario_sha256=sha(x.scenario), workload_id='M019-E2-v1-RPL1-32B-2pps-60s'))
            (out/'run_context.json').write_text(json.dumps(ctx,indent=2))
        print(json.dumps(result))
    return not result['success']

if __name__ == '__main__':
    raise SystemExit(main())
