import unittest
from simulation.rescue_reporting import Config, POLICIES, episode


class RescueTests(unittest.TestCase):
    def test_full_contact_small_reports_match_ideal_with_tick_delay(self):
        cfg=Config(reach=99)
        ideal,_=episode(cfg,'ideal',0)
        actual,detail=episode(cfg,'priority',0)
        self.assertEqual(actual['received'],ideal['received'])
        self.assertLessEqual(ideal['report_auc']-actual['report_auc'],1/cfg.horizon+1e-12)
        self.assertTrue(all(r['received']>r['discovered'] for r in detail['reports']))

    def test_no_evidence_fifo_and_priority_equal(self):
        a,ad=episode(Config(),'fifo',2)
        b,bd=episode(Config(),'priority',2)
        a.pop('policy');b.pop('policy')
        self.assertEqual(a,b);self.assertEqual(ad,bd)

    def test_queue_policies_preserve_search_and_generation(self):
        cfg=Config(evidence=524288)
        a,ad=episode(cfg,'fifo',3)
        b,bd=episode(cfg,'priority',3)
        self.assertEqual(ad['robots'],bd['robots'])
        self.assertEqual([(r['room'],r['node'],r['discovered']) for r in ad['reports']],
                         [(r['room'],r['node'],r['discovered']) for r in bd['reports']])
        self.assertGreaterEqual(b['report_auc'],a['report_auc'])

    def test_budget_resource_and_causal_invariants(self):
        for policy in POLICIES:
            row,detail=episode(Config(evidence=524288),policy,7,True)
            self.assertLessEqual(row['received'],row['discovered'])
            self.assertLessEqual(row['relays'],2)
            self.assertGreaterEqual(row['link_bytes'],row['application_bytes'])
            self.assertAlmostEqual(row['capped_delay'],row['contact_wait']+row['after_contact_wait'])
            for r in detail['robots']:
                self.assertEqual(r['pos'],0);self.assertLessEqual(r['finish'],600)
                self.assertEqual(len(r['visited']),len(set(r['visited'])))
            for report in detail['reports']:
                if report['received'] is not None:
                    self.assertGreaterEqual(report['received'],report['discovered'])
                    self.assertLessEqual(report['first_contact'],report['received'])

    def test_repeatability(self):
        self.assertEqual(episode(Config(),'relay_return',9,True),episode(Config(),'relay_return',9,True))


if __name__=='__main__':unittest.main()
