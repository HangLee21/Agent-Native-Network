import hashlib,importlib.util,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path('D:/Multi-Agent Network/.worktrees/production');sys.path.insert(0,str(BASE/'app/gateway_setup'))
import linux_installer as mod
import setup_gateway as win

class Offline(unittest.TestCase):
 def test_plan_scopes_dhcp_without_router_dns(self):
  c=mod.configuration('eth0','192.168.137.200','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
  self.assertIn('interface=eth0\n',c['dnsmasq']);self.assertIn('dhcp-option=3\n',c['dnsmasq']);self.assertIn('dhcp-option=6\n',c['dnsmasq'])
  u=mod.render_units(c,'/usr/bin/python3');self.assertIn('--forwarder-host 127.0.0.1',u[mod.SERVICE]);self.assertNotIn('tx-config',u[mod.SERVICE]);self.assertIn('User=nobody',u[mod.SERVICE]);self.assertIn('--systemd-sockets',u[mod.SERVICE]);self.assertNotIn('CAP_NET_RAW',u[mod.SERVICE]);self.assertIn('BindToDevice=eth0',u[mod.HTTP_SOCKET]);self.assertIn('BindToDevice=eth0',u[mod.DISCOVERY_SOCKET])
  with self.assertRaises(mod.SetupError):mod.configuration('eth0','192.168.137.30','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
  with self.assertRaises(mod.SetupError):mod.configuration('eth0;id','192.168.137.200','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
 def test_delivery_package_and_hash_corruption(self):
  with tempfile.TemporaryDirectory() as d:
   meta=win.prepare(d);self.assertEqual(meta['minimum_python'],[3,4]);self.assertEqual(len(meta['files']),2)
   mod.verify_package(d);extra=Path(d)/'services/untrusted.py';extra.write_text('bad')
   with self.assertRaises(mod.SetupError):mod.verify_package(d)
   extra.unlink();p=Path(d)/'services'/next(iter(meta['files']));p.write_bytes(b'corrupted')
   with self.assertRaises(mod.SetupError):mod.verify_package(d)
 def run_transaction(self,fail):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);base=root/'gateway';system=root/'system';iface=root/'sys/net/eth0';iface.mkdir(parents=True);(iface/'type').write_text('1');system.mkdir()
   old=root/'pktfwd/local_conf.json';old.parent.mkdir();oldtext=json.dumps({'gateway_conf':{'gateway_ID':'b827ebFFFE32e2c1','server_address':'192.168.137.10'}});old.write_text(oldtext)
   package=root/'package';package.mkdir();win.prepare(package)
   names={'STATE':str(root/'state'),'SERVICE':str(system/'ann-gateway.service'),'DHCP':str(system/'ann-gateway-dhcp.service'),'ADDRESS':str(system/'ann-gateway-address.service'),'HTTP_SOCKET':str(system/'ann-gateway-http.socket'),'DISCOVERY_SOCKET':str(system/'ann-gateway-discovery.socket'),'DHCP_CONF':str(root/'etc/ann-gateway/dnsmasq.conf'),'LOCAL_CONF':str(old),'RELEASE':str(base/'release'),'SYS_NET':str(root/'sys/net'),'SYSTEMD_DIR':str(system)}
   calls=[];trigger=[False]
   def call(*args,**kw):
    calls.append(args)
    if fail and not trigger[0] and args[:3]==('systemctl','start','ann-gateway.service'):
     trigger[0]=True
     if fail=='crash':raise KeyboardInterrupt('synthetic crash')
     raise mod.SetupError('injected failure')
    text=''
    if args[:2]==('systemctl','is-active'):text='inactive' if args[2]=='dnsmasq.service' else 'active'
    if args[:2]==('systemctl','is-enabled'):text='enabled'
    return types.SimpleNamespace(stdout=text,stderr='',returncode=0)
   class Child:
    def __init__(self,*a,**kw):pass
    def wait(self):return 0
   c=mod.configuration('eth0','192.168.137.200','192.168.137.0/24','192.168.137.20','192.168.137.99','b827ebfffe32e2c1')
   patches=[patch.object(mod,k,v) for k,v in names.items()];patches += [patch.object(mod,'PATHS',[names[x] for x in ['SERVICE','DHCP','ADDRESS','HTTP_SOCKET','DISCOVERY_SOCKET','DHCP_CONF','LOCAL_CONF']]),patch.object(mod.os,'geteuid',return_value=0,create=True),patch.object(mod.os,'chown',return_value=None,create=True),patch.object(mod.shutil,'which',return_value='fake'),patch.object(mod,'call',side_effect=call),patch.object(mod,'verify_service',return_value=None),patch.object(mod,'check_ports',return_value=None),patch.object(mod.subprocess,'Popen',Child),patch.dict(sys.modules,{'pwd':types.SimpleNamespace(getpwnam=lambda _:types.SimpleNamespace(pw_uid=1,pw_gid=1))})]
   from contextlib import ExitStack
   with ExitStack() as stack:
    for p in patches:stack.enter_context(p)
    if fail=='crash':
     with self.assertRaises(KeyboardInterrupt):mod.install(package,c)
     self.assertTrue((Path(names['STATE'])/'backup.json').exists())
     mod.install(package,c);mod.rollback()
    elif fail:
     with self.assertRaises(mod.SetupError):mod.install(package,c)
    else:
     mod.install(package,c);installed=json.loads(old.read_text());self.assertEqual(installed['gateway_conf']['server_address'],'127.0.0.1')
     mod.install(package,c);mod.rollback()
    self.assertEqual(old.read_text(),oldtext);self.assertFalse(Path(names['SERVICE']).exists());self.assertFalse(Path(names['RELEASE']).exists())
    self.assertTrue(any(x[:3]==('systemctl','restart','pktfwd.service') for x in calls))
 def test_apply_idempotent_rollback(self):self.run_transaction(False)
 def test_apply_failure_restores_original(self):self.run_transaction(True)
 def test_interrupted_install_auto_rollback_on_retry(self):self.run_transaction('crash')
 def test_fake_ssh_no_password_arguments(self):
  calls=[]
  def runner(args,**kw):calls.append(args);return types.SimpleNamespace(stdout='',returncode=0)
  win.remote_exec('rxhf','192.168.137.200','install','eth0','b827ebfffe32e2c1',runner)
  self.assertEqual([x[0] for x in calls],['scp','ssh']);self.assertIn('--dedicated',calls[1][-1]);self.assertNotIn('password',' '.join(sum(calls,[])).lower())
if __name__=='__main__':unittest.main(verbosity=2)
