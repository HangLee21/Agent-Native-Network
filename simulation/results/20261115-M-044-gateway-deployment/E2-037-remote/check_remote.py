import sys,pathlib,socket,subprocess,json,time,base64,unittest,urllib.request,urllib.error,threading
root=pathlib.Path.cwd().parent.parent;sys.path.insert(0,str(root/'app/services'))
from tools.mobile_gateway.remote import RemoteGateway
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame,decode_frame
from tools.flight_link.compat_decoder import decode_frame as compat
EUI='b827ebfffe32e2c1'
def free(kind):
 s=socket.socket(socket.AF_INET,kind);s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
class Checks(unittest.TestCase):
 def test_real_appliance_discovery_receive_restart(self):
  udp,http,discovery=free(socket.SOCK_DGRAM),free(socket.SOCK_STREAM),free(socket.SOCK_DGRAM)
  cmd=[sys.executable,'-I','-u','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("tools.flight_link.appliance",run_name="__main__")',str(root/'app/services'),'--gateway-eui',EUI,'--forwarder-port',str(udp),'--http-host','127.0.0.1','--http-port',str(http),'--discovery-host','127.0.0.1','--discovery-port',str(discovery)]
  p=None
  try:
   p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');self.assertEqual(json.loads(p.stdout.readline())['status'],'ready')
   remote=RemoteGateway(EUI,['127.0.0.1'],http,discovery,broadcast='127.0.0.1');self.assertEqual(remote.discover(),('127.0.0.1',http));first=remote.topology();self.assertFalse(first['receiver']['gateway_observed']);self.assertEqual(remote.info['state'],'connected')
   wrong=RemoteGateway('0000000000000001',['127.0.0.1'],http,discovery,broadcast='127.0.0.1');self.assertEqual(wrong.topology()['reports'],[]);self.assertEqual(wrong.info['state'],'unavailable')
   r=dict(observer_id='02:00:00:00:00:01',observer_boot=1,report_seq=1,snapshot_at_ms=10,wifi_group=1,report_period_ms=10000,neighbors=[]);frame=encode_frame(r);self.assertEqual(compat(frame),decode_frame(frame))
   r2=dict(r,neighbors=[dict(peer_id='02:00:00:00:00:02',peer_boot=3,state='bidirectional',seen_age_ms=5,ack_age_ms=9,rssi_dbm=-70,rf_age_ms=20,channel=6)]);rich=encode_frame(r2);self.assertEqual(compat(rich),decode_frame(rich))
   op=urllib.request.build_opener(urllib.request.ProxyHandler({}));request=urllib.request.Request('http://127.0.0.1:%d/api/v1/commands'%http,b'{}',method='POST')
   with self.assertRaises(urllib.error.HTTPError) as err:op.open(request)
   self.assertEqual(err.exception.code,403)
   for broken in (frame[:-1],frame[:-1]+bytes([frame[-1]^1])):
    for decoder in (compat,decode_frame):
     with self.assertRaises(ValueError):decoder(broken)
   packet={'stat':1,'size':len(frame),'freq':470.5,'data':base64.b64encode(frame).decode()};eui=bytes.fromhex(EUI)
   sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));sock.settimeout(2)
   try:
    sock.sendto(bytes([2])+b'aa'+bytes([2])+eui,('127.0.0.1',udp));self.assertEqual(sock.recvfrom(128)[0][3],4)
    sock.sendto(bytes([2])+b'bb'+bytes([0])+eui+json.dumps({'rxpk':[packet]}).encode(),('127.0.0.1',udp));self.assertEqual(sock.recvfrom(128)[0][3],1)
   finally:sock.close()
   time.sleep(1.1);top=remote.topology();self.assertTrue(top['receiver']['gateway_observed']);self.assertEqual(top['reports'][0]['report']['observer_id'],r['observer_id']);self.assertFalse(top['control']['enabled'])
   studio_port=free(socket.SOCK_STREAM);run=pathlib.Path.cwd()/'studio-run';fleet=pathlib.Path.cwd()/'fleet.json';fleet.write_text(json.dumps({'schema_version':1,'nodes':[]}));stop=pathlib.Path.cwd()/'stop'
   scmd=[sys.executable,'-I','-u','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));import tools.mobile_gateway.remote as r;original=r.RemoteGateway;r.RemoteGateway=lambda e,c,h,d:original(e,c,h,d,broadcast="127.0.0.1");runpy.run_module("tools.mobile_gateway.studio",run_name="__main__")',str(root/'app/services'),'--port',str(studio_port),'--output',str(run),'--production-output','--fleet',str(fleet),'--registry',str(pathlib.Path.cwd()/'absent-registry'),'--gateway-mode','remote','--gateway-eui',EUI,'--candidate-host','127.0.0.2','--remote-http-port',str(http),'--discovery-port',str(discovery),'--stop-file',str(stop)]
   studio=subprocess.Popen(scmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
   try:
    self.assertIn('url',json.loads(studio.stdout.readline()));op=urllib.request.build_opener(urllib.request.ProxyHandler({}));url='http://127.0.0.1:%s/api/v1/lora/topology'%studio_port;self.assertEqual(len(json.load(op.open(url))['reports']),1)
    p.terminate();p.communicate(timeout=5);time.sleep(1.1);self.assertEqual(remote.topology()['reports'],[]);self.assertEqual(remote.info['state'],'unavailable');self.assertEqual(json.load(op.open(url))['reports'],[])
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');self.assertEqual(json.loads(p.stdout.readline())['status'],'ready');time.sleep(1.1);self.assertEqual(json.load(op.open(url))['reports'],[]);self.assertEqual(remote.topology()['reports'],[]);self.assertEqual(remote.info['state'],'connected')
   finally:
    studio.terminate();studio.communicate(timeout=5)
  finally:
   if p and p.poll() is None:p.terminate();p.communicate(timeout=5)
 def test_wrong_nonce_and_unreachable(self):
  r=RemoteGateway(EUI,[],free(socket.SOCK_STREAM),free(socket.SOCK_DGRAM),broadcast='127.0.0.1');self.assertIsNone(r.discover());self.assertEqual(r.topology()['receiver']['state'],'unavailable')
  sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.settimeout(2)
  def reply():
   try:
    _,addr=sock.recvfrom(1024);sock.sendto(json.dumps({'schema':'ann.gateway.discover.v1','nonce':'0'*32,'gateway_eui':EUI,'api_version':1,'http_port':8780}).encode(),addr)
   finally:sock.close()
  thread=threading.Thread(target=reply);thread.start()
  try:self.assertIsNone(RemoteGateway(EUI,[],8780,port,broadcast='127.0.0.1').discover())
  finally:thread.join(3)
if __name__=='__main__':unittest.main(verbosity=2)
