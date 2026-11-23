import pathlib,socket,sys,threading,time,unittest
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'))
from tools.mobile_gateway.sources import Sources
class BlockedHttp:
 def __init__(self):self.entered=threading.Event();self.release=threading.Event()
 def topology(self):
  self.entered.set();self.release.wait(8)
  return {'schema':'lora.topology.v1','receiver':{'gateway_id':'http','gateway_observed':True,'state':'receiving'},'reports':[],'labels':{},'control':{'enabled':False}}
class Serial:
 def topology(self):return {'schema':'lora.topology.v1','receiver':{'gateway_id':'node-mac','gateway_observed':True,'identity_verified':True,'state':'receiving'},'reports':[{'gateway_id':'node-mac','pc_receive_age_ms':200}],'labels':{},'control':{'enabled':False}}
class TestIsolation(unittest.TestCase):
 def test_stalled_http_does_not_block_serial_or_udp_ack(self):
  source=Sources(udp_host='127.0.0.1',udp_port=0);http=BlockedHttp();client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(.75)
  try:
   source.add('serial',Serial(),'node');source.add('http',http,'slow');self.assertTrue(http.entered.wait(1));start=time.monotonic();listing=source.sources();snap=source.topology();self.assertLess(time.monotonic()-start,.5);self.assertEqual(snap['source_id'],'serial:configured');self.assertEqual(snap['reports'][0]['gateway_id'],'node-mac');self.assertEqual((listing['selected_source_id'],listing['selection_epoch']),(snap['source_id'],snap['selection_epoch']))
   fixture=pathlib.Path(r'D:\Multi-Agent Network\simulation\outputs\H-025\20261115-02-legacy-fixture');start=time.monotonic();client.sendto((fixture/'pull-data.bin').read_bytes(),source.sock.getsockname());self.assertEqual(client.recv(32).hex(),'02567804');elapsed=time.monotonic()-start;self.assertLess(elapsed,.5);print('HTTP blocked; PULL_ACK elapsed_ms=%.1f'%(elapsed*1000))
   start=time.monotonic();client.sendto((fixture/'push-data.bin').read_bytes(),source.sock.getsockname());self.assertEqual(client.recv(32).hex(),'02123401');elapsed=time.monotonic()-start;self.assertLess(elapsed,.5);print('HTTP blocked; PUSH_ACK elapsed_ms=%.1f'%(elapsed*1000));self.assertEqual(source.topology()['source_id'],'serial:configured')
  finally:http.release.set();client.close();source.close()
if __name__=='__main__':unittest.main(verbosity=2)
