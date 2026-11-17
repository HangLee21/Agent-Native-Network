import base64,json,socket,threading,time,unittest,urllib.request,struct,zlib
from .gateway import Gateway,Handler
from .codec import encode_command,decode_receipt,FORMAT
from http.server import ThreadingHTTPServer
from firmware.mid_baseline.field_agent.lora_ref.decoder import encode_frame
EUI='b827ebfffe32e2c1';A='02:00:00:00:00:01';B='02:00:00:00:00:02';TX=dict(freq=470.5,rfch=0,powe=14,modu='LORA',datr='SF7BW125',codr='4/5',ipol=False,ncrc=False)
class FakeSocket:
 def __init__(self):self.sent=[]
 def sendto(self,data,addr):self.sent.append((data,addr));return len(data)
def report(node,seq=1):
 return encode_frame(dict(observer_id=node,observer_boot=1,report_seq=seq,snapshot_at_ms=seq*10,wifi_group=1,report_period_ms=10000,neighbors=[]))
def pkt(frame):return dict(stat=1,size=len(frame),freq=470.5,data=base64.b64encode(frame).decode())
def receipt():
 raw=FORMAT.pack(b'LRA2',1,2,48,bytes.fromhex(A.replace(':','')),0,1,1,1,2,0,10,0)
 return raw[:-4]+struct.pack('<I',zlib.crc32(raw[:-4]))
