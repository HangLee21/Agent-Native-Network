"""Explicit-release gateway/Studio supervisor; hardware discovery only on actual launch."""
import argparse,ctypes,hashlib,ipaddress,json,msvcrt,os,re,socket,subprocess,sys,threading,time,urllib.request,uuid,webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MAC=re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}')
MODULE=re.compile(r'[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+')
JOB=None

class OwnedJob:
 def __init__(self):
  from ctypes import wintypes as w
  class Basic(ctypes.Structure):
   _fields_=[('PerProcessUserTimeLimit',ctypes.c_longlong),('PerJobUserTimeLimit',ctypes.c_longlong),('LimitFlags',w.DWORD),('MinimumWorkingSetSize',ctypes.c_size_t),('MaximumWorkingSetSize',ctypes.c_size_t),('ActiveProcessLimit',w.DWORD),('Affinity',ctypes.c_size_t),('PriorityClass',w.DWORD),('SchedulingClass',w.DWORD)]
  class Io(ctypes.Structure):
   _fields_=[(x,ctypes.c_ulonglong) for x in ('ReadOperationCount','WriteOperationCount','OtherOperationCount','ReadTransferCount','WriteTransferCount','OtherTransferCount')]
  class Extended(ctypes.Structure):
   _fields_=[('BasicLimitInformation',Basic),('IoInfo',Io),('ProcessMemoryLimit',ctypes.c_size_t),('JobMemoryLimit',ctypes.c_size_t),('PeakProcessMemoryUsed',ctypes.c_size_t),('PeakJobMemoryUsed',ctypes.c_size_t)]
  self.k=ctypes.WinDLL('kernel32',use_last_error=True);self.k.CreateJobObjectW.restype=w.HANDLE;self.k.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];self.k.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];self.k.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];self.k.CloseHandle.argtypes=[w.HANDLE]
  self.handle=self.k.CreateJobObjectW(None,None)
  if not self.handle:raise OSError(ctypes.get_last_error(),'CreateJobObject failed')
  limits=Extended();limits.BasicLimitInformation.LimitFlags=0x2000
  if not self.k.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)):
   self.close();raise OSError(ctypes.get_last_error(),'SetInformationJobObject failed')
 def add(self,child):
  if not self.k.AssignProcessToJobObject(self.handle,int(child._handle)):
   child.terminate();child.wait();raise OSError(ctypes.get_last_error(),'AssignProcessToJobObject failed')
 def close(self):
  if self.handle:self.k.CloseHandle(self.handle);self.handle=None


def config(path):
 c=json.loads(Path(path).read_text(encoding='utf-8-sig'))
 if type(c.get('schema_version')) is not int or c['schema_version']!=1 or not isinstance(c.get('nodes'),list):raise ValueError('unsupported fleet schema')
 ids=set();macs=set()
 for n in c['nodes']:
  i=n.get('node_id');mac=n.get('mac')
  if isinstance(mac,str):mac=mac.strip().lower()
  if type(i) is not int or not 1<=i<=0xffffffff or not isinstance(mac,str) or not MAC.fullmatch(mac) or i in ids or mac in macs:raise ValueError('invalid or duplicate node ID/MAC')
  ids.add(i);macs.add(mac)
 g=c['gateway'];eui=g['eui']
 mode=g.get('mode','remote')
 if mode not in ('remote','legacy_local'):raise ValueError('invalid gateway mode')
 for name in ('http_port','discovery_port'):
  v=g.get(name,8780 if name=='http_port' else 8781)
  if type(v) is not int or not 1024<=v<=65535:raise ValueError('invalid gateway '+name)
 if not isinstance(eui,str) or not re.fullmatch(r'[0-9a-fA-F]{16}',eui):raise ValueError('gateway EUI required')
 if not isinstance(g['candidate_hosts'],list) or not 1<=len(g['candidate_hosts'])<=8:raise ValueError('one to eight explicit gateway candidates required')
 for host in g['candidate_hosts']:ipaddress.IPv4Address(host)
 ports=[g.get('udp_port',1680),c['services']['topology_port'],c['services']['studio_port']]
 if any(type(v) is not int or not 1024<=v<=65535 for v in ports) or ports[1]==ports[2]:raise ValueError('invalid service ports')
 return c


