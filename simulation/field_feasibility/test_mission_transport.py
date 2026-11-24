"""Provisional integration against D-045's actual network, synthetic field only."""
import unittest
from mission import simulate
from mission_transport import MissionTransport
from test_mission import SyntheticField, CONFIG


class ActualTransportTests(unittest.TestCase):
    def test_messages_are_delivered_before_use(self):
        network=MissionTransport({'range_m':500,'bandwidth_bps':1000000},seed=9)
        d=simulate(SyntheticField(),CONFIG,policy='D',seed=5,transport=network)
        snapshot=network.snapshot(30.)
        self.assertGreater(snapshot['metrics']['total']['delivered'],0)
        self.assertTrue(any(x['received_sample_ids'] for x in d['decisions']))
        self.assertTrue(any(x['selected_target_index']!=x['local_counterfactual_index'] for x in d['decisions']))
        self.assertTrue(all(x['created_s']<=x['delivered_s'] for x in d['events'] if x['kind']!='SAFETY_FREEZE'))

    def test_loss_does_not_create_phantom_coordination(self):
        net=MissionTransport({'range_m':500,'bandwidth_bps':1000000,'loss_probability':1.},seed=9)
        d=simulate(SyntheticField(),CONFIG,policy='D',seed=5,transport=net)
        c=simulate(SyntheticField(),CONFIG,policy='C',seed=5)
        self.assertEqual(d['samples'],c['samples'])
        self.assertEqual(d['trajectory'],c['trajectory'])


if __name__=='__main__': unittest.main()
