import json,pathlib,runpy,sys,time,types
root=pathlib.Path(r'D:\Multi-Agent Network\.worktrees\production');sys.path.insert(0,str(root/'app/services'))
import serial,serial.tools.list_ports
trace=pathlib.Path(sys.argv.pop(1));target='90:da:72:48:a5:cc'
ports=[types.SimpleNamespace(device='COM%d'%i,vid=0x1a86,pid=0x7523,location='test-%d'%i) for i in range(1,9)]
ports.append(types.SimpleNamespace(device='COM99',vid=0x1234,pid=0x5678,location='chosen-location'))
serial.tools.list_ports.comports=lambda:ports
class Fake:
 def __init__(self,**kw):self.port=None;self.dtr=None;self.rts=None;self.buf=b'';self.reply=b'';self.in_waiting=0
 def open(self):
  assert self.dtr is False and self.rts is False
  with trace.open('a') as f:f.write('open '+self.port+'\n')
 def write(self,part):
  self.buf+=part
  if b'\n' in self.buf:
   req=json.loads(self.buf);self.buf=b'';assert req['cmd'] in ('info','lora_ref_status')
   with trace.open('a') as f:f.write(req['cmd']+' '+self.port+'\n')
   v={'schema':'mid.serial.v1','event':'command_result','nonce':req['nonce'],'ok':True,'node_id':target}
   v.update({'firmware':'mid-espnow','chip':'esp32s3','lora_ref_api':1} if req['cmd']=='info' else {'lora_ref_requested_role':'rx','lora_ref_worker_state':1,'requested_generation':2,'applied_generation':2})
   self.reply=json.dumps(v).encode()+b'\n'
  return len(part)
 def read(self,n):
  r=self.reply;self.reply=b''
  if not r:time.sleep(.01)
  return r
 def close(self):pass
serial.Serial=Fake
runpy.run_module('tools.mobile_gateway.studio',run_name='__main__')
