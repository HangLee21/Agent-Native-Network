import json, threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
STATIC=Path(r'D:\Multi-Agent Network\.worktrees\production\app\services\assets\mobile_gateway')
IDS=['90:da:72:48:a4:f8','90:da:72:48:a5:cc','90:da:72:48:a4:e0','90:da:72:48:a5:20']
state={'selected':'a','preferred':None,'available':{'a':True,'b':True},'age':200,'fail':False}

def sources():
 rows=[]
 for i,name in enumerate(('a','b','unverified')):
  ok=state['available'].get(name,True)
  rows.append({'id':name,'kind':'serial' if name=='b' else 'udp','label':{'a':'甲来源','b':'乙来源','unverified':'未知来源'}[name],
   'gateway_id':IDS[min(i,1)],'state':'receiving' if ok else 'unavailable','available':ok,'verified':name!='unverified',
   'selected':name==state['selected'],'capabilities':{'receive':True,'transmit':False,'reason':None}})
 return {'schema':'lora.sources.v1','selection':'manual' if state['preferred'] else 'auto',
  'selected_source_id':state['selected'],'preferred_source_id':state['preferred'],'sources':rows}

class H(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(STATIC),**kw)
 def log_message(self,*a):pass
 def reply(self,value):
  b=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  if self.path!='/api/v1/lora/sources/select':self.send_error(404);return
  v=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['source_id'];state['preferred']=v
  if v:state['selected']=v
  self.reply(sources())
 def do_GET(self):
  if self.path=='/api/v1/lora/sources':value=sources()
  elif self.path=='/api/v1/lora/topology':
   if state['fail']:self.send_error(503);return
   key=state['selected'];observer=IDS[2 if key=='a' else 3];gateway='rx-custom-id' if key=='a' else IDS[1]
   reports=[{'label':'现场标签-'+key,'report':{'frame_schema':'LRN1','observer_id':observer,'observer_boot':12,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':1,'neighbors':[{'peer_id':IDS[0],'state':'bidirectional','rssi_dbm':-55,'seen_age_ms':200}]},'pc_receive_age_ms':state['age'],'pc_received_at':'fixture','lora':{'rssi_dbm':-40}}]
   value={'schema':'lora.topology.v1','source_id':key,'source':'fixture_snapshot','receiver':{'mode':'node_serial' if key=='b' else 'gateway','gateway_id':gateway,'gateway_observed':state['available'][key],'state':'receiving' if state['available'][key] else 'unavailable'},'reports':reports}
  elif self.path=='/api/v1/fleet':value={'schema_version':1,'nodes':[{'node_id':1,'mac':IDS[0]},{'node_id':2,'mac':IDS[1]}]}
  elif self.path=='/api/studio/status':value={'mode':'live','fake_gps':False}
  elif self.path=='/api/pc/status':value={'entries':[]}
  elif self.path=='/api/v1/state':value={'gateway_instance':'test','nodes':[],'edges':[]}
  elif self.path.startswith('/api/v1/timeline?'):value={'gateway_instance':'test','events':[],'cursor':0}
  else:return super().do_GET()
  self.reply(value)

server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
results=[]
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
  def wait(expr):page.wait_for_function(expr,timeout=15000)
  def record(name):
   value=page.evaluate("() => ({status:document.querySelector('#sourceStatus').textContent,banner:document.querySelector('#recoveryStatus').textContent,rows:[...document.querySelectorAll('#nodeList .nodeRow')].map(x=>x.textContent),edges:[...document.querySelectorAll('#linkLayer .mapLink')].map(e=>({pair:e.getAttribute('data-pair'),state:e.getAttribute('data-pair-state')}))})")
   (OUT/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');results.append(name);return value
  wait("() => document.querySelector('#sourceStatus').textContent.includes('甲来源') && document.querySelector('#nodeList').textContent.includes('现场标签-a')")
  assert page.locator('#receiverSource option[value=unverified]').evaluate('(e) => e.disabled')
  a=record('01-auto');assert any(x['pair'].endswith('rx-custom-id') for x in a['edges']);assert not any('现场标签-b' in row for row in a['rows'])
  page.select_option('#receiverSource','b')
  wait("() => document.querySelector('#sourceStatus').textContent.includes('手动优先：乙来源') && document.querySelector('#nodeList').textContent.includes('现场标签-b')")
  b=record('02-manual');assert not any('现场标签-a' in row for row in b['rows']);assert '节点 2 串口接收' in b['banner']
  state['available']['b']=False;state['selected']='a'
  wait("() => document.querySelector('#sourceStatus').textContent.includes('当前已回退') && document.querySelector('#nodeList').textContent.includes('现场标签-a')")
  c=record('03-fallback');assert not any('现场标签-b' in row for row in c['rows']);assert page.locator('#receiverSource').input_value()=='b';assert not page.locator('#receiverSource option[value=b]').evaluate('(e) => e.disabled')
  state['available']['b']=True;state['selected']='b'
  wait("() => !document.querySelector('#sourceStatus').textContent.includes('当前已回退') && document.querySelector('#nodeList').textContent.includes('现场标签-b')")
  record('04-recovery')
  state['age']=40000
  wait("() => document.querySelector('#recoveryStatus').textContent.includes('超时未见 1')")
  e=record('05-timeout');assert any(x['state']=='historical' for x in e['edges'])
  state['fail']=True
  wait("() => document.querySelector('#loraTitle').textContent.includes('暂时不可读取')")
  f=record('06-interrupted');assert any('现场标签-b' in row and '观测中断' in row for row in f['rows']);assert all(x['state']=='historical' for x in f['edges'])
  state['fail']=False;state['age']=200
  wait("() => document.querySelector('#recoveryStatus').textContent.includes('在线 1')")
  page.select_option('#receiverSource','');wait("() => document.querySelector('#sourceStatus').textContent.includes('自动选择')")
  record('07-auto-restored');assert not errors,errors
  page.locator('#map').scroll_into_view_if_needed();page.screenshot(path=str(OUT/'07-auto-restored.png'));browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','cases':results,'page_errors':errors,'physical_devices':False},ensure_ascii=False,indent=2),encoding='utf-8')
finally:
 server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
