import json,pathlib,sys,types,unittest
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'))
from tools.mobile_gateway.sources import Sources
from tools.mobile_gateway.serial_discovery import SerialDiscovery
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
class Port:
 def __init__(self,name):self.device=name;self.vid=0x1a86;self.pid=0x7523
class FakeWire:
 def __init__(self,db,**kwargs):self.db=db;self.port=None;self.dtr=None;self.rts=None;self.buf=b'';self.in_waiting=0;self.commands=[];self.closed=False
 def open(self):assert self.dtr is False and self.rts is False
 def write(self,part):
  self.buf+=part
  if b'\n' in self.buf:
   request=json.loads(self.buf);self.buf=b'';name=request['cmd'];self.commands.append(name);assert name in ('info','lora_ref_status');config=self.db[self.port]
   base={'schema':'mid.serial.v1','event':'command_result','nonce':request['nonce'],'ok':True,'node_id':config['mac']}
   base.update({'firmware':'mid-espnow','chip':'esp32s3','lora_ref_api':1} if name=='info' else {'lora_ref_requested_role':config['role'],'lora_ref_worker_state':1,'requested_generation':2,'applied_generation':2})
   self.response=json.dumps(base).encode()+b'\n'
  return len(part)
 def read(self,n):value=getattr(self,'response',b'');self.response=b'';return value
 def close(self):self.closed=True
class Tests(unittest.TestCase):
 def setUp(self):
  self.db={'COM8':{'mac':'90:da:72:48:a5:cc','role':'rx'},'COM9':{'mac':'90:da:72:48:a4:f8','role':'tx'}};self.wires=[];self.sources=Sources(start=False)
  def factory(**kw):
   w=FakeWire(self.db,**kw);self.wires.append(w);return w
  self.scan=SerialDiscovery(self.sources,None,start=False,serial_factory=factory)
 def tearDown(self):
  for key in list(self.scan.sessions):self.scan.drop(key)
  self.sources.close()
 def test_unconfigured_non1_rx_and_tx_capability(self):
  self.scan.scan_once([Port('COM8'),Port('COM9')]);v=self.sources.sources();rows={r['gateway_id']:r for r in v['sources']};self.assertTrue(rows[self.db['COM8']['mac']]['available']);self.assertTrue(rows[self.db['COM8']['mac']]['capabilities']['receive']);self.assertFalse(rows[self.db['COM9']['mac']]['available']);self.assertFalse(rows[self.db['COM9']['mac']]['capabilities']['receive']);self.assertIn('未运行',rows[self.db['COM9']['mac']]['capabilities']['reason']);self.assertEqual(v['selected_source_id'],'serial:'+self.db['COM8']['mac']);self.assertTrue(all(w.commands==['info','lora_ref_status'] for w in self.wires))
 def test_port_drift_and_new_mac_isolated(self):
  self.scan.scan_once([Port('COM8')]);mac=self.db['COM8']['mac'];a=self.scan.sessions['COM8']['adapter'];report={'observer_id':'02:00:00:00:00:02','observer_boot':1,'report_seq':1,'snapshot_at_ms':10,'wifi_group':1,'report_period_ms':10000,'neighbors':[]};line=json.dumps({'schema':'lora.ref.v1','event':'lora_ref_rx','gateway_id':mac,'gateway_boot':3,'rx_seq':1,'received_at_ms':100,'lora':{'rssi_dbm':-70,'snr_db':5},'frame_hex':encode_frame(report).hex()});a.ingest(line)
  self.db['COM12']=self.db.pop('COM8');self.scan.scan_once([Port('COM12')]);self.assertIs(self.scan.sessions['COM12']['adapter'],a);self.assertEqual(len(a.topology()['reports']),1)
  self.scan.scan_once([]);self.db['COM12']={'mac':'90:da:72:48:a4:e0','role':'rx'};self.scan.scan_once([Port('COM12')]);new=self.scan.sessions['COM12']['adapter'];self.assertNotEqual(new.mac,mac);self.assertEqual(new.topology()['reports'],[]);self.assertIn('serial:'+mac,self.sources.entries);self.assertEqual(self.sources.topology()['source_id'],'serial:'+new.mac)
if __name__=='__main__':unittest.main(verbosity=2)
