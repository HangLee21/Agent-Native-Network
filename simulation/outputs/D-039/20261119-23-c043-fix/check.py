import json, threading, time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
STATIC=Path(r'D:\Multi-Agent Network\research\agent_native_network\mobile_gateway')
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
  if self.path in ('/api/v1/replay/start','/api/v1/replay/stop'):
   state['active']=self.path.endswith('start');return self.reply({'id':'test'})
  if self.path!='/api/v1/lora/sources/select':return self.send_error(404)
  v=json.loads(self.rfile.read(int(self.headers['Content-Length'])))['source_id'];state['selected']=v or 'a';state['epoch']+=1;self.reply(source_list())
 def do_GET(self):
  p=self.path.split('?')[0]
  if p=='/api/v1/replay/sessions':v={'sessions':[{'id':'test','started_ms':1700000000000,'active':state.get('active',False),'count':65}],'active_id':'test' if state.get('active') else None,'error':state.get('error')}
  elif p=='/api/v1/replay/session':
   from urllib.parse import parse_qs,urlsplit
   q=parse_qs(urlsplit(self.path).query);offset=int(q['offset'][0]);limit=int(q['limit'][0]);state.setdefault('requests',[]).append((offset,limit))
   frames=[]
   for i in range(offset,min(offset+limit,65)):
    row={'peer_id':IDS[0],'state':'bidirectional' if i==1 else 'heard' if i==2 else 'lost','seen_age_ms':100,'ack_age_ms':200,'rf_age_ms':300,'rssi_dbm':-55}
    report={'frame_schema':'LRN1','observer_id':IDS[1],'observer_boot':1,'report_seq':i+1,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':1,'neighbors':([] if i==4 else [row]),'truncated':i==4,'status':{'reset_reason':1,'heap_free_kb':42,'supply_mv':0},'status_age_ms':1200,'gps_age_ms':900,'gps':{'valid':True,'lat_e7':300000000,'lon_e7':1200000000}}
    frames.append({'t_ms':1700000000000+i*1000,'topology':{'schema':'lora.topology.v1','source':'synthetic','source_id':'a','selection_epoch':1,'receiver':{'gateway_id':IDS[2],'gateway_observed':True,'state':'receiving','recent_threshold_ms':30000},'reports':[{'report':report,'pc_receive_age_ms':100,'uplink_quality':{'samples':20,'sequence_span':25,'observed_fraction':0.8,'last_interval_ms':1000,'max_interval_ms':2000},'lora':{'rssi_dbm':-45,'snr_db':7,'channel':2}}]}})
    reverse={'frame_schema':'LRN1','observer_id':IDS[0],'observer_boot':2,'report_seq':i+1,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':1,'neighbors':[{'peer_id':IDS[1],'state':'bidirectional' if i in (1,2) else 'lost','seen_age_ms':100,'ack_age_ms':200,'rf_age_ms':300,'rssi_dbm':-54}]}
    frames[-1]['topology']['reports'].append({'report':reverse,'pc_receive_age_ms':100,'lora':{'rssi_dbm':-40}})
    for extra in IDS[3:]:
     frames[-1]['topology']['reports'].append({'report':{'frame_schema':'LRN1','observer_id':extra,'observer_boot':1,'report_seq':i+1,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':100,'lora':{'rssi_dbm':-55}})
   v={'id':'test','offset':offset,'total':65,'frames':frames}
  elif p=='/api/v1/fleet':v={'schema_version':1,'nodes':[{'node_id':i+1,'mac':m} for i,m in enumerate(IDS)]}
  elif p=='/api/v1/state':
   if state.get('block'):
    state['entered'].set();state['release'].wait(10)
   v=snap();v['now_ms']=1700000000000
  elif p=='/api/v1/timeline':
   events=[{'cursor':1,'type':'route_selected','node_id':IDS[1],'received_ms':1700000000000,'data':{'origin':IDS[1],'origin_boot':9,'seq':1,'dst':IDS[0],'path':[IDS[1],IDS[0]]}}, {'cursor':2,'type':'tx_submit','node_id':IDS[1],'received_ms':1700000000000,'data':{'origin':IDS[1],'origin_boot':9,'seq':1,'dst':IDS[0],'next_hop':IDS[0]}}]
   events.append({'cursor':3,'type':'rx_local','node_id':IDS[0],'received_ms':1700000000000,'data':{'origin':IDS[1],'origin_boot':9,'seq':1,'dst':IDS[0],'previous_hop':IDS[1],'payload_hex':'ab'}})
   v={'gateway_instance':state['generation'],'events':events,'cursor':3}
  elif p=='/api/v1/lora/sources':v=source_list()
  elif p=='/api/v1/lora/topology':
   k=state['selected'];idx=0 if k=='a' else 1
   v={'schema':'lora.topology.v1','source_id':k,'selection_epoch':state['epoch'],'source':'synthetic','receiver':{'gateway_id':IDS[0],'gateway_observed':True,'state':'receiving'},'reports':[{'label':'仅来源-'+k,'report':{'frame_schema':'LRN1','observer_id':IDS[idx+1],'observer_boot':1,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':100}]}
  elif p=='/api/studio/status':v={'mode':'live','fake_gps':False}
  elif p=='/api/pc/status':v={'entries':[]}
  else:return super().do_GET()
  self.reply(v)

state.update(n=5,dense=False,generation='live',entered=threading.Event(),release=threading.Event())
server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  page=browser.new_page(viewport={'width':1440,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
  page.wait_for_function("() => document.querySelector('#packetList .packetRow') && document.querySelector('#nodeLayer').textContent.includes('TX 提交') && document.querySelector('#nodeLayer').textContent.includes('RX 收到')",timeout=20000)
  page.evaluate("id=>{window.MobileStudio.pc={entries:[{node_id:id,connected:true}]};document.querySelector('#packetOverlay').checked=true;document.querySelector('#packetOverlay').dispatchEvent(new Event('change'));}",IDS[1])
  page.click('#refresh');page.wait_for_function("() => document.querySelector('#packetLayer').children.length>0 && document.querySelector('#nodeLayer').textContent.includes('热点 IP 入口') && document.querySelector('#nodeLayer').textContent.includes('RX 收到')",timeout=20000)
  page.locator('#map').screenshot(path=str(OUT/'01-live.png'))
  state['block']=True;page.click('#refresh');assert state['entered'].wait(8)
  page.select_option('#replaySessions','test');page.click('#replayOpen');page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('历史观测')",timeout=15000)
  state['block']=False;state['release'].set();page.wait_for_timeout(1200)
  def assert_history():
   assert page.locator('#packetLayer').locator('*').count()==0
   text=page.locator('#nodeLayer').text_content();assert 'TX 提交' not in text and 'RX 收到' not in text and '热点 IP 入口' not in text
  assert_history();pair='wifi:'+IDS[0]+'/'+IDS[1]
  def state_at(index,expected):
   if index:page.select_option('#replayEvents',str(index))
   page.wait_for_function("([pair,state]) => document.querySelector('[data-pair=\"'+pair+'\"]')?.getAttribute('data-pair-state')===state",arg=[pair,expected],timeout=15000)
   assert_history();page.locator('#map').screenshot(path=str(OUT/('state-'+expected+'.png')))
  page.click('#replayIndex');page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('事件索引完成')",timeout=15000)
  values=page.locator('#replayEvents option').evaluate_all('es=>es.map(e=>e.value)');assert all(str(x) in values for x in (1,2,3)) and '4' not in values and '5' not in values,values
  state_at(1,'mutual');state_at(2,'partial');state_at(3,'lost');page.click('#replayLive')
  page.wait_for_function("() => document.querySelector('#packetLayer').children.length>0 && document.querySelector('#nodeLayer').textContent.includes('TX 提交') && document.querySelector('#nodeLayer').textContent.includes('热点 IP 入口') && document.querySelector('#nodeLayer').textContent.includes('RX 收到')",timeout=20000)
  assert not errors,errors;browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','synthetic':True,'cases':['live_overlay_present','inflight_live_response_isolated','mutual_partial_lost_event_navigation','truncated_absence_no_event','return_live_restores_overlay'],'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:state['release'].set();server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
