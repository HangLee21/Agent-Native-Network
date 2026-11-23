import hashlib,io,sys,tempfile,types,unittest,time,threading
from pathlib import Path
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import ssh_transport as t
class Channel:
 def __init__(self,chunks,code=0):self.chunks=chunks;self.code=code;self.sent=[];self.command=''
 def get_pty(self):pass
 def settimeout(self,x):pass
 def exec_command(self,x):self.command=x
 def recv_ready(self):return bool(self.chunks)
 def recv(self,n):return self.chunks.pop(0)
 def sendall(self,x):self.sent.append(x)
 def exit_status_ready(self):return not self.chunks
 def recv_exit_status(self):return self.code
 def close(self):pass
class T(unittest.TestCase):
 def test_import_vendor(self):self.assertEqual(t.load_ssh_library().__version__,'3.5.1')
 def test_sudo_only_sends_after_nonce_no_echo(self):
  class C(Channel):
   def exec_command(self,x):
    super().exec_command(x);import re
    marker=re.search(r'ANN_SUDO_[0-9a-f]+:',x).group().encode();self.chunks=[b'hello\n'+marker[:12],marker[12:],b'done\n']
  c=C([]);client=types.SimpleNamespace(get_transport=lambda:types.SimpleNamespace(open_session=lambda:c));out=io.StringIO();t.sudo_command(client,['/usr/bin/id'],'SECRET',output=out)
  self.assertEqual(c.sent,[b'SECRET\n']);self.assertNotIn('SECRET',c.command);self.assertNotIn('SECRET',out.getvalue());self.assertTrue(c.command.startswith('stty -echo &&'))
 def test_no_prompt_no_password(self):
  c=Channel([b'done\n']);client=types.SimpleNamespace(get_transport=lambda:types.SimpleNamespace(open_session=lambda:c));t.sudo_command(client,['/usr/bin/id'],'SECRET',output=io.StringIO());self.assertEqual(c.sent,[])
 def test_repeated_prompt_fails(self):
  class C(Channel):
   def exec_command(self,x):
    import re
    marker=re.search(r'ANN_SUDO_[0-9a-f]+:',x).group().encode();self.chunks=[marker,marker,marker]
  c=C([]);client=types.SimpleNamespace(get_transport=lambda:types.SimpleNamespace(open_session=lambda:c))
  with self.assertRaises(t.TransportError):t.sudo_command(client,['/usr/bin/id'],'SECRET',output=io.StringIO(),secret=lambda _: 'SECOND')
  self.assertEqual(c.sent,[b'SECRET\n',b'SECOND\n'])
 def test_unknown_key_requires_confirmation_and_changed_key_rejected(self):
  class Policy:pass
  class Keys:
   def __init__(self,known):self.known=known;self.added=[]
   def lookup(self,name):return {'other':object()} if self.known else None
   def add(self,*args):self.added.append(args)
  class Client:
   def __init__(self):self.keys=Keys(Client.known);self.policy=None;self.saved=False
   def load_host_keys(self,p):pass
   def set_missing_host_key_policy(self,x):self.policy=x
   def get_host_keys(self):return self.keys
   def save_host_keys(self,p):self.saved=True
   def connect(self,**kw):self.policy.missing_host_key(self,kw['hostname'],types.SimpleNamespace(asbytes=lambda:b'key',get_name=lambda:'ssh-ed25519'))
   def close(self):pass
  lib=types.SimpleNamespace(SSHClient=Client,MissingHostKeyPolicy=Policy)
  with tempfile.TemporaryDirectory() as d:
   Client.known=False
   with self.assertRaises(t.TransportError):t.connect('test','user',ask=lambda x:'N',secret=lambda x:'secret',known_hosts=Path(d)/'hosts',lib=lib)
   c,pw=t.connect('test','user',ask=lambda x:'YES',secret=lambda x:'secret',known_hosts=Path(d)/'hosts',lib=lib);self.assertTrue(c.saved)
   Client.known=True
   with self.assertRaises(t.TransportError):t.connect('test','user',ask=lambda x:self.fail('must not ask'),secret=lambda x:'secret',known_hosts=Path(d)/'hosts',lib=lib)
 def test_stream_upload_and_corruption(self):
  data={}
  class File(io.BytesIO):
   def __init__(self,key,mode,corrupt):self.key=key;self.mode=mode;self.corrupt=corrupt;super().__init__(data.get(key,b'') if mode=='rb' else b'')
   def close(self):
    if self.mode=='wb':data[self.key]=self.getvalue()+(b'x' if self.corrupt else b'')
    super().close()
  class SFTP:
   def __init__(self,corrupt):self.corrupt=corrupt
   def open(self,k,m):return File(k,m,self.corrupt)
   def close(self):pass
   def get_channel(self):return types.SimpleNamespace(settimeout=lambda x:None)
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'pkg';path.write_bytes(b'a'*1100000);digest=hashlib.sha256(path.read_bytes()).hexdigest()
   t.upload_verified(types.SimpleNamespace(open_sftp=lambda:SFTP(False),get_transport=lambda:None,close=lambda:None),path,'/tmp/p',digest);self.assertEqual(len(data['/tmp/p']),1100000)
   with self.assertRaises(t.TransportError):t.upload_verified(types.SimpleNamespace(open_sftp=lambda:SFTP(True),get_transport=lambda:None,close=lambda:None),path,'/tmp/p',digest)
 def test_sftp_silent_handshake_times_out_and_closes(self):
  released=threading.Event();closed=threading.Event()
  class Sock:
   def close(self):released.set()
  class Client:
   def open_sftp(self):released.wait(2);raise EOFError('closed')
   def get_transport(self):return types.SimpleNamespace(sock=Sock())
   def close(self):closed.set()
  start=time.monotonic()
  with self.assertRaisesRegex(t.TransportError,'超时'):t.open_sftp_bounded(Client(),timeout=.1)
  self.assertLess(time.monotonic()-start,1);self.assertTrue(closed.wait(.5))
 def test_hostkey_fingerprint(self):
  key=types.SimpleNamespace(asbytes=lambda:b'known');self.assertTrue(t.fingerprint(key).startswith('SHA256:'))
if __name__=='__main__':unittest.main(verbosity=2)
