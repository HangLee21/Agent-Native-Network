import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mid_analysis',ROOT/'tools/mid_baseline/validation/analyze.py')
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
OUT=Path(os.environ['E2_MID_TEST_OUTPUT'])


class AnalyzerTests(unittest.TestCase):
    def calculate(self,rows,**changes):
        d=OUT/self.id().split('.')[-1];d.mkdir(exist_ok=True)
        cfg=dict(schema='mid.validation.config.v1',run_id='fixture',evidence_kind='synthetic',streams=[dict(flow_id='f',source_id='A',destination_id='B',expected_generated=1,source_log_complete=True,receiver_log_complete=True,measurement_duration_us=1000000,duration_clock='host_monotonic_controlled_window')])
        cfg.update(changes)
        (d/'config.json').write_text(json.dumps(cfg));(d/'raw.jsonl').write_text('\n'.join(json.dumps(r) for r in rows)+'\n')
        return a.analyze_files(d/'config.json',[d/'raw.jsonl'])

    def row(self,event,node='A',seq=1,**kw):
        r=dict(schema='mid.validation.event.v1',run_id='fixture',event=event,node_id=node,boot_id=node+'-boot',event_seq=seq,t_us=10,flow_id='f',origin_id='A',origin_boot_id='A-boot',seq=1,destination_id='B',payload_bytes=16,evidence_kind='synthetic')
        r.update(kw);return r

    def test_callbacks_and_queued_are_not_endpoint_delivery(self):
        v=self.calculate([self.row('generated'),self.row('tx_queued',seq=2),self.row('link_callback',seq=3,success=True)])['streams'][0]
        self.assertEqual(v['pdr'],0);self.assertEqual(v['link_callback_events'],1);self.assertIsNone(v['rtt_p95_ms'])

    def test_unique_receive_dedup_and_invalid_flags(self):
        rows=[self.row('generated'),self.row('endpoint_rx','B',unique_receive=True),self.row('endpoint_rx','B',seq=2,unique_receive=True)]
        v=self.calculate(rows)['streams'][0];self.assertEqual(v['pdr'],1);self.assertEqual(v['goodput_bps'],128);self.assertEqual(v['duplicates_observed'],1)
        for flag in [0,1,None,'false']:
            rows[1]['unique_receive']=flag
            v=self.calculate(rows)['streams'][0];self.assertIsNone(v['pdr']);self.assertTrue(v['issues'])

    def test_missing_coverage_or_generation_count_stays_unknown(self):
        rows=[self.row('generated'),self.row('endpoint_rx','B',unique_receive=True)]
        cfg=dict(flow_id='f',source_id='A',destination_id='B',expected_generated=2,source_log_complete=True,receiver_log_complete=True)
        self.assertIsNone(self.calculate(rows,streams=[cfg])['streams'][0]['pdr'])
        cfg.update(expected_generated=1,receiver_log_complete=False)
        self.assertIsNone(self.calculate(rows,streams=[cfg])['streams'][0]['pdr'])

    def test_same_source_multiple_destinations_remain_distinct(self):
        rows=[];streams=[]
        for dest in ['B','C']:
            streams.append(dict(flow_id='f',source_id='A',destination_id=dest,expected_generated=1,source_log_complete=True,receiver_log_complete=True))
            rows += [self.row('generated',seq=len(rows)+1,destination_id=dest),self.row('endpoint_rx',dest,seq=1,destination_id=dest,unique_receive=True)]
        v=self.calculate(rows,streams=streams)
        self.assertEqual([s['pdr'] for s in v['streams']],[1,1])

    def test_analyzer_supports_all_twenty_directed_pairs_without_merging(self):
        rows=[];streams=[];counter={n:0 for n in 'ABCDE'}
        for src in 'ABCDE':
            for dst in 'ABCDE':
                if src==dst:continue
                flow=src+'-'+dst
                streams.append(dict(flow_id=flow,source_id=src,destination_id=dst,expected_generated=1,source_log_complete=True,receiver_log_complete=True))
                for event,node in [('generated',src),('endpoint_rx',dst)]:
                    counter[node]+=1
                    rows.append(self.row(event,node,seq=counter[node],flow_id=flow,origin_id=src,origin_boot_id=src+'-boot',destination_id=dst,unique_receive=True))
        result=self.calculate(rows,streams=streams)
        self.assertFalse(result['issues']);self.assertEqual(len(result['streams']),20)
        self.assertTrue(all(s['pdr']==1 for s in result['streams']))

    def test_hardware_without_capture_context_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'context'):self.calculate([self.row('generated')],evidence_kind='hardware_measured')

    def test_wrong_run_hash_and_synthetic_provenance_rejected(self):
        d=OUT/self.id().split('.')[-1];d.mkdir()
        log=d/'log.jsonl';cfg=d/'config.json';ctx=d/'context.json'
        rows=[dict(direction='device_rx',event=self.row('generated'),evidence_kind='hardware_serial')]
        log.write_text('\n'.join(json.dumps(r) for r in rows))
        c=dict(schema='mid.validation.config.v1',run_id='fixture',evidence_kind='hardware_measured',streams=[],input_freezes={'E1':'hypothetical-freeze','H':'hypothetical-freeze'})
        cfg.write_text(json.dumps(c));base=dict(task_id='H-005',run_id='fixture',status='capture_complete',evidence_kind='hardware_measured',input_freezes=c['input_freezes'],log_sha256={str(log.resolve()):a.sha(log)})
        for fault in ['run','hash','freeze','synthetic']:
            v=copy.deepcopy(base)
            if fault=='run':v['run_id']='OTHER'
            if fault=='hash':v['log_sha256']={}
            if fault=='freeze':v['input_freezes']={}
            ctx.write_text(json.dumps(v))
            with self.subTest(fault=fault),self.assertRaises(ValueError):a.analyze_files(cfg,[log],ctx)

    def test_strict_JSON_and_unknown_schema_cannot_prove_coverage(self):
        with self.assertRaises(ValueError):a.strict('{"run_id":"a","run_id":"b"}')
        with self.assertRaises(ValueError):a.strict('{"t_us":NaN}')
        value=self.calculate([self.row('generated'),{'schema':'vendor'},self.row('endpoint_rx','B',unique_receive=True)])
        self.assertTrue(value['issues']);self.assertIsNone(value['streams'][0]['pdr'])

    def test_oled_command_callback_and_endpoint_sources(self):
        for kind,state,node in [('command_accepted','CMD_OK','A'),('tx_queued','TX_QUEUED','A'),('link_callback','LINK_OK','A'),('endpoint_rx','LOCAL_RX','B')]:
            row=self.row(kind,node,success=True,unique_receive=True)
            snapshot=self.row('display_snapshot',node,seq=2,based_on_event_seq=1,display_state=state)
            events={(node,node+'-boot',1):row}
            self.assertIsNone(a.oled_issue(snapshot,events))
            snapshot['display_state']='DELIVERED';self.assertIsNotNone(a.oled_issue(snapshot,events))
        row=self.row('endpoint_rx','relay',unique_receive=True)
        self.assertIsNotNone(a.oled_issue(self.row('display_snapshot','relay',based_on_event_seq=1,display_state='LOCAL_RX'),{('relay','relay-boot',1):row}))

    def test_source_reboot_and_event_conflict_cannot_fabricate_delivery(self):
        rows=[self.row('generated'),self.row('endpoint_rx','B',origin_boot_id='new',unique_receive=True)]
        self.assertIsNone(self.calculate(rows)['streams'][0]['pdr'])
        rows=[self.row('generated'),self.row('generated')]
        self.assertIsNone(self.calculate(rows)['streams'][0]['pdr'])