def save_config_backup(source,local):
 payload=Path(source).read_text(encoding='utf-8-sig');config(source)
 if payload!=Path(source).read_text(encoding='utf-8-sig'):raise ValueError('fleet changed during validation')
 raw=payload.encode('utf-8');record=dict(source=str(Path(source).resolve()).casefold(),sha256=hashlib.sha256(raw).hexdigest(),payload=payload)
 local.mkdir(parents=True,exist_ok=True);path=local/'fleet.last-good.json';tmp=path.with_name(path.name+'.tmp');tmp.write_text(json.dumps(record,ensure_ascii=False),encoding='utf-8');os.replace(tmp,path)

def config_with_backup(source,local):
 try:return config(source),Path(source),False
 except (OSError,ValueError,KeyError,TypeError):
  try:
   record=json.loads((local/'fleet.last-good.json').read_text(encoding='utf-8'));payload=record['payload'];raw=payload.encode('utf-8')
   if record['source']!=str(Path(source).resolve()).casefold() or record['sha256']!=hashlib.sha256(raw).hexdigest():raise ValueError('invalid config backup')
   recovered=local/'fleet.recovered.json';tmp=recovered.with_name(recovered.name+'.tmp');tmp.write_bytes(raw);os.replace(tmp,recovered)
   return config(recovered),recovered,True
  except (OSError,ValueError,KeyError,TypeError) as exc:raise ValueError('配置与已验证副本均不可用') from exc


def inside(root,relative):
 if not isinstance(relative,str):raise ValueError('relative release file required')
 p=(root/relative).resolve()
 if not p.is_relative_to(root) or not p.is_file():raise ValueError('release file missing or outside selected package: '+relative)
 return p


def release(path):
 path=Path(path).resolve();manifest=path/'manifest.json' if path.is_dir() else path;root=ROOT/'app/services'
 m=json.loads(manifest.read_text(encoding='utf-8-sig'))
 if m.get('schema_version')!=1 or m.get('status') not in ('candidate','validated') or not isinstance(m.get('release_id'),str) or not m['release_id'] or not isinstance(m.get('source_commit'),str) or not re.fullmatch(r'[0-9a-f]{40,64}',m['source_commit']):raise ValueError('release identity/source/status not frozen')
 svc=m.get('services',{});hashes=m.get('service_files_sha256')
 if not isinstance(hashes,dict) or not hashes:raise ValueError('release needs service_files_sha256 for frozen services')
 for key in ('gateway_module','studio_module'):
  name=svc.get(key)
  if not isinstance(name,str) or not MODULE.fullmatch(name):raise ValueError('release '+key+' unavailable')
  relative=name.replace('.','/')+'.py'
  if relative not in hashes:raise ValueError('entry module is not hashed: '+relative)
 for relative,expected in hashes.items():
  if not isinstance(expected,str) or not re.fullmatch(r'[0-9a-f]{64}',expected):raise ValueError('invalid SHA256 in release')
  if hashlib.sha256(inside(root,relative).read_bytes()).hexdigest()!=expected:raise ValueError('release service hash mismatch: '+relative)
 for source in root.rglob('*'):
  if source.is_file() and source!=manifest and '__pycache__' not in source.parts and source.suffix.lower() in ('.py','.json','.html','.js','.css') and source.relative_to(root).as_posix() not in hashes:
   raise ValueError('unhashed runtime file in release: '+str(source.relative_to(root)))
 for key in ('gateway_args','studio_args'):
  if not isinstance(svc.get(key),list) or any(not isinstance(v,str) for v in svc[key]):raise ValueError('release needs explicit '+key)
 return root,m


def available(tcp_ports,udp_port):
 sockets=[]
 try:
  for p in tcp_ports:
   s=socket.socket(socket.AF_INET,socket.SOCK_STREAM);sockets.append(s);s.bind(('127.0.0.1',p))
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sockets.append(s);s.bind(('0.0.0.0',udp_port))
 finally:
  for s in sockets:s.close()


def start_child(root,module,args,log):
 # Isolated Python removes the development checkout and PYTHONPATH from imports.
 code='import runpy,sys;root=sys.argv.pop(1);name=sys.argv.pop(1);sys.path.insert(0,root);runpy.run_module(name,run_name="__main__")'
 child=subprocess.Popen([sys.executable,'-I','-u','-X','utf8','-c',code,str(root),module,*args],cwd=root,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
 if JOB:JOB.add(child)
 return child


def arguments(template,values):
 for item in template:
  names=re.findall(r'\{([^{}]+)\}',item)
  if any(x not in values for x in names) or '{' in re.sub(r'\{[^{}]+\}','',item) or '}' in re.sub(r'\{[^{}]+\}','',item):raise ValueError('unknown argument placeholder')
  if (os.path.isabs(item) or re.match(r'^[A-Za-z]:[\\/]',item)) and not item.startswith(('{release_dir}','{run_dir}')):raise ValueError('absolute argument paths must use release_dir or run_dir')
  if re.search(r'(^|[\\/])\.\.([\\/]|$)',item):raise ValueError('argument path traversal is not permitted')
 return [item.format_map(values) for item in template]


def get_json(url):
 with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=.5) as response:return json.load(response)


