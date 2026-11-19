import base64,json,pathlib,sys,tempfile,unittest,threading
from unittest.mock import patch
root=pathlib.Path(r'D:\Multi-Agent Network');sys.path.insert(0,str(root))
from tools.mobile_gateway.replay import Replay
from tools.mid_baseline.gateway_probe.topology_server import Topology
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
class T(unittest.TestCase):
 def test_reopen_and_observation_transitions(self):
  value={'schema':'lora.topology.v1','source_id':'serial:test','selection_epoch':1,'receiver':{'gateway_observed':True},'reports':[]}
  with tempfile.TemporaryDirectory() as d:
   p=pathlib.Path(d)/'r.sqlite';r=Replay(p,lambda:value,interval=60);ident=r.start();r.sample();value['receiver']['gateway_observed']=False;r.sample();value['receiver']['gateway_observed']=True;r.sample();r.stop();r.close();r=Replay(p,lambda:value,interval=60)
   try:
    rows=r.session(ident)['frames'];self.assertEqual([x['topology']['receiver']['gateway_observed'] for x in rows],[True,False,True]);self.assertEqual(r.sessions()['sessions'][0]['count'],3)
   finally:r.close()
 def test_old_and_sparse_status(self):
  t=Topology();base=dict(observer_id='02:00:00:00:00:02',observer_boot=1,report_seq=1,snapshot_at_ms=10,wifi_group=1,report_period_ms=10000,neighbors=[])
  def ingest(report):t.ingest({'data':base64.b64encode(encode_frame(report)).decode(),'freq':470.5})
  ingest(base);v=t.snapshot()['reports'][0];self.assertIsNone(v['report']['status']);self.assertIsNone(v['status_age_ms'])
  status=dict(reset_reason=0,supply_mv=3300,die_temp_c=20,heap_free_kb=10,queue_depth=0,tx_drops=0,routes=0,lora_tx_power_dbm=10,lora_sf=7,fault_flags=0,pi_flags=0,pi_cpu_temp_c=0,pi_load_x10=0,pi_mem_free_mb=0,pi_wifi_rssi=0,serial_errors=0,battery_pct=0)
  ingest(dict(base,report_seq=2,status=status));v=t.snapshot()['reports'][0];stamp=v['status_received_at_ms'];self.assertIsNotNone(stamp)
  ingest(dict(base,report_seq=3));v=t.snapshot()['reports'][0];self.assertEqual(v['status_received_at_ms'],stamp);self.assertEqual(v['report']['status']['supply_mv'],3300)
  ingest(dict(base,observer_boot=2,report_seq=1));self.assertIsNone(t.snapshot()['reports'][0]['report']['status'])
  previous=t.last_rx;t.ingest({'data':base64.b64encode(b'foreign').decode()});self.assertEqual(t.last_rx,previous)
 def test_pull_heartbeat_with_no_lrn1(self):
  from tools.mid_baseline.gateway_probe import topology_server as mod
  stop=threading.Event();top=Topology()
  class Sock:
   def setsockopt(self,*a):pass
   def bind(self,*a):pass
   def settimeout(self,*a):pass
   def recvfrom(self,n):stop.set();return bytes.fromhex('02567802b827ebfffe32e2c1'),('127.0.0.1',3333)
   def sendto(self,data,addr):self.ack=data
   def close(self):pass
  sock=Sock()
  with patch.object(mod,'claim_port',return_value=True),patch.object(mod.socket,'socket',return_value=sock):mod.udp_loop(top,1680,stop)
  self.assertEqual(sock.ack.hex(),'02567804');self.assertTrue(top.snapshot()['receiver']['gateway_observed']);self.assertIsNone(top.last_rx);self.assertEqual(top.snapshot()['reports'],[])
if __name__=='__main__':unittest.main(verbosity=2)
