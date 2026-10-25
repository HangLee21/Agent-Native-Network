"""Delivery semantics tests using the fixed author's environment, no rollouts."""
import copy
import json
import os
import sys
import unittest

os.environ['MPLBACKEND']='Agg'
from simulation.heteromrta_network import ASSETS, IntentView, ShadowBank, encode_body, case_passed
sys.path.insert(0,str(ASSETS))
from env.task_env import TaskEnv


class IntentDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.world=TaskEnv(per_species_range=(3,3),species_range=(3,3),tasks_range=(15,15),seed=0)
        self.world.init_state()
        self.view=IntentView(self.world)

    def command(self, actor=0, action=1, seq=1, now=0):
        self.world.current_time=now
        result=self.world.agent_step(actor,action,0)
        self.assertTrue(result[1])
        return encode_body(actor,seq,now,action,self.world.agent_dic[actor],0)

    def test_global_mutation_and_enqueue_do_not_change_receiver(self):
        before=self.view.signature()
        raw=self.command()
        self.world.task_dic[0]['requirements'][:]=99
        self.assertEqual(before,self.view.signature())
        self.view.receive(raw,0)
        self.assertNotEqual(before,self.view.signature())
        self.assertNotEqual(self.view.env.task_dic[0]['requirements'].tolist(),[99]*5)

    def test_header_is_not_body_and_duplicate_is_idempotent(self):
        raw=self.command()
        before=self.view.signature()
        header=json.dumps(dict(kind='header',source=0,seq=1)).encode()
        self.assertEqual(self.view.receive(header,0),[])
        self.assertEqual(before,self.view.signature())
        self.assertEqual(self.view.receive(raw,0),[1])
        delivered=self.view.signature()
        self.assertEqual(self.view.receive(raw,1),[])
        self.assertEqual(delivered,self.view.signature())

    def test_out_of_order_intents_wait_for_missing_predecessor(self):
        first=self.command(action=1,seq=1)
        second=self.command(action=2,seq=2)
        before=self.view.signature()
        self.assertEqual(self.view.receive(second,0),[])
        self.assertEqual(before,self.view.signature())
        self.assertEqual(len(self.view.pending[0]),1)
        self.assertEqual(self.view.receive(first,1),[1,2])
        self.assertEqual(self.view.env.agent_dic[0]['route'],self.world.agent_dic[0]['route'])

    def test_future_generation_rejected(self):
        raw=self.command(now=2)
        with self.assertRaisesRegex(ValueError,'before generation'):
            self.view.receive(raw,1)

    def test_branch_uses_receiver_copy_only(self):
        import numpy as np
        mask=np.ones((1,16),dtype=bool)
        self.assertEqual(self.view.branch(0,mask),'no_choice')
        for task in self.world.task_dic.values():
            task['feasible_assignment']=True
        self.assertEqual(self.view.branch(0,mask),'no_choice')
        for task in self.view.env.task_dic.values():
            task['feasible_assignment']=True
        self.assertEqual(self.view.branch(0,mask),'skip_at_depot')

    def test_body_transport_delay_and_local_self_visibility(self):
        bank=ShadowBank(self.world,[0.0,2.0])
        self.world.agent_step(0,1,0)
        bank.publish(0,0,1,self.world.agent_dic[0],0)
        self.assertEqual(bank.views[2.0][0].expected[0],2)
        self.assertEqual(bank.views[2.0][1].expected[0],1)
        bank.flush(1.999)
        self.assertEqual(bank.views[2.0][1].expected[0],1)
        bank.flush(2)
        self.assertEqual(bank.views[2.0][1].expected[0],2)

    def test_depot_action_zero_keeps_species_specific_route_id(self):
        raw=self.command(actor=6,action=0)
        self.view.receive(raw,0)
        self.assertEqual(self.view.env.agent_dic[6]['route'][-1],-3)
        self.assertEqual(self.view.env.agent_dic[6]['current_task'],-1)

    def test_published_body_excludes_global_task_snapshot(self):
        msg=json.loads(self.command())
        self.assertEqual(set(msg),{'kind','schema','source','seq','generated_at','command'})
        self.assertEqual(set(msg['command']),{'action','arrival','departure','travel_time','travel_dist','decision_step'})

    def test_error_or_changed_reference_cannot_pass_on_shadow_equality(self):
        record=dict(status='completed',reference_success=True,zero_delay_equivalent=True,archived_reference_equal=True)
        self.assertTrue(case_passed(record))
        for key in ['reference_success','zero_delay_equivalent','archived_reference_equal']:
            broken=record.copy()
            broken[key]=False
            self.assertFalse(case_passed(broken))
        record['status']='error'
        self.assertFalse(case_passed(record))


if __name__=='__main__':
    unittest.main()
