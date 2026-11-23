import contextlib,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import yaml
sys.path.insert(0,r'D:\Multi-Agent Network\tools\mid_baseline\gateway_probe')
import mkcard as m
class Checks(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.boot=Path(self.tmp.name)/'boot';self.boot.mkdir();self.env=Path(self.tmp.name)/'dummy.env';self.env.write_text('WIFI_SSID=fixture\nWIFI_IDENTITY=test-user\nWIFI_PASSWORD=example-only\nTAILSCALE_AUTHKEY=example-only\n')
  (self.boot/'cmdline.txt').write_text('console=serial0,115200 root=PARTUUID=fake ds=nocloud;i=old-imager-id systemd.run=/old\n')
  (self.boot/'meta-data').write_text('instance-id: old-meta-id\nlocal-hostname: old-name\n')
  (self.boot/'user-data').write_text('#cloud-config\nhostname: old-name\nusers:\n  - name: eora\n    ssh_authorized_keys: [example-key]\nruncmd:\n  - [echo, existing]\n')
  (self.boot/'network-config').write_text('network:\n  version: 2\n  wifis:\n    wlan0:\n      access-points:\n        other-network: {password: example}\n')
 def tearDown(self):self.tmp.cleanup()
 def run_card(self,n):
  with patch.object(m,'ENV_FILE',self.env),patch.object(sys,'argv',['mkcard','--card',str(self.boot),'--number',str(n)]),contextlib.redirect_stdout(io.StringIO()):return m.main()
 def test_reuse_04_05_06_and_repeat(self):
  for n in (4,5,6,6):
   self.assertEqual(self.run_card(n),0);line=(self.boot/'cmdline.txt').read_text();self.assertEqual(len(line.splitlines()),1);meta=yaml.safe_load((self.boot/'meta-data').read_text());user=yaml.safe_load((self.boot/'user-data').read_text());self.assertIn('i='+meta['instance-id'],line);self.assertEqual(meta['local-hostname'],'eora-air-%02d'%n);self.assertEqual(user['hostname'],meta['local-hostname']);self.assertEqual(user['users'][0]['ssh_authorized_keys'],['example-key']);self.assertEqual(user['runcmd'].count(['bash','/boot/firmware/eora-firstboot.sh']),1);self.assertIn(['echo','existing'],user['runcmd']);self.assertIn('other-network',yaml.safe_load((self.boot/'network-config').read_text())['network']['wifis']['wlan0']['access-points']);self.assertNotIn('systemd.run=',line)
  script=(self.boot/m.INSTALLER_NAME).read_text();self.assertIn('systemctl start --no-block',script);self.assertNotIn('pip install --user',m.LOGIC);self.assertIn('runuser -u eora',m.LOGIC);self.assertIn('set -euo pipefail',m.LOGIC)
 def test_imager_top_level_network_and_missing_yaml(self):
  path=self.boot/'network-config';path.write_text('version: 2\nwifis:\n  wlan0:\n    access-points:\n      other-network: {password: example}\n')
  self.assertEqual(self.run_card(4),0);net=yaml.safe_load(path.read_text());self.assertNotIn('network',net);self.assertIn('other-network',net['wifis']['wlan0']['access-points']);self.assertIn('fixture',net['wifis']['wlan0']['access-points'])
  before={p.name:p.read_bytes() for p in self.boot.iterdir() if p.is_file()}
  with patch.object(m,'yaml',None):self.assertEqual(self.run_card(5),2)
  self.assertEqual(before,{p.name:p.read_bytes() for p in self.boot.iterdir() if p.is_file()})
 def test_invalid_cmdline_no_change(self):
  for line in ('root=PARTUUID=fake ds=nocloud-extra\n','root=PARTUUID=fake ds=nocloud ds=nocloud-net\n','root=PARTUUID=fake\n'):
   (self.boot/'cmdline.txt').write_text(line);before={p.name:p.read_bytes() for p in self.boot.iterdir()}
   with self.assertRaisesRegex(SystemExit,'不支持的镜像'):self.run_card(4)
   self.assertEqual(before,{p.name:p.read_bytes() for p in self.boot.iterdir()})
 def test_nocloud_variants(self):
  for token in ('ds=nocloud','ds=nocloud-net','ds=nocloud;s=/boot/firmware/','ds=nocloud-net;seedfrom=https://example.test/;instance-id=old','ds=nocloud;i=old;instance-id=old2;s=/media/'):
   (self.boot/'cmdline.txt').write_text('console=tty1 '+token+' root=PARTUUID=fake\n')
   self.assertEqual(self.run_card(5),0)
   line=(self.boot/'cmdline.txt').read_text(); instance=yaml.safe_load((self.boot/'meta-data').read_text())['instance-id']
   self.assertIn('i='+instance,line);self.assertNotIn('instance-id=',line);self.assertEqual(line.count(';i='),1)
   self.assertIn('console=tty1',line);self.assertIn('root=PARTUUID=fake',line)
   if 'seedfrom=' in token:self.assertIn('seedfrom=https://example.test/',line)
   if 's=/media/' in token:self.assertIn('s=/media/',line)
 def test_network_failure_reporting(self):
  self.assertIn('wifi_error=$(nmcli connection up',m.LOGIC)
  self.assertIn('wifi_error=${wifi_error//"$EORA_WIFI_PASS"/[redacted]}',m.LOGIC)
  self.assertIn('FAILED: wlan0 has no IPv4 address',m.LOGIC)
  self.assertLess(m.LOGIC.index('FAILED: wlan0 has no IPv4 address'),m.LOGIC.index('4/6 network up: $wlan_ip'))
 def test_write_failure_restores_originals(self):
  before={p.name:p.read_bytes() for p in self.boot.iterdir()};real=m.os.replace;calls=[0]
  def fail_once(a,b):
   calls[0]+=1
   if calls[0]==2:raise OSError('injected failure')
   return real(a,b)
  with patch.object(m.os,'replace',side_effect=fail_once):
   with self.assertRaises(OSError):self.run_card(4)
  for name,data in before.items():self.assertEqual((self.boot/name).read_bytes(),data)
  self.assertFalse((self.boot/m.INSTALLER_NAME).exists());self.assertTrue(any(p.name.startswith('eora-backup-') for p in self.boot.iterdir()))
 def test_bad_yaml_no_change(self):
  (self.boot/'user-data').write_text('#cloud-config\nusers: [broken\n');before={p.name:p.read_bytes() for p in self.boot.iterdir()}
  with self.assertRaises(SystemExit):self.run_card(4)
  self.assertEqual(before,{p.name:p.read_bytes() for p in self.boot.iterdir()})
if __name__=='__main__':unittest.main(verbosity=2)
