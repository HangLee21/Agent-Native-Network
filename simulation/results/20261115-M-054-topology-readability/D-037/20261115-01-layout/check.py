import json, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
STATIC=Path(r'D:\Multi-Agent Network\.worktrees\production\app\services\assets\mobile_gateway')
IDS=[f'02:00:00:00:00:{i:02x}' for i in range(1,31)]
state={'n':5,'dense':True,'generation':'five','offline':None,'selected':'a','epoch':1}
def snap():
 n=state['n'];nodes=[{'node_id':IDS[i],'boot_id':1,'session_id':'x','seq':1,'online':i!=state['offline']} for i in range(n)]
 pairs=[(i,j) for i in range(n) for j in range(i+1,n) if state['dense'] or j==i+1]
 edges=[{'from':IDS[a],'to':IDS[b],'state':'bidirectional','sample_freshness':'fresh','sample_age_ms':10,'rssi_dbm':-50,'mutual_confirmed':True} for a,b in pairs for a,b in [(a,b),(b,a)]]
 return {'gateway_instance':state['generation'],'nodes':nodes,'edges':edges,'offline_after_ms':30000,'stale_after_ms':30000}
def source_list():
 return {'schema':'lora.sources.v1','selection':'manual','preferred_source_id':state['selected'],'selected_source_id':state['selected'],'selection_epoch':state['epoch'],'sources':[{'id':k,'kind':'serial','label':k,'available':True,'verified':True,'state':'receiving','selected':k==state['selected'],'capabilities':{'receive':True,'transmit':False,'reason':None}} for k in ('a','b')]}
class H(SimpleHTTPRequestHandler):
 def __init__(self,*a,**kw):super().__init__(*a,directory=str(STATIC),**kw)
 def log_message(self,*a):pass
 def reply(self,v):
  b=json.dumps(v).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
 def do_POST(self):
  if self.path!='/api/v1/lora/sources/select':return self.send_error(404)
  v=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['source_id'];state['selected']=v or 'a';state['epoch']+=1;self.reply(source_list())
 def do_GET(self):
  p=self.path.split('?')[0]
  if p=='/api/v1/fleet':v={'schema_version':1,'nodes':[{'node_id':i+1,'mac':m} for i,m in enumerate(IDS)]}
  elif p=='/api/v1/state':v=snap()
  elif p=='/api/v1/timeline':v={'gateway_instance':state['generation'],'events':[],'cursor':0}
  elif p=='/api/v1/lora/sources':v=source_list()
  elif p=='/api/v1/lora/topology':
   k=state['selected'];idx=0 if k=='a' else 1
   v={'schema':'lora.topology.v1','source_id':k,'selection_epoch':state['epoch'],'source':'synthetic','receiver':{'gateway_id':IDS[0],'gateway_observed':True,'state':'receiving'},'reports':[{'label':'仅来源-'+k,'report':{'frame_schema':'LRN1','observer_id':IDS[idx+1],'observer_boot':1,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':100}]}
  elif p=='/api/studio/status':v={'mode':'live','fake_gps':False}
  elif p=='/api/pc/status':v={'entries':[]}
  else:return super().do_GET()
  self.reply(v)

server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();results={}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  errors=[]
  def openpage(width=1440):
   p=browser.new_page(viewport={'width':width,'height':900});p.on('pageerror',lambda e:errors.append(str(e)));p.goto('http://127.0.0.1:'+str(server.server_port)+'/');p.select_option('#topologySource','wifi');return p
  def wait_nodes(p,n):p.wait_for_function('(n) => document.querySelectorAll("#nodeLayer .mapNode").length===n',arg=n,timeout=25000)
  def record(p,name):
   d=p.evaluate('''() => ({viewport:[innerWidth,innerHeight],nodes:document.querySelectorAll('#nodeLayer .mapNode').length,edges:document.querySelectorAll('#linkLayer .mapLink').length,edgeLabels:document.querySelectorAll('#linkLayer .edgeAgeLabel').length,nodeTexts:document.querySelectorAll('#nodeLayer text').length,scope:document.querySelector('#mapScope').textContent,rows:[...document.querySelectorAll('#nodeList .nodeRow')].filter(x=>!x.hidden).length})''');results[name]=d;p.locator('#map').screenshot(path=str(OUT/(name+'.png')));return d
  p=openpage();wait_nodes(p,5);d=record(p,'01-five');assert d['edges']==10 and d['edgeLabels']==0
  p.close();state.update(n=30,dense=False,generation='sparse',offline=4)
  p=openpage();wait_nodes(p,30);d=record(p,'02-sparse');assert d['edges']==29 and d['nodes']==30 and d['nodeTexts']<=32
  p.select_option('#nodeFilter','problem');assert p.locator('#nodeList .nodeRow:visible').count()==1
  p.click('#clearNodeFilter');p.fill('#nodeSearch',IDS[9]);assert p.locator('#nodeList .nodeRow:visible').count()==1
  p.click('#clearNodeFilter');assert p.locator('#nodeList .nodeRow:visible').count()==30
  p.close();state.update(n=30,dense=True,generation='dense',offline=4)
  p=openpage();wait_nodes(p,30);d=record(p,'03-dense-overview');assert d['edges']==0 and '435 对连接' in d['scope'] and '隐藏不代表不存在' in d['scope']
  p.locator(f'#map .mapNode[data-node="{IDS[0]}"]').click();d=record(p,'04-dense-focused');assert d['edges']==29
  ms=p.evaluate("() => {let t=performance.now(),s=document.querySelector('#edgeMode');s.value='all';s.dispatchEvent(new Event('change'));return performance.now()-t}")
  d=record(p,'05-dense-all');d['switch_to_all_ms']=round(ms,2);assert d['edges']==435 and d['edgeLabels']==0
  p.close();state.update(n=29,dense=False,generation='dynamic',offline=None)
  p=openpage();wait_nodes(p,29);before=p.locator(f'#map .mapNode[data-node="{IDS[0]}"] circle').first.get_attribute('cx');state.update(n=30,offline=3)
  p.click('#refresh');wait_nodes(p,30);after=p.locator(f'#map .mapNode[data-node="{IDS[0]}"] circle').first.get_attribute('cx');assert before==after,(before,after)
  p.wait_for_function("() => document.querySelectorAll('#nodeList .pill.off').length===1",timeout=15000);record(p,'06-dynamic')
  p.select_option('#topologySource','lora');p.wait_for_function("() => document.querySelector('#loraReports').textContent.includes('2 →')",timeout=15000)
  p.select_option('#receiverSource','b');p.wait_for_function("() => document.querySelector('#loraReports').textContent.includes('3 →')",timeout=15000)
  assert '2 →' not in p.locator('#loraReports').inner_text();results['source_switch']='passed';p.close()
  state.update(n=30,dense=True,generation='narrow',offline=4);p=openpage(700);wait_nodes(p,30);d=record(p,'07-narrow');assert d['edges']==0 and d['nodes']==30
  assert not errors,errors;p.close();browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','synthetic':True,'cases':results,'page_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
