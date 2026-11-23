import contextlib,io,sys,tempfile,types,unittest
from pathlib import Path
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import ssh_transport as t
class Auth(Exception):pass
class BadAuth(Auth):pass
class HostError(Exception):pass
class Policy:pass
class FakeClient:
 outcomes=[];created=[]
 def __init__(self):self.closed=False;self.password=None;FakeClient.created.append(self)
 def load_host_keys(self,p):self.loaded=True
 def set_missing_host_key_policy(self,p):self.policy=p
 def connect(self,**kwargs):
  self.password=kwargs['password'];out=FakeClient.outcomes.pop(0)
  if out:raise out
 def close(self):self.closed=True
 def get_transport(self):return None
class Tests(unittest.TestCase):
 def setUp(self):
  FakeClient.created=[];FakeClient.outcomes=[];self.lib=types.SimpleNamespace(SSHClient=FakeClient,MissingHostKeyPolicy=Policy,AuthenticationException=Auth,BadAuthenticationType=BadAuth);self.tmp=tempfile.TemporaryDirectory();self.hosts=Path(self.tmp.name)/'known_hosts';self.hosts.write_text('existing')
 def tearDown(self):self.tmp.cleanup()
 def run_connect(self,values):
  values=iter(values);out=io.StringIO()
  with contextlib.redirect_stdout(out):
   result=t.connect('192.168.137.200','rxhf',secret=lambda _:next(values),known_hosts=self.hosts,lib=self.lib)
  return result,out.getvalue()
 def test_wrong_then_correct_uses_new_client_and_input(self):
  FakeClient.outcomes=[Auth('rejected'),None];(client,password),out=self.run_connect(['bad_secret','good_secret'])
  self.assertEqual(password,'good_secret');self.assertIs(client,FakeClient.created[1]);self.assertTrue(FakeClient.created[0].closed);self.assertTrue(all(x.loaded for x in FakeClient.created));self.assertIn('192.168.137.200',out);self.assertIn('rxhf',out);self.assertIn('拒绝',out);self.assertNotIn('secret',out)
 def test_three_rejections_stop(self):
  FakeClient.outcomes=[Auth(),Auth(),Auth()];values=iter(['a','b','c'])
  with self.assertRaisesRegex(t.TransportError,'认证未通过'):t.connect('host','rxhf',secret=lambda _:next(values),known_hosts=self.hosts,lib=self.lib)
  self.assertEqual(len(FakeClient.created),3);self.assertTrue(all(c.closed for c in FakeClient.created));self.assertEqual([c.password for c in FakeClient.created],['a','b','c'])
 def test_cancel_and_host_or_network_errors_do_not_retry(self):
  with self.assertRaisesRegex(t.TransportError,'取消'):t.connect('host','rxhf',secret=lambda _:'',known_hosts=self.hosts,lib=self.lib)
  self.assertEqual(len(FakeClient.created),0)
  def interrupted(_):raise KeyboardInterrupt()
  with self.assertRaisesRegex(t.TransportError,'取消'):t.connect('host','rxhf',secret=interrupted,known_hosts=self.hosts,lib=self.lib)
  for err in (HostError('hostkey'),OSError('network')):
   FakeClient.created=[];FakeClient.outcomes=[err]
   with self.assertRaises(type(err)):t.connect('host','rxhf',secret=lambda _:'a',known_hosts=self.hosts,lib=self.lib)
   self.assertEqual(len(FakeClient.created),1);self.assertTrue(FakeClient.created[0].closed)
  FakeClient.created=[];FakeClient.outcomes=[KeyboardInterrupt()]
  with self.assertRaisesRegex(t.TransportError,'取消'):t.connect('host','rxhf',secret=lambda _:'a',known_hosts=self.hosts,lib=self.lib)
  self.assertEqual(len(FakeClient.created),1);self.assertTrue(FakeClient.created[0].closed)
 def test_unsupported_auth_type_does_not_retry(self):
  FakeClient.outcomes=[BadAuth('no password')]
  with self.assertRaisesRegex(t.TransportError,'不支持当前密码认证'):t.connect('host','rxhf',secret=lambda _:'a',known_hosts=self.hosts,lib=self.lib)
  self.assertEqual(len(FakeClient.created),1);self.assertTrue(FakeClient.created[0].closed)
if __name__=='__main__':unittest.main(verbosity=2)
