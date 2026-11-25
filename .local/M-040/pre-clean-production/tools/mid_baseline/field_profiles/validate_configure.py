"""Fake-serial test of credential helper: identity/idle gate and secret-free stdout."""
from pathlib import Path
import argparse,datetime,json,sys,types,os,io,contextlib,importlib.util
ROOT=Path(__file__).resolve().parents[3]
def main():
 p=argparse.ArgumentParser();p.add_argument('--run',required=True);a=p.parse_args()
 if not a.run or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in a.run):raise ValueError('simple run name')
 out=ROOT/'simulation/outputs/E1-027'/a.run;out.mkdir(parents=True,exist_ok=False);instances=[];wrong=False
 class FakeSerial:
  def __init__(self,**kw):assert kw['port'] is None;self.dtr=self.rts=True;self.port=None;self.opened=False;self.tx=[];self.rx=[];instances.append(self)
  def open(self):assert self.port=='FAKE' and not self.dtr and not self.rts;self.opened=True
  def __enter__(self):assert self.opened;return self
  def __exit__(self,*args):self.opened=False
  def write(self,raw):
   obj=json.loads(raw);self.tx.append(obj);reply=dict(event='command_result',nonce=obj['nonce'],ok=True,node_id='02:00:00:00:00:09' if wrong else '02:00:00:00:00:01',field_api=2,radio=False,stopping=False);self.rx.append((json.dumps(reply)+'\n').encode());return len(raw)
  def readline(self):return self.rx.pop(0) if self.rx else b''
 original_module=sys.modules.get('serial');original_argv=sys.argv[:];old_ssid=os.environ.get('FIELD_SSID');old_pw=os.environ.get('FIELD_PASSWORD');sys.modules['serial']=types.SimpleNamespace(Serial=FakeSerial);os.environ['FIELD_SSID']='NON_SECRET_TEST_SSID';os.environ['FIELD_PASSWORD']='NON_SECRET_TEST_PASSWORD'
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 try:
  path=ROOT/'tools/mid_baseline/field_profiles/configure_wifi.py';spec=importlib.util.spec_from_file_location('configure_field_under_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
  sys.argv=[str(path),'--port','FAKE','--node-id','02:00:00:00:00:01','--bssid','02:00:00:00:00:aa','--channel','6','--pc-ip','192.0.2.1'];capture=io.StringIO()
  with contextlib.redirect_stdout(capture):module.main()
  assert len(instances[-1].tx)==2 and instances[-1].tx[-1]['cmd']=='ip_config' and not instances[-1].opened
  assert 'NON_SECRET_TEST_SSID' not in capture.getvalue() and 'NON_SECRET_TEST_PASSWORD' not in capture.getvalue()
  wrong=True
  try:module.main();raise AssertionError('wrong identity accepted')
  except RuntimeError:pass
  assert len(instances[-1].tx)==1 and not instances[-1].opened
  log='PASS actual helper opens with DTR/RTS disabled before context, verifies identity+idle before credentials, closes handles, prints no credentials; fake serial only\n';(out/'host.log').write_text(log,encoding='utf-8');print(log)
 finally:
  sys.argv=original_argv
  if original_module is None:sys.modules.pop('serial',None)
  else:sys.modules['serial']=original_module
  for key,value in [('FIELD_SSID',old_ssid),('FIELD_PASSWORD',old_pw)]:
   if value is None:os.environ.pop(key,None)
   else:os.environ[key]=value
 m=json.loads((ROOT/'coordination/templates/RUN_MANIFEST.json').read_text(encoding='utf-8-sig'));m.update(template_only=False,task_id='E1-027',run_id=a.run,started_at=start,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=['validate_configure.py','--run',a.run],status='passed',exit_code=0,worktree=str(ROOT),output_directory=str(out),budget=dict(device_access=0),limitations=['Fake serial only; dummy non-secret credentials never printed; no real port or hotspot accessed.']);(out/'RUN_MANIFEST.json').write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');return 0
if __name__=='__main__':raise SystemExit(main())
