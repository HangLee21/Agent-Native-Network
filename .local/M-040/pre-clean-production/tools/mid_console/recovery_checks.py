"""Recovery synchronization/persistence checks with synthetic H; no device calls."""
import argparse
import concurrent.futures
import copy
import datetime
import http.client
import json
from pathlib import Path
import threading
import time
import unittest

from server import Console, Handler, ROOT, RequestError, ThreadingHTTPServer
from recovery import validate_receipt, MAC_A

OUT = None
RID = 'a' * 24
NEW = 'b' * 24
PID = 'c' * 24
NODES = ['node-A', 'node-B']


class FakeH:
    def __init__(self, kind='confirmed_stopped', **changes):
        self.calls = 0
        self.started, self.gate = threading.Event(), threading.Event()
        self.proof = dict(run_id=RID, safe_to_release=True, kind=kind, all_ports_closed=True,
                          stop_confirmed={n: True for n in NODES}, proof_complete=True, effects_started=False)
        self.proof.update(changes)

    def recover(self, record, output, stop_event, timeout=30):
        self.calls += 1
        self.started.set()
        if not self.gate.wait(3):
            raise RuntimeError('fixture gate timed out')
        return self.proof


class Fixture(Console):
    def hardware_status(self, publisher=None):
        return dict(busy=False, run_available=True, ready_nodes=['A', 'B'])


def fixture(store=None, **changes):
    app = Fixture(True, store)
    app.adapter = FakeH(**changes)
    app.active = RID
    app.runs[RID] = dict(ok=True, run_id=RID, plan_id=PID, state='cleanup_unconfirmed',
        participants=NODES, worker_running=False, finished_at=time.time(),
        error='original failure retained', result=dict(status='failed', packets=[]),
        events=[], stop_event=threading.Event())
    app.plans[PID] = dict(request=dict(src='A', dst='B'), plan=None, run_id=RID, created=0)
    app.persist()
    return app


