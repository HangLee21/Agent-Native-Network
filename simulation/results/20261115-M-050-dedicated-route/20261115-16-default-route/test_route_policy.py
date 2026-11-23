import ast,io,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack,redirect_stdout
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import linux_installer as m
class GateReached(Exception):pass
class Tests(unittest.TestCase):
 def config(self):return m.configuration('eth0','192.168.137.200','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
 def test_without_confirmation_stops_before_any_work(self):
  with patch.object(m,'verify_package',side_effect=AssertionError('must stop first')):
   with self.assertRaisesRegex(m.SetupError,'专用网口'):m.install('package',self.config())
  with patch.object(sys,'argv',['installer','install','--package','fake']),patch.object(m,'install',side_effect=AssertionError('must not install')):self.assertEqual(m.main(),1)
 def exercise_route(self,route):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);iface=root/'net'/'eth0';iface.mkdir(parents=True);(iface/'type').write_text('1');system=root/'system';system.mkdir();calls=[]
   def call(*a,**kw):
    calls.append(a);return types.SimpleNamespace(stdout=route if a[:4]==('ip','route','show','default') else 'inactive',stderr='',returncode=0)
   pwd=types.SimpleNamespace(getpwnam=lambda _:types.SimpleNamespace(pw_uid=123));grp=types.SimpleNamespace(getgrnam=lambda _:types.SimpleNamespace(gr_gid=456))
   patches=[patch.object(m,'SYS_NET',str(root/'net')),patch.object(m,'SYSTEMD_DIR',str(system)),patch.object(m,'STATE',str(root/'state')),patch.object(m,'RELEASE',str(root/'release')),patch.object(m.os,'geteuid',return_value=0,create=True),patch.object(m,'verify_package',return_value={'minimum_python':[3,4]}),patch.object(m.shutil,'which',return_value='fake'),patch.object(m,'call',side_effect=call),patch.object(m,'check_ports',side_effect=GateReached),patch.dict(sys.modules,{'pwd':pwd,'grp':grp})]
   out=io.StringIO()
   with ExitStack() as stack,redirect_stdout(out):
    for x in patches:stack.enter_context(x)
    with self.assertRaises(GateReached):m.install('package',self.config(),dedicated=True)
   route_calls=[x for x in calls if x[:2]==('ip','route')];self.assertEqual(route_calls,[('ip','route','show','default','dev','eth0')]);return out.getvalue()
 def test_confirmed_preserves_existing_route(self):
  out=self.exercise_route('default via 192.168.137.1 dev eth0\n');self.assertIn('保留原配置',out)
 def test_confirmed_without_route_and_dhcp_scope(self):
  self.exercise_route('');c=self.config();self.assertIn('interface=eth0\n',c['dnsmasq']);self.assertIn('bind-interfaces\n',c['dnsmasq']);self.assertIn('dhcp-option=3\n',c['dnsmasq']);self.assertIn('dhcp-option=6\n',c['dnsmasq']);ast.parse(Path(m.__file__).read_text(encoding='utf-8'),feature_version=(3,4))
if __name__=='__main__':unittest.main(verbosity=2)
