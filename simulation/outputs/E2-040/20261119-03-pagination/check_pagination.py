import json,pathlib,sys,tempfile,threading,unittest,urllib.error,urllib.request,zlib
from unittest.mock import patch
from http.server import ThreadingHTTPServer
root=pathlib.Path(r'D:\Multi-Agent Network');sys.path.insert(0,str(root))
from tools.mobile_gateway.replay import Replay,PaginationRequired
from tools.mobile_gateway.studio import StudioHandler
class Checks(unittest.TestCase):
 def test_sql_paging_and_http(self):
  with tempfile.TemporaryDirectory() as d:
   n=[0]
   def source():return {'schema':'lora.topology.v1','source':'fixture','seq':n[0],'reports':[]}
   r=Replay(pathlib.Path(d)/'replay.sqlite3',source,60);ident=r.start()
   for i in range(131):n[0]=i;r.sample()
   r.stop()
   try:
    with patch('tools.mobile_gateway.replay.zlib.decompress',wraps=zlib.decompress) as dec:
     page=r.session(ident,30,30);self.assertEqual((page['offset'],page['total']),(30,131));self.assertEqual([x['topology']['seq'] for x in page['frames']],list(range(30,60)));self.assertEqual(dec.call_count,30)
    self.assertEqual(len(r.session(ident,120,30)['frames']),11);self.assertEqual(r.session(ident,999,30)['frames'],[])
    with self.assertRaises(PaginationRequired):r.session(ident)
    with self.assertRaises(ValueError):r.session(ident,0,101)
    server=ThreadingHTTPServer(('127.0.0.1',0),StudioHandler);server.replay=r;thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:%d/api/v1/replay/session?id=%s'%(server.server_port,ident);op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
     result=json.load(op.open(base+'&offset=60&limit=30',timeout=2));self.assertEqual((result['offset'],result['total'],len(result['frames'])),(60,131,30));self.assertEqual(result['frames'][0]['topology']['seq'],60)
     for suffix,code in [('',413),('&offset=0',400),('&offset=-1&limit=30',400),('&offset=0&limit=101',400)]:
      with self.assertRaises(urllib.error.HTTPError) as err:op.open(base+suffix,timeout=2)
      self.assertEqual(err.exception.code,code)
      if code==413:self.assertEqual(json.load(err.exception)['total'],131)
    finally:server.shutdown();server.server_close();thread.join(3)
    small=r.start();r.sample();r.stop();self.assertEqual(r.session(small)['total'],1)
   finally:r.close()
if __name__=='__main__':unittest.main(verbosity=2)