class Checks(unittest.TestCase):
 def setUp(self):
  self.t=[0.];self.g=Gateway(EUI,'127.0.0.1',TX,clock=lambda:self.t[0],encoder=encode_command,ack_decoder=decode_receipt);self.g.sock=FakeSocket();self.addr=('127.0.0.1',1700)
 def test_node_age_boot_dedup_and_invalid(self):
  self.g.ingest(pkt(report(A)));self.t[0]=4;self.g.ingest(pkt(report(B)));self.g.ingest(pkt(report(A)));bad=pkt(report(B,2));bad['data']='!';self.g.ingest(bad);self.t[0]=5
  v={x['report']['observer_id']:x for x in self.g.snapshot()['reports']};self.assertEqual(v[A]['pc_receive_age_ms'],5000);self.assertEqual(v[B]['pc_receive_age_ms'],1000);self.assertEqual(self.g.stats['old_reports'],1);self.assertEqual(self.g.stats['invalid_frames'],1)
  self.t[0]=35;self.assertEqual(self.g.snapshot()['receiver']['state'],'stale')
 def test_gateway_ack_is_not_execution_and_late_receipt(self):
  self.g.handle(bytes([2])+b'aa'+bytes([2])+bytes.fromhex(EUI),self.addr);self.assertEqual(self.g.sock.sent[-1][0],bytes([2])+b'aa'+bytes([4]))
  self.assertTrue(self.g.snapshot()['receiver']['gateway_observed'])
  self.g.ingest(pkt(report(A)));q=dict(cmd_id='0000000000000001',target=A,target_boot=1,report_seq=1,operation='status',ttl_ms=10000);self.g.enqueue(q);self.g.flush();wire=self.g.sock.sent[-1][0];self.assertEqual(wire[3],3);tx=json.loads(wire[4:])['txpk'];self.assertEqual(base64.b64decode(tx['data'])[:4],b'LRC2')
  self.g.handle(bytes([2])+wire[1:3]+bytes([5])+bytes.fromhex(EUI)+b'{"txpk_ack":{"error":"NONE"}}',self.addr);self.assertEqual(self.g.commands['0000000000000001']['state'],'gateway_accepted');self.assertIsNone(self.g.commands['0000000000000001']['receipt'])
  self.t[0]=11;self.g.flush();self.assertEqual(self.g.commands['0000000000000001']['state'],'execution_unknown_timeout')
  self.t[0]=31;self.assertFalse(self.g.snapshot()['receiver']['gateway_observed'])
  ack=receipt();self.g.ingest(pkt(ack));self.assertEqual(self.g.commands['0000000000000001']['state'],'executed');self.g.ingest(pkt(ack));self.assertEqual(self.g.stats['duplicate_receipts'],1)
 def test_safety_capability_and_foreign_gateway(self):
  self.g.encoder=None
  with self.assertRaisesRegex(ValueError,'codec unavailable'):self.g.enqueue(dict(cmd_id='0000000000000001',target=A,target_boot=1,report_seq=1,operation='status',ttl_ms=10000))
  with self.assertRaises(ValueError):self.g.enqueue(dict(cmd_id='0000000000000002',target=A,target_boot=1,report_seq=1,operation='flight_action',ttl_ms=10000))
  self.g.handle(bytes([2])+b'aa'+bytes([2])+bytes.fromhex(EUI),('127.0.0.2',1700));self.assertIsNone(self.g.pull)
 def test_bounded_retries_and_obsolete_ack(self):
  self.g.ingest(pkt(report(A)));self.g.handle(bytes([2])+b'aa'+bytes([2])+bytes.fromhex(EUI),self.addr)
  q=dict(cmd_id='0000000000000001',target=A,target_boot=1,report_seq=1,operation='status',ttl_ms=10000);self.g.enqueue(q);self.g.flush();first=self.g.sock.sent[-1][0]
  self.t[0]=1;self.g.flush();second=self.g.sock.sent[-1][0];self.assertNotEqual(first[1:3],second[1:3])
  self.g.handle(bytes([2])+first[1:3]+bytes([5])+bytes.fromhex(EUI)+b'{"txpk_ack":{"error":"TOO_LATE"}}',self.addr)
  self.assertEqual(self.g.commands[q['cmd_id']]['state'],'gateway_sent')
  self.t[0]=2;self.g.flush();self.t[0]=3;before=len(self.g.sock.sent);self.g.flush();self.assertEqual(len(self.g.sock.sent),before);self.assertEqual(self.g.commands[q['cmd_id']]['attempts'],3)
  self.t[0]=10;self.g.flush();self.assertEqual(self.g.commands[q['cmd_id']]['state'],'execution_unknown_timeout')
 def test_crc_and_report_anchor(self):
  raw=receipt();broken=raw[:-1]+bytes([raw[-1]^1])
  with self.assertRaises(ValueError):decode_receipt(broken)
  self.g.ingest(pkt(report(A)))
  with self.assertRaisesRegex(ValueError,'most recent'):self.g.enqueue(dict(cmd_id='0000000000000002',target=A,target_boot=1,report_seq=2,operation='status',ttl_ms=10000))
  with self.assertRaises(ValueError):self.g.enqueue(dict(cmd_id='0000000000000003',target=A,target_boot=1,report_seq=1,operation='period',value=10000,ttl_ms=10000))
 def test_udp_send_failure_is_explicit(self):
  self.g.ingest(pkt(report(A)));self.g.handle(bytes([2])+b'aa'+bytes([2])+bytes.fromhex(EUI),self.addr)
  q=dict(cmd_id='0000000000000001',target=A,target_boot=1,report_seq=1,operation='status',ttl_ms=10000);self.g.enqueue(q)
  class Broken:
   def sendto(self,*args):raise OSError('synthetic UDP failure')
  self.g.sock=Broken();self.g.flush();self.assertEqual(self.g.commands[q['cmd_id']]['state'],'gateway_send_error')
  self.assertEqual(self.g.stats['gateway_send_errors'],1)
 def test_real_udp_and_http_loopback(self):
  server=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);server.bind(('127.0.0.1',0));server.settimeout(1);client=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);client.bind(('127.0.0.1',0));client.settimeout(1);self.g.sock=server
  try:
   wire=bytes([2])+b'ab'+bytes([0])+bytes.fromhex(EUI)+json.dumps({'rxpk':[pkt(report(A))]}).encode();client.sendto(wire,server.getsockname());data,addr=server.recvfrom(65535);self.g.handle(data,addr);self.assertEqual(client.recvfrom(1024)[0],bytes([2])+b'ab'+bytes([1]))
   http=ThreadingHTTPServer(('127.0.0.1',0),Handler);http.gateway=self.g;thread=threading.Thread(target=http.serve_forever);thread.start()
   try:
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}));value=json.load(opener.open(f'http://127.0.0.1:{http.server_port}/api/v1/lora/topology'));self.assertEqual(value['reports'][0]['report']['observer_id'],A)
   finally:http.shutdown();http.server_close();thread.join()
  finally:server.close();client.close()
if __name__=='__main__':unittest.main()
