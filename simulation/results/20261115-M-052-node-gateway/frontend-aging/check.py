import json, os, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT=Path(__file__).resolve().parent
STATIC=Path(r'D:\Multi-Agent Network\.worktrees\production\app\services\assets\mobile_gateway')
IDS=['90:da:72:48:a4:f8','90:da:72:48:a5:cc','90:da:72:48:a4:e0','90:da:72:48:a5:20']
fixture={'mode':'normal'}
class H(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(STATIC),**kw)
 def log_message(self,*a):pass
 def do_GET(self):
  if self.path=='/api/v1/lora/topology':
   if fixture['mode']=='fail':self.send_error(503);return
   if fixture['mode']=='hang':time.sleep(8);self.send_error(503);return
   reports=[]
   for i in (1,2):
    age=40000 if fixture['mode']=='timeout' and i==2 else 34000 if fixture['mode']=='near' and i==2 else 200
    reports.append({'report':{'frame_schema':'LRN1','observer_id':IDS[i],'observer_boot':10+i,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':1,'neighbors':[{'peer_id':IDS[0],'state':'bidirectional','rssi_dbm':-55,'seen_age_ms':200}]},'pc_receive_age_ms':age,'pc_received_at':'fixture','lora':{'rssi_dbm':-40}})
   value={'schema':'lora.topology.v1','source':'lora_received_snapshot','receiver':{'mode':'node_serial','gateway_id':IDS[0],'gateway_observed':fixture['mode']!='disconnected','state':'receiving' if fixture['mode']!='disconnected' else 'unavailable'},'reports':reports}
  elif self.path=='/api/v1/fleet':value={'schema_version':1,'nodes':[{'node_id':i+1,'mac':m} for i,m in enumerate(IDS)]}
  elif self.path=='/api/studio/status':value={'mode':'live','fake_gps':False}
  elif self.path=='/api/pc/status':value={'entries':[]}
  elif self.path=='/api/v1/state':value={'gateway_instance':'test','nodes':[],'edges':[]}
  elif self.path.startswith('/api/v1/timeline?'):value={'gateway_instance':'test','events':[],'cursor':0}
  else:return super().do_GET()
  b=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
  page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('在线 2')",timeout=12000)
  def capture(name):
   data=page.evaluate("() => ({banner:document.querySelector('#recoveryStatus').textContent,rows:[...document.querySelectorAll('#nodeList .nodeRow')].map(x=>x.textContent),edges:[...document.querySelectorAll('#linkLayer .mapLink')].map(e=>({pair:e.getAttribute('data-pair'),state:e.getAttribute('data-pair-state'),stroke:e.getAttribute('stroke')}))})")
   (OUT/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');page.screenshot(path=str(OUT/(name+'.png')));return data
  a=capture('01-normal');assert '从未观测' in ''.join(a['rows']);assert any(x['pair'].startswith('wifi:') for x in a['edges']) and any(x['pair'].startswith('lora:') for x in a['edges'])
  fixture['mode']='timeout';page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('超时未见 1')",timeout=10000);a=capture('02-timeout');assert any('超时未见' in x for x in a['rows']);assert any(x['state']=='historical' for x in a['edges'])
  fixture['mode']='disconnected';page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('观测中断 2')",timeout=10000);a=capture('03-interrupted');assert all(x['state']=='historical' for x in a['edges'])
  fixture['mode']='normal';page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('在线 2')",timeout=10000);capture('04-recovered')
  fixture['mode']='fail';page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('观测中断 2')",timeout=12000);a=capture('05-http-failure');assert len(a['edges'])>0 and all(x['state']=='historical' for x in a['edges']);fixture['mode']='normal'
  page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('在线 2')",timeout=10000);fixture['mode']='near';page.wait_for_function("() => [...document.querySelectorAll('#nodeList .nodeRow')].some(x=>x.textContent.includes('34.0 s'))",timeout=10000);fixture['mode']='hang';page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('超时未见 1')",timeout=5000);capture('06-local-timeout');page.wait_for_function("() => document.querySelector('#recoveryStatus').textContent.includes('观测中断 2')",timeout=12000);capture('07-hung-api-interrupted');assert not errors,errors;browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','cases':['normal','one_timeout','source_interrupted','recovered','api_failure_cached'],'page_errors':errors,'physical_devices':False},indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}))
