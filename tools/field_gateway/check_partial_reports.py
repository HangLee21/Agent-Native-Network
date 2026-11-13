"""Finite partial RF/sample and packet evidence checks; no production writes."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from .application import Application
from .client import Client
from .offline import OfflineLink
from .observations import FieldState
from .packet_evidence import summarize_packets
from .server import Server
from .wireless import normalize_report, WirelessLink
from .direct import DirectQueries
from tools.mobile_gateway.state import State

A,B,C,D,E=['02:00:00:00:00:0'+str(i) for i in range(1,6)]
OUT=None


def row(peer,age=0,**extra):
    return dict(peer_id=peer,state='confirmed',rssi_dbm=-60,rf_source='simulated',sample_age_ms=age,**extra)


def report(node=A,seq=1,neighbors=(),boot=11,session=None,partial=True,**extra):
    return dict(schema_version=1,node_id=node,boot_id=boot,session_id=session or 'boot-'+str(boot),
                seq=seq,label=node,position=None,neighbors=list(neighbors),events=[],neighbors_partial=partial,**extra)


class Checks(unittest.TestCase):
    def test_07_wire_decode_live_table_and_complete_omission(self):
        mono=[10.0];state=FieldState(monotonic=lambda:mono[0])
        state.accept(report(A,neighbors=[row(B)]));state.accept(report(B,boot=22,neighbors=[row(A)]))
        link=WirelessLink('127.0.0.1',0,neighbor_snapshots=True)
        try:
            link.pc_id=1;link.pc_boot=77;link.direct=DirectQueries(clock=lambda:mono[0])
            events=[];link.callback=events.append
            for node,boot,port in ((A,11,8801),(B,22,8802)):
                link.registry.register(node,boot,['127.0.0.1',port],metadata=dict(neighbors_api=1))
            queries=link.direct.requests(link.registry.status()['entries'])
            for address,request in queries:
                observer=A if request['entry_boot']==11 else B
                value=dict(schema='field.ip.v2',event='neighbors',entry_id=observer,entry_boot=request['entry_boot'],
                    pc_id=1,pc_session=77,query_id=request['query_id'],ok=True,encoding='nd.rf.v1',
                    confirm_ms=9000,lost_ms=12000,snapshot_at_ms=10000,nd_full=0,
                    rows=[[B if observer==A else A,22 if observer==A else 11,2,101,201,-55,51,11]])
                raw=json.dumps(value).encode();self.assertLessEqual(len(raw),1024)
                link.handle(raw,address);state.accept_direct(events[-1]['proof'])
                with self.assertRaises(ValueError):link.handle(raw,address)
            self.assertTrue(all(edge['mutual_confirmed'] for edge in state.snapshot()['edges']))
            mono[0]+=2.01
            queries=link.direct.requests(link.registry.status()['entries'])
            address,request=next((a,r) for a,r in queries if r['entry_boot']==11)
            empty=dict(value,entry_id=A,entry_boot=11,query_id=request['query_id'],rows=[])
            link.handle(json.dumps(empty).encode(),address);state.accept_direct(events[-1]['proof'])
            edges=state.snapshot()['edges']
            self.assertFalse(any(edge['mutual_confirmed'] for edge in edges))
            self.assertEqual(next(edge for edge in edges if edge['to']==A)['direct_freshness'],'unknown')
            self.assertEqual(next(edge for edge in edges if edge['to']==B)['direct_freshness'],'fresh')
            mono[0]+=2.01
            queries=link.direct.requests(link.registry.status()['entries'])
            address,request=next((a,r) for a,r in queries if r['entry_boot']==11)
            capped=dict(empty,query_id=request['query_id'],rows=[[B,22,0,12000,9000,-55,12000,11]])
            link.handle(json.dumps(capped).encode(),address);state.accept_direct(events[-1]['proof'])
            capped_edge=next(edge for edge in state.snapshot()['edges'] if edge['to']==A)
            self.assertIsNone(capped_edge['sample_age_upper_bound_ms'])
            self.assertIsNone(capped_edge['confirmation_age_upper_bound_ms'])
            self.assertGreaterEqual(capped_edge['sample_age_lower_bound_ms'],12000)
            self.assertEqual(capped_edge['direct_freshness'],'stale')
            # Current ND evidence survives the existing PC HTTP projection.
            app=Application(OUT/'direct-http',OfflineLink());app.map=state
            server=Server(0,app,OUT);thread=threading.Thread(target=server.serve_forever);thread.start()
            try:
                snapshot=Client(server.server_port).call('/api/v1/state')
                self.assertTrue(all(edge['sample_age_ms'] is None for edge in snapshot['edges']))
                self.assertEqual(snapshot['direct_neighbor_policy'],'nonce_rtt_nd_9s_12s_v1')
                (OUT/'direct-http-state.json').write_text(json.dumps(snapshot,indent=2))
            finally:server.shutdown();server.server_close();thread.join();app.close()
        finally:link.close()

    def test_06_nonce_snapshot_upper_bounds_and_decay(self):
        mono=[10.0];wall=[100000]
        queries=DirectQueries(clock=lambda:mono[0])
        entries=[dict(node_id=A,boot_id=11,address=['127.0.0.1',8801],connected=True,status=dict(neighbors_api=1)),
                 dict(node_id=B,boot_id=22,address=['127.0.0.1',8802],connected=True,status=dict(neighbors_api=1))]
        requests=queries.requests(entries)
        state=FieldState(clock=lambda:wall[0],monotonic=lambda:mono[0])
        state.accept(report(A,neighbors=[dict(row(B),sample_age_ms=None,age_is_lower_bound=True)]))
        state.accept(report(B,boot=22,neighbors=[dict(row(A),sample_age_ms=None,age_is_lower_bound=True)]))
        replies=[]
        for address, request in requests:
            observer=A if request['entry_boot']==11 else B
            value=dict(entry_id=observer,entry_boot=request['entry_boot'],pc_session=77,
                query_id=request['query_id'],ok=True,encoding='nd.rf.v1',confirm_ms=9000,lost_ms=12000,
                snapshot_at_ms=50000,nd_full=0,rows=[[B if observer==A else A,22 if observer==A else 11,2,101,1001,-60,51,11]])
            with self.assertRaises(ValueError):queries.receive(dict(value,pc_session=76),address,77)
            with self.assertRaises(ValueError):queries.receive(dict(value,query_id=9999),address,77)
            with self.assertRaises(ValueError):queries.receive(value,('127.0.0.1',9999),77)
            mono[0]+=0.01
            proof=queries.receive(value,address,77);state.accept_direct(proof);replies.append(proof)
            with self.assertRaises(ValueError):queries.receive(value,address,77)
        edges=state.snapshot()['edges']
        self.assertTrue(all(edge['mutual_confirmed'] for edge in edges))
        self.assertTrue(all(edge['sample_age_ms'] is None and edge['sample_freshness']=='fresh' for edge in edges))
        self.assertTrue(all(edge['rssi_sample_age_upper_bound_ms']<edge['direct_evidence']['seen_age_upper_bound_ms'] for edge in edges))
        self.assertTrue(all(edge['direct_evidence']['confirmation_age_upper_bound_ms']>=1010 for edge in edges))
        before=edges[0]['direct_evidence']['confirmation_age_upper_bound_ms']
        wall[0]-=60000 # UTC adjustment cannot extend monotonic evidence.
        mono[0]+=8
        self.assertFalse(any(edge['mutual_confirmed'] for edge in state.snapshot()['edges']))
        self.assertGreaterEqual(state.snapshot()['edges'][0]['direct_evidence']['confirmation_age_upper_bound_ms'],before+8000)
        mono[0]+=5
        self.assertTrue(all(edge['direct_freshness']=='stale' for edge in state.snapshot()['edges']))
        # A recorded peer restart immediately invalidates both old certificates.
        state.accept(report(B,boot=33,neighbors=[]))
        self.assertFalse(any(edge['mutual_confirmed'] for edge in state.snapshot()['edges']))
        more=queries.requests(entries);mono[0]+=1.01
        address,request=more[0]
        with self.assertRaises(ValueError):queries.receive(dict(value,query_id=request['query_id'],entry_id=A,
            entry_boot=11),address,77)
        self.assertEqual(queries.requests([dict(entries[0],status={})]),[])
        (OUT/'direct-snapshots.json').write_text(json.dumps(dict(proofs=replies,expired=state.snapshot()),indent=2))

    def test_01_rotation_preserves_independent_sample_age(self):
        now=[100000];state=State(clock=lambda:now[0])
        state.accept(report(neighbors=[row(B),row(C)]))
        now[0]+=5000;state.accept(report(seq=2,neighbors=[row(D),row(E)]))
        values={n['peer_id']:n for n in state.snapshot()['nodes'][0]['neighbors']}
        self.assertEqual(len(values),4);self.assertEqual(values[B]['sample_age_ms'],5000)
        self.assertEqual(values[D]['sample_age_ms'],0)
        now[0]+=35000;state.accept(report(seq=3,neighbors=[row(D),row(E)]))
        values={n['peer_id']:n for n in state.snapshot()['nodes'][0]['neighbors']}
        self.assertEqual(values[B]['sample_age_ms'],40000)
        self.assertEqual(values[B]['sample_freshness'],'stale')
        state.accept(report(seq=4,neighbors=[row(D)],partial=False))
        self.assertEqual([n['peer_id'] for n in state.snapshot()['nodes'][0]['neighbors']],[D])
        (OUT/'rotation.json').write_text(json.dumps(values,indent=2))

    def test_02_duplicate_old_samples_and_lower_bound(self):
        now=[100000];state=State(clock=lambda:now[0])
        state.accept(report(neighbors=[row(B,sample_at_ms=80)]))
        now[0]+=5000;state.accept(report(seq=2,neighbors=[row(B,age=5000,sample_at_ms=80)]))
        first=state.snapshot()['edges'][0]
        self.assertEqual(first['sample_report_seq'],1);self.assertEqual(first['sample_age_ms'],5000)
        state.accept(report(seq=3,neighbors=[row(B,age=10000,sample_at_ms=79)]))
        self.assertEqual(state.snapshot()['edges'][0]['sample_age_ms'],5000)
        raw=dict(schema='field.ip.v2',entry_id=A,entry_boot=11,pc_id=1,pc_session=1,event='report',
                 observer_id=A,observer_boot=11,seq=1,transport_age_ms=None,
                 neighbors=[dict(peer_id=B,state='bidirectional',rf_source='simulated',rssi_dbm=-60,
                                 sample_age_ms=0,age_is_lower_bound=True)])
        bound=FieldState(clock=lambda:now[0]);bound.accept(normalize_report(raw))
        now[0]+=15000;bound.accept(normalize_report(dict(raw,seq=2)))
        edge=bound.snapshot()['edges'][0]
        self.assertIsNone(edge['sample_age_ms']);self.assertEqual(edge['sample_age_lower_bound_ms'],15000)
        self.assertEqual(edge['sample_freshness'],'unknown');self.assertFalse(edge['mutual_confirmed'])
        now[0]+=16000;self.assertEqual(bound.snapshot()['edges'][0]['sample_freshness'],'stale')
        stamped=dict(raw,seq=3,neighbors=[dict(raw['neighbors'][0],sample_at_ms=80)])
        bound.accept(normalize_report(stamped))
        self.assertEqual(bound.snapshot()['edges'][0]['sample_age_lower_bound_ms'],31000)
        # A first learned stamp enriches the old sample without making it new.
        self.assertEqual(bound.snapshot()['edges'][0]['sample_report_seq'],1)
        changed=dict(raw,seq=4,neighbors=[dict(raw['neighbors'][0],sample_at_ms=81)])
        bound.accept(normalize_report(changed))
        self.assertEqual(bound.snapshot()['edges'][0]['sample_age_lower_bound_ms'],0)
        self.assertEqual(bound.snapshot()['edges'][0]['sample_freshness'],'unknown')
        # Known transport age is counted once; lower-bound precision stays unknown.
        exact=dict(raw,seq=3,transport_age_ms=500,neighbors=[dict(raw['neighbors'][0],sample_age_ms=100,age_is_lower_bound=False)])
        another=FieldState(clock=lambda:now[0]);another.accept(normalize_report(exact))
        self.assertEqual(another.snapshot()['edges'][0]['sample_age_ms'],600)

    def test_03_lost_restart_retired_and_mutual_epochs(self):
        now=[100000];state=State(clock=lambda:now[0])
        state.accept(report(A,neighbors=[row(B)]))
        state.accept(report(B,neighbors=[row(A)],boot=22))
        self.assertTrue(all(e['mutual_confirmed'] for e in state.snapshot()['edges']))
        now[0]+=1000;state.accept(report(A,seq=2,neighbors=[dict(row(B),state='lost')]))
        self.assertFalse(any(e['mutual_confirmed'] for e in state.snapshot()['edges']))
        state.accept(report(A,seq=3,neighbors=[]))
        self.assertEqual(next(e for e in state.snapshot()['edges'] if e['to']==A)['state'],'lost')
        now[0]+=1000;state.accept(report(A,neighbors=[],boot=33))
        self.assertEqual(state.snapshot()['edges'],[])
        self.assertEqual(state.accept(report(A,seq=99,neighbors=[row(B)],boot=11,session='late-old-boot'))['status'],'retired_boot')
        state.accept(report(B,seq=2,neighbors=[row(A,age=3000)],boot=22))
        edge=state.snapshot()['edges'][0]
        self.assertEqual(edge['invalidated_reason'],'peer_restart_sample_epoch_unverified')
        self.assertFalse(edge['mutual_confirmed'])
        now[0]+=1000;state.accept(report(B,seq=3,neighbors=[row(A,peer_boot=33)],boot=22))
        state.accept(report(A,seq=2,neighbors=[row(B,peer_boot=22)],boot=33))
        self.assertTrue(all(e['mutual_confirmed'] for e in state.snapshot()['edges']))

    def test_04_packet_identity_positive_and_unknown_evidence(self):
        def event(name,observer,seq=1,boot=11,**extra):
            return dict(event=name,node_id=observer,origin=A,origin_boot=boot,seq=seq,dst=B,**extra)
        events=[event('tx_queued',A,payload_hex='4869'),event('tx_submit',A),event('rx_relay',C)]
        self.assertEqual(summarize_packets(events)[0]['state'],'relayed_pending')
        events += [event('rx_local',B,payload_hex='4869'),event('tx_link_fail',A)]
        value=summarize_packets(events,history_gap=True)[0]
        self.assertEqual(value['state'],'destination_received');self.assertTrue(value['bytes_match_source'])
        self.assertTrue(value['coverage_limited']);self.assertFalse(value['absence_means_loss'])
        events += [event('tx_queued',A,boot=44),event('route_no_route',A,seq=2),
                   event('route_no_route',A,seq=3,reason=6),event('route_selected',A,seq=99,sequence_scope='route_request')]
        values=summarize_packets(events)
        self.assertEqual(len(values),4)
        self.assertEqual(next(p for p in values if p['origin_boot']==44)['state'],'queued_only')
        self.assertEqual(next(p for p in values if p['seq']==2)['state'],'explicit_no_route')
        self.assertEqual(next(p for p in values if p['seq']==3)['state'],'cancelled_before_submission')
        mismatch=summarize_packets([event('tx_queued',A,payload_hex='01'),event('rx_local',B,payload_hex='02')])[0]
        self.assertEqual(mismatch['state'],'evidence_conflict')
        wrong_observer=summarize_packets([event('rx_local',C,payload_hex='01')])[0]
        self.assertFalse(wrong_observer['destination_observed'])

    def test_05_real_http_pc_partial_projection(self):
        app=Application(OUT/'http',OfflineLink(),pc_id=7);now=[100000]
        app.map=FieldState(clock=lambda:now[0])
        static=Path(__file__).resolve().parents[2]/'research/agent_native_network/mobile_gateway'
        server=Server(0,app,static);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05});thread.start()
        try:
            raw=dict(event='report',entry_id=A,entry_boot=11,pc_id=7,pc_session=app.store.pc_boot,
                observer_id=A,observer_boot=11,seq=1,transport_age_ms=None,
                neighbors=[dict(peer_id=p,state='heard',rssi_dbm=-60,rf_source='simulated',sample_age_ms=0,age_is_lower_bound=True) for p in (B,C)])
            app.handle(dict(type='report',report=normalize_report(raw),raw=raw))
            now[0]+=5000;second=dict(raw,seq=2,neighbors=[dict(n,peer_id=p) for n,p in zip(raw['neighbors'],(D,E))])
            app.handle(dict(type='report',report=normalize_report(second),raw=second))
            snap=Client(server.server_port).call('/api/v1/state')
            self.assertEqual(len(snap['edges']),4)
            old=next(e for e in snap['edges'] if e['from']==B)
            self.assertEqual(old['sample_age_lower_bound_ms'],5000)
            self.assertFalse(any(e['mutual_confirmed'] for e in snap['edges']))
            (OUT/'http/checks.json').write_text(json.dumps(snap,indent=2))
        finally:server.shutdown();server.server_close();thread.join();app.close()


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    OUT=parser.parse_args().output;OUT.mkdir(parents=True,exist_ok=False)
    root=Path(__file__).resolve().parents[2];files=list((root/'tools/field_gateway').glob('*'))
    files += [root/'tools/mobile_gateway/state.py',root/'tools/mobile_gateway/studio.py']
    hashes={}
    for path in files:
        if path.is_file():
            raw=path.read_bytes();rel=path.relative_to(root);target=OUT/'source'/rel
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw);hashes[rel.as_posix()]=hashlib.sha256(raw).hexdigest()
    manifest=dict(task_id='E2-031',run_id=OUT.name,started_at=datetime.now(timezone.utc).isoformat(),timezone='Asia/Shanghai',worktree=str(root),
        git_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),dirty_files_sha256=hashes,command=getattr(sys,'orig_argv',sys.argv),
        python_executable=sys.executable,dependency_snapshot=sys.version,upstream_commit=None,data_and_weights_sha256={},config_file=None,seeds=[],
        budget=dict(finite_tests=unittest.defaultTestLoader.loadTestsFromTestCase(Checks).countTestCases()),output_directory=str(OUT.resolve()),process_id=os.getpid(),finished_at=None,exit_code=None,status='running',review_reference=None,
        limitations=['Synthetic samples and ephemeral localhost HTTP; no board commands, RF test or production POST.'])
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    with (OUT/'unittest.txt').open('x',encoding='utf-8') as log:
        class Tee:
            def write(self,value):sys.stderr.write(value);log.write(value)
            def flush(self):sys.stderr.flush();log.flush()
        result=unittest.TextTestRunner(stream=Tee(),verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    manifest.update(finished_at=datetime.now(timezone.utc).isoformat(),exit_code=0 if result.wasSuccessful() else 1,status='passed' if result.wasSuccessful() else 'failed')
    (OUT/'RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    (OUT/'summary.json').write_text(json.dumps(dict(tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),success=result.wasSuccessful()),indent=2),encoding='utf-8')
    raise SystemExit(manifest['exit_code'])


if __name__=='__main__':main()
