"""Synthetic-only checks; these are not V2 field experiments."""
import unittest
import numpy as np
from mission import simulate, _safe_moves
from sampling import segment_min_distance,select_target
from analysis import observations_at, score


class SyntheticField:
    def __init__(self): self.calls=[]
    def query(self,x,y,h,t):
        self.calls.append((x,y,h,t))
        return -60+0.01*x-0.02*y+0.001*t


class Transport:
    """In-memory fixture only; no loss, limited bandwidth, or topology."""
    def __init__(self, enabled=True): self.enabled=enabled; self.pending=[]
    def advance(self, now, positions):
        result={i:[] for i in range(len(positions))}
        if self.enabled:
            for msg in self.pending:
                for receiver in result:
                    if receiver!=msg['sender']:
                        result[receiver].append({**msg,'receiver':receiver,'delivered_s':now})
        self.pending=[]
        return result
    def send(self, now, positions, outgoing): self.pending.extend(outgoing)


CONFIG={'nodes':4,'dt_s':10,'duration_s':40,'speed_m_s':1,
        'min_separation_m':3,'noise_sigma_db':0.5,'region_m':[0,0,200,200],
        'heights_m':[20]}


class MissionTests(unittest.TestCase):
    def test_fixed_ab_same_trajectory_and_noise_and_queries(self):
        f1=SyntheticField(); f2=SyntheticField()
        a=simulate(f1,CONFIG,policy='A',seed=42)
        b=simulate(f2,CONFIG,policy='B',seed=42,transport=Transport())
        self.assertEqual(a['samples'],b['samples'])
        self.assertEqual(a['trajectory'],b['trajectory'])
        self.assertEqual(a['flight_distance_m'],b['flight_distance_m'])
        self.assertEqual(len(f1.calls),16)
        for s,call in zip(a['samples'],f1.calls):
            self.assertEqual((s['x_m'],s['y_m'],s['h_m'],s['t_s']),call)
        self.assertGreater(len(b['events']),0)

    def test_d_without_delivery_matches_c(self):
        c=simulate(SyntheticField(),CONFIG,policy='C',seed=5)
        d=simulate(SyntheticField(),CONFIG,policy='D',seed=5,transport=Transport(False))
        self.assertEqual(c['samples'],d['samples'])
        self.assertEqual(c['trajectory'],d['trajectory'])
        self.assertTrue(all(not x['received_sample_ids'] for x in d['decisions']))

    def test_delivered_intents_change_a_decision(self):
        d=simulate(SyntheticField(),CONFIG,policy='D',seed=5,transport=Transport())
        self.assertTrue(any(x['selected_target_index']!=x['local_counterfactual_index'] for x in d['decisions']))
        self.assertTrue(any(x['received_sample_ids'] for x in d['decisions']))
        for e in d['events']:
            if e['kind']!='SAFETY_FREEZE': self.assertLessEqual(e['created_s'],e['delivered_s'])

    def test_segments_cross_even_if_endpoints_far(self):
        self.assertAlmostEqual(segment_min_distance([0,0,0],[10,0,0],[5,-5,0],[5,5,0]),0)
        after,hazards=_safe_moves([[0,0,0],[5,-5,0]],[[10,0,0],[5,5,0]],2)
        self.assertEqual(len(hazards),1)
        np.testing.assert_allclose(after,[[0,0,0],[5,-5,0]])

    def test_communication_policy_fails_closed_without_network(self):
        with self.assertRaises(ValueError): simulate(SyntheticField(),CONFIG,policy='D',seed=1)
        with self.assertRaises(ValueError): simulate(SyntheticField(),CONFIG,policy='B',seed=1)

    def test_held_out_positions_are_never_queried(self):
        field=SyntheticField()
        result=simulate(field,CONFIG,policy='A',seed=3,allow_observation=lambda x,y,h,t: x<100)
        self.assertTrue(any(not s['observation_allowed'] for s in result['samples']))
        self.assertTrue(all(x<100 for x,y,h,t in field.calls))
        self.assertTrue(all(s['value_dbm'] is None for s in result['samples'] if not s['observation_allowed']))

    def test_fixed_ab_pooled_score_equal_but_online_visibility_differs(self):
        a=simulate(SyntheticField(),CONFIG,policy='A',seed=42)
        b=simulate(SyntheticField(),CONFIG,policy='B',seed=42,transport=Transport())
        qa=[[100,100,20,30]]; truth=[-61.]
        self.assertEqual(score(qa,truth,observations_at(a,0,3,offline=True)),
                         score(qa,truth,observations_at(b,0,3,offline=True)))
        self.assertGreater(len(observations_at(b,0,3)),len(observations_at(a,0,3)))

    def test_scoring_rejects_future_training_samples(self):
        a=simulate(SyntheticField(),CONFIG,policy='A',seed=42)
        with self.assertRaises(ValueError): score([[100,100,20,0]],[-60],observations_at(a,0,3,offline=True))

    def test_seed_changes_initial_layout_but_preserves_pairing(self):
        a=simulate(SyntheticField(),CONFIG,policy='A',seed=41)
        b=simulate(SyntheticField(),CONFIG,policy='A',seed=42)
        self.assertNotEqual(a['trajectory'][0],b['trajectory'][0])

    def test_only_same_height_unexpired_messages_change_scores(self):
        pos=[0,0,20]; candidates=[[10,0,20],[-10,0,20]]
        wrong={'target_index':0,'sender':0,'height_m':50,'expires_s':20}
        right={**wrong,'height_m':20}
        summary={'target_index':1,'sender':0,'height_m':50,'expires_s':20,'variance':100}
        a,_,_=select_target(pos,candidates,[],0,intents=[wrong],summaries=[summary],node_id=1)
        b,_,_=select_target(pos,candidates,[],0,intents=[right],node_id=1)
        self.assertEqual(a,0); self.assertEqual(b,1)


if __name__=='__main__': unittest.main()
