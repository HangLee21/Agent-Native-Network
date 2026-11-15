import ast,os,socket,subprocess,sys,unittest
from unittest.mock import patch
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\services')
from tools.flight_link import appliance
class Fake:
 def __init__(self,kind,addr,device=b'eth0\0',listen=1,domain=socket.AF_INET):self.kind=kind;self.addr=addr;self.device=device;self.listen=listen;self.domain=domain;self.closed=False
 def getsockopt(self,level,opt,*args):
  if opt==socket.SO_TYPE:return self.kind
  if opt==39:return self.domain
  if opt==25:return self.device
  if opt==30:return self.listen
  raise AssertionError(opt)
 def getsockname(self):return self.addr
 def close(self):self.closed=True
class Checks(unittest.TestCase):
 def run_case(self,items,pid=None,count='2',interface='eth0'):
  env={'LISTEN_PID':str(os.getpid() if pid is None else pid),'LISTEN_FDS':count}
  with patch.object(appliance.sys,'platform','linux'),patch.dict(os.environ,env,clear=True),patch.object(appliance.socket,'SO_DOMAIN',39,create=True),patch.object(appliance.socket,'SO_BINDTODEVICE',25,create=True),patch.object(appliance.socket,'SO_ACCEPTCONN',30,create=True),patch.object(appliance.socket,'socket',side_effect=lambda **kw:items[kw['fileno']]):
   return appliance.activated_sockets(interface,'0.0.0.0',8780,'0.0.0.0',8781)
 def pair(self):return {3:Fake(socket.SOCK_DGRAM,('0.0.0.0',8781)),4:Fake(socket.SOCK_STREAM,('0.0.0.0',8780))}
 def test_reversed_fd_types(self):
  v=self.pair();http,udp=self.run_case(v);self.assertIs(http,v[4]);self.assertIs(udp,v[3])
 def test_invalid_environment(self):
  for opts in ({'pid':os.getpid()+1},{'count':'1'},{'count':'x'},{'interface':None}):
   with self.assertRaises(ValueError):self.run_case(self.pair(),**opts)
 def test_wrong_socket_properties(self):
  for change in ('interface','port','kind','family','listener'):
   v=self.pair()
   if change=='interface':v[3].device=b'wlan0\0'
   if change=='port':v[3].addr=('0.0.0.0',9999)
   if change=='kind':v[3].kind=socket.SOCK_STREAM
   if change=='family':v[3].domain=socket.AF_INET6
   if change=='listener':v[4].listen=0
   with self.assertRaises(ValueError):self.run_case(v)
   self.assertTrue(v[3].closed)
 def test_no_activation_environment_fails(self):
  cmd=[sys.executable,'-I','-c','import sys,runpy;sys.path.insert(0,sys.argv.pop(1));runpy.run_module("tools.flight_link.appliance",run_name="__main__")',r'D:\Multi-Agent Network\.worktrees\production\app\services','--gateway-eui','b827ebfffe32e2c1','--interface','eth0','--systemd-sockets']
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=5);self.assertNotEqual(p.returncode,0);self.assertNotIn('ready',p.stdout)
 def test_python34_syntax(self):
  from pathlib import Path
  ast.parse(Path(appliance.__file__).read_text(encoding='utf-8'),feature_version=(3,4))
if __name__=='__main__':unittest.main(verbosity=2)
