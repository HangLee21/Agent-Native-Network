"""Small synthetic checks, not simulation results."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys
import unittest
import metrics


class Checks(unittest.TestCase):
    def test_delayed_degradation_not_recovery_before_loss(self):
        r=metrics.recovery([512]*25+[0]*5+[512]*30,20,20)
        self.assertEqual(r['recovery_window_end_s'],33)
        self.assertEqual(r['recovery_s'],13)
    def test_partition_anchor_separates_unreachable_duration(self):
        r=metrics.recovery([512]*20+[0]*15+[512]*25,20,35)
        self.assertEqual(r['recovery_s'],3)
        self.assertEqual(r['elapsed_from_impact_s'],18)
    def test_censor_no_interruption_unknown(self):
        self.assertEqual(metrics.recovery([512]*20+[0]*40,20,20)['status'],'right_censored')
        self.assertEqual(metrics.recovery([512]*60,20,20)['status'],'no_interruption')
        self.assertEqual(metrics.recovery([512]*20+[None]*40,20,20)['status'],'unknown')
        self.assertEqual(metrics.recovery([0]*60,20,20)['status'],'not_assessable')
    def test_directional_reachability(self):
        self.assertEqual(metrics.directed_path('ABC',[('A','C'),('C','B')],'A','B'),['A','C','B'])
        self.assertIsNone(metrics.directed_path('ABC',[('A','C'),('C','B')],'B','A'))
    def test_unknown_gaps_and_descriptive_distribution(self):
        self.assertIsNone(metrics.longest_unreceived([],False)['packets'])
        self.assertEqual(metrics.distribution([None,1,2,3,4,5])['median'],3)
        self.assertEqual(metrics.distribution([1,2,3,4,5])['IQR'],2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
    root=Path(__file__).resolve().parents[3];out=Path(args.output).resolve()
    assert out.is_relative_to(root/'simulation/outputs/E2-019') and not out.exists();out.mkdir(parents=True)
    with (out/'checks.txt').open('x',encoding='utf-8') as f:
        r=unittest.TextTestRunner(stream=f,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks))
    result=dict(tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),passed=r.wasSuccessful(),evidence_kind='synthetic_unit_checks',simulation_experiment_runs=0,hardware_operations=0)
    (out/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    m=json.loads((root/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'))
    m.update(template_only=False,task_id='E2-019',run_id=out.name,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),worktree=str(root),python_executable=sys.executable,command=sys.argv,output_directory=str(out),status='passed' if r.wasSuccessful() else 'failed',exit_code=0 if r.wasSuccessful() else 1,budget={'hardware_operations':0},dirty_files_sha256={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path(metrics.__file__)]},limitations=['Synthetic statistic checks, no E1 simulation experiment data yet.'])
    (out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2),encoding='utf-8');print(json.dumps(result));raise SystemExit(m['exit_code'])


if __name__=='__main__':main()
