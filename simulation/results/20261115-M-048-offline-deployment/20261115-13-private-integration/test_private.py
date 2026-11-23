import io,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import private_deploy as d,setup_gateway as g,linux_installer as ins
GOOD='CONNECTION 192.168.137.250 1 192.168.137.200 22\nARCH armv7l\nDPKG_ARCH armhf\nOS "Raspbian GNU/Linux 8 (jessie)"\nSYSTEMD_VERSION systemd 215\nSUDO_PATH /usr/bin/sudo\nPKG libc6 2.19-18+deb8u7 install ok installed\nLOADER_OK\nSPACE_OPT 200000\nSPACE_TMP 200000\nMISSING python3\nMISSING dnsmasq\nADDRESS eth0 192.168.137.200/24\n'
class DummySFTP:
 def __init__(self,calls):self.calls=calls
 def mkdir(self,*a):self.calls.append(('mkdir',a))
 def close(self):pass
 def get_channel(self):return types.SimpleNamespace(settimeout=lambda x:None)
 def remove(self,*a):self.calls.append(('remove',a))
 def rmdir(self,*a):self.calls.append(('rmdir',a))
class Client:
 def __init__(self,calls):self.calls=calls
 def open_sftp(self):return DummySFTP(self.calls)
 def close(self):self.calls.append(('close',))
 def get_transport(self):return types.SimpleNamespace(is_active=lambda:True,sock=None)
class Tests(unittest.TestCase):
 def test_lease_user_group_and_directory(self):
  c=ins.configuration('eth0','192.168.137.200','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
  for line in ('user=nobody','group=nogroup','dhcp-leasefile=/var/lib/ann-gateway/state/dnsmasq.leases'):self.assertIn(line+'\n',c['dnsmasq'])
  fakepwd=types.SimpleNamespace(getpwnam=lambda x:types.SimpleNamespace(pw_uid=1));fakegrp=types.SimpleNamespace(getgrnam=lambda x:(_ for _ in ()).throw(KeyError(x)))
  with patch.object(ins.os,'geteuid',return_value=0,create=True),patch.object(ins,'verify_package',return_value={'minimum_python':[3,4]}),patch.object(ins.shutil,'which',return_value='fake'),patch.dict(sys.modules,{'pwd':fakepwd,'grp':fakegrp}),patch.object(ins,'capture',side_effect=AssertionError('must not modify')):
   with self.assertRaisesRegex(ins.SetupError,'nogroup'):ins.install('unused',c)
 def test_real_runtime_manifest_and_safe_archive(self):
  m,p,h=d.load_runtime();self.assertEqual(p.stat().st_size,m['archive_size']);self.assertEqual(h,m['archive_sha256'])
 def test_preflight_target_validation(self):
  d.validate_target(GOOD,134217728)
  for text in (GOOD.replace('armhf','armel'),GOOD.replace('LOADER_OK','LOADER_MISSING'),GOOD.replace('SPACE_OPT 200000','SPACE_OPT 1'),GOOD.replace('systemd 215','systemd 252')):
   with self.assertRaises(d.DeployError):d.validate_target(text,134217728)
 def test_install_is_single_connection_and_validates_before_sudo(self):
  calls=[];client=Client(calls);m={'minimum_free_bytes':134217728}
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'runtime.tar.gz';path.write_bytes(b'runtime')
   api=types.SimpleNamespace(prepare=lambda p:(p/'service').write_bytes(b'x'),package_bytes=lambda p:b'pkg',PREFLIGHT='preflight',log_preflight=lambda t:None,choose_remote_interface=lambda t,h:'eth0')
   with patch.object(d,'load_runtime',return_value=(m,path,'a'*64)),patch.object(d.ssh,'connect',side_effect=lambda *a:(calls.append(('connect',)) or (client,'secret'))),patch.object(d.ssh,'readonly_command',side_effect=lambda *a:(calls.append(('preflight',)) or GOOD)),patch.object(d.ssh,'upload_verified',side_effect=lambda *a:calls.append(('upload',))),patch.object(d.ssh,'sudo_command',side_effect=lambda *a,**k:calls.append(('sudo',a[1]))):
    d.deploy('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',api)
   self.assertEqual([x[0] for x in calls].count('connect'),1);order=[x[0] for x in calls];self.assertLess(order.index('preflight'),order.index('upload'));self.assertLess(order.index('upload'),order.index('sudo'))
   command=[x[1] for x in calls if x[0]=='sudo'][0];self.assertEqual(command[0:2],['/bin/sh','-c']);self.assertIn('dnsmasq" --test',command[2]);self.assertIn('--python-wrapper',command[2]);self.assertNotIn('secret',str(command))
 def test_sftp_timeout_propagates_and_closes_without_sudo(self):
  calls=[];client=Client(calls);m={'minimum_free_bytes':134217728}
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'r';path.write_bytes(b'r');api=types.SimpleNamespace(prepare=lambda p:None,package_bytes=lambda p:b'p',PREFLIGHT='x',log_preflight=lambda t:None,choose_remote_interface=lambda t,h:'eth0')
   with patch.object(d,'load_runtime',return_value=(m,path,'a'*64)),patch.object(d.ssh,'connect',return_value=(client,'secret')),patch.object(d.ssh,'readonly_command',return_value=GOOD),patch.object(d.ssh,'open_sftp_bounded',side_effect=d.ssh.TransportError('网关文件传输超时，连接已关闭')),patch.object(d.ssh,'sudo_command',side_effect=lambda *a,**k:calls.append(('sudo',))):
    with self.assertRaises(d.ssh.TransportError):d.deploy('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',api)
   self.assertTrue(any(x[0]=='close' for x in calls));self.assertFalse(any(x[0]=='sudo' for x in calls))
 def test_failed_preflight_never_uploads(self):
  calls=[];client=Client(calls);m={'minimum_free_bytes':134217728}
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'r';path.write_bytes(b'r');api=types.SimpleNamespace(prepare=lambda p:None,package_bytes=lambda p:b'p',PREFLIGHT='x',log_preflight=lambda t:None)
   with patch.object(d,'load_runtime',return_value=(m,path,'a'*64)),patch.object(d.ssh,'connect',return_value=(client,'secret')),patch.object(d.ssh,'readonly_command',return_value=GOOD.replace('LOADER_OK','LOADER_MISSING')),patch.object(d.ssh,'upload_verified',side_effect=lambda *a:calls.append(('upload',))),patch.object(d.ssh,'sudo_command',side_effect=lambda *a,**k:calls.append(('sudo',))):
    with self.assertRaises(d.DeployError):d.deploy('rxhf','192.168.137.200','install',None,'b827ebfffe32e2c1',api)
   self.assertFalse(any(x[0] in ('upload','sudo','mkdir') for x in calls))
if __name__=='__main__':unittest.main(verbosity=2)
