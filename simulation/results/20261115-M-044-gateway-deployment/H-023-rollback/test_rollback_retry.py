import json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,r'D:\Multi-Agent Network\.worktrees\production\app\gateway_setup')
import linux_installer as m

class RollbackRetry(unittest.TestCase):
 def exercise(self,fail_action,original_active='inactive'):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);state_dir=root/'state';state_dir.mkdir();release=root/'release'
   original=root/'local_conf.json';original.write_text('new')
   snapshot={'type':'file','data':'b2xk','mode':420,'uid':1,'gid':1}
   c={'interface':'eth0','address':'192.168.137.200','prefix':24}
   backup=state_dir/'backup.json';backup.write_text(json.dumps({'phase':'installed','files':{str(original):snapshot},'address_was_present':False,'config':c,'pktfwd':{'enabled':'disabled','active':original_active},'package_files':{}}))
   active={x:True for x in m.UNITS};enabled={x:True for x in m.UNITS};present=[True];pktfwd=[True,'enabled'];fail=[True]
   def call(*args,**kwargs):
    a=list(args);out='';rc=0;err='';key=None
    if a[:2]==['systemctl','show']:
     unit=a[-1];out='LoadState=loaded' if unit in active else 'LoadState=not-found'
    elif a[:2]==['systemctl','is-active']:
     unit=a[2];out=('active' if (pktfwd[0] if unit=='pktfwd.service' else active[unit]) else 'inactive')
    elif a[:2]==['systemctl','is-enabled']:
     unit=a[2];out=pktfwd[1] if unit=='pktfwd.service' else ('enabled' if enabled[unit] else 'disabled')
    elif a[0]=='systemctl' and a[1] in ('stop','disable','enable','restart'):
     action,unit=a[1:3];key=action+':'+unit
     if not (fail[0] and key==fail_action):
      if unit=='pktfwd.service':
       if action in ('stop','restart'):pktfwd[0]=(action=='restart')
       else:pktfwd[1]='enabled' if action=='enable' else 'disabled'
      elif action=='stop':active[unit]=False
      elif action=='disable':enabled[unit]=False
    elif a[:5]==['ip','-o','-4','addr','show']:
     out='inet 192.168.137.200/24' if present[0] else ''
    elif a[:3]==['/sbin/ip','address','del']:
     key='address:del'
     if not (fail[0] and key==fail_action):present[0]=False
    if fail[0] and key==fail_action:rc=1;err='injected failure';fail[0]=False
    return types.SimpleNamespace(stdout=out,stderr=err,returncode=rc)
   with patch.object(m,'STATE',str(state_dir)),patch.object(m,'RELEASE',str(release)),patch.object(m,'call',side_effect=call),patch.object(m.os,'chown',create=True):
    # Simulated call honors check=True like the real wrapper.
    raw=call
    def checked(*a,**kw):
     r=raw(*a,**kw)
     if r.returncode and kw.get('check',True):raise m.SetupError('command failed: '+r.stderr)
     return r
    with patch.object(m,'call',side_effect=checked):
     with self.assertRaises(m.SetupError):m.rollback()
     self.assertTrue(backup.exists());self.assertEqual(json.loads(backup.read_text())['phase'],'rolling_back')
     self.assertFalse(list(state_dir.glob('backup-restored-*')))
     m.rollback();self.assertFalse(backup.exists());self.assertEqual(len(list(state_dir.glob('backup-restored-*'))),1)
     self.assertEqual(original.read_text(),'old');self.assertFalse(present[0]);self.assertFalse(any(active.values()));self.assertFalse(any(enabled.values()))
 def test_socket_stop_failure(self):self.exercise('stop:ann-gateway-http.socket')
 def test_socket_disable_failure(self):self.exercise('disable:ann-gateway-discovery.socket')
 def test_address_delete_failure(self):self.exercise('address:del')
 def test_forwarder_stop_failure(self):self.exercise('stop:pktfwd.service')
 def test_forwarder_restart_failure(self):self.exercise('restart:pktfwd.service','active')
if __name__=='__main__':unittest.main(verbosity=2)

