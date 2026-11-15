import base64,io,json,re,sys,tarfile,tempfile,types,unittest,subprocess,os
from pathlib import Path
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import setup_gateway as g
OK='CONNECTION 192.168.137.250 123 192.168.137.200 22\nARCH armv7l\nDPKG_ARCH armhf\nOS "Raspbian GNU/Linux 8"\nPY_PATH /usr/bin/python3\nPY_VERSION 3.4.2\nPY_OK\nSUDO_PATH /usr/bin/sudo\nADDRESS eth0 192.168.137.200/24\n'
class Tests(unittest.TestCase):
 def test_single_session_and_preflight_before_write(self):
  calls=[]
  class Proc:
   def __init__(self,args,**kwargs):calls.append(args);self.stdout=io.StringIO("ARCH armv7l\nMISSING python3\n");self.kwargs=kwargs
   def wait(self):return 20
  with self.assertRaises(Exception):g.remote_exec('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',Proc)
  self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'ssh');self.assertIn('-tt',calls[0]);command=calls[0][-1]
  self.assertLess(command.index('missing=$('),command.index('mkdir -m 700'));self.assertLess(command.index('grep -qx PY_OK'),command.index('mkdir -m 700'));self.assertIn('ConnectTimeout=5',calls[0])
  match=re.search(r"printf '%s' '([A-Za-z0-9+/=]+)'",command);self.assertIsNotNone(match)
  with tarfile.open(fileobj=io.BytesIO(base64.b64decode(match.group(1))),mode='r:gz') as tar:
   self.assertTrue(all(x.mtime==0 for x in tar.getmembers()));self.assertIn('linux_installer.py',tar.getnames())
 def test_stream_password_not_logged(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'log.jsonl';g.LOG_FILE=str(p)
   class Proc:
    def __init__(self,*a,**kw):self.stdout=io.StringIO('ARCH armv7l\nPassword: SECRET\n')
    def wait(self):return 0
   g.stream_session(['ssh'],Proc);self.assertNotIn('SECRET',p.read_text());self.assertIn('ARCH armv7l',p.read_text());g.LOG_FILE=None
 def test_real_local_shell_gate(self):
  bash=r'C:\environment\Git\bin\bash.exe'
  captured=[]
  class Proc:
   def __init__(self,args,**kwargs):captured.append(args[-1]);self.stdout=io.StringIO('')
   def wait(self):return 0
  original=g.PREFLIGHT
  try:
   g.PREFLIGHT="printf 'MISSING python3\\n'"
   g.remote_exec('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',Proc)
   script="mkdir() { printf 'MOCK_WRITE_REACHED\\n'; return 1; }\n"+captured.pop()
   result=subprocess.run([bash,'-s'],input=script,capture_output=True,text=True,encoding='utf-8');self.assertEqual(result.returncode,20);self.assertNotIn('MOCK_WRITE_REACHED',result.stdout)
   g.PREFLIGHT="printf 'PY_PATH /usr/bin/python3\\nPY_OK\\nSUDO_PATH /usr/bin/sudo\\nADDRESS eth0 192.168.137.200/24\\n'"
   g.remote_exec('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',Proc)
   script="mkdir() { printf 'MOCK_WRITE_REACHED\\n'; return 1; }\n"+captured.pop();env=os.environ.copy();env['SSH_CONNECTION']='192.168.137.250 123 192.168.137.200 22'
   result=subprocess.run([bash,'-s'],input=script,capture_output=True,text=True,encoding='utf-8',env=env);self.assertEqual(result.returncode,1,msg=result.stderr+result.stdout);self.assertIn('MOCK_WRITE_REACHED',result.stdout)
  finally:g.PREFLIGHT=original
 def test_incompatible_and_missing_deps(self):
  for extra in ('MISSING dnsmasq','MISSING python3_compatible','MISSING systemctl'):
   with self.assertRaises(g.SetupError):g.parse_preflight(OK+extra+'\n')
  self.assertEqual(g.parse_preflight(OK+'MISSING dnsmasq\n','rollback'),('/usr/bin/python3','/usr/bin/sudo'))
 def test_fact_allowlist_no_secrets(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'log.jsonl';g.LOG_FILE=str(p);g.log_preflight(OK+'SSH_PASSWORD SECRET\nPKG python3 3.4.2 install ok installed\n')
   record=json.loads(p.read_text());self.assertNotIn('SECRET',p.read_text());self.assertIn('DPKG_ARCH armhf',record['facts']);self.assertIn('PKG python3 3.4.2 install ok installed',record['facts']);g.LOG_FILE=None
if __name__=='__main__':unittest.main(verbosity=2)
