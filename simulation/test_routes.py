import unittest
import numpy as np
from simulation.route_pilot import RouteConfig, episode


class RouteTests(unittest.TestCase):
    def setUp(self):
        rng=np.random.default_rng(9)
        self.truth=rng.uniform(.05,.2,(64,6))
        self.response=np.zeros((6,3))
        for i in range(3):self.response[2*i:2*i+2,i]=.5
        self.remote=self.truth@self.response
        self.initial=rng.uniform(.05,.2,(4,6))
        x,y=np.meshgrid(np.linspace(2,77,8),np.linspace(2,77,8))
        self.xy=np.column_stack([x.ravel(),y.ravel()])

    def run_case(self,mode,nodes=2,cfg=None,sharing=True,measure=None):
        return episode(self.remote,self.xy,self.initial,self.response,
                       measure or (lambda s:self.truth[s]),nodes,mode,cfg or RouteConfig(),sharing)

    def test_budget_and_endpoint(self):
        for mode in ('nearest','static','local','ideal'):
            _,result=self.run_case(mode)
            for node in result['nodes']:
                self.assertLessEqual(node['finish_time'],node['budget']+1e-8)
                self.assertEqual(node['path'][-1],[39.,79.] if node['node']==0 else [40.,79.])
                self.assertAlmostEqual(node['finish_time'],node['distance']+len(node['samples'])*4.25)
            self.assertEqual(len(result['sites']),len(set(result['sites'])))

    def test_no_free_samples_when_only_direct_travel_fits(self):
        for mode in ('nearest','static','local','ideal'):
            _,result=self.run_case(mode,cfg=RouteConfig(factor=1))
            self.assertEqual(result['samples'],0)

    def test_disabled_sharing_equals_local(self):
        a,ra=self.run_case('local')
        b,rb=self.run_case('ideal',sharing=False)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(ra,rb)

    def test_single_node_ideal_equals_local(self):
        a,ra=self.run_case('local',nodes=1)
        b,rb=self.run_case('ideal',nodes=1)
        np.testing.assert_array_equal(a,b)
        self.assertEqual(ra,rb)

    def test_static_plan_never_reads_future_spectra(self):
        _,a=self.run_case('static',measure=lambda s:np.zeros(6))
        _,b=self.run_case('static',measure=lambda s:np.ones(6))
        self.assertEqual(a['nodes'],b['nodes'])

    def test_delivery_precedes_consumption_and_decision(self):
        _,result=self.run_case('ideal')
        generated,delivered,consumed=set(),set(),set()
        for event in result['events']:
            if event['event']=='sample':generated.add(event['oid'])
            elif event['event']=='deliver':
                self.assertIn(event['oid'],generated)
                delivered.add((event['node'],event['oid']))
            elif event['event']=='consume':
                key=(event['node'],event['oid'])
                self.assertIn(key,delivered);consumed.add(key)
            elif event['event']=='decision':
                for oid in event['known_ids']:
                    if oid//1000000!=event['node']:
                        self.assertIn((event['node'],oid),consumed)
        self.assertTrue(consumed)

    def test_repeatability(self):
        a,ra=self.run_case('ideal')
        b,rb=self.run_case('ideal')
        np.testing.assert_array_equal(a,b)
        self.assertEqual(ra,rb)


if __name__=='__main__':unittest.main()
