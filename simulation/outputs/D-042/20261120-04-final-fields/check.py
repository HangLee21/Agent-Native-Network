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
    row={'peer_id':IDS[0],'state':'lost' if i==45 else 'bidirectional' if i<31 else 'heard','seen_age_ms':100,'ack_age_ms':200,'rf_age_ms':300,'rssi_dbm':-55,'wifi_channel':6,'valid':0 if i==3 else 15}
    report={'frame_schema':'LRN1','observer_id':IDS[1],'observer_boot':1,'report_seq':i+1,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':1,'neighbors':([] if i==40 else [row]),'truncated':i==40,'status':{'reset_reason':1,'heap_free_kb':42,'supply_mv':0,'lora_sf':0,'lora_tx_power_dbm':0},'status_age_ms':1200,'gps_age_ms':900,'wifi_channel':11,'gps':{'valid':True,'lat_e7':300000000,'lon_e7':1200000000}}
    frames.append({'t_ms':1700000000000+i*1000,'topology':{'schema':'lora.topology.v1','source':'synthetic','source_id':'a','selection_epoch':1,'receiver':{'gateway_id':IDS[2] if i==45 else IDS[0],'gateway_observed':i!=20,'state':'unavailable' if i==20 else 'receiving','recent_threshold_ms':30000},'reports':[{'report':report,'gateway_boot':0,'pc_receive_age_ms':31000 if i==10 else 100,'uplink_quality':{'samples':20,'sequence_span':25,'observed_fraction':0.8,'last_interval_ms':1000,'max_interval_ms':2000},'lora':{'rssi':-45,'lsnr':10.8,'chan':5,'freq':470.5}}]}})
    if i==4:
     row.pop('valid',None);row.pop('wifi_channel',None);row['channel']=11
    frames[-1]['topology']['receiver']['mode']='node_serial' if i==2 else 'legacy_local'
    variants=[{'datr':'SF7BW125','codr':'4/5','rfch':0,'rssi':-45,'lsnr':10.8,'chan':5,'freq':470.5},{'datarate':'SF7BW125','coding_rate':'4/5','rf_chain':0,'rssi_dbm':-45,'snr_db':10.8,'channel':5,'frequency_hz':470500000},{'sf':7,'bandwidth_hz':125000,'coding_rate':5,'rssi_dbm':-45,'snr_db':10.8,'frequency_hz':470500000},{'datr':'invalid','rssi_dbm':-45}]
    frames[-1]['topology']['reports'][0]['lora']=variants[min(i,3)]
    for extra in IDS[2:]:
     frames[-1]['topology']['reports'].append({'report':{'frame_schema':'LRN1','observer_id':extra,'observer_boot':1,'report_seq':i+1,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':100,'lora':{'rssi_dbm':-55}})
   v={'id':'test','offset':offset,'total':65,'frames':frames}
  elif p=='/api/v1/fleet':v={'schema_version':1,'nodes':[{'node_id':i+1,'mac':m} for i,m in enumerate(IDS)]}
  elif p=='/api/v1/state':v=snap()
  elif p=='/api/v1/timeline':v={'gateway_instance':state['generation'],'events':[],'cursor':0}
  elif p=='/api/v1/lora/sources':v=source_list()
  elif p=='/api/v1/lora/topology':
   k=state['selected'];idx=0 if k=='a' else 1
   v={'schema':'lora.topology.v1','source_id':k,'selection_epoch':state['epoch'],'source':'synthetic','receiver':{'gateway_id':IDS[0],'gateway_observed':True,'state':'receiving'},'reports':[{'label':'仅来源-'+k,'report':{'frame_schema':'LRN1','observer_id':IDS[idx+1],'observer_boot':1,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':100,'lora':{'rssi':-61,'lsnr':4.5,'chan':3,'freq':433.775}}]}
  elif p=='/api/studio/status':v={'mode':'live','fake_gps':False}
  elif p=='/api/pc/status':v={'entries':[]}
  else:return super().do_GET()
  self.reply(v)

server=ThreadingHTTPServer(('127.0.0.1',0),H);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();results={}
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  page=browser.new_page(viewport={'width':1366,'height':768});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));page.goto('http://127.0.0.1:'+str(server.server_port)+'/');page.wait_for_function("() => document.querySelector('#replaySessions').options.length>1",timeout=15000)
  page.locator('.recordTools > summary').click();page.select_option('#replaySessions','test');page.click('#replayOpen');page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('历史观测')");page.locator('.recordTools > summary').click()
  page.get_by_text('逐方向无线记录',exact=True).first.click()
  def frame(i):
   page.locator('#replayTime').evaluate('(e,i)=>{e.value=String(i);e.dispatchEvent(new Event("input"))}',i)
   page.wait_for_function('(i)=>document.querySelector("#replayStatus").textContent.includes("第 "+(i+1)+" / ")',arg=i,timeout=15000)
   page.locator('#directions button').first.click();return page.locator('#uplinkSummary').inner_text(),page.locator('#edgeDetail').inner_text()
  for index,name in [(0,'direct'),(1,'legacy'),(2,'serial'),(3,'invalid')]:
   summary,detail=frame(index);results[name]={'summary':summary,'detail':detail}
   if index<3:assert 'SF7' in summary and '125 kHz' in summary and '编码率 4/5' in detail,(name,summary,detail)
   if index<2:assert '网关逐帧元数据' in detail and '上行数据率 SF7BW125' in detail and 'RF 接收链 0' in detail and 'Wi-Fi 信道：6' in detail,(name,detail)
   if index==2:assert '接收节点配置' in detail and '接收节点配置' in summary and '上行数据率 未提供' in detail and 'RF 接收链 未提供' in detail,(summary,detail)
   if index==3:assert '扩频因子\n未提供' in summary and '编码率 未提供' in detail and 'Wi-Fi 信道：未提供' in detail and 'Wi-Fi RSSI：未提供' in detail and 'ACK 年龄：未知' in detail and 'RF 帧年龄：未知' in detail and '-55 → -55 → -55 → -55' not in detail,(summary,detail)
  _,old=frame(4);assert 'Wi-Fi 信道：11' in old,old
  frame(0);page.locator(f'#nodeList .nodeRow[data-id="{IDS[1]}"]').click();node=page.locator('#detail').inner_text();assert '节点 SF 未采集' in node and '节点发射功率 未采集' in node and '状态块年龄 1.2 s' in node,node
  page.locator('#uplinkSummary').screenshot(path=str(OUT/'summary.png'));page.locator('#edgeDetail').screenshot(path=str(OUT/'edge.png'));assert not errors,errors;browser.close()
 (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','synthetic':True,'cases':results,'node':node,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
finally:server.shutdown();server.server_close();thread.join();(OUT/'PROCESS_END.json').write_text(json.dumps({'fixture_thread_stopped':not thread.is_alive()}),encoding='utf-8')
