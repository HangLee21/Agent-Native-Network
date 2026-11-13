"""Bounded telemetry regression; native-format fixtures, no production services."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
import urllib.error
from .application import Application
from .client import Client
from .offline import OfflineLink
from .protocol import SCHEMA
from .read_observations import ObservationReader
from .server import Server
from .wireless import WirelessLink
from tools.mobile_gateway.server import Gateway
from tools.mobile_gateway.state import State

A,B = '02:00:00:00:00:01','02:00:00:00:00:02'
OUT = None


class DormantLink(WirelessLink):
    def attach(self, callback, pc_id, pc_boot):
        self.callback,self.pc_id,self.pc_boot = callback,pc_id,pc_boot


class ReadFixtureLink(OfflineLink):
    def status(self):
        return dict(super().status(),entries=[dict(node_id=A,boot_id=11,connected=True)],connected=True)


def report(seq=1,cursor=1,session=1,pc=7):
    return dict(schema=SCHEMA,event='report',entry_id=A,entry_boot=11,pc_id=pc,pc_session=session,
        event_cursor=cursor,observer_id=B,observer_boot=22,seq=seq,segment=1,transport_age_ms=None,
        source_admitted=9,relay_submitted=2,destination_received=8,record_overwritten=4,
        neighbors=[dict(peer_id=A,state='bidirectional',rssi_dbm=-58,rf_source='simulated',
                        sample_age_ms=1000,age_is_lower_bound=True)])


class Checks(unittest.TestCase):
    def test_01_valid_report_reaches_state_without_gps(self):
        link=DormantLink('127.0.0.1',0)
        app=Application(OUT/'report',link,pc_id=7)
        address=('127.0.0.1',19871)
        link.registry.register(A,11,address)
        try:
            value=report(session=app.store.pc_boot)
            link.handle(json.dumps(value).encode(),address)
            snapshot=app.map.snapshot()
            self.assertEqual(len(snapshot['nodes']),1)
            self.assertEqual(len(snapshot['edges']),1)
            self.assertIsNone(snapshot['nodes'][0]['position'])
            self.assertEqual(snapshot['nodes'][0]['telemetry_status'],'unknown')
            self.assertEqual(snapshot['edges'][0]['from'],A)
            self.assertEqual(snapshot['edges'][0]['to'],B)
            self.assertFalse(snapshot['edges'][0]['mutual_confirmed'])
            self.assertIsNone(snapshot['edges'][0]['sample_age_ms'])
            # A newer IP event with the same observer sample is not a fresh map sample.
            link.handle(json.dumps(dict(value,event_cursor=2)).encode(),address)
            self.assertEqual(app.status()['telemetry']['map_outcomes'],{'accepted':1,'duplicate':1})
            link.handle(json.dumps(value).encode(),address)
            self.assertEqual(link.counters['reports_normalized'],2)
            (OUT/'report/checks.json').write_text(json.dumps(dict(status=app.status(),map=snapshot),indent=2))
        finally:app.close()

    def test_02_distinct_rejection_stages(self):
        link=DormantLink('127.0.0.1',0)
        app=Application(OUT/'rejection',link,pc_id=7)
        address=('127.0.0.1',19872)
        link.registry.register(A,11,address)
        try:
            broken=report(session=app.store.pc_boot)
            broken['observer_id']='invalid'
            with self.assertRaises(ValueError):link.handle(json.dumps(broken).encode(),address)
            self.assertEqual(link.counters['report_normalization_rejected'],1)
            invalid=report(seq=2,cursor=2,session=app.store.pc_boot)
            invalid['neighbors'][0]['rssi_dbm']=999
            with self.assertRaises(ValueError):link.handle(json.dumps(invalid).encode(),address)
            self.assertEqual(app.status()['telemetry']['map_outcomes'],{'rejected':1})
            self.assertEqual(app.status()['telemetry']['recent_rejections'][0]['stage'],'map.accept')
            self.assertEqual(len(app.map.snapshot()['nodes']),0)
            (OUT/'rejection/checks.json').write_text(json.dumps(app.status(),indent=2))
        finally:app.close()

    def test_03_seen_poll_event_advances_after_retention_gap(self):
        link=DormantLink('127.0.0.1',0)
        app=Application(OUT/'cursor',link,pc_id=7)
        address=('127.0.0.1',19873)
        link.registry.register(A,11,address)
        value=dict(schema=SCHEMA,event='inbox',entry_id=A,entry_boot=11,pc_id=7,
            pc_session=app.store.pc_boot,event_cursor=3,origin=B,origin_boot=22,
            seq=1,transaction=1,logical_dst='pc:7',payload_hex='4869')
        try:
            link.handle(json.dumps(value).encode(),address)
            link._range(A,11,dict(oldest_cursor=3))
            link.handle(json.dumps(value).encode(),address)
            self.assertEqual(link.cursors[(A,11)],3)
            self.assertEqual(len(app.store.inbox()['records']),1)
            self.assertEqual(link.counters['event_duplicates'],1)
            self.assertNotIn(1,link.received_cursors[(A,11)])
            (OUT/'cursor/checks.json').write_text(json.dumps(dict(status=app.status(),inbox=app.store.inbox()),indent=2))
        finally:app.close()

    def test_04_post_state_boundary(self):
        app=Application(OUT/'http',OfflineLink(),pc_id=7)
        static=Path(__file__).resolve().parents[2]/'research/agent_native_network/mobile_gateway'
        pc=Server(0,app,static);generic=Gateway(('127.0.0.1',0),State(),static)
        threads=[]
        for server in (pc,generic):
            t=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});t.start();threads.append(t)
        value=dict(schema_version=1,node_id=A,boot_id=11,session_id='isolated-test',seq=1,
                   label='fixture',position=None,neighbors=[],events=[])
        try:
            with self.assertRaises(urllib.error.HTTPError) as error:
                Client(pc.server_port).call('/api/v1/reports',value)
            self.assertEqual(error.exception.code,404)
            self.assertEqual(Client(pc.server_port).call('/api/v1/state')['nodes'],[])
            answer=Client(generic.server_port).call('/api/v1/reports',value)
            self.assertEqual(answer['status'],'accepted')
            self.assertEqual(len(Client(generic.server_port).call('/api/v1/state')['nodes']),1)
            (OUT/'http/checks.json').write_text(json.dumps(dict(pc_post_status=404,pc_nodes=0,
                generic_post_status=200,generic_nodes=1,production_ports_used=False),indent=2))
        finally:
            for server in (pc,generic):server.shutdown();server.server_close()
            for thread in threads:thread.join()
            app.close()

    def test_05_passive_reader_and_instance_isolation(self):
        app=Application(OUT/'reader',ReadFixtureLink(),pc_id=7)
        static=Path(__file__).resolve().parents[2]/'research/agent_native_network/mobile_gateway'
        server=Server(0,app,static)
        thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});thread.start()
        def observed(raw):app.handle(dict(type='wireless_status',raw=raw))
        base=dict(schema=SCHEMA,entry_id=A,entry_boot=11,pc_id=7,pc_session=app.store.pc_boot)
        observed(dict(base,event='field_status',agent_running=True,source_admitted=4,source_submitted=3,
            destination_received=2,relay_received=1,relay_submitted=1,record_overwritten=9,latest_record_cursor=12))
        observed(dict(base,event='record',record_cursor=12,kind='destination_received',origin=B,
            origin_boot=22,seq=9,dst=A,payload_hex='4869',segment=1,at_ms=300,entry_uptime_ms=1000))
        try:
            reader=ObservationReader(server.server_port)
            value=reader.read()
            self.assertEqual(len(value['native_status']),1)
            self.assertFalse(value['native_status'][0]['rf_rows_available'])
            self.assertEqual(value['records'][0]['observer_id'],A)
            self.assertEqual(value['records'][0]['origin'],B)
            self.assertGreaterEqual(value['records'][0]['record_age_lower_bound_ms'],700)
            self.assertEqual(value['map_state']['nodes'],[])
            self.assertTrue(all(v==0 for v in value['side_effects'].values()))
            app.instance_id='new-instance';app.events.clear();app.cursor=0
            fresh=reader.read()
            self.assertEqual(fresh['native_status'],[])
            self.assertEqual(fresh['records'],[])
            (OUT/'reader/checks.json').write_text(json.dumps(value,indent=2))
        finally:server.shutdown();server.server_close();thread.join();app.close()


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    OUT=parser.parse_args().output;OUT.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2];hashes={}
    files=list((root/'tools/field_gateway').glob('*'))+list((root/'deploy/field_gateway').glob('*'))
    files += [root/'tools/mobile_gateway/state.py',root/'tools/mobile_gateway/server.py']
    for path in files:
        if path.is_file():
            raw=path.read_bytes();relative=path.relative_to(root);target=OUT/'source'/relative
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
            hashes[relative.as_posix()]=hashlib.sha256(raw).hexdigest()
    manifest=dict(task_id='E2-030',run_id=OUT.name,started_at=datetime.now(timezone.utc).isoformat(),
        timezone='Asia/Shanghai',worktree=str(root),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        dirty_files_sha256=hashes,command=getattr(sys,'orig_argv',sys.argv),python_executable=sys.executable,
        dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=[],
        budget=dict(bounded_tests=5),output_directory=str(OUT.resolve()),process_id=os.getpid(),finished_at=None,
        exit_code=None,status='running',review_reference=None,limitations=['Synthetic native-format replay and ephemeral localhost HTTP only.',
            'No production POST, UDP to boards, serial, service restart or RF measurement.'])
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with (OUT/'unittest.txt').open('x',encoding='utf-8') as log:
        class Tee:
            def write(self,value):sys.stderr.write(value);log.write(value)
            def flush(self):sys.stderr.flush();log.flush()
        result=unittest.TextTestRunner(stream=Tee(),verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),exit_code=0 if result.wasSuccessful() else 1,
                    status='passed' if result.wasSuccessful() else 'failed')
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'summary.json').write_text(json.dumps(dict(tests=result.testsRun,success=result.wasSuccessful(),
        failures=len(result.failures),errors=len(result.errors)),indent=2),encoding='utf-8')
    raise SystemExit(manifest['exit_code'])


if __name__=='__main__':main()
