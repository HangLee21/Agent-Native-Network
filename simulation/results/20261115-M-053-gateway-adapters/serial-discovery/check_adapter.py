import json, pathlib, socket, sys, time, unittest, subprocess, urllib.request
from unittest.mock import patch
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'));sys.path.insert(0,str(root/'app/start'))
from tools.mobile_gateway.sources import Sources
import launcher
fixture=pathlib.Path(r'D:\Multi-Agent Network\simulation\outputs\H-025\20261115-02-legacy-fixture')
class Fake:
 def __init__(self,id):self.id=id;self.alive=True;self.age=100
 def topology(self):return dict(schema='lora.topology.v1',source='fixture',receiver=dict(gateway_id=self.id,gateway_observed=self.alive,identity_verified=True,state='receiving' if self.alive else 'unavailable'),reports=[dict(gateway_id=self.id,pc_receive_age_ms=self.age)],control={'enabled':False,'reason':'fixture'},labels={})
class Checks(unittest.TestCase):
 def test_loopback_historical_frame_and_acks(self):
  s=Sources(udp_port=0,udp_host='127.0.0.1');client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.settimeout(2)
  try:
   addr=s.sock.getsockname();client.sendto((fixture/'pull-data.bin').read_bytes(),addr);self.assertEqual(client.recv(32).hex(),'02567804');client.sendto((fixture/'push-data.bin').read_bytes(),addr);self.assertEqual(client.recv(32).hex(),'02123401')
   for _ in range(20):
    v=s.topology()
    if v['reports']:break
    time.sleep(.05)
   self.assertEqual(len(v['reports']),1);self.assertEqual(v['receiver']['gateway_id'],'b827ebfffe32e2c1');self.assertTrue(v['source_id'].startswith('udp:'));self.assertFalse(v['control']['enabled'])
  finally:client.close();s.close()
 def test_selection_fallback_recovery_isolation(self):
  s=Sources(start=False);a=Fake('a');b=Fake('b');s.add('serial',a,'A');s.add('http',b,'B')
  try:
   s.select('serial:configured');self.assertEqual(s.topology()['reports'][0]['gateway_id'],'a');a.alive=False;v=s.sources();self.assertEqual(v['preferred_source_id'],'serial:configured');self.assertEqual(v['selected_source_id'],'http:configured');self.assertEqual(s.topology()['reports'][0]['gateway_id'],'b');a.age=36000;a.alive=True;self.assertEqual(s.topology()['reports'][0]['pc_receive_age_ms'],36000);self.assertEqual(s.topology()['source_id'],'serial:configured')
   with self.assertRaises(ValueError):s.select('unknown')
  finally:s.close()
 def test_serial_no_eui_and_non1_config(self):
  p=pathlib.Path.cwd()/'fleet-test.json';c=json.loads((root/'config/fleet.default.json').read_text());c['gateway']={'mode':'node_serial','serial_node_mac':c['nodes'][1]['mac']};p.write_text(json.dumps(c));v=launcher.config(p);self.assertEqual(v['gateway']['serial_node_mac'],c['nodes'][1]['mac'])
  calls=[]
  with patch.object(launcher,'start_child',side_effect=RuntimeError('stop after args')) as start:
   class Dummy:
    def shutdown(self):pass
    def server_close(self):pass
   run=pathlib.Path.cwd()/'launch';run.mkdir();manifest={'services':{'studio_args':[],'studio_module':'tools.mobile_gateway.studio'}}
   with self.assertRaises(RuntimeError):launcher.launch_remote(v,root,manifest,run,None,p)
   self.assertEqual(start.call_args.args[2][start.call_args.args[2].index('--node-mac')+1],c['nodes'][1]['mac'])
 def test_studio_sources_http(self):
  sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();u=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);u.bind(('127.0.0.1',0));udp=u.getsockname()[1];u.close()
  out=pathlib.Path.cwd()/'studio';fleet=pathlib.Path.cwd()/'minimal-fleet.json';fleet.write_text(json.dumps({'schema_version':1,'nodes':[{'node_id':2,'mac':'90:da:72:48:a5:cc'}]}))
  cmd=[sys.executable,'-I','-X','utf8','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("tools.mobile_gateway.studio",run_name="__main__")',str(root/'app/services'),'--port',str(port),'--udp-port',str(udp),'--output',str(out),'--production-output','--fleet',str(fleet),'--gateway-mode','node_serial','--node-mac','90:da:72:48:a5:cc']
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8')
  try:
   self.assertIn('url',json.loads(proc.stdout.readline()));op=urllib.request.build_opener(urllib.request.ProxyHandler({}));base='http://127.0.0.1:%d'%port
   v=json.load(op.open(base+'/api/v1/lora/sources',timeout=3));self.assertEqual(v['schema'],'lora.sources.v1');self.assertEqual(v['selection'],'auto')
   topology=json.load(op.open(base+'/api/v1/lora/topology',timeout=3));self.assertIsNone(topology['source_id'])
   req=urllib.request.Request(base+'/api/v1/lora/sources/select',data=b'{"source_id":null}',headers={'Content-Type':'application/json','Origin':base});self.assertEqual(json.load(op.open(req,timeout=3))['selection'],'auto')
  finally:proc.terminate();proc.communicate(timeout=5)
 def test_existing_http_identity_and_disconnect(self):
  from tools.mobile_gateway.remote import RemoteGateway
  eui='b827ebfffe32e2c1';remote=RemoteGateway(eui,['127.0.0.1'])
  values=[{'schema':'ann.gateway.appliance.v1','gateway_eui':eui,'api_version':1,'ready':True},{'schema':'lora.topology.v1','receiver':{'gateway_id':eui,'gateway_observed':True},'reports':[{'pc_receive_age_ms':123}]}]
  with patch.object(remote,'discover',return_value=None),patch('tools.mobile_gateway.remote.get_json',side_effect=values):self.assertEqual(remote.topology()['receiver']['gateway_id'],eui)
  remote.last_at=0;remote.good_at-=2
  with patch.object(remote,'discover',return_value=None),patch('tools.mobile_gateway.remote.get_json',side_effect=OSError('offline')):
   v=remote.topology();self.assertFalse(v['receiver']['gateway_observed']);self.assertGreaterEqual(v['reports'][0]['pc_receive_age_ms'],2123)
if __name__=='__main__':unittest.main(verbosity=2)