def discover(url,eui,child,seconds=8):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if child.poll() is not None:return False,'gateway service exited'
  try:
   info=get_json(url);r=info.get('receiver',{})
   if str(r.get('gateway_id','')).lower()==eui.lower() and r.get('gateway_observed') is True:return True,'verified PULL_DATA gateway EUI'
  except (OSError,ValueError):pass
  time.sleep(.2)
 return False,'no matching gateway PULL_DATA within timeout'


class Offline(BaseHTTPRequestHandler):
 def do_GET(self):
  reason=self.server.reason
  if self.path.split('?')[0]=='/api/v1/recovery':
   health=getattr(self.server,'health',None)
   data=json.dumps(dict(schema='studio.recovery.v1',state=health.state if health else 'unavailable',reason=health.reason if health else reason,updated_at=time.time()),ensure_ascii=False).encode();kind='application/json; charset=utf-8'
  elif self.path.startswith('/api/'):
   data=json.dumps(dict(online=False,mode='offline',reason=reason,replay=False),ensure_ascii=False).encode();kind='application/json; charset=utf-8'
  else:
   import html
   data=('''<!doctype html><meta charset="utf-8"><title>Studio 正在恢复</title><h1>Studio 正在连接</h1><p>'''+html.escape(reason)+'''</p><p>没有显示实况或历史回放；服务恢复后页面自动更新。</p><script>setInterval(async()=>{try{let r=await fetch('/api/status',{cache:'no-store'});if(!r.ok||(await r.json()).mode!=='offline')location.reload()}catch(e){}},2000)</script>''').encode();kind='text/html; charset=utf-8'
  self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def log_message(self,*_):pass


def open_studio_page(url):
 print('Studio 地址（可点击或复制到浏览器）：'+url,flush=True)
 try:
  os.startfile(url)
  print('已请求系统打开浏览器；若页面没有出现，请使用上面的地址。',flush=True)
  return 'requested'
 except (OSError,AttributeError) as exc:
  print('系统浏览器调用未成功，正在尝试备用方式：'+str(exc),flush=True)
 try:
  if webbrowser.open(url,new=2):
   print('已请求备用浏览器打开页面；若页面没有出现，请使用上面的地址。',flush=True)
   return 'requested_fallback'
 except Exception as exc:
  print('备用浏览器调用未成功：'+str(exc),flush=True)
 print('浏览器未能自动打开，请使用上面的地址。',flush=True)
 return 'failed'


def offline(port,reason,open_browser=True):
 server=ThreadingHTTPServer(('127.0.0.1',port),Offline);server.reason=reason
 print(json.dumps(dict(state='offline',reason=reason,url=f'http://127.0.0.1:{server.server_port}/'),ensure_ascii=False),flush=True)
 if open_browser:open_studio_page(f'http://127.0.0.1:{server.server_port}/')
 try:server.serve_forever()
 finally:server.server_close()


