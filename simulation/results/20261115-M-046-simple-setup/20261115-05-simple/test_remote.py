import sys,unittest
sys.path.insert(0,r"D:\Multi-Agent Network\.worktrees\production\app\gateway_setup")
import setup_gateway as g
class Tests(unittest.TestCase):
 def test_unique_match(self):
  x="CONNECTION 192.168.137.250 41000 192.168.137.200 22\nADDRESS eth0 192.168.137.200/24\nADDRESS eth1 10.0.0.1/24\n"
  self.assertEqual(g.choose_remote_interface(x,"192.168.137.200",lambda _:self.fail("unexpected prompt")),"eth0")
 def test_ambiguous_select(self):
  x="CONNECTION 192.168.137.250 41000 192.168.137.200 22\nADDRESS eth0 192.168.137.200/24\nADDRESS eth1 192.168.137.200/24\n"
  self.assertEqual(g.choose_remote_interface(x,"192.168.137.200",lambda _:"2"),"eth1")
 def test_no_blind_first(self):
  x="CONNECTION 1.1.1.1 1 192.168.137.200 22\nADDRESS eth1 10.0.0.1/24\n"
  with self.assertRaises(g.SetupError):g.choose_remote_interface(x,"192.168.137.200",lambda _:"N")
if __name__=="__main__":unittest.main(verbosity=2)
