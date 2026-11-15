import sys,json,pathlib,unittest,subprocess,socket,time,urllib.request
from unittest.mock import patch
root=pathlib.Path.cwd().parent.parent;sys.path.insert(0,str(root/'app/services'))
from tools.mobile_gateway.node_serial import SerialTopology
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
MAC='90:da:72:48:a4:f8'
def line(seq=1,mac=MAC):
 report=dict(observer_id='02:00:00:00:00:02',observer_boot=1,report_seq=seq,snapshot_at_ms=seq*10,wifi_group=1,report_period_ms=10000,neighbors=[])
 return json.dumps(dict(schema='lora.ref.v1',event='lora_ref_rx',gateway_id=mac,gateway_boot=3,rx_seq=seq,received_at_ms=seq*100,lora={'rssi_dbm':-70,'snr_db':5},frame_hex=encode_frame(report).hex()))
class Checks(unittest.TestCase):
 def test_age_identity_loss_and_recovery(self):
  now=[0.];t=SerialTopology(MAC,clock=lambda:now[0],start=False);t.serial_open=True;self.assertTrue(t.ingest(line()));self.assertFalse(t.ingest(line()));now[0]=36;v=t.topology();self.assertTrue(v['receiver']['gateway_observed']);self.assertEqual(v['reports'][0]['node_observation_state'],'timed_out');self.assertEqual(v['reports'][0]['pc_receive_age_ms'],36000)
  t.serial_open=False;t.verified=False;t.state='unavailable';now[0]=40;v=t.topology();self.assertFalse(v['receiver']['gateway_observed']);self.assertEqual(v['reports'][0]['pc_receive_age_ms'],40000)
  with self.assertRaises(ValueError):t.ingest(line(2,'90:da:72:48:a5:cc'))
  t.serial_open=True;self.assertTrue(t.ingest(line(2)));self.assertTrue(t.topology()['receiver']['gateway_observed']);self.assertEqual(t.topology()['reports'][0]['node_observation_state'],'recent')
 def test_location_and_missing_lease(self):
  class Port:
   def __init__(self,device,location):self.device=device;self.location=location
  with patch('serial.tools.list_ports.comports',return_value=[Port('COM91','1-1'),Port('COM3','1-2')]):self.assertEqual(SerialTopology(MAC,location='1-1',start=False).select_port(),'COM91')
  with patch('serial.tools.list_ports.comports',return_value=[Port('COM91','1-1'),Port('COM92','1-1')]):
   with self.assertRaises(ValueError):SerialTopology(MAC,location='1-1',start=False).select_port()
  with patch('serial.tools.list_ports.comports',side_effect=AssertionError('unexpected enumeration')):
   with self.assertRaises(ValueError):SerialTopology(MAC,start=False).select_port()
  with self.assertRaises(ValueError):SerialTopology(MAC,start=False).acquire_lease()
 def test_shared_windows_lease(self):
  lease=pathlib.Path.cwd()/'lease';lease.mkdir();lock=lease/'serial.lock';code='import msvcrt,sys;f=open(sys.argv[1],"a+b");f.write(b"0");f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1);print("ready",flush=True);sys.stdin.readline()';p=subprocess.Popen([sys.executable,'-u','-c',code,str(lock)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
  try:
   self.assertEqual(p.stdout.readline().strip(),'ready')
   with self.assertRaises(OSError):SerialTopology(MAC,lease_dir=lease,start=False).acquire_lease()
  finally:p.communicate(input='stop\n',timeout=5)
  h=SerialTopology(MAC,lease_dir=lease,start=False).acquire_lease();h.close();self.assertEqual(json.loads((lease/'owner.json').read_text())['owner'],'H020-Studio-LoRa')
 def test_mode_dispatch(self):
  sys.path.insert(0,str(root/'app/start'));import launcher
  for mode in ('remote','node_serial'):
   with patch.object(launcher,'launch_remote',return_value=('selected',mode)) as launch:
    self.assertEqual(launcher.launch({'gateway':{'mode':mode}},None,None,None),('selected',mode));launch.assert_called_once()
 def test_actual_studio_no_lease_no_serial(self):
  sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();run=pathlib.Path.cwd()/'studio';cfg=pathlib.Path.cwd()/'fleet.json';cfg.write_text(json.dumps({'schema_version':1,'nodes':[{'node_id':1,'mac':MAC}]}));cmd=[sys.executable,'-I','-u','-X','utf8','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("tools.mobile_gateway.studio",run_name="__main__")',str(root/'app/services'),'--port',str(port),'--output',str(run),'--production-output','--fleet',str(cfg),'--gateway-mode','node_serial','--node-mac',MAC];p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
  try:
   self.assertIn('url',json.loads(p.stdout.readline()));op=urllib.request.build_opener(urllib.request.ProxyHandler({}));v=json.load(op.open('http://127.0.0.1:%d/api/v1/lora/topology'%port,timeout=3));self.assertEqual(v['receiver']['mode'],'node_serial');self.assertFalse(v['receiver']['gateway_observed']);self.assertEqual(v['reports'],[])
  finally:p.terminate();p.communicate(timeout=5)
if __name__=='__main__':unittest.main(verbosity=2)
