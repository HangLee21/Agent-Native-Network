"""Real supervisor and child-process recovery, on isolated loopback only."""
import copy,ctypes,hashlib,json,os,signal,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path
import launcher

FAKE='''import argparse,json,os\nfrom pathlib import Path\nfrom http.server import BaseHTTPRequestHandler,HTTPServer\np=argparse.ArgumentParser();p.add_argument("--port",type=int);p.add_argument("--mode");p.add_argument("--run");a=p.parse_args();root=Path(a.run);(root/(a.mode+".pid")).write_text(str(os.getpid()))\nclass H(BaseHTTPRequestHandler):\n def do_GET(self):\n  observed=(root/"gateway-ready").exists() and not (root/"disconnect").exists();body=json.dumps({"receiver":{"gateway_id":"b827ebfffe32e2c1","gateway_observed":observed}}).encode();self.send_response(200);self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)\n def log_message(self,*a):pass\ns=HTTPServer(("127.0.0.1",a.port),H);s.serve_forever()\n'''

class Recovery(unittest.TestCase):
 def free(self,kind=socket.SOCK_STREAM):
  with socket.socket(socket.AF_INET,kind) as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
 def wait_for(self,fn,timeout=15):
  end=time.monotonic()+timeout
  while time.monotonic()<end:
   try:
    value=fn()
    if value:return value
   except (OSError,ValueError,KeyError):pass
   time.sleep(.1)
  self.fail('timed out waiting for recovery condition')
 def test_real_process_recovery_and_reuse(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);pkg=root/'release'/'mock';pkg.mkdir(parents=True)
   for name in ('gateway','studio'):(pkg/(name+'.py')).write_text(FAKE,encoding='utf-8')
   hashes={'mock/'+x+'.py':hashlib.sha256((pkg/(x+'.py')).read_bytes()).hexdigest() for x in ('gateway','studio')}
   m=dict(schema_version=1,release_id='mock-only',status='candidate',source_commit='a'*40,service_files_sha256=hashes,services=dict(gateway_module='mock.gateway',studio_module='mock.studio',gateway_args=['--port','{topology_port}','--mode','gateway','--run','{run_dir}'],studio_args=['--port','{studio_port}','--mode','studio','--run','{run_dir}']))
   manifest=root/'release'/'manifest.json';manifest.write_text(json.dumps(m));c=copy.deepcopy(launcher.config(launcher.ROOT/'production/config/fleet.example.json'));c['gateway']['candidate_hosts']=['127.0.0.1'];c['gateway']['udp_port']=self.free(socket.SOCK_DGRAM);c['services']['topology_port']=self.free();c['services']['studio_port']=self.free();cfg=root/'fleet.json';cfg.write_text(json.dumps(c))
   code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv.pop(1));import launcher;launcher.ROOT=Path(sys.argv.pop(1));launcher.webbrowser.open=lambda *a: True;raise SystemExit(launcher.main())'
   cmd=[sys.executable,'-X','utf8','-c',code,str(Path(launcher.__file__).parent),str(root),'--config',str(cfg),'--release',str(manifest)]
   p=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);sentinel=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);children=[];timing={};start=time.monotonic()
   try:
    run=self.wait_for(lambda:next(iter((root/'production/local/logs').glob('studio-*')),None));state=root/'production/local/studio-recovery.json'
    def health():return json.loads(state.read_text(encoding='utf-8'))['state']
    self.wait_for(lambda:(run/'gateway.pid').exists());self.assertEqual(health(),'connecting');self.assertFalse((run/'studio.pid').exists());(run/'gateway-ready').touch()
    self.wait_for(lambda:health()=='online');timing['late_gateway_s']=round(time.monotonic()-start,3);studio_pid=int((run/'studio.pid').read_text());gateway_pid=int((run/'gateway.pid').read_text());children=[studio_pid,gateway_pid]
    dup=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8',timeout=8);self.assertEqual(dup.returncode,0,dup.stderr);self.assertEqual(int((run/'studio.pid').read_text()),studio_pid)
    start=time.monotonic();(run/'disconnect').touch();self.wait_for(lambda:health()=='recovering');timing['disconnect_detection_s']=round(time.monotonic()-start,3);start=time.monotonic();(run/'disconnect').unlink();self.wait_for(lambda:health()=='recovered');timing['reconnect_s']=round(time.monotonic()-start,3)
    start=time.monotonic();os.kill(studio_pid,signal.SIGTERM);self.wait_for(lambda:(run/'studio.pid').is_file() and int((run/'studio.pid').read_text())!=studio_pid and health()=='recovered',timeout=25);timing['studio_restart_s']=round(time.monotonic()-start,3)
    new_studio=int((run/'studio.pid').read_text());new_gateway=int((run/'gateway.pid').read_text());children=[new_studio,new_gateway]
    start=time.monotonic();os.kill(new_gateway,signal.SIGTERM);self.wait_for(lambda:(run/'gateway.pid').is_file() and int((run/'gateway.pid').read_text())!=new_gateway and health()=='recovered',timeout=25);timing['gateway_restart_s']=round(time.monotonic()-start,3)
    children=[int((run/'studio.pid').read_text()),int((run/'gateway.pid').read_text())]
    p.kill();p.wait(timeout=5)
    # The kernel lock and job are released even though no cleanup handler ran.
    (root/'production/local/studio-instance.json').write_text(json.dumps({'port':1,'token':'stale','pid':sentinel.pid}),encoding='utf-8')
    start=time.monotonic()
    q=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
     previous=run;run=self.wait_for(lambda:next((x for x in (root/'production/local/logs').glob('studio-*') if x!=previous),None),timeout=20)
     (run/'gateway-ready').touch();self.wait_for(lambda:(run/'studio.pid').exists() and health() in ('online','recovered'),timeout=25);timing['stale_lock_restart_s']=round(time.monotonic()-start,3);self.assertIsNone(sentinel.poll())
     children=[int((run/'studio.pid').read_text()),int((run/'gateway.pid').read_text())]
    finally:q.kill();q.wait(timeout=5)
    print(json.dumps({'synthetic_recovery_timings':timing},sort_keys=True),flush=True)
   finally:
    if p.poll() is None:p.kill();p.wait(timeout=5)
    if sentinel.poll() is None:sentinel.terminate();sentinel.wait(timeout=5)

if __name__=='__main__':unittest.main()
