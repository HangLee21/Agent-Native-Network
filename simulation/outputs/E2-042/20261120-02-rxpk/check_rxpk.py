import base64,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,r'D:\Multi-Agent Network')
from tools.mid_baseline.gateway_probe.topology_server import Topology
from tools.flight_link.gateway import Gateway
from tools.mobile_gateway.replay import Replay
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame,decode_frame
fixture=pathlib.Path(r'D:\Multi-Agent Network\simulation\outputs\H-025\20261115-02-legacy-fixture\push-data.bin')
class Checks(unittest.TestCase):
 def test_historical_rxpk_both_paths_and_missing_zero(self):
  pkt=json.loads(fixture.read_bytes()[12:])['rxpk'][0];self.assertEqual(pkt['codr'],'4/5');self.assertNotIn('rfch',pkt)
  for extended in (pkt,dict(pkt,rfch=0),{k:v for k,v in pkt.items() if k not in ('codr','rfch')}):
   t=Topology();t.ingest(extended);legacy=t.snapshot()['reports'][0]['lora'];g=Gateway('b827ebfffe32e2c1','127.0.0.1',None);g.ingest(extended);direct=g.snapshot()['reports'][0]['lora'];self.assertEqual(legacy['coding_rate'],extended.get('codr'));self.assertEqual(legacy['rf_chain'],extended.get('rfch'));self.assertEqual(direct['codr'],extended.get('codr'));self.assertEqual(direct['rfch'],extended.get('rfch'));self.assertEqual(legacy['channel'],extended['chan']);self.assertEqual(legacy['datarate'],extended['datr']);g.archive.close()
 def test_neighbor_valid_bits(self):
  report=dict(observer_id='02:00:00:00:00:02',observer_boot=1,report_seq=1,snapshot_at_ms=10,wifi_group=1,report_period_ms=10000,neighbors=[dict(peer_id='02:00:00:00:00:03',peer_boot=2,state='heard',seen_age_ms=10,ack_age_ms=None,rssi_dbm=None,rf_age_ms=None,channel=None),dict(peer_id='02:00:00:00:00:04',peer_boot=3,state='bidirectional',seen_age_ms=10,ack_age_ms=0,rssi_dbm=-70,rf_age_ms=0,channel=11)])
  raw=encode_frame(report);decoded=decode_frame(raw);t=Topology();t.ingest({'data':base64.b64encode(raw).decode(),'freq':470.5});rows=t.snapshot()['reports'][0]['report']['neighbors']
  for a,b in zip(rows,decoded['neighbors']):
   self.assertEqual(a['ack_age_ms'],b['ack_age_ms']);self.assertEqual(a['rf_age_ms'],b['rf_age_ms']);self.assertEqual(a['wifi_channel'],b['channel']);self.assertEqual(a['rssi_dbm'],b['rssi_dbm'])
 def test_old_record_unchanged(self):
  old={'schema':'lora.topology.v1','reports':[{'lora':{'channel':5,'datarate':'SF7BW125'}}]}
  with tempfile.TemporaryDirectory() as d:
   r=Replay(pathlib.Path(d)/'rec.sqlite3',lambda:old,60);ident=r.start();r.sample();r.stop();self.assertEqual(r.session(ident)['frames'][0]['topology'],old);r.close()
if __name__=='__main__':unittest.main(verbosity=2)
