import base64,pathlib,sys,tempfile,threading,time,unittest
sys.path.insert(0,r'D:\Multi-Agent Network')
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
from tools.mid_baseline.gateway_probe.topology_server import Topology
from tools.flight_link.gateway import Gateway
from tools.mobile_gateway.sources import AsyncSnapshot
from tools.mobile_gateway.replay import Replay
base=dict(observer_id='02:00:00:00:00:02',observer_boot=1,report_seq=1,snapshot_at_ms=10,wifi_group=1,report_period_ms=10000,neighbors=[])
status={'supply_mv':3300};gps={'flags':1,'lat_e7':12345678,'lon_e7':87654321}
def packet(**changes):
 data=encode_frame(dict(base,**changes));return {'data':base64.b64encode(data).decode(),'size':len(data),'stat':1,'freq':470.5}
class Checks(unittest.TestCase):
 def test_legacy_reorder_duplicate_retired_and_wrap(self):
  t=Topology();t.ingest(packet(report_seq=2,snapshot_at_ms=20,status=status));first=t.last_rx_by[base['observer_id']]
  t.ingest(packet(report_seq=1,snapshot_at_ms=10,status={'supply_mv':1111}));t.ingest(packet(report_seq=2,snapshot_at_ms=20));v=t.snapshot()['reports'][0];self.assertEqual(v['report']['report_seq'],2);self.assertEqual(v['report']['status']['supply_mv'],3300);self.assertEqual(t.last_rx_by[base['observer_id']],first)
  t.ingest(packet(observer_boot=2,report_seq=1));t.ingest(packet(observer_boot=1,report_seq=3,snapshot_at_ms=30));self.assertEqual(t.snapshot()['reports'][0]['report']['observer_boot'],2)
  w=Topology();w.ingest(packet(report_seq=4294967295));w.ingest(packet(report_seq=0,snapshot_at_ms=11));self.assertEqual(w.snapshot()['reports'][0]['report']['report_seq'],0)
 def test_udp_sparse_blocks_and_boot(self):
  now=[10.];g=Gateway('b827ebfffe32e2c1','127.0.0.1',None,clock=lambda:now[0]);g.ingest(packet(status=status,gps=gps));v=g.snapshot()['reports'][0];stamp=v['status_received_at_ms'];now[0]=12;g.ingest(packet(report_seq=2,snapshot_at_ms=20));now[0]=15;v=g.snapshot()['reports'][0];self.assertEqual(v['report']['status']['supply_mv'],3300);self.assertEqual(v['report']['gps']['lat_e7'],12345678);self.assertEqual(v['status_received_at_ms'],stamp);self.assertEqual(v['gps_age_ms'],5000);g.ingest(packet(observer_boot=2,report_seq=1));v=g.snapshot()['reports'][0];self.assertIsNone(v['report']['status']);self.assertIsNone(v['gps_age_ms']);g.archive.close()
 def test_cache_age_interruption_recovery_recorded(self):
  now=[0.];ready=threading.Event();calls=[0]
  class Source:
   def topology(self):
    calls[0]+=1;ready.set();return {'schema':'lora.topology.v1','receiver':{'gateway_observed':True},'reports':[{'pc_receive_age_ms':100,'status_age_ms':100,'gps_age_ms':200}]}
  cache=AsyncSnapshot(Source(),clock=lambda:now[0]);self.assertTrue(ready.wait(2))
  try:
   with tempfile.TemporaryDirectory() as d:
    r=Replay(pathlib.Path(d)/'r.sqlite',cache.topology,60);ident=r.start();r.sample();now[0]=5;r.sample();v=cache.topology();self.assertFalse(v['receiver']['gateway_observed']);self.assertEqual(v['reports'][0]['status_age_ms'],5100);self.assertEqual(v['reports'][0]['gps_age_ms'],5200)
    with cache.lock:cache.at=now[0]
    r.sample();frames=r.session(ident)['frames'];self.assertEqual([f['topology']['receiver']['gateway_observed'] for f in frames],[True,False,True]);self.assertEqual(frames[1]['topology']['reports'][0]['status_age_ms'],5100);r.close()
  finally:cache.close()
if __name__=='__main__':unittest.main(verbosity=2)
