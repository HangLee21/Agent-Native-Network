import pathlib,sys,unittest
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'))
from tools.mobile_gateway.sources import Sources
class Fake:
 def __init__(self,mac):self.mac=mac;self.online=True
 def topology(self):return {'schema':'lora.topology.v1','receiver':{'gateway_id':self.mac,'gateway_observed':self.online,'identity_verified':True,'state':'receiving' if self.online else 'unavailable'},'reports':[{'gateway_id':self.mac}],'control':{'enabled':False},'labels':{}}
class TestEpoch(unittest.TestCase):
 def test_selection_epoch_is_bound_to_snapshot(self):
  s=Sources(start=False);a=Fake('a');b=Fake('b');s.add('serial',a,'A');s.add('http',b,'B')
  try:
   initial=s.sources();same=s.topology();self.assertEqual((same['source_id'],same['selection_epoch']),(initial['selected_source_id'],initial['selection_epoch']));self.assertEqual(s.sources()['selection_epoch'],initial['selection_epoch'])
   choice=s.select('serial:configured');snap=s.topology();self.assertEqual(choice['selection_epoch'],initial['selection_epoch']+1);self.assertEqual((snap['source_id'],snap['selection_epoch'],snap['reports'][0]['gateway_id']),('serial:configured',choice['selection_epoch'],'a'))
   a.online=False;fallback=s.topology();listing=s.sources();self.assertEqual(fallback['selection_epoch'],choice['selection_epoch']+1);self.assertEqual((fallback['source_id'],fallback['selection_epoch'],fallback['reports'][0]['gateway_id']),(listing['selected_source_id'],listing['selection_epoch'],'b'));self.assertEqual(s.topology()['selection_epoch'],fallback['selection_epoch'])
   a.online=True;recover=s.topology();self.assertEqual((recover['source_id'],recover['selection_epoch']),('serial:configured',fallback['selection_epoch']+1))
  finally:s.close()
if __name__=='__main__':unittest.main(verbosity=2)
