import json,pathlib,socket,subprocess,sys,time,unittest,urllib.request
from unittest.mock import patch
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'));sys.path.insert(0,str(root/'app/start'))
from tools.mobile_gateway.serial_discovery import SerialDiscovery
from tools.mobile_gateway.sources import Sources
class P:
 def __init__(self,dev,loc=None,vid=0x1a86,pid=0x7523):self.device=dev;self.location=loc;self.vid=vid;self.pid=pid
class Checks(unittest.TestCase):
 def test_location_priority_ambiguity_and_mac_rejection(self):
  sources=Sources(start=False);d=SerialDiscovery(sources,None,node_mac='90:da:72:48:a5:cc',location='wanted',port='COM99',start=False)
  seen=[]
  with patch.object(d,'probe',side_effect=lambda p:seen.append(p.device)):
   d.scan_once([P('COM3','wanted'),P('COM99','other')]);self.assertEqual(seen,['COM3']);seen.clear()
   d.scan_once([P('COM3','wanted'),P('COM4','wanted')]);self.assertEqual(seen,[])
  class Wire:
   def __init__(self,**kw):self.port=None;self.dtr=self.rts=None;self.closed=False
   def open(self):pass
   def close(self):self.closed=True
  wire=Wire();d.serial_factory=lambda **_:wire
  with patch.object(d,'command',return_value={'firmware':'mid-espnow','chip':'esp32s3','node_id':'90:da:72:48:a4:f8','lora_ref_api':1}) as cmd:
   with self.assertRaises(ValueError):d.probe(P('COM3','wanted'))
   self.assertEqual(cmd.call_count,1);self.assertEqual(sources.entries,{});self.assertTrue(wire.closed)
  sources.close()
 def test_studio_actual_worker_explicit_nonch340_port_beyond_first_eight(self):
  p=socket.socket();p.bind(('127.0.0.1',0));port=p.getsockname()[1];p.close();u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.bind(('127.0.0.1',0));udp=u.getsockname()[1];u.close()
  wd=pathlib.Path.cwd();fleet=wd/'fleet.json';fleet.write_text(json.dumps({'schema_version':1,'nodes':[{'node_id':2,'mac':'90:da:72:48:a5:cc'}]}));trace=wd/'trace.txt';fixture=pathlib.Path(r'D:\Multi-Agent Network\simulation\outputs\E2-039\20261115-08-explicit-serial\studio_fake_serial.py')
  cmd=[sys.executable,'-u','-X','utf8',str(fixture),str(trace),'--port',str(port),'--udp-port',str(udp),'--output',str(wd/'studio'),'--production-output','--fleet',str(fleet),'--gateway-mode','node_serial','--node-mac','90:da:72:48:a5:cc','--serial-port','COM99','--serial-lease-dir',str(wd/'lease')]
  child=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8');op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  try:
   self.assertIn('url',json.loads(child.stdout.readline()));end=time.monotonic()+4;rows=[]
   while time.monotonic()<end:
    rows=json.load(op.open('http://127.0.0.1:%d/api/v1/lora/sources'%port,timeout=1))['sources']
    if any(r['gateway_id']=='90:da:72:48:a5:cc' and r['available'] for r in rows):break
    time.sleep(.05)
   self.assertTrue(any(r['id']=='serial:90:da:72:48:a5:cc' and r['available'] for r in rows));lines=trace.read_text().splitlines();self.assertEqual(lines,['open COM99','info COM99','lora_ref_status COM99'])
  finally:child.terminate();child.communicate(timeout=5)
if __name__=='__main__':unittest.main(verbosity=2)
