import io,os,subprocess,sys,tempfile,threading,time,types,unittest
from pathlib import Path
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import private_deploy as d,ssh_transport as s,setup_gateway as g
BASE='ARCH armv7l\nDPKG_ARCH armhf\nOS "Raspbian GNU/Linux 8 (jessie)"\nSYSTEMD_VERSION systemd 215\nSUDO_PATH /usr/bin/sudo\nPKG libc6 2.19-18+deb8u7 install ok installed\nLOADER_OK\nSPACE_OPT 200000\n'
class Tests(unittest.TestCase):
 def test_stage_choice_and_diagnostics(self):
  small=20*1024*1024
  self.assertEqual(d.validate_target(BASE+'SPACE_TMP 24000\nSPACE_VARTMP 30000\n',128*1024*1024,small)[1],'/tmp')
  self.assertEqual(d.validate_target(BASE+'SPACE_TMP 4000\nSPACE_VARTMP 30000\n',128*1024*1024,small)[1],'/var/tmp')
  with self.assertRaisesRegex(d.DeployError,'空间不足.*需要 20.0 MiB'):d.validate_target(BASE+'SPACE_TMP 4000\nSPACE_VARTMP 5000\n',128*1024*1024,small)
  with self.assertRaisesRegex(d.DeployError,'无法读取可写'):d.validate_target(BASE+'SPACE_TMP INVALID\nSPACE_VARTMP UNWRITABLE\n',128*1024*1024,small)
  with self.assertRaisesRegex(d.DeployError,'无法读取网关 /opt'):d.validate_target(BASE.replace('SPACE_OPT 200000','SPACE_OPT INVALID')+'SPACE_TMP 30000\nSPACE_VARTMP 40000\n',128*1024*1024,small)
 def test_normal_close_order_and_forced_timeout(self):
  calls=[]
  class Sock:
   def close(self):calls.append('socket')
  class Client:
   def get_transport(self):return types.SimpleNamespace(sock=Sock())
   def close(self):calls.append('client')
  s.close_bounded(Client());self.assertEqual(calls,['client']);calls.clear();s.close_bounded(Client(),force=True);self.assertEqual(calls,['socket','client'])
 def test_real_df_shell_and_log_allowlist(self):
  bash=r'C:\environment\Git\bin\bash.exe'
  proc=subprocess.run([bash,'-s'],input=d.EXTRA_PREFLIGHT,text=True,encoding='utf-8',capture_output=True,timeout=10)
  self.assertEqual(proc.returncode,0,proc.stderr)
  for key in ('SPACE_OPT ','SPACE_TMP ','SPACE_VARTMP '):
   rows=[x for x in proc.stdout.splitlines() if x.startswith(key)];self.assertEqual(len(rows),1,proc.stdout)
   value=rows[0].split(' ',1)[1];self.assertTrue(value.isdigit() or value in ('INVALID','UNWRITABLE'),rows[0])
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'log';g.LOG_FILE=str(p);g.log_preflight(proc.stdout+'\nSPACE_OPT_REQUIRED 134217728\nSPACE_TMP_REQUIRED 17100000');content=p.read_text();g.LOG_FILE=None
   self.assertIn('SPACE_TMP ',content);self.assertIn('SPACE_VARTMP ',content);self.assertIn('SPACE_TMP_REQUIRED 17100000',content)
if __name__=='__main__':unittest.main(verbosity=2)
