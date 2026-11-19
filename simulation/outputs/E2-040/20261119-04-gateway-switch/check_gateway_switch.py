import base64,pathlib,sys,unittest
sys.path.insert(0,r'D:\Multi-Agent Network')
from tools.mid_baseline.gateway_probe.topology_server import Topology
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
class Check(unittest.TestCase):
 def test_new_gateway_pull_clears_old_observations(self):
  t=Topology();node='02:00:00:00:00:02';t.labels[node]='manual label';t.note_gateway('0000000000000001')
  status=dict(reset_reason=0,supply_mv=3300,die_temp_c=20,heap_free_kb=10,queue_depth=0,tx_drops=0,routes=0,lora_tx_power_dbm=10,lora_sf=7,fault_flags=0,pi_flags=0,pi_cpu_temp_c=0,pi_load_x10=0,pi_mem_free_mb=0,pi_wifi_rssi=0,serial_errors=0,battery_pct=0)
  frame=dict(observer_id=node,observer_boot=1,report_seq=1,snapshot_at_ms=10,wifi_group=1,report_period_ms=10000,neighbors=[],status=status)
  t.ingest({'data':base64.b64encode(encode_frame(frame)).decode(),'freq':470.5});self.assertEqual(t.snapshot()['reports'][0]['report']['status']['supply_mv'],3300)
  t.note_gateway('0000000000000002');v=t.snapshot();self.assertEqual(v['receiver']['gateway_id'],'0000000000000002');self.assertTrue(v['receiver']['gateway_observed']);self.assertIsNone(v['receiver']['last_rx_age_ms']);self.assertEqual(v['reports'],[]);self.assertEqual(v['labels'][node],'manual label');self.assertEqual(t.last_rx_by,{})
  frame.pop('status');frame['report_seq']=2;t.ingest({'data':base64.b64encode(encode_frame(frame)).decode(),'freq':470.5});self.assertIsNone(t.snapshot()['reports'][0]['report']['status'])
if __name__=='__main__':unittest.main(verbosity=2)
