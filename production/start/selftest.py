"""Offline-only launcher checks: generated mock release and ephemeral loopback ports."""
import copy,hashlib,json,socket,tempfile,threading,unittest,subprocess,sys
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import launcher

class Checks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.cfg=launcher.config(launcher.ROOT/'production/config/fleet.example.json')
 def tearDown(self):self.tmp.cleanup()
 def free(self,kind):
  s=socket.socket(socket.AF_INET,kind);s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
 def fake_release(self):
  root=self.root/'release';root.mkdir();program='''import argparse,json,threading\nfrom http.server import BaseHTTPRequestHandler,HTTPServer\np=argparse.ArgumentParser();p.add_argument("--port",type=int,required=True);p.add_argument("--mode",required=True);a=p.parse_args()\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  x=json.dumps({"receiver":{"gateway_id":"b827ebfffe32e2c1","gateway_observed":True}}).encode();self.send_response(200);self.send_header("Content-Length",str(len(x)));self.end_headers();self.wfile.write(x)\n def log_message(self,*a):pass\ns=HTTPServer(("127.0.0.1",a.port),H)\nif a.mode=="studio":threading.Timer(1.0,s.shutdown).start()\ns.serve_forever();s.server_close()\n'''
  for name in ['mock_gateway.py','mock_studio.py']:(root/name).write_text(program,encoding='utf-8')
  hashes={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['mock_gateway.py','mock_studio.py']}
  m=dict(schema_version=1,release_id='mock-only',status='candidate',source_commit='a'*40,service_files_sha256=hashes,services=dict(gateway_module='mock.gateway',studio_module='mock.studio',gateway_args=['--port','{topology_port}','--mode','gateway'],studio_args=['--port','{studio_port}','--mode','studio']))
  pkg=root/'mock';pkg.mkdir()
  for src,name in [('mock_gateway.py','gateway.py'),('mock_studio.py','studio.py')]:
   (pkg/name).write_bytes((root/src).read_bytes());(root/src).unlink()
  m['service_files_sha256']={f'mock/{n}.py':hashlib.sha256((pkg/(n+'.py')).read_bytes()).hexdigest() for n in ['gateway','studio']}
  (root/'manifest.json').write_text(json.dumps(m));return root,m
 def test_default_release_is_explicitly_missing(self):
  with self.assertRaises((ValueError,FileNotFoundError)):launcher.release(launcher.ROOT/'production/release/manifest.example.json')
 def test_duplicate_ids_and_release_hash(self):
  c=copy.deepcopy(self.cfg);c['nodes'][1]['node_id']=c['nodes'][0]['node_id'];p=self.root/'fleet.json';p.write_text(json.dumps(c))
  with self.assertRaises(ValueError):launcher.config(p)
  root,m=self.fake_release();launcher.release(root);(root/'mock/gateway.py').write_text('tampered')
  with self.assertRaisesRegex(ValueError,'hash mismatch'):launcher.release(root)
 def test_fleet_normalization_conflict(self):
  c=copy.deepcopy(self.cfg);c['nodes'][0]['mac']=c['nodes'][0]['mac'].upper();p=self.root/'fleet.json';p.write_text(json.dumps(c));launcher.config(p)
  c['nodes'][1]['mac']=c['nodes'][0]['mac'].lower();p.write_text(json.dumps(c))
  with self.assertRaises(ValueError):launcher.config(p)
 def test_validated_fleet_backup_recovery(self):
  p=self.root/'fleet.json';p.write_text(json.dumps(self.cfg),encoding='utf-8');local=self.root/'local';launcher.save_config_backup(p,local)
  p.write_text('{invalid',encoding='utf-8');value,selected,recovered=launcher.config_with_backup(p,local)
  self.assertTrue(recovered);self.assertEqual(value,self.cfg);self.assertNotEqual(selected,p);self.assertEqual(p.read_text(),'{invalid')
  backup=local/'fleet.last-good.json';item=json.loads(backup.read_text(encoding='utf-8'));item['sha256']='0'*64;backup.write_text(json.dumps(item),encoding='utf-8')
  with self.assertRaises(ValueError):launcher.config_with_backup(p,local)
 def test_unverified_eui_is_not_online(self):
  class Child:
   def poll(self):return None
  with patch.object(launcher,'get_json',return_value={'receiver':{'gateway_id':'b827ebfffe32e2c1','gateway_observed':False}}):
   found,_=launcher.discover('http://unused','b827ebfffe32e2c1',Child(),seconds=.01);self.assertFalse(found)
 def test_offline_endpoint(self):
  server=ThreadingHTTPServer(('127.0.0.1',0),launcher.Offline);server.reason='missing frozen package';thread=threading.Thread(target=server.serve_forever);thread.start()
  try:
   v=launcher.get_json(f'http://127.0.0.1:{server.server_port}/api/status');self.assertFalse(v['online']);self.assertFalse(v['replay']);self.assertEqual(v['reason'],'missing frozen package')
  finally:server.shutdown();server.server_close();thread.join()
 def test_port_conflict_and_lock(self):
  held=socket.socket(socket.AF_INET,socket.SOCK_STREAM);held.bind(('127.0.0.1',0))
  try:
   with self.assertRaises(OSError):launcher.available([held.getsockname()[1]],self.free(socket.SOCK_DGRAM))
  finally:held.close()
  path=self.root/'instance.lock';handle=launcher.lock(path)
  try:
   code='import sys;sys.path.insert(0,sys.argv[1]);import launcher;launcher.lock(__import__("pathlib").Path(sys.argv[2]))'
   result=subprocess.run([sys.executable,'-c',code,str(Path(launcher.__file__).parent),str(path)],capture_output=True,text=True,timeout=5)
   self.assertNotEqual(result.returncode,0);self.assertIn('instance lock',result.stderr)
  finally:handle.close()
 def test_mock_services_with_release_isolation(self):
  root,m=self.fake_release();root,m=launcher.release(root);c=copy.deepcopy(self.cfg);c['services']['topology_port']=self.free(socket.SOCK_STREAM);c['services']['studio_port']=self.free(socket.SOCK_STREAM);c['gateway']['udp_port']=self.free(socket.SOCK_DGRAM)
  run=self.root/'run';run.mkdir()
  with patch.object(launcher.webbrowser,'open',return_value=True):ok,reason=launcher.launch(c,root,m,run)
  self.assertFalse(ok);self.assertIn('exited',reason);self.assertTrue((run/'gateway-192.168.137.200.log').exists())
 def test_offline_then_gateway_reconnect(self):
  root,m=self.fake_release();c=copy.deepcopy(self.cfg);c['services']['topology_port']=self.free(socket.SOCK_STREAM);c['gateway']['udp_port']=self.free(socket.SOCK_DGRAM)
  server=ThreadingHTTPServer(('127.0.0.1',0),launcher.Offline);server.reason='waiting';c['services']['studio_port']=server.server_port
  thread=threading.Thread(target=server.serve_forever);thread.start();run=self.root/'retry';run.mkdir()
  try:
   self.assertFalse(launcher.get_json(f'http://127.0.0.1:{server.server_port}/api/status')['online'])
   with patch.object(launcher,'discover',side_effect=[(False,'no matching gateway PULL_DATA within timeout'),(True,'verified PULL_DATA gateway EUI')]),patch.object(launcher.webbrowser,'open',return_value=True) as browser:
    ok,reason=launcher.launch(c,root,m,run,server)
   self.assertFalse(ok);self.assertIn('exited',reason);browser.assert_called_once()
  finally:server.shutdown();server.server_close();thread.join()

def main():
 result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Checks));return 0 if result.wasSuccessful() else 1