def lock(path):
 path.parent.mkdir(parents=True,exist_ok=True);f=path.open('a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
 try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
 except OSError:f.close();raise RuntimeError('another Studio launcher owns the instance lock')
 return f


class Health:
 def __init__(self,path,url):self.path=path;self.url=url;self.state='connecting';self.reason='正在连接';self.had_recovery=False;self.set('connecting',self.reason)
 def set(self,state,reason):
  self.state=state;self.reason=reason
  if state=='recovering':self.had_recovery=True
  self.path.parent.mkdir(parents=True,exist_ok=True)
  tmp=self.path.with_name(self.path.name+'.tmp');tmp.write_text(json.dumps(dict(schema='studio.recovery.v1',state=state,reason=reason,updated_at=time.time()),ensure_ascii=False),encoding='utf-8');os.replace(tmp,self.path)

class Control(BaseHTTPRequestHandler):
 def do_GET(self):
  if self.headers.get('X-Studio-Token')!=self.server.token:self.send_error(403);return
  body=json.dumps(dict(schema='studio.instance.v1',url=self.server.health.url,state=self.server.health.state,gateway_mode=self.server.gateway_mode)).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def log_message(self,*_):pass

def reuse_instance(path,expected_port,expected_mode):
 end=time.monotonic()+3
 while time.monotonic()<end:
  try:
   v=json.loads(path.read_text(encoding='utf-8'));req=urllib.request.Request(f"http://127.0.0.1:{v['port']}/",headers={'X-Studio-Token':v['token']})
   with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req,timeout=.5) as r:info=json.load(r)
   if info.get('schema')=='studio.instance.v1' and info.get('url')==f'http://127.0.0.1:{expected_port}/':
    if info.get('gateway_mode')!=expected_mode:print('检测到旧版或不同网关模式的实例，请关闭原窗口后重新双击。',flush=True);return 'incompatible'
    open_studio_page(info['url']);return True
  except (OSError,ValueError,KeyError,TypeError):pass
  time.sleep(.15)
 return False

def launch_remote(c,release_root,m,run_dir,offline_server=None,fleet_path=None,health=None):
 g=c['gateway'];ports=c['services'];svc=m['services'];child=None;log=None
 try:
  if offline_server:offline_server.shutdown();offline_server.server_close()
  session_dir=run_dir/('session-'+uuid.uuid4().hex[:12]);session_dir.mkdir(parents=True,exist_ok=False)
  values=dict(udp_port=g.get('udp_port',1680),topology_port=ports['topology_port'],studio_port=ports['studio_port'],gateway_ip=g['candidate_hosts'][0],gateway_eui=g['eui'].lower(),run_dir=str(session_dir),release_dir=str(release_root))
  args=arguments(svc['studio_args'],values)+['--fleet',str(Path(fleet_path).resolve()),'--registry',str(ROOT/'data/registry.json'),'--production-output','--gateway-mode','remote','--gateway-eui',g['eui'].lower(),'--remote-http-port',str(g.get('http_port',8780)),'--discovery-port',str(g.get('discovery_port',8781))]
  for host in g['candidate_hosts']:args+=['--candidate-host',host]
  if health:args+=['--recovery-file',str(health.path)]
  log=(run_dir/'studio.log').open('a',encoding='utf-8');child=start_child(release_root,svc['studio_module'],args,log);url=f"http://127.0.0.1:{ports['studio_port']}/";end=time.monotonic()+8;ready=False
  while time.monotonic()<end and child.poll() is None:
   try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=.5) as response:ready=response.status==200
    if ready:break
   except OSError:time.sleep(.2)
  if not ready:return False,'Studio 服务未就绪'
  if health:health.set('recovering','等待远端网关连接')
  print(json.dumps(dict(state='recovering',url=url,reason='等待远端网关连接'),ensure_ascii=False),flush=True);open_studio_page(url)
  was=False
  while child.poll() is None:
   try:
    info=get_json(url+'api/v1/remote/health');observed=info.get('state')=='connected' and info.get('gateway_observed') is True
   except (OSError,ValueError,AttributeError):observed=False
   if health:health.set(('recovered' if health.had_recovery else 'online') if observed else 'recovering','网关已连接' if observed else '等待远端网关连接')
   if observed!=was:print('网关状态：'+('已恢复' if observed else '等待连接'),flush=True);was=observed
   time.sleep(2)
  return False,'Studio 服务退出，正在恢复'
 finally:
  if child and child.poll() is None:
   child.terminate()
   try:child.wait(timeout=5)
   except subprocess.TimeoutExpired:child.kill();child.wait()
  if log:log.close()


