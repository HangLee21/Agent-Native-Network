"""Small semantic fixtures, separate from the 40-episode research budget."""
import json
import unittest
from simulation.heteromrta_causal import CausalWorld
from simulation.heteromrta_demand_execution import DemandWorld, keyed_uniform
from simulation.message_service import MessageService


def catalog():
    return dict(tasks={0:dict(requirements=[1,1,0,0,0],location=[1.,0.],time=2.)},
                agents={0:dict(abilities=[1,0,0,0,0],depot=[0.,0.],velocity=1.,species=0),
                        1:dict(abilities=[0,1,0,0,0],depot=[0.,0.],velocity=1.,species=1)})


def chooser(obs, actor):
    return 0 if obs[2][0,1] else 1


def world(recovery=False, delay=0.):
    return DemandWorld(catalog(), MessageService(mode='fixed_delay',delay=delay), chooser,
                       seed=13,recovery=recovery,horizon=100.)


class DemandExecutionTests(unittest.TestCase):
    def test_legacy_behavior_same_as_parent(self):
        for delay in (0.,.5):
            old = CausalWorld(catalog(),MessageService(mode='fixed_delay',delay=delay),chooser,horizon=100.)
            new = world(delay=delay)
            old.run(); new.run()
            self.assertEqual(old.trace,new.trace)
            self.assertEqual(old.messages,new.messages)
            self.assertEqual(old.decisions,new.decisions)

    def test_startup_gate_survives_network_receipt_and_decide(self):
        w = world(True)
        target = max(w.gate_until, key=w.gate_until.get)
        source = 1-target
        w.now = 0.
        w.self_state(source,'test_local_change'); w.flush()
        self.assertNotIn(target,w.ready)
        self.assertEqual(w.views[target].states[source]['seq'],1)
        w.decide(target)
        self.assertEqual(len(w.decisions),0)
        w.now = w.gate_until[target]
        w.handle('startup_ready',dict(actor=target))
        self.assertIn(target,w.ready)

    def test_cancel_retains_site_and_uses_actual_delivery(self):
        w = world(True,delay=.5)
        w.now=1.; w.depart(0,1)
        w.now=2.; w.arrive(0); w.flush()
        w.now=2.5; w.flush()
        self.assertEqual(w.views[1].states[0]['mode'],'waiting')
        w.now=25.; w.handle('wait_timeout',dict(actor=0,arrival=2.))
        self.assertEqual(w.actors[0]['target'],0)
        self.assertEqual(w.actors[0]['mode'],'idle')
        self.assertNotIn(0,w.ready)
        self.assertEqual(w.views[1].states[0]['mode'],'waiting')
        w.now=25.5; w.flush()
        self.assertEqual(w.views[1].states[0]['mode'],'idle')
        self.assertNotIn(0,w.ready)
        self.assertTrue(any(json.loads(m['payload_utf8'])['state']['mode']=='idle'
                            for m in w.messages if m['kind']=='self_state'))

    def test_wait_timeout_does_not_interrupt_work(self):
        w=world(True); w.now=1.; w.depart(0,1); w.depart(1,1)
        w.now=2.; w.arrive(0); w.arrive(1)
        before=len(w.messages)
        w.now=3.; w.handle('wait_timeout',dict(actor=0,arrival=2.))
        self.assertEqual(w.actors[0]['mode'],'working')
        self.assertEqual(len(w.messages),before)

    def test_randomness_is_keyed_and_interval_bounded(self):
        w=world(True)
        self.assertTrue(all(0 <= t < 1 for t in w.gate_until.values()))
        self.assertNotEqual(w.gate_until[0],w.gate_until[1])
        self.assertEqual(keyed_uniform(13,0,'startup',0),w.gate_until[0])
        w.now=1.; w.depart(0,1); w.now=2.; w.arrive(0)
        times=[t for t,_,k,d in w.heap if k=='wait_timeout' and d['actor']==0]
        self.assertTrue(all(22 <= t < 27 for t in times))

    def test_unknown_and_network_provenance_are_separate(self):
        w=world(delay=.5)
        w.decide(0)
        consulted=[r for r in w.info_ledger if r['kind']=='information_consulted'][0]
        self.assertEqual(consulted['scene_unknown_count'],1)
        w.now=.5; w.flush(); w.decide(1)
        consulted=[r for r in w.info_ledger if r['kind']=='information_consulted'][-1]
        ref=next(r for r in consulted['references'] if r['object']=='self_state' and r['object_id']==0)
        fact=next(r for r in w.info_ledger if r['id']==ref['fact_id'])
        self.assertEqual(fact['origin'],'network')
        self.assertEqual(fact['actor'],1)
        self.assertIsNone(consulted['causal_value'])
        self.assertLess(fact['ordinal'],int(consulted['id'][1:]))

    def test_recovery_closed_loop_completes_fixture(self):
        w=world(True); result=w.run()
        self.assertTrue(result['success'])
        self.assertEqual(result['completed'],1)
        ids=[r['id'] for r in w.info_ledger]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertEqual(sum(r['kind']=='decision' for r in w.info_ledger),len(w.decisions))


if __name__ == '__main__':
    unittest.main(verbosity=2)
