import unittest
from simulation.agent_collab import Config, episode


class CollaborationTests(unittest.TestCase):
    def test_no_need(self):
        for p in ('independent','ideal','fifo','priority','on_demand'):
            row,_=episode(Config(need=0),p,0)
            self.assertEqual(row['mean_completion'],10)
            self.assertEqual(row['collaborative'],0)

    def test_no_background(self):
        cfg=Config(background=0,need=1)
        a,_=episode(cfg,'fifo',4)
        for p in ('priority','on_demand'):
            b,_=episode(cfg,p,4)
            self.assertEqual(a,b)

    def test_causal_hops(self):
        _,trace=episode(Config(need=1),'priority',5,True)
        created={e['message']:e['time'] for e in trace['events'] if e['event']=='create'}
        first={}
        for e in trace['events']:
            if e['event']=='hop_receive':
                if e['hop']==1:
                    self.assertGreater(e['time'],created[e['message']]);first[e['message']]=e['time']
                else:self.assertGreater(e['time'],first[e['message']])
        for task in trace['tasks']:
            if task['result_created'] is not None:
                self.assertGreaterEqual(task['service_start'],task['request_arrival'])
                self.assertEqual(task['result_created'],task['service_start']+5)
            if task['mode']=='collaborative':
                self.assertEqual(task['completed'],task['result_arrival']+10)
            elif task['mode']=='fallback':self.assertEqual(task['completed'],task['release']+210)

    def test_ideal_retains_service_queue(self):
        row,trace=episode(Config(need=1),'ideal',0)
        self.assertEqual(row['mean_completion'],17.5)
        self.assertEqual(row['service_wait_sum'],30)
        self.assertEqual(trace['tasks'][6]['service_start'],5)

    def test_inputs_identical(self):
        _,a=episode(Config(need=.5),'fifo',2,True)
        _,b=episode(Config(need=.5),'priority',2,True)
        self.assertEqual(a['phases'],b['phases'])
        self.assertEqual([t['need'] for t in a['tasks']],[t['need'] for t in b['tasks']])

    def test_high_capacity_connected(self):
        row,_=episode(Config(rate=65536,background=0,need=1,intermittent=False),'priority',0)
        self.assertEqual(row['collaborative'],12)
        self.assertEqual(row['fallback'],0)
        self.assertEqual(row['mean_completion'],21.5)


if __name__=='__main__':unittest.main()