def launch(c,release_root,m,run_dir,offline_server=None,fleet_path=None,health=None):
 if c['gateway'].get('mode','remote')=='remote':return launch_remote(c,release_root,m,run_dir,offline_server,fleet_path,health)
 g=c['gateway'];ports=c['services'];available([ports['topology_port']] if offline_server else [ports['topology_port'],ports['studio_port']],g['udp_port']);svc=m['services'];children=[];logs=[]
 try:
  found=False;service_ready=False;reason='no gateway candidate'
  while True:
   for host in g['candidate_hosts']:
    values=dict(udp_port=g['udp_port'],topology_port=ports['topology_port'],studio_port=ports['studio_port'],gateway_ip=host,gateway_eui=g['eui'].lower(),run_dir=str(run_dir),release_dir=str(release_root))
    log=(run_dir/('gateway-'+host+'.log')).open('a',encoding='utf-8');logs.append(log)
    gateway_args=arguments(svc['gateway_args'],values)
    if svc['gateway_module']=='tools.flight_link.gateway':gateway_args+=['--state-file',str(ROOT/'data/command-journal.json')]
    child=start_child(release_root,svc['gateway_module'],gateway_args,log);children.append(child)
    found,reason=discover(f"http://127.0.0.1:{ports['topology_port']}/api/v1/lora/topology",g['eui'],child)
    if child.poll() is None:
     try:
      gateway_state=get_json(f"http://127.0.0.1:{ports['topology_port']}/api/v1/lora/topology")
      service_ready=gateway_state.get('schema')=='lora.topology.v1' and str(gateway_state.get('receiver',{}).get('gateway_id','')).lower()==g['eui'].lower()
     except (OSError,ValueError,AttributeError):service_ready=False
    if found or service_ready:break
    if child.poll() is None:child.terminate();child.wait(timeout=5)
    children.remove(child);log.close();logs.remove(log)
    if reason=='gateway service exited':return False,'网关服务退出，正在自动恢复。'
   if found or service_ready or offline_server is None:break
   offline_server.reason='尚未收到匹配网关；请检查设备电源和连接，程序会自动重试。'
   if health:health.set('recovering','等待网关重新连接')
   time.sleep(2)
  if not children:return False,reason
  if offline_server:
   offline_server.shutdown();offline_server.server_close()
  log=(run_dir/'studio.log').open('w',encoding='utf-8');logs.append(log)
  studio_args=arguments(svc['studio_args'],values)
  if svc['studio_module']=='tools.mobile_gateway.studio':
   if fleet_path is None:raise ValueError('Studio requires the launch fleet configuration path')
   studio_args+=['--fleet',str(Path(fleet_path).resolve()),'--registry',str(ROOT/'data/registry.json'),'--topology-port',str(ports['topology_port']),'--production-output']
   if health:studio_args+=['--recovery-file',str(health.path)]
  child=start_child(release_root,svc['studio_module'],studio_args,log);children.append(child)
  url=f"http://127.0.0.1:{ports['studio_port']}/";end=time.monotonic()+8;ready=False
  while time.monotonic()<end and child.poll() is None:
   try:
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url,timeout=.5) as response:ready=response.status==200
    if ready:break
   except OSError:time.sleep(.2)
  if not ready:return False,'Studio failed to start; inspect studio.log'
  if health:health.set(('recovered' if health.had_recovery else 'online') if found else 'recovering','网关已连接' if found else '等待网关连接')
  print(json.dumps(dict(state='online' if found else 'recovering',url=url,reason=reason,logs=str(run_dir)),ensure_ascii=False),flush=True);open_studio_page(url)
  observed=found;next_check=time.monotonic()+2
  while all(child.poll() is None for child in children):
   if time.monotonic()>=next_check:
    try:
     receiver=get_json(f"http://127.0.0.1:{ports['topology_port']}/api/v1/lora/topology").get('receiver',{})
     current=str(receiver.get('gateway_id','')).lower()==g['eui'].lower() and receiver.get('gateway_observed') is True
    except (OSError,ValueError):current=False
    if current!=observed:
     print(json.dumps(dict(state='gateway_observed' if current else 'gateway_disconnected',logs=str(run_dir)),ensure_ascii=False),flush=True);observed=current
     if health:health.set('recovered' if current else 'recovering','网关已重新连接' if current else '等待网关重新连接')
    elif health:health.set(health.state,health.reason)
    next_check=time.monotonic()+2
   time.sleep(.5)
  return False,'a managed service exited; inspect logs'
 finally:
  for child in reversed(children):
   if child.poll() is None:
    child.terminate()
    try:child.wait(timeout=5)
    except subprocess.TimeoutExpired:child.kill();child.wait()
  for log in logs:log.close()


