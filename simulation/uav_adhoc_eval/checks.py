import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import analyze
from geometry import measure
class Checks(unittest.TestCase):
 def test_distinct_packet_and_reachability(self):
  p=dict(origin='a',origin_boot=1,seq=1,dst='b')
  ev=[dict(type='offered',t=0,reachable_at_offer=True,**p),dict(type='admitted',t=.1,**p),dict(type='delivered',t=.2,receiver='b',**p),dict(type='delivered',t=.3,receiver='b',**p),dict(type='offered',t=1,reachable_at_offer=False,**dict(p,seq=2))]
  out,_=analyze(dict(events=ev));self.assertEqual((out['offered'],out['delivered_unique'],out['reachable_offered'],out['reachable_delivered']),(2,1,1,1))
 def test_per_pair_aoi_and_old_report(self):
  ev=[dict(type='neighbor_received',t=2,observer='a',peer='b',generated_at=1),dict(type='neighbor_received',t=4,observer='a',peer='b',generated_at=0),dict(type='aoi_sample',t=5,observer='a',peer='b'),dict(type='aoi_sample',t=5,observer='a',peer='c')]
  out,s=analyze(dict(events=ev));self.assertEqual([v['aoi_s'] for v in s],[4,None]);self.assertEqual(out['aoi_unknown'],1)
 def test_command_ack_not_execution_and_duplicates(self):
  ev=[dict(type='command_issued',t=0,cmd_id='x',target='b'),dict(type='gateway_ack',t=1,cmd_id='x',target='b'),dict(type='command_executed',t=2,cmd_id='x',target='b',executor='b'),dict(type='command_executed',t=3,cmd_id='x',target='b',executor='b')]
  out,_=analyze(dict(events=ev));self.assertEqual((out['commands_executed'],out['duplicate_executions']),(1,1))
 def test_geometry_relative_and_partition(self):
  pos={'a':(0,0),'b':(1,0),'c':(10,0)};vel={'a':(5,0),'b':(-5,0),'c':(5,0)}
  out=measure(pos,vel,2);self.assertEqual((out['components'],out['directed_reachable_pairs'],out['max_pair_relative_speed_m_s']),(2,2,10))
if __name__=='__main__':unittest.main()