class Checks(unittest.TestCase):
    def finish(self, app):
        app.adapter.gate.set()
        app.workers[RID].join(4)
        self.assertFalse(app.workers[RID].is_alive())

    def test_reason_and_running_guard(self):
        app = fixture()
        self.assertEqual(app.status()['reason'], 'cleanup_unconfirmed')
        app.runs[RID].update(worker_running=True, owner_pid=__import__('os').getpid())
        self.assertFalse(app.status()['recovery_available'])
        with self.assertRaises(RequestError):
            app.recover(RID)
        self.assertEqual(app.adapter.calls, 0)

    def test_concurrent_recovery_is_one_and_idempotent(self):
        app = fixture()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(lambda _: app.recover(RID), range(8)))
        self.assertTrue(app.adapter.started.wait(1))
        self.assertEqual(app.status()['reason'], 'console_recovering')
        self.assertEqual(app.adapter.calls, 1)
        self.finish(app)
        self.assertIsNone(app.active)
        self.assertEqual(app.runs[RID]['state'], 'failed')
        self.assertEqual(app.runs[RID]['error'], 'original failure retained')
        self.assertEqual(app.recover(RID)['recovery']['status'], 'released')
        self.assertEqual(len(app.runs[RID]['recovery_history']), 1)
        self.assertEqual(app.run(PID)['run_id'], RID)
        self.assertEqual(app.adapter.calls, 1)

    def test_partial_stop_remains_blocked(self):
        app = fixture(stop_confirmed={'node-A': True})
        app.recover(RID)
        self.finish(app)
        self.assertEqual(app.active, RID)
        self.assertEqual(app.runs[RID]['state'], 'cleanup_unconfirmed')
        self.assertEqual(app.runs[RID]['recovery']['status'], 'not_released')

    def test_complete_prestart_proof_only(self):
        for changes, expected in [({}, True), ({'effects_started': True}, False),
                                  ({'proof_complete': False}, False), ({'all_ports_closed': False}, False),
                                  ({'run_id': NEW}, False)]:
            app = fixture(kind='prestart_no_side_effects', **changes)
            app.recover(RID)
            self.finish(app)
            self.assertEqual(app.active is None, expected)

    def test_old_completion_does_not_clear_new_active(self):
        app = fixture()
        app.recover(RID)
        self.assertTrue(app.adapter.started.wait(1))
        with app.lock:
            app.active = NEW  # Adversarial interleaving: must never release a newer owner.
        self.finish(app)
        self.assertEqual(app.active, NEW)

    def test_unknown_or_nonactive_target_rejected(self):
        app = fixture()
        with self.assertRaises(RequestError):
            app.recover(NEW)
        app.runs[NEW] = dict(app.runs[RID], run_id=NEW)
        with self.assertRaises(RequestError):
            app.recover(NEW)
        self.assertEqual(app.adapter.calls, 0)

    def test_restart_retains_failed_run_and_consumed_plan(self):
        directory = OUT / 'durable'
        app = fixture(directory)
        restored = Fixture(True, directory)
        self.assertEqual(restored.active, RID)
        self.assertEqual(restored.runs[RID]['error'], app.runs[RID]['error'])
        self.assertEqual(restored.run(PID)['run_id'], RID)
        self.assertEqual(restored.plans[PID], app.plans[PID])

    def test_original_snapshot_import_does_not_rearm_plan(self):
        app = Fixture(True, OUT/'migration')
        source = ROOT/'simulation/outputs/E2-018/20261107-06-recovery-before/failed-run.json'
        before = source.read_bytes()
        app.restore_run(source)
        rid = app.active
        self.assertEqual(app.runs[rid]['selection'], dict(mode='hops', count=1, src='C', dst='E', hops=2))
        self.assertEqual(app.run(app.runs[rid]['plan_id'])['run_id'], rid)
        self.assertEqual(before, source.read_bytes())
        self.assertTrue(app.plans[app.runs[rid]['plan_id']]['migration_original_plan_unavailable'])

    def test_HTTP_origin_and_client_proof_rejection(self):
        app = fixture()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.console = app
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_port
            def post(body, origin):
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
                conn.request('POST', '/api/runs/'+RID+'/recover', json.dumps(body),
                             {'Content-Type':'application/json', 'Origin':origin})
                response=conn.getresponse();response.read();status=response.status;conn.close();return status
            self.assertEqual(post({}, 'https://evil.test'), 403)
            self.assertEqual(post({'proof':True}, 'http://127.0.0.1:'+str(port)), 400)
            self.assertEqual(post({}, 'http://127.0.0.1:'+str(port)), 202)
            self.finish(app)
        finally:
            server.shutdown();server.server_close();thread.join(2)

    def test_H_receipt_freshness_hash_and_failure_binding(self):
        import hashlib
        now=datetime.datetime.now(datetime.timezone.utc)
        old_path=ROOT/'simulation/outputs/H-007/fixture-old/result.json'
        new_path=ROOT/'simulation/outputs/H-007/fixture-new/result.json'
        old=dict(all_ports_closed=True,stop_confirmed={MAC_A:False,'B':True})
        info=dict(node_id=MAC_A,device_label='A',boot_id=12,build_id='test-build',uart_baud=460800)
        current=dict(success=True,closed=True,stop_confirmed=True,info=info,
            stats=dict(info,mode='idle',queue_depth=0,radio=False,stopping=False,locked_until_reset=False),finished_at=now.isoformat())
        blobs={old_path:json.dumps(old).encode(),new_path:json.dumps(current).encode()}
        record=dict(run_id=RID,participants=[MAC_A,'B'],output_directory=str(old_path.parent),result=old,finished_at=now.timestamp()-5)
        receipt=dict(schema='mid.console.cleanup_recovery.v1',run_id=RID,status='verified_stop_only',
            verified_at=now.isoformat(),stop_confirmed={MAC_A:True,'B':True},all_ports_closed=True,
            actual_A=dict(mac=MAC_A,boot=12,build='test-build',uart_baud=460800,mode='idle',queue_depth=0),
            sources=[dict(path=str(p),sha256=hashlib.sha256(b).hexdigest()) for p,b in blobs.items()],
            original_failure_retained=True,automatic_business_resend=False)
        self.assertTrue(validate_receipt(record,receipt,now=now,read_bytes=blobs.__getitem__)['safe_to_release'])
        for altered in [dict(receipt,run_id=NEW),dict(receipt,stop_confirmed={MAC_A:True}),dict(receipt,automatic_business_resend=True)]:
            with self.assertRaises(ValueError):validate_receipt(record,altered,now=now,read_bytes=blobs.__getitem__)
        with self.assertRaises(ValueError):validate_receipt(record,receipt,now=now+datetime.timedelta(seconds=301),read_bytes=blobs.__getitem__)
        with self.assertRaises(ValueError):validate_receipt(dict(record,finished_at=now.timestamp()+1),receipt,now=now,read_bytes=blobs.__getitem__)
        with self.assertRaises(ValueError):validate_receipt(record,receipt,now=now,read_bytes=lambda path:blobs[path]+b' ')


def main():
    global OUT
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    OUT=Path(args.output).resolve();assert OUT.is_relative_to(ROOT/'simulation/outputs/E2-018') and not OUT.exists();OUT.mkdir(parents=True)
    with (OUT/'tests.txt').open('x',encoding='utf-8') as stream:
        result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    report=dict(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),passed=result.wasSuccessful(),evidence_kind='synthetic_host_only',RF_operations=0)
    (OUT/'result.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    template=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    import hashlib
    template.update(template_only=False,task_id='E2-018',run_id=OUT.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=__import__('sys').argv,output_directory=str(OUT),status='passed' if result.wasSuccessful() else 'failed',exit_code=0 if result.wasSuccessful() else 1,budget={'RF_operations':0},dirty_files_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'tools/mid_console/server.py',ROOT/'tools/mid_console/state.py']},limitations=['Synthetic H recovery proof only. No physical cleanup, user send or live-service mutation.'])
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(template,indent=2),encoding='utf-8')
    print(json.dumps(report));raise SystemExit(template['exit_code'])


if __name__=='__main__':main()