class AuthorProbes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=ROOT/'.local/mid/E2-016/author'
        cls.inputs=json.loads((cls.source/'SOURCES.json').read_bytes())
        if any(hashlib.sha256((cls.source/r['path']).read_bytes()).hexdigest()!=r['sha256'] for r in cls.inputs['files']):raise RuntimeError('author source drift')
        (OUT/'author_inputs.json').write_text(json.dumps(cls.inputs,indent=2))

    def function(self,path,name,env):
        text=(self.source/path).read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name)
        exec(compile(ast.Module(body=[node],type_ignores=[]),path,'exec'),env)
        return env[name]

    def test_actual_author_sampler_attempts_multiple_routes_and_ignores_errors(self):
        observations=[]
        for coin in [0.25,0.75]:
            commands=[];p=NS(sim_run=True,routing_table={'src':[['dest','g1','g2'],[0.5,0.5]]},HOST='node',rt_tables_ids=[],statistics_collection=False,WIFI_IF='fake',rt_update_period=0.5)
            def stop(_):p.sim_run=False
            env=dict(Params=p,subprocess=NS(run=lambda cmd,**kw:commands.append(cmd) or NS(returncode=2),DEVNULL=None),random=NS(uniform=lambda lo,hi:coin),sleep=stop)
            with contextlib.redirect_stdout(io.StringIO()):self.function('routing_protocol/src/main_cli.py','rt_update_thread',env)()
            adds=[cmd for cmd in commands if cmd[1:4]==['ip','route','add']]
            self.assertEqual([x[x.index('via')+1] for x in adds],['g1','g2'] if coin==.25 else ['g2'])
            observations.append(dict(coin=coin,attempted_adds=adds,all_fake_returncodes=2,exception_raised=False))
        (OUT/'author_sampler_observation.json').write_text(json.dumps(observations,indent=2))

    def test_actual_author_rebroadcast_uses_original_sender_sequence(self):
        messages=[json.dumps(['server',n,{}]).encode() for n in [4,4,3,5]];sent=[];p=NS(sim_run=True,HOST='node',SERVER='server',BROADCAST='fake',PORT=1)
        def recv(_):
            x=messages.pop(0)
            if not messages:p.sim_run=False
            return x,('relay-'+str(len(messages)%2),123)
        p.cs=NS(recvfrom=recv,sendto=lambda data,address:sent.append(data))
        env=dict(Params=p,select=NS(select=lambda *x:([p.cs],[],[])),json=json,parse_server_msg=lambda msg:None)
        with contextlib.redirect_stdout(io.StringIO()):self.function('routing_protocol/src/main_cli.py','status_receive_update_thread',env)()
        self.assertEqual([json.loads(x)[1] for x in sent],[4,5])
        (OUT/'author_broadcast_observation.json').write_text(json.dumps(dict(forwarded=[json.loads(x) for x in sent],socket='in-memory; no UDP opened'),indent=2))

    def test_actual_author_conversion_overwrites_same_source_second_destination(self):
        p=NS(sim_run=True,update_source='ROS');data=[['node','src','d1','g1',1.0],['node','src','d2','g2',1.0]]
        def line():p.sim_run=False;return json.dumps(data).encode()
        child=NS(readline=line,terminate=lambda:None)
        env=dict(Params=p,pexpect=NS(spawn=lambda *a,**kw:child),select=NS(select=lambda *x:([child],[],[])),json=json)
        self.function('routing_protocol/src/main_srv.py','global_rt_update_thread',env)()
        self.assertEqual(p.routing_table['node']['src'][0][0],'d2')
        (OUT/'author_conversion_observation.json').write_text(json.dumps(p.routing_table,indent=2))
