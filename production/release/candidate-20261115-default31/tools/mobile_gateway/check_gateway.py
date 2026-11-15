"""Finite state/HTTP regression checks; never opens serial or existing services."""
import argparse
import copy
import json
from pathlib import Path
import threading
import urllib.error
import urllib.request

from .server import Gateway
from .state import State, validate

A, B = '02:00:00:00:00:01', '02:00:00:00:00:02'


def report(node=A, peer=B, seq=1, session='one', boot=101):
    return dict(schema_version=1, node_id=node, boot_id=boot, session_id=session, seq=seq,
                label=node[-2:], position=dict(lat=30, lon=120, source='simulated', age_ms=100),
                neighbors=[dict(peer_id=peer, state='confirmed', rssi_dbm=-65, sample_age_ms=200, rf_source='simulated')],
                events=[dict(event='rx_local', origin=peer, origin_boot=102, seq=7, dst=node, payload_hex='00ff')])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    checks = []
    def ok(name, condition):
        if not condition:
            raise AssertionError(name)
        checks.append(name)
    now = [100000]
    state = State(clock=lambda: now[0], offline_ms=1000, stale_ms=2000)
    state.accept(report())
    edge = state.snapshot()['edges'][0]
    ok('RSSI direction is peer B to reporter A, not symmetric', edge['from'] == B and edge['to'] == A and not edge['mutual_confirmed'])
    state.accept(report(B, A))
    ok('two fresh confirmed directions produce mutual confirmation', all(e['mutual_confirmed'] for e in state.snapshot()['edges']))
    ok('duplicate snapshot is ignored', state.accept(report())['status'] == 'duplicate')
    state.accept(report(seq=3))
    ok('out-of-order cannot replace current snapshot', state.accept(report(seq=2))['status'] == 'out_of_order' and state.snapshot()['nodes'][0]['seq'] == 3)
    ok('same endpoint observation is counted once despite later reports', sum(x['type'] == 'rx_local' and x['node_id'] == A for x in state.history()['events']) == 1)
    state.accept(report(session='two', seq=1))
    ok('old known session remains retired even with large seq', state.accept(report(seq=999))['status'] == 'retired_session')
    changed = report(session='two', seq=2, boot=999)
    try:
        state.accept(changed)
    except ValueError:
        checks.append('boot cannot change inside one process session')
    else:
        raise AssertionError('session boot changed')
    state.accept(report(session='three', boot=999))
    now[0] += 1500
    snap = state.snapshot()
    ok('telemetry offline does not rewrite wireless confirmed to lost', all(n['telemetry_status'] == 'offline' for n in snap['nodes']) and all(e['state'] == 'confirmed' and not e['mutual_confirmed'] for e in snap['edges']))
    now[0] += 1000
    ok('position age increases using gateway elapsed time', state.snapshot()['nodes'][0]['position']['age_ms'] == 2600 and state.snapshot()['nodes'][0]['position']['stale'])
    stale = report(session='four')
    stale['report_age_ms'] = 10000
    state.accept(stale)
    ok('new arrival of cached report does not refresh GPS or neighbor freshness', state.snapshot()['nodes'][0]['position']['age_ms'] == 10100 and state.snapshot()['nodes'][0]['telemetry_status'] == 'offline')
    none = report(session='four', seq=2)
    none['position'] = None
    none['neighbors'][0].update(rssi_dbm=None, rf_source='unavailable')
    state.accept(none)
    ok('unknown location and RSSI remain null', state.snapshot()['nodes'][0]['position'] is None and state.snapshot()['edges'][0]['rssi_dbm'] is None)
    unknown_age=report(session='four',seq=3)
    unknown_age['neighbors'][0].update(rssi_dbm=None,rf_source='unavailable',sample_age_ms=None)
    state.accept(unknown_age)
    ok('unknown sample age cannot establish reciprocal freshness',state.snapshot()['edges'][0]['sample_age_ms'] is None and not state.snapshot()['edges'][0]['mutual_confirmed'])
    malformed = report()
    malformed['neighbors'][0]['rssi_dbm'] = float('nan')
    try:
        validate(malformed)
    except ValueError:
        checks.append('nonfinite measurements rejected')
    else:
        raise AssertionError('NaN accepted')
    fixture = args.output / 'static'
    fixture.mkdir()
    (fixture / 'index.html').write_text('<h1>offline fixture</h1>', encoding='utf-8')
    (fixture / 'map.js').write_text('"use strict";', encoding='utf-8')
    server = Gateway(('127.0.0.1', 0), state, fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = 'http://127.0.0.1:' + str(server.server_port)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def get(path, data=None):
        req = urllib.request.Request(base + path, data=data, headers={'Content-Type': 'application/json'})
        try:
            with opener.open(req, timeout=3) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    try:
        ok('offline map and script served from configured static root', get('/')[0] == 200 and get('/map.js')[1] == b'"use strict";')
        ok('static traversal and hidden paths denied', all(get(path)[0] == 404 for path in ['/%2e%2e/state.py', '/..%5cstate.py', '/.secret', '/unknown.js']))
        code, data = get('/api/v1/state')
        ok('state API contains observer nodes and directed edges', code == 200 and len(json.loads(data)['nodes']) == 2)
        ok('no business forwarding endpoint', get('/api/edge/send', b'{}')[0] == 404)
        fresh = report(session='four', seq=4)
        code, data = get('/api/v1/reports', json.dumps(fresh).encode())
        ok('v1 POST ingests a real HTTP report', code == 200 and json.loads(data)['status'] == 'accepted')
        ok('malformed reports return 400', get('/api/v1/reports', b'{"schema_version":99}')[0] == 400)
        ok('timeline cursor returns only subsequent events', not json.loads(get('/api/v1/timeline?after=' + str(state.cursor))[1])['events'])
        (args.output / 'state.json').write_text(json.dumps(state.snapshot(), indent=2), encoding='utf-8')
        (args.output / 'timeline.json').write_text(json.dumps(state.history(), indent=2), encoding='utf-8')
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
    result = dict(status='passed', checks=checks, evidence_kind='synthetic_state_and_isolated_loopback_HTTP', serial_opens=0, rf_packets=0, existing_services_changed=False)
    (args.output / 'CHECKS.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