def main():
 global JOB
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path);p.add_argument('--release',type=Path);p.add_argument('--dry-run',action='store_true');p.add_argument('--self-test',action='store_true');a=p.parse_args()
 if a.self_test:
  code='import sys;sys.path.insert(0,sys.argv[1]);import tools.flight_link.gateway,tools.mobile_gateway.studio'
  result=subprocess.run([sys.executable,'-I','-c',code,str(ROOT/'app/services')],capture_output=True,text=True)
  print('service imports: '+('ok' if result.returncode==0 else result.stderr),flush=True)
  return result.returncode
 local=ROOT/'data';default_local=local/'fleet.json';backup=local/'fleet.last-good.json'
 if a.config:cfg=a.config
 elif default_local.is_file():cfg=default_local
 elif backup.exists():
  try:
   remembered=json.loads(backup.read_text(encoding='utf-8'))['source']
   if not isinstance(remembered,str) or not Path(remembered).is_absolute():raise ValueError('invalid remembered fleet path')
   cfg=Path(remembered)
  except (OSError,ValueError,KeyError,TypeError) as e:print('配置副本无法验证，请重试或恢复原配置：',e,file=sys.stderr);return 2
 else:cfg=ROOT/'config/fleet.default.json'
 original_cfg=cfg
 try:
  if a.dry_run:c=config(cfg);recovered=False
  else:c,cfg,recovered=config_with_backup(cfg,local)
 except Exception as e:print('配置无法读取或校验失败，请联系交付人员修复默认 fleet 配置：',e,file=sys.stderr);return 2
 manifest=a.release or ROOT/'firmware/manifest.json'
 try:rr,m=release(manifest);reason=None
 except (ValueError,OSError,KeyError,json.JSONDecodeError) as e:rr=m=None;reason='发布服务包不可用，请联系交付人员安装并校验完整发布包：'+str(e)
 if a.dry_run:
  print(json.dumps(dict(state='dry_run',config=str(cfg),release=str(manifest),release_ready=m is not None,reason=reason,gateway_mode=c['gateway'].get('mode','remote'),hardware_probed=False),ensure_ascii=False));return 0
 if 'mode' not in c['gateway']:print('旧配置未指定网关模式：本次使用 remote（不绑定电脑 UDP 1680）；显式 legacy_local 可回退。',flush=True)
 instance_file=local/'studio-instance.json';url=f"http://127.0.0.1:{c['services']['studio_port']}/"
 try:handle=lock(local/'studio.lock')
 except (OSError,RuntimeError) as e:
  reused=reuse_instance(instance_file,c['services']['studio_port'],c['gateway'].get('mode','remote'))
  if reused=='incompatible':return 1
  if reused:print('已连接到运行中的 Studio。',flush=True);return 0
  print('Studio 正在启动或无法访问，请稍后再次双击。',e,file=sys.stderr);return 1
 control=None
 try:
  if not recovered:save_config_backup(original_cfg,local)
  JOB=OwnedJob()
  health=Health(local/'studio-recovery.json',url)
  control=ThreadingHTTPServer(('127.0.0.1',0),Control);control.token=secrets_token=uuid.uuid4().hex+uuid.uuid4().hex;control.health=health;control.gateway_mode=c['gateway'].get('mode','remote')
  threading.Thread(target=control.serve_forever,daemon=True).start()
  instance_file.write_text(json.dumps(dict(port=control.server_port,token=secrets_token)),encoding='utf-8')
  run_dir=ROOT/'data/logs'/('studio-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]);run_dir.mkdir(parents=True,exist_ok=False)
  if m:
   failures=0;opened=False
   while True:
    server=None;started=time.monotonic()
    try:
     server=ThreadingHTTPServer(('127.0.0.1',c['services']['studio_port']),Offline);server.reason='正在连接网关；请确认设备供电和连接，程序会自动重试。';server.health=health
     threading.Thread(target=server.serve_forever,daemon=True).start()
     if not opened:open_studio_page(url);opened=True
     _,reason=launch(c,rr,m,run_dir,server,cfg,health)
    except (OSError,ValueError,RuntimeError) as e:reason='服务暂不可用，正在自动重试：'+str(e)
    finally:
     if server:server.shutdown();server.server_close()
    failures=1 if time.monotonic()-started>60 else min(failures+1,5)
    delay=min(2**(failures-1),15);health.set('recovering',reason)
    print(json.dumps(dict(state='recovering',reason=reason,retry_seconds=delay),ensure_ascii=False),flush=True);time.sleep(delay)
  health.set('unavailable',reason)
  print('日志目录：'+str(run_dir),flush=True)
  try:offline(c['services']['studio_port'],reason)
  except OSError as e:print('离线页面端口不可用：'+str(e),file=sys.stderr);return 1
 except KeyboardInterrupt:print('Studio 已停止。')
 finally:
  if control:control.shutdown();control.server_close()
  if JOB:JOB.close();JOB=None
  handle.close()
 return 0
if __name__=='__main__':raise SystemExit(main())
