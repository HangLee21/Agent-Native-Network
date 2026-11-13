"""Focused synthetic identity/metric checks, not E1 experiment results."""
import argparse,datetime,hashlib,json,sys,unittest
from pathlib import Path
import analyze
from truth import Truth


def fixture(arm='fixed',drop=(),complete=True,duplicate=False,late=False):
    shared=dict(scenario_sha256='assumed-scenario',source_plan_sha256='240-fixed-slots',initial_table_sha256='same-table',channel_draw_index='seed/time/edge/packet',delay_model='declared-identical')
    context=dict(evidence_kind='software_simulation',run_id=arm,scenario_id='relay_exit',seed=11,arm=arm,
                 duration_s=60,interval_s=.5,payload_bytes=32,capture_complete=complete,flows=[dict(src='A',dst='B'),dict(src='B',dst='A')],evaluation=dict(impact_start_s=20,recovery_anchor_s=20),shared_inputs=shared)
    events=[]
    for d,(src,dst) in enumerate([('A','B'),('B','A')]):
        for slot in range(120):
            identity=dict(src=src,dst=dst,packet_id=str(d)+'-'+str(slot))
            events.append(dict(identity,t_s=slot/2,event='generate',direction=d,slot=slot,payload_bytes=32,payload_tag='payload-'+str(slot)))
            events.append(dict(identity,t_s=slot/2+.01,event='tx_attempt',node=src,next_hop=dst))
            if slot not in drop:
                rx=dict(identity,t_s=60.1 if late and slot==119 else slot/2+.02,event='destination_rx',node=dst,payload_tag='payload-'+str(slot))
                events.append(rx)
                if duplicate:events.append(dict(rx,t_s=rx['t_s']+.001))
            else:events.append(dict(identity,t_s=slot/2+.03,event='drop',reason='link_failure'))
    return context,events


class Checks(unittest.TestCase):
    def test_unique_endpoint_events_and_zeros(self):
        c,e=fixture(drop=range(40,120),duplicate=True);r=analyze.analyze(c,e,Truth('relay_exit'))
        self.assertTrue(r['metrics_valid']);self.assertEqual(len(r['packets']),240);self.assertEqual(r['directions'][0]['delivered_observed'],40)
        self.assertTrue(all(s['goodput_bps']==0 for s in r['seconds'] if s['second']>=20))
        self.assertEqual(r['directions'][0]['loss_observations'][0]['reachable_at_terminal'],True)
        self.assertEqual(r['directions'][0]['loss_observations'][0]['terminal_reason'],'link_failure')
    def test_late_destination_not_inserted_into_last_bin(self):
        c,e=fixture(late=True);r=analyze.analyze(c,e)
        self.assertEqual(r['directions'][0]['delivered_observed'],120);self.assertEqual(r['directions'][0]['delivered_in_window'],119)
        self.assertEqual(r['directions'][0]['late_after_window'],1);self.assertEqual(r['seconds'][59]['goodput_bps'],256)
    def test_incomplete_run_nulls(self):
        c,e=fixture(complete=False);r=analyze.analyze(c,e[:20])
        self.assertFalse(r['metrics_valid']);self.assertTrue(all(s['goodput_bps'] is None for s in r['seconds']));self.assertIsNone(r['directions'][0]['missing']['packets'])
    def test_link_attempt_does_not_count_as_delivery(self):
        c,e=fixture();e=[r for r in e if r['event']!='destination_rx'];r=analyze.analyze(c,e)
        self.assertEqual(r['directions'][0]['delivered_observed'],0);self.assertIsNone(r['control']['tx_bytes'])
    def test_pair_input_gate_and_difference(self):
        c,e=fixture(drop=range(40,120));f=analyze.analyze(c,e);c,e=fixture('adaptive',drop=range(40,45));n=analyze.analyze(c,e)
        p=analyze.paired([f,n]);self.assertEqual(p['pairs'][0]['status'],'matched');self.assertEqual(p['pairs'][0]['directions'][0]['delivery_difference_adaptive_minus_fixed'],75)
        n['shared_inputs']['channel_draw_index']='different';self.assertEqual(analyze.paired([f,n])['pairs'][0]['status'],'shared_inputs_unknown_or_mismatch')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);args=p.parse_args();root=Path(__file__).resolve().parents[3];out=Path(args.output).resolve();assert out.is_relative_to(root/'simulation/outputs/E2-019') and not out.exists();out.mkdir(parents=True)
    with (out/'checks.txt').open('x',encoding='utf-8') as stream:r=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    result=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),evidence_kind='synthetic_unit_checks',E1_experiment_runs=0,hardware_operations=0)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');m=json.loads((root/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E2-019',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),python_executable=sys.executable,command=sys.argv,output_directory=str(out),status='passed' if r.wasSuccessful() else 'failed',exit_code=0 if r.wasSuccessful() else 1,dirty_files_sha256={str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in [Path(__file__),Path(analyze.__file__)]},limitations=['Unit fixtures only; no E1 packet experiment consumed.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(result));raise SystemExit(m['exit_code'])


if __name__=='__main__':main()
