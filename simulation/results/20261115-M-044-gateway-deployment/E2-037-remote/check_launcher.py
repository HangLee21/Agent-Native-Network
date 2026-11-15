import sys,pathlib,socket,subprocess,json,time,urllib.request
root=pathlib.Path.cwd().parent.parent;test=pathlib.Path.cwd();(test/'data').mkdir(exist_ok=True)
def free(kind):
 s=socket.socket(socket.AF_INET,kind);s.bind(('127.0.0.1',0));p=s.getsockname()[1];s.close();return p
udp,top,studio,discovery=free(socket.SOCK_DGRAM),free(socket.SOCK_STREAM),free(socket.SOCK_STREAM),free(socket.SOCK_DGRAM)
c=json.loads((root/'data/fleet.json').read_text(encoding='utf-8-sig'));c['gateway'].pop('mode',None);c['gateway'].update(candidate_hosts=['127.0.0.1'],udp_port=udp,http_port=top,discovery_port=discovery);c['services'].update(topology_port=top,studio_port=studio);(test/'fleet.json').write_text(json.dumps(c),encoding='utf-8');m=json.loads((root/'firmware/manifest.json').read_text(encoding='utf-8'));(test/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
code='import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv.pop(1));import launcher;launcher.ROOT=Path(sys.argv.pop(1));launcher.JOB=launcher.OwnedJob();launcher.open_studio_page=lambda u:None;r=launcher.ROOT;c=launcher.config(r/"fleet.json");m=json.loads((r/"manifest.json").read_text());h=launcher.Health(r/"data/recovery.json","http://127.0.0.1:"+str(c["services"]["studio_port"])+"/");launcher.launch(c,Path(sys.argv.pop(1)),m,r,fleet_path=r/"fleet.json",health=h)'
cmd=[sys.executable,'-I','-u','-X','utf8','-c',code,str(root/'app/start'),str(test),str(root/'app/services')];p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');op=urllib.request.build_opener(urllib.request.ProxyHandler({}));url='http://127.0.0.1:%s/'%studio
try:
 end=time.monotonic()+12;response=None
 while time.monotonic()<end and p.poll() is None:
  try:
   response=op.open(url,timeout=.5).read();break
  except OSError:time.sleep(.2)
 assert response and b'fleet-model.js' in response,'Studio page unavailable';topology=json.load(op.open(url+'api/v1/lora/topology',timeout=5));assert topology['reports']==[] and topology['receiver']['state']=='unavailable'
 probe=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);probe.bind(('0.0.0.0',udp));probe.close();print(json.dumps({'old_config_defaults_remote':True,'page_http':200,'offline_no_reports':True,'pc_udp_test_port_not_bound':udp}))
finally:
 if p.poll() is None:p.kill()
 stdout,stderr=p.communicate(timeout=6);(test/'launcher.stdout').write_text(stdout,encoding='utf-8');(test/'launcher.stderr').write_text(stderr,encoding='utf-8')
