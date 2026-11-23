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
  def page_for(dense):
   state.update(n=30,dense=dense,generation='dense' if dense else 'sparse',offline=None)
   page=browser.new_page(viewport={'width':1440,'height':900});page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(server.server_port)+'/');page.select_option('#topologySource','wifi')
   page.wait_for_function('() => document.querySelectorAll("#nodeLayer .mapNode").length===30',timeout=30000);return page
  page=page_for(True);page.locator(f'#map .mapNode[data-node="{IDS[0]}"]').click();page.wait_for_function('() => document.querySelectorAll("#linkLayer .mapLink").length===29',timeout=30000)
  page.locator('#map').screenshot(path=str(OUT/'dense-focused.png'))
  geometry=page.evaluate("""() => {const nodes=[...document.querySelectorAll('#nodeLayer .mapNode')].map(g=>({id:g.dataset.node,x:+g.querySelector('circle').getAttribute('cx'),y:+g.querySelector('circle').getAttribute('cy')}));return [...document.querySelectorAll('#linkLayer .mapLink')].map(e=>{const ids=e.dataset.pair.split('/');let hits=[];for(let i=1;i<40;i++){const p=e.getPointAtLength(e.getTotalLength()*i/40);for(const n of nodes)if(!ids.includes(n.id)&&Math.hypot(p.x-n.x,p.y-n.y)<25)hits.push(n.id)}return{pair:e.dataset.pair,path:e.getAttribute('d'),collisions:[...new Set(hits)]}})}""")
  results['focused']={'nodes':30,'edges':len(geometry),'collisions':{x['pair']:x['collisions'] for x in geometry if x['collisions']},'paths':geometry};assert not results['focused']['collisions'],results['focused']['collisions']
  for other in [1,5,6,24]:
   page.locator(f'#map .mapNode[data-node="{IDS[0]}"]').click();pair=IDS[0]+'/'+IDS[other]
   point=page.evaluate("""pair => {const p=document.querySelector('[data-pair="'+pair+'"]');const matrix=p.getScreenCTM(),len=p.getTotalLength();for(let i=5;i<36;i++){let pt=p.getPointAtLength(len*i/40).matrixTransform(matrix),hit=document.elementFromPoint(pt.x,pt.y);if(hit===p||hit?.dataset.hitPair===pair)return {x:pt.x,y:pt.y}}return null}""",pair)
   assert point is not None,('no clickable segment',pair);page.mouse.click(point['x'],point['y']);assert page.locator('#edgeDetail').inner_text().find('RSSI')>=0
   assert page.locator(f'#linkLayer .mapLink[data-pair="{pair}"]').get_attribute('stroke-width')=='4'
  results['same_row_and_column_clicks']='passed';page.close()
  page=page_for(False);page.wait_for_function('() => document.querySelectorAll("#linkLayer .mapLink").length===29',timeout=30000);page.locator('#map').screenshot(path=str(OUT/'sparse.png'))
  sparse=page.evaluate("""() => {const nodes=[...document.querySelectorAll('#nodeLayer .mapNode')].map(g=>({id:g.dataset.node,x:+g.querySelector('circle').getAttribute('cx'),y:+g.querySelector('circle').getAttribute('cy')}));return [...document.querySelectorAll('#linkLayer .mapLink')].map(e=>{const ids=e.dataset.pair.split('/');let hits=[];for(let i=1;i<40;i++){const p=e.getPointAtLength(e.getTotalLength()*i/40);for(const n of nodes)if(!ids.includes(n.id)&&Math.hypot(p.x-n.x,p.y-n.y)<25)hits.push(n.id)}return{pair:e.dataset.pair,collisions:[...new Set(hits)]}})}""")
  results['sparse']={'edges':len(sparse),'collisions':{x['pair']:x['collisions'] for x in sparse if x['collisions']}};assert not results['sparse']['collisions'],results['sparse']['collisions'];assert not errors,errors;page.close();browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','synthetic':True,'cases':results,'page_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
