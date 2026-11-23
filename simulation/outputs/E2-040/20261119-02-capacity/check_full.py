import pathlib,sys,tempfile,unittest,random
sys.path.insert(0,r'D:\Multi-Agent Network')
from tools.mobile_gateway.replay import Replay
class Check(unittest.TestCase):
 def test_full_stops_preserves_frames(self):
  rng=random.Random(8)
  with tempfile.TemporaryDirectory() as d:
   r=Replay(pathlib.Path(d)/'r.sqlite',lambda:{'schema':'lora.topology.v1','payload':rng.randbytes(20000).hex()},60);r.db.execute('PRAGMA max_page_count=24');ident=r.start()
   for _ in range(20):
    r.sample()
    if not r.active:break
   status=r.sessions();self.assertIsNone(status['active_id']);self.assertIsNotNone(status['error']);self.assertGreater(len(r.session(ident)['frames']),0);print('full_error='+status['error']);r.close()
if __name__=='__main__':unittest.main(verbosity=2)
