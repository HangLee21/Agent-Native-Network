import unittest
from proactive_subset import Node
class Checks(unittest.TestCase):
 def test_local_hello_mpr_and_tc(self):
  n=Node(0,'hop');n.ownpos=(0,0);self.assertIsNone(n.next_hop(2))
  n.receive_hello(dict(origin=1,seq=1,pos=(1,0),heard=[0,2],mpr=[0],qualities={}),0);n.expire(0)
  self.assertEqual(n.mpr,{1});self.assertEqual(n.selectors,{1});self.assertIsNone(n.next_hop(2))
  self.assertTrue(n.receive_tc(dict(origin=1,seq=1,edges=[(1,2,1.)]),1));self.assertEqual(n.next_hop(2),1)
  self.assertFalse(n.receive_tc(dict(origin=1,seq=1,edges=[]),2));n.expire(8);self.assertIsNone(n.next_hop(2))
 def test_speed_weight(self):
  n=Node(0,'predictive_subset');v=dict(q=.9,reverse=.9,radial=10)
  self.assertGreater(n.weight(v),Node(0,'etx_subset').weight(v));v['radial']=-10;self.assertLess(n.weight(v),Node(0,'etx_subset').weight(v))
 def test_accounting(self):
  from proactive_subset import sample
  for metric in ('hop','etx_subset','predictive_subset'):
   c,events=sample('crossing',0,12,metric)
   self.assertEqual(c['offered'],c['delivered']+c['no_route']+c['stale_next_hop']+c['loop_or_hoplimit'])
   self.assertEqual(c['control_bytes'],sum(e['bytes'] for e in events if e['event'] in ('hello','tc')))
   self.assertEqual(c['control_airtime_us'],sum(e['airtime_us'] for e in events if e['event'] in ('hello','tc')))
if __name__=='__main__':unittest.main()
