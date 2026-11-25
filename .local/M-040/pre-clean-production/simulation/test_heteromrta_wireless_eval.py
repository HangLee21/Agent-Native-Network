"""Small fixtures for refresh semantics and fixed trace replay; no learned tasks."""
import copy
import json
import unittest
from simulation.heteromrta_wireless_eval import WirelessWorld,encode
from simulation.wireless_trace_replay import replay_messages
from simulation.message_service import MessageService


def catalog():
    return dict(tasks={i:dict(requirements=[1,1,0,0,0],location=[1.+i,0.],time=2.) for i in (0,1)},
        agents={0:dict(abilities=[1,0,0,0,0],depot=[0.,0.],velocity=1.,species=0),
                1:dict(abilities=[0,1,0,0,0],depot=[0.,0.],velocity=1.,species=1)})


def world(refresh=True):
    return WirelessWorld(catalog(),MessageService(mode='fixed_delay',delay=.01),
        lambda obs,actor:0,seed=13,recovery=True,refresh=refresh,horizon=10.)


class WirelessTests(unittest.TestCase):
    def test_refresh_keeps_bytes_version_age_and_does_not_create_local_fact(self):
        w=world();w.now=.1;w.self_state(0,'fixture')
        first=copy.deepcopy(w.messages[-1]);facts=len(w.views[0].evidence);ready=set(w.ready)
        seq=w.actors[0]['seq'];decisions=copy.deepcopy(w.decisions)
        w.actors[0]['mode']='working' # unobserved world mutation must not leak
        w.now=1.;w.handle('refresh_timer',dict(actor=0))
        repeat=w.messages[-1]
        self.assertEqual(first['payload_utf8'],repeat['payload_utf8'])
        self.assertEqual(repeat['body_generated_at'],.1)
        self.assertEqual(repeat['enqueued_at'],1.)
        self.assertEqual(repeat['refresh_origin_message_id'],first['message_id'])
        self.assertIsNone(repeat['local_evidence'])
        self.assertEqual(facts,len(w.views[0].evidence))
        self.assertEqual(ready,w.ready)
        self.assertEqual(seq,w.actors[0]['seq'])
        self.assertEqual(decisions,w.decisions)

    def test_scene_witness_does_not_republish_other_source(self):
        w=world();w.now=.1;w.tasks[0]['present'].update((0,1));w.scene(0,'fixture')
        self.assertTrue(w.views[1].evidence)
        before=len(w.messages);w.handle('refresh_timer',dict(actor=1))
        self.assertEqual(before,len(w.messages))

    def test_refresh_only_own_origin_not_received_cache(self):
        w=world();w.now=.1;w.self_state(0,'fixture');w.now=.2;w.flush()
        self.assertEqual(w.views[1].states[0]['seq'],1)
        before=len(w.messages);w.handle('refresh_timer',dict(actor=1))
        self.assertEqual(before,len(w.messages))

    def test_scene_objects_and_latest_local_version_are_separate(self):
        w=world();w.now=.1;w.self_state(0,'first');w.now=.2;w.self_state(0,'second')
        for tid in (0,1):
            w.tasks[tid]['present'].add(0);w.scene(tid,'fixture')
        w.now=1.;w.handle('refresh_timer',dict(actor=0))
        copies=[m for m in w.messages if m['publication_reason']=='refresh']
        self.assertEqual(len(copies),3)
        states=[json.loads(m['payload_utf8']) for m in copies if m['kind']=='self_state']
        self.assertEqual(states[0]['state']['seq'],2)
        self.assertEqual({json.loads(m['payload_utf8'])['scene']['task'] for m in copies if m['kind']=='task_scene'},{0,1})

    def test_refresh_schedule_and_event_only_scope(self):
        w=world();due=[(t,d['actor']) for t,_,k,d in w.heap if k=='refresh_timer']
        self.assertEqual(sorted(due),[(0.,0),(.5,1)])
        event=world(False)
        self.assertFalse(any(k=='refresh_timer' for _,_,k,_ in event.heap))

    def test_replay_cutoff_then_drain_and_fact_age(self):
        body=dict(kind='self_state',source=0,generated_at=0.,state={'source':0,'seq':1})
        m=dict(message_id='origin',source=0,recipients=[1],kind='self_state',generated_at=1.,
               payload_utf8=encode(body).decode())
        result,deliveries,mapping=replay_messages([m],MessageService(mode='fixed_delay',delay=.5),1.)
        self.assertEqual(result['window_receiver_copies'],0)
        self.assertEqual(result['drained_receiver_copies'],1)
        self.assertEqual(result['drain_after_window_seconds'],10.)
        self.assertEqual(deliveries[0]['fact_age_seconds'],30.)
        self.assertEqual(mapping[0]['original_message_id'],'origin')
        self.assertFalse(result['task_executed'])

    def test_wireless_service_receives_original_body(self):
        from simulation.wireless_broadcast_service import WirelessBroadcastService
        w=WirelessWorld(catalog(),WirelessBroadcastService(policy='latest_state',seed=0),
                       lambda obs,actor:0,seed=13,recovery=True,refresh=True,horizon=10.)
        w.now=.1;w.self_state(0,'fixture');original=copy.deepcopy(w.messages[-1])
        w.now=.2;w.flush()
        self.assertEqual(w.views[1].states[0]['seq'],1)
        w.now=1.;w.handle('refresh_timer',dict(actor=0));w.now=1.1;w.flush()
        self.assertEqual(w.messages[-1]['payload_utf8'],original['payload_utf8'])
        self.assertFalse(w.deliveries[-1]['applied'])
        self.assertEqual(w.service.stats(w.now)['delivered'],2)
        self.assertGreater(w.summary()['delivery_metrics']['fact_age_seconds_max'],18.)

if __name__=='__main__':
    unittest.main(verbosity=2)
