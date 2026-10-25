"""Causal boundary tests; tiny hand-built catalogs, not research episodes."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from simulation.heteromrta_causal import CausalWorld, LocalView
from simulation.message_service import MessageService


def catalog():
    return dict(tasks={0:dict(requirements=[1,1,0,0,0],location=[1.,0.],time=2.)},
                agents={0:dict(abilities=[1,0,0,0,0],depot=[0.,0.],velocity=1.,species=0),
                        1:dict(abilities=[0,1,0,0,0],depot=[0.,0.],velocity=1.,species=1)})


def world(delay=0.,choose=lambda obs,i:1):
    return CausalWorld(catalog(),MessageService(mode='fixed_delay',delay=delay),choose,horizon=10.)


class CausalTests(unittest.TestCase):
    def test_remote_state_only_after_delivery(self):
        w=world(2.)
        before=w.views[1].signature()
        w.depart(0,1)
        self.assertEqual(w.views[1].signature(),before)
        self.assertEqual(w.views[0].states[0]['target'],0)
        w.now=1.99; w.flush()
        self.assertEqual(w.views[1].signature(),before)
        w.now=2.; w.flush()
        self.assertEqual(w.views[1].states[0]['target'],0)

    def test_departure_is_causal_and_pose_is_interpolated(self):
        w=world(); w.now=5.; w.depart(0,1)
        route=w.actors[0]['route'][0]
        self.assertEqual(route['departure'],5.)
        self.assertEqual(route['arrival'],6.)
        self.assertEqual(w.network_pose(0,5.5),[.5,0.])
        self.assertEqual(w.actors[0]['position'],[0.,0.])

    def test_intents_do_not_start_physical_task(self):
        w=world(); w.depart(0,1); w.depart(1,1); w.flush()
        self.assertTrue(w.views[0].planned_tasks(0.)[0]['feasible'])
        self.assertEqual(w.tasks[0]['phase'],'open')
        w.now=1.; w.arrive(0)
        self.assertEqual(w.tasks[0]['phase'],'open')
        w.arrive(1)
        self.assertEqual(w.tasks[0]['phase'],'running')
        self.assertEqual(w.tasks[0]['started_at'],1.)
        self.assertEqual(w.tasks[0]['workers'],[0,1])
        self.assertTrue(all(a['mode']=='working' for a in w.actors.values()))
        with self.assertRaises(AssertionError): w.depart(0,0)

    def test_done_is_absorbing_across_sources(self):
        v=LocalView(catalog(),0)
        def report(source,version,phase):
            return dict(kind='task_scene',source=source,generated_at=0.,scene=dict(task=0,phase=phase,
                        version=version,workers=[0,1],witnesses=[source],started_at=1.,finished_at=3.))
        v.apply(report(0,5,'done'),4.,'network',1)
        v.apply(report(1,4,'running'),5.,'network',2)
        v.apply(report(1,6,'open'),5.,'network',3)
        self.assertEqual(v.scenes[0]['phase'],'done')

    def test_owner_state_sequence_prevents_old_reservation(self):
        w=world(); w.depart(0,1)
        first=json.loads(w.messages[0]['payload_utf8'])
        second=copy.deepcopy(first)
        second['state'].update(seq=2,target=-1,mode='idle')
        v=LocalView(catalog(),1)
        v.apply(second,0.,'network',2); v.apply(first,1.,'network',1)
        self.assertEqual(v.states[0]['target'],-1)

    def test_completed_remote_task_does_not_reject_dispatch(self):
        w=world(2.); w.tasks[0].update(phase='done',started_at=0.,finished_at=0.)
        w.depart(0,1)
        self.assertEqual(w.actors[0]['mode'],'travel')
        self.assertNotIn(0,w.views[0].scenes)
        w.now=1.; w.arrive(0)
        self.assertEqual(w.views[0].scenes[0]['phase'],'done')
        self.assertNotIn(0,w.views[1].scenes)

    def test_world_mutation_cannot_change_remote_observation(self):
        w=world(2.)
        before=w.views[1].signature()
        w.tasks[0].update(phase='running',started_at=9.,finished_at=11.,workers=[0])
        w.actors[0].update(target=0,mode='working',position=[1.,0.])
        self.assertEqual(w.views[1].signature(),before)

    def test_scene_rejects_missing_witness(self):
        v=LocalView(catalog(),1)
        with self.assertRaises(ValueError):
            v.apply(dict(kind='task_scene',source=0,generated_at=0.,scene=dict(witnesses=[1])),0.,'network',1)

    def test_two_robot_closed_loop_finishes_and_returns(self):
        def choose(obs,actor):
            return 0 if obs[2][0,1] else 1
        w=world(0.,choose)
        result=w.run()
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['makespan_return'],4.)
        self.assertEqual(result['completed'],1)
        self.assertEqual(result['returned'],2)
        starts=[e for e in w.trace if e['kind']=='task_start']
        self.assertEqual(len(starts),1)
        self.assertEqual(starts[0]['time'],1.)


if __name__=='__main__':
    unittest.main(verbosity=2)
