"""Offline integration check: actual Studio process and temporary loopback port."""
import json,os,socket,subprocess,sys,tempfile,time,unittest,urllib.request,urllib.error
from pathlib import Path
from .server import ROOT
from .fleet_registry import merged_fleet

class MergeFixtures(unittest.TestCase):
 def test_validation_and_normalization(self):
  with tempfile.TemporaryDirectory() as d:
   base=Path(d);fleet=base/'fleet.json';registry=base/'registry.json'
   def put(path,nodes,version=1):path.write_text(json.dumps({'schema_version':version,'nodes':nodes}),encoding='utf-8')
   a={'mac':'AA:00:00:00:00:01','node_id':1};b={'mac':'aa:00:00:00:00:1b','node_id':27};c={'mac':'aa:00:00:00:00:64','node_id':100}
   put(fleet,[a]);self.assertEqual(len(merged_fleet(fleet,registry)['nodes']),1)
   put(registry,[a,b,c]);result=merged_fleet(fleet,registry);self.assertEqual([n['node_id'] for n in result['nodes']],[1,27,100]);self.assertEqual(result['nodes'][0]['mac'],a['mac'].lower())
   for rows in ([a,a],[b,dict(b,node_id=28)],[b,dict(c,node_id=27)],[dict(b,node_id=True)],[dict(b,node_id=0x100000000)]):
    put(registry,rows)
    with self.assertRaises(ValueError):merged_fleet(fleet,registry)
   for rows in ([dict(a,node_id=2)],[dict(b,node_id=1)]):
    put(registry,rows)
    with self.assertRaisesRegex(ValueError,'冲突'):merged_fleet(fleet,registry)
   put(registry,[b],version=2)
   with self.assertRaises(ValueError):merged_fleet(fleet,registry)
   put(registry,[b]);put(fleet,[a,a])
   with self.assertRaises(ValueError):merged_fleet(fleet,registry)

class Integration(unittest.TestCase):
 def test_fleet_and_production_output(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);fleet={'schema_version':1,'nodes':[{'node_id':105,'mac':'02:00:00:00:00:01'}]};cfg=root/'fleet.json';cfg.write_text(json.dumps(fleet));registry=root/'registry.json';recovery=root/'recovery.json';stop=root/'stop';out=root/'run'
   with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
   cmd=[sys.executable,'-X','utf8','-m','tools.mobile_gateway.studio','--port',str(port),'--output',str(out),'--production-output','--fleet',str(cfg),'--registry',str(registry),'--recovery-file',str(recovery),'--stop-file',str(stop)]
   p=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
   try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));until=time.monotonic()+8;result=None
    while time.monotonic()<until and p.poll() is None:
     try:
      with opener.open(f'http://127.0.0.1:{port}/api/v1/fleet',timeout=.3) as r:result=json.load(r)
      break
     except OSError:time.sleep(.1)
    if result is None:
     p.terminate();stdout,stderr=p.communicate(timeout=5);self.fail('Studio failed: '+stdout+stderr)
    self.assertEqual(result,fleet);self.assertTrue((out/'PROCESS.json').is_file())
    def update(value):
     tmp=root/'new-registry.json';tmp.write_text(json.dumps(value),encoding='utf-8');os.replace(tmp,registry)
    def fetch():
     with opener.open(f'http://127.0.0.1:{port}/api/v1/fleet',timeout=2) as r:return json.load(r)
    # These are reservations only, including one representing a failed provisioning attempt.
    reserved=[{'mac':'02:00:00:00:00:1b','node_id':27},{'mac':'02:00:00:00:00:64','node_id':100}]
    update({'schema_version':1,'nodes':reserved});self.assertEqual(fetch(),{'schema_version':1,'nodes':fleet['nodes']+reserved})
    update({'schema_version':1,'nodes':[{'mac':'02:00:00:00:00:02','node_id':105}]})
    with self.assertRaises(urllib.error.HTTPError) as error:fetch()
    self.assertEqual(error.exception.code,503);self.assertIn('冲突',json.load(error.exception)['error'])
    update({'schema_version':2,'nodes':reserved})
    with self.assertRaises(urllib.error.HTTPError) as error:fetch()
    self.assertEqual(error.exception.code,503)
    update({'schema_version':1,'nodes':reserved});self.assertEqual(fetch()['nodes'][-1],reserved[-1])
    for status in ('recovering','recovered'):
     recovery.write_text(json.dumps({'schema':'studio.recovery.v1','state':status,'reason':'synthetic','updated_at':time.time()}),encoding='utf-8')
     with opener.open(f'http://127.0.0.1:{port}/api/v1/recovery',timeout=2) as r:self.assertEqual(json.load(r)['state'],status)
    recovery.write_text(json.dumps({'schema':'studio.recovery.v1','state':'online','reason':'stale','updated_at':0}),encoding='utf-8')
    with self.assertRaises(urllib.error.HTTPError) as error:opener.open(f'http://127.0.0.1:{port}/api/v1/recovery',timeout=2)
    self.assertEqual(error.exception.code,503)
    with opener.open(f'http://127.0.0.1:{port}/',timeout=2) as r:self.assertIn(b'fleet-model.js',r.read())
    stop.touch();stdout,stderr=p.communicate(timeout=10);self.assertEqual(p.returncode,0,stdout+stderr)
   finally:
    if p.poll() is None:p.kill();p.communicate(timeout=5)

if __name__=='__main__':unittest.main()
