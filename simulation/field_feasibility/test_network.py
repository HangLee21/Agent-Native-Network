import json
import unittest

from simulation.field_feasibility.network import Network, NetworkConfig, serialize_message

P = {'node_id': 1, 'position': [0, 0, 0], 'velocity': [0, 0, 0], 'timestamp': 0}
POS = {1: (0, 0, 0), 2: (5, 0, 0), 3: (50, 0, 0)}


class NetworkTest(unittest.TestCase):
    def network(self, **options):
        n = Network({'range_m': 10, 'bandwidth_bps': 8000, **options}, seed=7)
        n.update(0, POS)
        return n

    def test_queue_latency_and_inboxes(self):
        n = self.network(propagation_delay_s=1)
        a = n.send(0, 1, 'NODE_STATE', P, 2)
        self.assertEqual(a, 0)
        self.assertEqual(n.poll(2, 0), [])
        self.assertEqual(n.metrics(0)['total']['pending'], 1)
        self.assertEqual(n.poll(2, 0.5), [])
        arrived = n.poll(2, 2)
        self.assertEqual(len(arrived), 1)
        self.assertEqual(arrived[0]['message_id'], a)
        self.assertGreater(arrived[0]['latency_s'], 1)
        self.assertEqual(n.poll(2, 2), [])
        self.assertEqual(n.poll(3, 2), [])
        self.assertEqual(len(n.drain(2)), 1)  # poll did not steal event accounting
        self.assertEqual(n.drain(2), [])

    def test_broadcast_neighbour_denominator_and_bytes(self):
        n = self.network()
        mid = n.send(0, 1, 'MAP_SUMMARY', {'region_id': '区1', 'mean': -60, 'variance': 1, 'sample_count': 2})
        n.drain(1)
        m = n.metrics(1)
        expected = len(serialize_message(1, None, 'MAP_SUMMARY', {'region_id': '区1', 'mean': -60, 'variance': 1, 'sample_count': 2}, 0, mid))
        self.assertEqual(m['by_class']['broadcast']['tx_bytes'], expected)
        self.assertEqual(m['by_class']['broadcast']['receive_opportunities'], 1)
        self.assertEqual(m['total']['delivered'], 1)
        self.assertEqual(n.poll(3, 1), [])

    def test_disconnected_unicast_is_not_success(self):
        n = self.network()
        n.send(0, 1, 'NODE_STATE', P, 3)
        n.drain(1)
        m = n.metrics(1)
        self.assertEqual((m['total']['delivered'], m['total']['dropped'], m['total']['pdr']), (0, 1, 0))
        self.assertEqual(n.poll(3, 1), [])

    def test_broadcast_counts_one_transmission_two_deliveries(self):
        n = self.network()
        n.update(0, {1:(0,0,0), 2:(5,0,0), 3:(8,0,0)})
        n.send(0, 1, 'NODE_STATE', P)
        n.drain(1)
        m = n.metrics(1)['by_class']['broadcast']
        self.assertEqual((m['tx_frames'], m['receive_opportunities'], m['delivered']), (1, 2, 2))
        self.assertEqual(m['rx_bytes'], 2 * m['tx_bytes'])
        self.assertEqual(len(n.poll(2,1)), 1)
        self.assertEqual(len(n.poll(3,1)), 1)

    def test_partition_and_recovery_integrated(self):
        n = self.network()
        n.update(2, {1:(0,0,0), 2:(5,0,0), 3:(8,0,0)})
        n.update(5, POS)
        n.update(7, {1:(0,0,0), 2:(5,0,0), 3:(8,0,0)})
        m = n.metrics(10)
        self.assertAlmostEqual(m['connectivity_ratio'], .6)
        self.assertAlmostEqual(m['partition_duration_s'], 4)
        self.assertAlmostEqual(m['average_node_degree'], (4*(2/3)+6*2)/10)
        self.assertEqual(len(n.topology()['edges']), 3)

    def test_new_topology_wins_same_timestamp(self):
        n = self.network()
        mid = n.send(0, 1, 'NODE_STATE', P, 2)
        duration = len(serialize_message(1, 2, 'NODE_STATE', P, 0, mid))*8/8000
        n.update(duration, {1:(0,0,0), 2:(100,0,0), 3:(50,0,0)})
        outcomes = n.drain(duration)
        self.assertEqual(outcomes[0]['reason'], 'link_unavailable_at_arrival')
        self.assertEqual(n.poll(2, duration), [])

    def test_independent_randomness_reproducible(self):
        def trace(seed):
            n = Network({'range_m':10, 'loss_probability':.5}, seed)
            n.update(0, POS)
            for i in range(50): n.send(i, 1, 'NODE_STATE', P, 2)
            outcomes = n.drain(51)
            return [x['status'] for x in outcomes], n.metrics(51)['total']
        a = trace(9); b = trace(9)
        self.assertEqual(a, b)
        self.assertGreater(a[1]['delivered'], 0)
        self.assertGreater(a[1]['dropped'], 0)

    def test_offline_and_recovery(self):
        n = self.network()
        n.update(1, POS, {1:True,2:False,3:True})
        n.send(1, 1, 'NODE_STATE', P, 2)
        n.drain(1.5)
        n.update(2, POS)
        n.send(2, 1, 'NODE_STATE', P, 2)
        n.drain(3)
        self.assertEqual((n.metrics(3)['total']['delivered'], n.metrics(3)['total']['dropped']), (1, 1))
        self.assertEqual(n.metrics(3)['by_node'][2]['offline_time_s'], 1)

    def test_link_interrupted_even_if_restored_before_arrival(self):
        n = self.network(propagation_delay_s=2)
        n.send(0, 1, 'NODE_STATE', P, 2)
        n.drain(.1)
        n.update(.2, {1:(0,0,0), 2:(100,0,0), 3:(50,0,0)})
        n.update(.3, POS)
        self.assertEqual(n.drain(3)[0]['reason'], 'link_unavailable_at_arrival')
        self.assertEqual(n.poll(2, 3), [])

    def test_offline_source_is_not_transmission(self):
        n = self.network()
        n.update(1, POS, {1:False, 2:True, 3:True})
        n.send(1, 1, 'NODE_STATE', P, 2)
        self.assertEqual(n.drain(2)[0]['reason'], 'source_offline')
        self.assertEqual(n.metrics(2)['total']['tx_frames'], 0)

    def test_shared_channel_and_queue_rejection(self):
        n = self.network(max_queue_delay_s=.001)
        self.assertIsNotNone(n.send(0, 1, 'NODE_STATE', P, 2))
        self.assertIsNone(n.send(0, 2, 'NODE_STATE', P, 1))
        m = n.metrics(0)
        self.assertEqual(m['total']['pending'], 1)
        self.assertEqual(m['total']['rejected_frames'], 1)
        self.assertEqual(m['total']['rejected_receive_opportunities'], 1)
        n.drain(1)
        self.assertEqual(n.metrics(1)['total']['delivered'], 1)

    def test_no_messages_or_neighbours(self):
        n = self.network()
        m = n.metrics(0)
        self.assertIsNone(m['total']['pdr']); self.assertIsNone(m['total']['mean_latency_s'])
        n.send(0, 3, 'NODE_STATE', P)
        n.drain(1)
        m = n.metrics(1)
        self.assertEqual(m['total']['tx_frames'], 1)
        self.assertEqual(m['total']['receive_opportunities'], 0)
        self.assertIsNone(m['total']['pdr'])

    def test_invalid_inputs_and_snapshot_copy(self):
        n = self.network()
        with self.assertRaises(ValueError): n.send(0,1,'TASK_INTENT',{})
        with self.assertRaises(ValueError): n.send(0,1,'NOPE',P)
        with self.assertRaises(ValueError): n.update(1, {1:(0,0,0)})
        with self.assertRaises(ValueError): n.send(-1,1,'NODE_STATE',P,2)
        x=n.topology(); x['positions'][1]=(999,0,0)
        self.assertEqual(n.topology()['positions'][1], (0,0,0))
        for args in ({'range_m':0}, {'bandwidth_bps':0}, {'loss_probability':2}):
            with self.assertRaises(ValueError): NetworkConfig(**args)

    def test_all_message_schemas_and_immutable_payload(self):
        msgs = [('NODE_STATE',dict(P)),('MAP_SUMMARY',{'region_id':1,'mean':1,'variance':0,'sample_count':2}),
                ('TASK_INTENT',{'region_id':1,'utility':3,'eta':2}),
                ('TASK_UPDATE',{'region_id':1,'owner':1,'status':'complete','expires_at':3}),
                ('SAMPLE',{'sample_id':'1:0','node_id':1,'step':0,'x_m':0,'y_m':0,'h_m':10,'t_s':0,'value_dbm':-60})]
        n=self.network()
        for kind, payload in msgs:
            n.send(0,1,kind,payload,2);payload.clear()
        n.drain(1)
        received = n.poll(2,1)
        self.assertEqual([v['kind'] for v in received], [x[0] for x in msgs])
        self.assertTrue(all(v['payload'] for v in received))
        self.assertEqual(n.metrics(1)['total']['delivered'],5)


if __name__ == '__main__':
    unittest.main()
