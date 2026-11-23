"""Real gateway subprocess restart with synthetic UDP and journal corruption."""
import json,socket,subprocess,sys,tempfile,time,unittest,urllib.request
from pathlib import Path
from .check_gateway import EUI,A,TX,pkt,report,receipt

class ProcessRecovery(unittest.TestCase):
 def test_uncertain_command_survives_process_kill_and_late_receipt(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);cfg=root/'tx.json';cfg.write_text(json.dumps(TX));journal=root/'commands.json';eui=bytes.fromhex(EUI)
   cmd=[sys.executable,'-u','-X','utf8','-m','tools.flight_link.gateway','--udp-host','127.0.0.1','--udp-port','0','--http-port','0','--gateway-ip','127.0.0.1','--gateway-eui',EUI,'--tx-config',str(cfg),'--state-file',str(journal)]
   proc=None
   with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as forwarder:
    forwarder.bind(('127.0.0.1',0));forwarder.settimeout(3)
    try:
     proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');ready=json.loads(proc.stdout.readline());addr=tuple(ready['udp']);base=f"http://127.0.0.1:{ready['http_port']}";opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
     def push(token,payload):
      forwarder.sendto(bytes([2])+token+bytes([0])+eui+json.dumps({'rxpk':[pkt(payload)]}).encode(),addr);self.assertEqual(forwarder.recvfrom(1024)[0][3],1)
     def pull():
      forwarder.sendto(bytes([2])+b'bb'+bytes([2])+eui,addr);self.assertEqual(forwarder.recvfrom(1024)[0][3],4)
     push(b'aa',report(A));pull();q=dict(cmd_id='0000000000000001',target=A,target_boot=1,report_seq=1,operation='status',ttl_ms=30000)
     req=urllib.request.Request(base+'/api/v1/commands',json.dumps(q).encode(),headers={'Content-Type':'application/json','Origin':base});self.assertEqual(json.load(opener.open(req))['state'],'queued');self.assertEqual(forwarder.recvfrom(2048)[0][3],3)
     proc.kill();proc.communicate(timeout=5);journal.write_text('{corrupt',encoding='utf-8')
     proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');ready=json.loads(proc.stdout.readline());addr=tuple(ready['udp']);base=f"http://127.0.0.1:{ready['http_port']}"
     def status():return json.load(opener.open(base+'/api/v1/lora/topology'))['commands'][0]
     self.assertEqual(status()['state'],'execution_unknown_restart');pull();forwarder.settimeout(1.3)
     with self.assertRaises(socket.timeout):forwarder.recvfrom(2048)
     forwarder.settimeout(3);push(b'cc',receipt());self.assertEqual(status()['state'],'executed')
    finally:
     if proc and proc.poll() is None:proc.kill();proc.communicate(timeout=5)

if __name__=='__main__':unittest.main()
