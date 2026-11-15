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
 pairs=[(i,j) for i in range(n) for j in range(i+1,n) if (state['dense'] or (j==i+1 and (not state.get('clusters') or i not in (9,19,24))))]
 edges=[{'from':IDS[a],'to':IDS[b],'state':'bidirectional','sample_freshness':'fresh','sample_age_ms':10,'rssi_dbm':-50,'mutual_confirmed':True} for a,b in pairs for a,b in [(a,b),(b,a)]]
 
 if state.get('gps'):
  for i,row in enumerate(nodes[:2]):row['position']={'lat':30+i*.0001,'lon':120+i*.0001,'age_ms':0,'source':'gpsd'}
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
  page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));state.update(n=5,dense=False,generation='five');page.goto('http://127.0.0.1:'+str(server.server_port)+'/');page.select_option('#topologySource','wifi')
  wait=lambda expr:page.wait_for_function(expr,timeout=30000)
  wait('() => document.querySelectorAll("#nodeLayer .mapNode").length===5');assert page.locator('#layoutMode').input_value()=='clear';page.locator('#map').screenshot(path=str(OUT/'01-clear-five.png'))
  state.update(n=30,dense=False,clusters=True,generation='clusters');page.click('#refresh');wait('() => document.querySelectorAll("#nodeLayer .mapNode").length===30');page.locator('#map').screenshot(path=str(OUT/'02-clear-clusters.png'))
  coords=page.evaluate("() => Object.fromEntries([...document.querySelectorAll('#nodeLayer .mapNode')].map(e=>[e.dataset.node,[+e.querySelector('circle').getAttribute('cx'),+e.querySelector('circle').getAttribute('cy')]]))")
  results['clusters']={'count':len(coords),'scope':page.locator('#mapScope').inner_text()}
  state.update(dense=False,clusters=False,generation='sparse');page.click('#refresh');wait("() => document.querySelector('#mapScope').textContent.includes('29 对连接')");page.locator('#map').screenshot(path=str(OUT/'02b-clear-sparse.png'))
  state.update(dense=True,generation='dense');page.click('#refresh');wait("() => document.querySelector('#mapScope').textContent.includes('435 对连接')");page.locator('#map').screenshot(path=str(OUT/'03a-clear-dense.png'));page.locator(f'#map .mapNode[data-node="{IDS[0]}"]').click();wait('() => document.querySelectorAll("#linkLayer .mapLink").length===29');page.locator('#map').screenshot(path=str(OUT/'03-clear-dense-focus.png'))
  page.select_option('#layoutMode','manual');page.click('#zoomIn');page.click('#zoomIn')
  page.locator('#map').scroll_into_view_if_needed();box=page.locator('#map').bounding_box();page.mouse.move(box['x']+20,box['y']+20);page.mouse.down();page.mouse.move(box['x']+60,box['y']+35,steps=4);page.mouse.up()
  node=page.locator(f'#map .mapNode[data-node="{IDS[0]}"] circle').first;other=page.locator(f'#map .mapNode[data-node="{IDS[1]}"] circle').first
  before=[float(node.get_attribute('cx')),float(node.get_attribute('cy'))];other_before=[other.get_attribute('cx'),other.get_attribute('cy')]
  pos=node.bounding_box();page.mouse.move(pos['x']+pos['width']/2,pos['y']+pos['height']/2);page.mouse.down();page.mouse.move(pos['x']+pos['width']/2+70,pos['y']+pos['height']/2+35,steps=8);page.mouse.up()
  after=[float(node.get_attribute('cx')),float(node.get_attribute('cy'))];other_after=[other.get_attribute('cx'),other.get_attribute('cy')];assert abs((after[0]-before[0])-70*960/box['width'])<2 and abs((after[1]-before[1])-35*960/box['width'])<2 and other_before==other_after,(before,after,other_before,other_after)
  page.locator('#map').screenshot(path=str(OUT/'04-manual-drag.png'));page.wait_for_timeout(2300);assert [float(node.get_attribute('cx')),float(node.get_attribute('cy'))]==after
  saved_before=page.evaluate("() => Object.entries(localStorage).find(([k])=>k.startsWith('mobile.manual.') && k.includes('wifi'))[1]")
  page.select_option('#layoutMode','clear');page.select_option('#layoutMode','manual');page.reload();wait('() => document.querySelectorAll("#nodeLayer .mapNode").length===30');assert page.locator('#layoutMode').input_value()=='manual'
  stored=page.evaluate("() => Object.fromEntries(Object.entries(localStorage).filter(([k])=>k.startsWith('mobile.manual.')))");assert stored
  # After reload auto-fit may change screen positions; persisted world coordinates are authoritative.
  saved=json.loads(next(v for k,v in stored.items() if 'wifi' in k));assert IDS[0] in saved and saved==json.loads(saved_before)
  oldscreen=[node.get_attribute('cx'),node.get_attribute('cy')];IDS.append('02:00:00:00:00:1f');state['n']=31;page.click('#refresh');wait('() => document.querySelectorAll("#nodeLayer .mapNode").length===31');assert [node.get_attribute('cx'),node.get_attribute('cy')]==oldscreen
  state['n']=30;page.select_option('#layoutMode','gps');state.update(gps=True,generation='gps');page.click('#refresh');wait('() => document.querySelectorAll("#nodeLayer .mapNode").length===2');assert '28 个未定位' in page.locator('#mapScope').inner_text();assert page.locator('#nodeList .nodeRow').count()==30
  page.locator('#map').screenshot(path=str(OUT/'05-gps-partial.png'));page.select_option('#layoutMode','manual');saved2=json.loads(page.evaluate("() => Object.entries(localStorage).find(([k])=>k.startsWith('mobile.manual.') && k.includes('wifi'))[1]"));assert saved2[IDS[0]]==saved[IDS[0]]
  page.click('#resetLayout');reset=json.loads(page.evaluate("() => Object.entries(localStorage).find(([k])=>k.startsWith('mobile.manual.') && k.includes('wifi'))[1]"));assert reset=={}, reset
  # LoRa source A and B have separate manual namespaces and cannot inherit a drag.
  page.select_option('#topologySource','lora');wait("() => document.querySelector('#loraReports').textContent.includes('2 →')");page.locator('#map').scroll_into_view_if_needed();node=page.locator(f'#map .mapNode[data-node="{IDS[0]}"] circle').first;pos=node.bounding_box();page.mouse.move(pos['x']+pos['width']/2,pos['y']+pos['height']/2);page.mouse.down();page.mouse.move(pos['x']+pos['width']/2+45,pos['y']+pos['height']/2+20,steps=5);page.mouse.up()
  a=page.evaluate("() => Object.entries(localStorage).find(([k])=>k.startsWith('mobile.manual.') && JSON.parse(k.slice('mobile.manual.'.length))[1]==='lora' && JSON.parse(k.slice('mobile.manual.'.length))[2]==='a')?.[1]");assert a, (pos,page.evaluate('() => Object.fromEntries(Object.entries(localStorage))'),page.locator('#sourceStatus').inner_text())
  page.select_option('#receiverSource','b');wait("() => document.querySelector('#loraReports').textContent.includes('3 →')");bkey=page.evaluate("() => Object.keys(localStorage).filter(k=>k.startsWith('mobile.manual.') && JSON.parse(k.slice('mobile.manual.'.length))[1]==='lora' && JSON.parse(k.slice('mobile.manual.'.length))[2]==='b')");assert not bkey
  page.select_option('#receiverSource','a');wait("() => document.querySelector('#loraReports').textContent.includes('2 →')");assert page.evaluate("() => Object.entries(localStorage).find(([k])=>k.startsWith('mobile.manual.') && JSON.parse(k.slice('mobile.manual.'.length))[1]==='lora' && JSON.parse(k.slice('mobile.manual.'.length))[2]==='a')[1]")==a
  assert not errors,errors;results.update(manual_drag_screen_before=before,manual_drag_screen_after=after,manual_other_unchanged=True,persisted=True,gps_partial=True,source_isolation=True,reset=True);browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','synthetic':True,'results':results,'page_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
