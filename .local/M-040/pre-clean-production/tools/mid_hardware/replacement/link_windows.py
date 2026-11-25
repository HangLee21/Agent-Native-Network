"""Make actual arrival-time link windows. Incomplete UART captures are invalid."""
import collections
import hashlib
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

def main():
    base = ROOT/'simulation/outputs/H-006'
    out = base/'20261107-link-service-windows'
    out.mkdir(exist_ok=False)
    windows, seconds, runs = [], [], []
    for g in sorted(base.glob('20261107-L*-link-*')):
        if not (g/'result.json').exists():
            continue
        plan = json.loads((g/'plan.json').read_text())
        result = json.loads((g/'result.json').read_text())
        log = g/'native.jsonl'
        objects = [json.loads(s) for s in log.read_text().splitlines()]
        digest = hashlib.sha256(log.read_bytes()).hexdigest()
        t0 = next(x['host_monotonic_ns'] for x in objects if x.get('event') == 'measurement_start')
        commands, owners, received = {}, {}, {}
        admissions = collections.defaultdict(collections.deque)
        issues = []
        def identity(e):
            return tuple(e.get(k) for k in ['origin','origin_boot','seq','dst'])
        for number, o in enumerate(objects, 1):
            if o.get('direction') == 'host_tx' and o['command'].get('cmd') == 'send':
                commands[o['command']['nonce']] = dict(o, line=number)
            if o.get('direction') != 'device_rx':
                continue
            e = o['event']
            if e.get('event') == 'tx_queued' and e.get('origin') == e.get('node_id'):
                admissions[e['node_id']].append((identity(e),o['host_monotonic_ns'],number))
            elif e.get('cmd') == 'send' and e.get('event') == 'command_result':
                cmd = commands.get(e.get('nonce'))
                if cmd is None:
                    issues.append('unassociated_send_reply')
                elif e.get('ok') and admissions[e['node_id']]:
                    key, at, line = admissions[e['node_id']].popleft()
                    owners[key] = dict(command=cmd, admission_ns=at, admission_line=line, reply_line=number)
                else:
                    issues.append('send_rejected_or_missing_admission')
            elif e.get('event') == 'rx_local':
                received.setdefault(identity(e), dict(event=e, at=o['host_monotonic_ns'],line=number))
        submitted = {identity(o['event']) for o in objects if o.get('direction')=='device_rx' and o['event'].get('event')=='tx_submit' and o['event'].get('origin')==o['event'].get('node_id') and o['event'].get('dst')}
        if any(admissions.values()):
            issues.append('unassociated_admission')
        valid = bool(result['success'] and all(result['stop_confirmed'].values()) and len(commands)==200 and len(owners)==200 and not issues)
        payload_ok = all(k not in received or received[k]['event'].get('payload_hex')==v['command']['command']['payload_hex'] for k,v in owners.items())
        valid = valid and payload_ok
        flows = []
        for fnum, flow in enumerate(plan['flows']):
            src, dst = flow['source'], flow['destination']
            start = t0+fnum*10000000000
            mine = {k:v for k,v in owners.items() if k[0]==src and k[3]==dst}
            arrivals = {k:v for k,v in received.items() if k in mine and v['event'].get('payload_hex')==mine[k]['command']['command']['payload_hex']}
            flow_valid = valid and len(mine)==100 and all(k in submitted for k in mine)
            for width, target in [(1,seconds),(2,windows)]:
                for index in range(10//width):
                    lo, hi = start+index*width*1000000000, start+(index+1)*width*1000000000
                    rx = sum(lo <= v['at'] < hi for v in arrivals.values())
                    dispatch = sum(lo <= v['command']['host_monotonic_ns'] < hi for v in mine.values())
                    accepted = sum(lo <= v['admission_ns'] < hi for v in mine.values())
                    target.append(dict(src=src,dst=dst,window_s=width,window_index=index,
                                       window_start_host_ns=lo,window_end_host_ns=hi,payload_bytes=32,
                                       scheduled=10*width,dispatched=dispatch,accepted=accepted,rx_unique=rx,
                                       bits_per_s=rx*256/width,valid=flow_valid,
                                       nominal_offered_pps=10,actual_dispatch_pps=dispatch/width,
                                       actual_accepted_pps=accepted/width,raw_source=str(log),raw_sha256=digest,
                                       scope='Observed service at stated injected load; not saturated capacity or calibrated channel uncertainty.'))
            flows.append(dict(src=src,dst=dst,scheduled=100,accepted=len(mine),submitted=sum(k in submitted for k in mine),
                              rx_unique=len(arrivals),rx_after_window=sum(v['at']>=start+10000000000 for v in arrivals.values()),valid=flow_valid))
        runs.append(dict(run=str(g),flows=flows,issues=issues,RF_window_seconds=result['RF_window_seconds'],valid=valid))
    assert len(runs)==10, 'Need all ten pairs; no partial model silently produced'
    (out/'windows-2s.json').write_text(json.dumps(dict(windows=windows),indent=2))
    (out/'windows-1s.json').write_text(json.dumps(dict(windows=seconds),indent=2))
    per_direction = []
    for src,dst in sorted({(w['src'],w['dst']) for w in windows}):
        rows=[w for w in windows if (w['src'],w['dst'])==(src,dst)]
        values=[w['bits_per_s'] for w in rows]
        per_direction.append(dict(src=src,dst=dst,valid=all(w['valid'] for w in rows),window_s=2,
                                  mean_bps=statistics.mean(values),sample_variance=statistics.variance(values),samples=5))
    summary=dict(status='complete' if all(r['valid'] for r in runs) else 'invalid_windows_retained',
                 directions=per_direction,runs=runs,RF_window_seconds=sum(r['RF_window_seconds'] for r in runs),
                 planned=2000,accepted=sum(f['accepted'] for r in runs for f in r['flows']),
                 destination_unique=sum(f['rx_unique'] for r in runs for f in r['flows']),
                 old_failed_windows_excluded_with_reason='Preserved separately; UART corruption and absent A, no valid complete window.',
                 limitations=['All-direct success only describes10pps32B load; no capacity/QoS claim.','Host arrival windows contain serial capture latency, not synchronized RF delay.'])
    (out/'result.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['runs','directions']}))

if __name__ == '__main__':
    main()
