"""Bounded, GET-only observation of an existing local LoRa receiver. No fixtures or control requests."""
import argparse
import datetime as dt
import http.client
import json
import math
import time
from pathlib import Path
from urllib.parse import urlsplit


def now():
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat()


def reject_fake(raw):
    pending = [raw]
    while pending:
        value = pending.pop()
        if isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, dict):
            if any(value.get(k) is True for k in ('mock', 'synthetic', 'fake_gps')) or value.get('provenance') == 'synthetic':
                raise ValueError('Explicit synthetic marker in live response')
            if any(str(value.get(k, '')).lower() in ('mock', 'demo', 'simulation', 'replay') for k in ('mode', 'view_mode')):
                raise ValueError('Explicit demo mode in live response')
            if str(value.get('source', '')).lower().startswith(('synthetic', 'mock', 'demo', 'simulat')):
                raise ValueError('Explicit synthetic source in live response')
            pending.extend(value.values())


def assess_stability(samples):
    """Separate successful reception from restart/time-out-free sampled operation."""
    ids = {n['id'] for s in samples for n in s['nodes']}
    boots = {ident: set() for ident in ids}
    missing, timed_out, unknown_boot = set(), set(), set()
    for sample in samples:
        missing.update(ids - {n['id'] for n in sample['nodes']})
        for node in sample['nodes']:
            ident = node['id']
            boots[ident].add(node.get('boot'))
            if node.get('boot') is None:
                unknown_boot.add(ident)
            age = node.get('report_age_ms')
            if not isinstance(age, (int, float)) or not 0 <= age <= sample.get('report_timeout_ms', 30000):
                timed_out.add(ident)
    changed = sorted(ident for ident, values in boots.items() if len(values) > 1)
    healthy_gateway = bool(samples) and all(s.get('gateway_observed') is True and s.get('receiver_state') == 'receiving' for s in samples)
    return {'stability_check_passed': bool(ids) and healthy_gateway and not (changed or missing or timed_out or unknown_boot),
            'boot_changed_nodes': changed, 'report_timeout_nodes': sorted(timed_out),
            'missing_sample_nodes': sorted(missing), 'unknown_boot_nodes': sorted(unknown_boot)}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--url', default='http://127.0.0.1:8780/api/v1/lora/topology')
    ap.add_argument('--output', required=True)
    ap.add_argument('--seconds', type=float, default=60)
    ap.add_argument('--interval', type=float, default=5)
    args = ap.parse_args()
    u = urlsplit(args.url)
    if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.path != '/api/v1/lora/topology' or u.query or u.fragment or u.username or u.password:
        ap.error('Only the explicitly selected local topology GET endpoint is allowed')
    if not all(math.isfinite(x) for x in (args.seconds, args.interval)) or not 5 <= args.seconds <= 300 or not 1 <= args.interval <= args.seconds:
        ap.error('Use a bounded 5..300 second window and interval >=1 second')
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    report = {'started_at': now(), 'endpoint': args.url, 'method': 'GET', 'fixtures_used': False,
              'provenance': 'unknown: legacy protocol has no provenance attestation', 'control_requests_sent': 0,
              'sampling_window_s': args.seconds, 'interval_s': args.interval, 'samples': [], 'nodes': {}, 'errors': []}
    observed = {}
    start = time.monotonic()
    for index in range(int(args.seconds // args.interval) + 1):
        time.sleep(max(0, start + index * args.interval - time.monotonic()))
        stamp = now()
        c = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=4)
        try:
            c.request('GET', u.path, headers={'Accept': 'application/json', 'Connection': 'close'})
            r = c.getresponse()
            body = r.read(2 * 1024 * 1024 + 1)
            if len(body) > 2 * 1024 * 1024:
                raise ValueError('Response exceeds 2 MiB')
            (out / ('%03d-body.json' % index)).write_bytes(body)
            if r.status != 200:
                raise ValueError('HTTP %s' % r.status)
            raw = json.loads(body)
            reject_fake(raw)
            if raw.get('schema') != 'lora.topology.v1' or not isinstance(raw.get('reports'), list):
                raise ValueError('Unexpected live topology schema')
            if index == 0:
                (out / 'first-pretty.json').write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding='utf-8')
            rx = raw['receiver']; threshold = rx.get('recent_threshold_ms', 30000)
            item = {'at': stamp, 'elapsed_s': round(time.monotonic() - start, 3), 'frames': rx.get('frames'),
                    'bad_frames': rx.get('bad_frames'), 'gateway_observed': rx.get('gateway_observed'),
                    'receiver_state': rx.get('state'), 'worker_state': rx.get('worker_state'), 'report_timeout_ms': threshold, 'nodes': []}
            for row in raw['reports']:
                n = row['report']; ident = n['observer_id']; seq = (n.get('observer_boot'), n.get('report_seq'))
                observed.setdefault(ident, set()).add(seq)
                gps = row.get('gps') or n.get('gps') or {}; status = row.get('status') or n.get('status') or {}
                fields = {'id': ident, 'node_number': n.get('node_number'), 'boot': seq[0], 'sequence': seq[1],
                          'report_age_ms': row.get('pc_receive_age_ms'), 'neighbors': len(n.get('neighbors') or []),
                          'gps_valid': gps.get('valid'), 'gps_age_ms': row.get('gps_age_ms'), 'gps': gps,
                          'lora': row.get('lora'), 'queue_depth': status.get('queue_depth'), 'tx_drops': status.get('tx_drops')}
                item['nodes'].append(fields)
                node = report['nodes'].setdefault(ident, {'node_number': n.get('node_number'), 'first_sequence': seq[1], 'first_boot': seq[0], 'ages_ms': []})
                node.update(last_sequence=seq[1], last_boot=seq[0], unique_boot_sequence_pairs=len(observed[ident]), last_gps_valid=gps.get('valid'))
                age = fields['report_age_ms']
                if isinstance(age, (int, float)):
                    node['ages_ms'].append(age)
                node['last_report_fresh'] = isinstance(age, (int, float)) and 0 <= age <= threshold
            report['samples'].append(item)
            print(json.dumps({'sample': index, 'frames': item['frames'], 'gateway_observed': item['gateway_observed'], 'nodes': len(item['nodes'])}), flush=True)
        except Exception as error:
            report['errors'].append({'at': stamp, 'sample': index, 'error': type(error).__name__, 'detail': str(error)})
        finally:
            c.close()
    report['finished_at'] = now()
    report['observed_node_count'] = len(report['nodes'])
    report['all_observed_nodes_advanced'] = bool(observed) and all(len(v) >= 2 for v in observed.values())
    report['all_observed_nodes_fresh_at_end'] = bool(observed) and all(n['last_report_fresh'] for n in report['nodes'].values())
    report['continuous_gateway_observation'] = bool(report['samples']) and all(s['gateway_observed'] is True for s in report['samples'])
    report['telemetry_check_passed'] = not report['errors'] and all(report[k] for k in ('all_observed_nodes_advanced', 'all_observed_nodes_fresh_at_end', 'continuous_gateway_observation'))
    report.update(assess_stability(report['samples']))
    report['stability_check_passed'] = report['stability_check_passed'] and not report['errors']
    report['limits'] = ['Reception success is not stability success; boot changes may be operator initiated', 'Not a packet-loss-rate, distance or downlink/control test', 'Expected physical node count was not provided', 'No GPS fix does not by itself prove hardware failure', 'Legacy provenance remains undeclared']
    path = out / 'REPORT.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'report': str(path), 'telemetry_check_passed': report['telemetry_check_passed'], 'stability_check_passed': report['stability_check_passed'], 'nodes': report['observed_node_count'], 'errors': report['errors']}), flush=True)
    # 0: observed reception and sampled stability; 1: reception failed; 2: reception works but instability/insufficient stability evidence.
    return (0 if report['stability_check_passed'] else 2) if report['telemetry_check_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
