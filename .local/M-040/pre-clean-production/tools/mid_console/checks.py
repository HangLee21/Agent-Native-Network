"""Focused service checks. Fake adapter cases are host fixtures, never RF evidence."""
import argparse
import concurrent.futures
import datetime
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from server import Console, ROOT, RequestError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    assert out.is_relative_to(ROOT / 'simulation/outputs/E2-018')
    out.mkdir(parents=True, exist_ok=False)
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    checks = []

    def check(name, condition):
        checks.append(dict(name=name, passed=bool(condition)))
        assert condition, name

    def request(path, body=None, origin='local', host=None, raw=None):
        connection = http.client.HTTPConnection('127.0.0.1', args.port, timeout=40)
        headers = {'Host': host or f'127.0.0.1:{args.port}'}
        if body is not None or raw is not None:
            headers['Content-Type'] = 'application/json'
            if origin is not None:
                headers['Origin'] = f'http://127.0.0.1:{args.port}' if origin == 'local' else origin
        payload = raw if raw is not None else json.dumps(body) if body is not None else None
        connection.request('POST' if payload is not None else 'GET', path, body=payload, headers=headers)
        response = connection.getresponse()
        data = response.read()
        code = response.status
        connection.close()
        try:
            data = json.loads(data)
        except ValueError:
            data = data.decode('utf-8')
        return code, data

    try:
        code, status = request('/api/status')
        check('real_service_preview_no_active_run', code == 200 and status['mode'] == 'preview' and status['active_run_id'] is None)
        code, page = request('/')
        check('same_origin_D_page', code == 200 and 'MID / FIVE-BOARD CONSOLE' in page)
        check('replay_same_origin', request('/replay/')[0] == 200)
        for name, host, origin in [('host', 'evil.test', 'local'), ('cross_origin', None, 'https://evil.test'), ('missing_origin', None, None), ('different_loopback_origin', None, f'http://localhost:{args.port}')]:
            check('reject_' + name, request('/api/plan', {}, host=host, origin=origin)[0] == 403)
        check('reject_duplicate_keys', request('/api/plan', raw='{"src":"A","src":"B"}')[0] == 400)
        check('reject_nonfinite', request('/api/plan', raw='{"src":NaN}')[0] == 400)
        check('reject_oversize', request('/api/plan', raw='x' * 16385)[0] == 400)
        check('reject_static_traversal', request('/%2e%2e/%2e%2e/coordination/CURRENT.md')[0] == 404)
        base = dict(src='A', dst='E', mode='hops', hops=4, count=1)
        for name, changed in [('same_endpoint', {'dst': 'A'}), ('zero_hops', {'hops': 0}), ('bool_hops', {'hops': True}), ('too_many_packets', {'count': 11}), ('path_injection', {'model_id': '../input.json'}), ('unknown_field', {'command': 'stop'}), ('node_not_label', {'src': ['A']})]:
            check('reject_' + name, request('/api/plan', dict(base, **changed))[0] == 400)
        code, plan = request('/api/plan', base)
        check('real_E1_exact_four_hop_plan', code == 200 and plan['chain'] == list('ABCDE') and plan['exact_hops'] == 4 and not plan['run_available'])
        (out / 'four-hop-response.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
        check('preview_run_does_not_execute', request('/api/run', {'plan_id': plan['plan_id']})[0] == 409)
        check('unknown_run', request('/api/runs/' + '0' * 24)[0] == 404)
        code, impossible = request('/api/plan', dict(base, graph_edges=[['A', 'E']]))
        check('exact_hops_infeasible_on_explicit_graph', code == 422 and impossible['error']['code'] == 'infeasible_hops')
        code, mid = request('/api/plan', dict(src='B', dst='E', mode='mid', count=1))
        check('real_SOCP_optimal_from_service', code == 200 and mid['solver']['status'] == 'optimal' and mid['chain'] is None and mid['candidate_edges'] and mid['model']['source_kind'] == 'assumption')
        (out / 'mid-response.json').write_text(json.dumps(mid, ensure_ascii=False, indent=2), encoding='utf-8')

        # Isolated synthetic adapter, with no imports or calls into H execute.
        class FakeAdapter:
            def __init__(self, clean=True, partial=False):
                self.calls, self.clean = 0, clean
                self.partial = partial
                self.entered, self.finished = threading.Event(), threading.Event()
            def execute(self, plan, output, stop_event, on_event=None, timeout=60):
                self.calls += 1
                self.entered.set()
                assert stop_event.wait(3), 'fixture expected explicit stop'
                self.finished.set()
                return dict(status='stopped', evidence_kind='synthetic_host_test', packets=[], requested=1,
                            destination_unique_received=0, all_ports_closed=self.clean,
                            actual_infos={n: {} for n in plan['network_update']['nodes']},
                            stop_confirmed={n: self.clean for n in (plan['network_update']['nodes'][:1] if self.partial else plan['network_update']['nodes'])})

        class FixtureConsole(Console):
            def hardware_status(self, publisher=None):
                return dict(run_available=True, busy=False, ready_nodes=list('ABCDE'), publisher=publisher or 'A', publisher_boot=1)

        def fixture(clean=True, partial=False):
            app = FixtureConsole(True)
            app.adapter = FakeAdapter(clean, partial)
            for pid in ('a' * 24, 'b' * 24):
                app.plans[pid] = dict(plan=plan, request=base, created=time.monotonic(), run_id=None)
            return app

        app = fixture()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: app.run('a' * 24), range(8)))
        check('host_fixture_concurrent_same_plan_only_once', len({r['run_id'] for r in replies}) == 1 and app.adapter.calls == 1)
        rid = replies[0]['run_id']
        try:
            app.run('b' * 24)
        except RequestError as exc:
            check('host_fixture_other_plan_busy', exc.status == 409)
        else:
            check('host_fixture_other_plan_busy', False)
        app.stop(rid)
        check('host_fixture_stop_received', app.adapter.finished.wait(3))
        # Joining the exact worker is unnecessary: status changes under the same lock.
        deadline = time.monotonic() + 3
        while app.active and time.monotonic() < deadline:
            time.sleep(.01)
        check('host_fixture_cleanup_release', app.active is None and app.public_run(rid)['state'] == 'stopped')
        check('host_fixture_replay_same_run', app.run('a' * 24)['run_id'] == rid and app.adapter.calls == 1)
        blocked = fixture(False)
        blocked_run = blocked.run('a' * 24)['run_id']
        blocked.stop(blocked_run)
        check('host_fixture_failed_cleanup_observed', blocked.adapter.finished.wait(3))
        deadline = time.monotonic() + 3
        while blocked.public_run(blocked_run)['state'] != 'cleanup_unconfirmed' and time.monotonic() < deadline:
            time.sleep(.01)
        check('host_fixture_failed_cleanup_retains_busy', blocked.active == blocked_run and blocked.public_run(blocked_run)['state'] == 'cleanup_unconfirmed')
        partial = fixture(True, True)
        partial_run = partial.run('a' * 24)['run_id']
        partial.stop(partial_run)
        check('host_fixture_partial_cleanup_observed', partial.adapter.finished.wait(3))
        deadline = time.monotonic() + 3
        while partial.public_run(partial_run)['state'] != 'cleanup_unconfirmed' and time.monotonic() < deadline:
            time.sleep(.01)
        check('host_fixture_missing_board_stop_retains_busy', partial.active == partial_run and partial.public_run(partial_run)['state'] == 'cleanup_unconfirmed')
        unavailable = fixture()
        unavailable.plans['a' * 24]['plan'] = dict(plan, required_nodes=['A', 'E'], chain=['A', 'E'])
        unavailable.hardware_status = lambda publisher=None: dict(run_available=True, busy=False, ready_nodes=['A', 'E'], publisher='A', publisher_boot=1)
        try:
            unavailable.run('a' * 24)
        except RequestError as exc:
            check('host_fixture_full_table_participants_required', exc.code == 'nodes_not_ready' and unavailable.adapter.calls == 0)
        else:
            check('host_fixture_full_table_participants_required', False)
        check('no_RF_run_created_by_HTTP_checks', request('/api/status')[1]['active_run_id'] is None)
    finally:
        (out / 'checks.json').write_text(json.dumps(dict(checks=checks, passed=sum(c['passed'] for c in checks),
            failed=sum(not c['passed'] for c in checks), evidence_kind='HTTP integration and isolated synthetic host concurrency fixtures',
            rf_executions=0), ensure_ascii=False, indent=2), encoding='utf-8')
        sources = [Path(__file__), ROOT/'tools/mid_console/server.py', ROOT/'tools/mid_console/worker.py',
                   ROOT/'tools/mid_baseline/planner/console/plans.py', ROOT/'tools/mid_hardware/console/adapter.py',
                   ROOT/'research/agent_native_network/mid_replacement_demo/control/index.html']
        manifest = json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
        manifest.update(template_only=False, task_id='E2-018', run_id=out.name, started_at=start,
            finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(), worktree=str(ROOT),
            git_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            dirty_files_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            command=subprocess.list2cmdline([sys.executable, *sys.argv]), python_executable=sys.executable,
            budget=dict(real_http_plan_requests=3, RF_packets=0), output_directory=str(out), process_id=os.getpid(),
            dependency_snapshot=dict(python_version=sys.version, planner_interpreter=str(Console().python)),
            exit_code=0 if checks and all(c['passed'] for c in checks) else 1,
            status='passed' if checks and all(c['passed'] for c in checks) else 'failed',
            limitations=['No H execute called. Fake adapter cases test synchronization only; no RF evidence.', 'Model coefficients are assumed; SOCP status is genuine.'])
        (out/'RUN_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(dict(passed=len(checks), output=str(out), rf_executions=0)))


if __name__ == '__main__':
    main()
