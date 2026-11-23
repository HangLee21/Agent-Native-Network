import json, sys, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT=Path(__file__).resolve().parent
ROOT=Path(r'D:\Multi-Agent Network\.worktrees\production\app\services')
sys.path.insert(0,str(ROOT))
from tools.mobile_gateway.studio import StudioHandler, Gateway
from tools.mobile_gateway.sources import Sources

IDS=['90:da:72:48:a4:f8','90:da:72:48:a5:cc','90:da:72:48:a4:e0','90:da:72:48:a5:20']
class FakeAdapter:
 def __init__(self,i):self.i=i
 def topology(self):
  i=self.i
  return {'schema':'lora.topology.v1','source':'fixture','receiver':{'mode':'node_serial','gateway_id':IDS[i],'gateway_observed':True,'state':'receiving','identity_verified':True},
   'reports':[{'label':'报告-'+str(i),'report':{'frame_schema':'LRN1','observer_id':IDS[i+2],'observer_boot':1,'report_seq':7,'snapshot_at_ms':100,'report_period_ms':10000,'total_rows':0,'neighbors':[]},'pc_receive_age_ms':200,'lora':{'rssi_dbm':-40}}],
   'control':{'enabled':False}}

sources=Sources(start=False);sources.add('serial',FakeAdapter(0),'甲来源');sources.add('http',FakeAdapter(1),'乙来源')
race={'armed':False,'fired':False}
class TopologyProxy:
 def topology(self):
  data=sources.topology()
  if race['armed']:
   race['armed']=False;race['fired']=True
   old=data['source_id'];other='serial:configured' if old=='http:configured' else 'http:configured'
   data['reports'][0]['label']='旧快照禁止显示';sources.select(other);sources.select(old)
  return data
class H(StudioHandler):
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/api/v1/fleet':return self.reply(200,{'schema_version':1,'nodes':[{'node_id':1,'mac':IDS[0]},{'node_id':2,'mac':IDS[1]}]})
  if path=='/api/studio/status':return self.reply(200,{'mode':'live','fake_gps':False})
  if path=='/api/pc/status':return self.reply(200,{'entries':[]})
  if path=='/api/v1/state':return self.reply(200,{'gateway_instance':'test','nodes':[],'edges':[]})
  if path=='/api/v1/timeline':return self.reply(200,{'gateway_instance':'test','events':[],'cursor':0})
  return super().do_GET()
server=Gateway(('127.0.0.1',0),None,ROOT/'assets/mobile_gateway');server.RequestHandlerClass=H;server.sources=sources;server.remote=TopologyProxy();server.serial=None
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(headless=True,executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',args=['--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
  page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:'+str(server.server_port)+'/')
  page.wait_for_function("() => document.querySelector('#nodeList').textContent.includes('报告-1')",timeout=15000)
  initial=sources.sources();assert initial['selected_source_id']=='http:configured'
  page.select_option('#receiverSource','serial:configured')
  page.wait_for_function("() => document.querySelector('#nodeList').textContent.includes('报告-0')",timeout=15000)
  assert not page.locator('#nodeList').inner_text().find('报告-1')>=0
  epoch=sources.sources()['selection_epoch'];race['armed']=True
  page.wait_for_function("() => document.querySelector('#loraNote').textContent.includes('来源读取期间发生切换')",timeout=15000)
  assert race['fired'] and sources.sources()['selection_epoch']==epoch+2
  assert '旧快照禁止显示' not in page.locator('#nodeList').inner_text()
  page.wait_for_function("() => document.querySelector('#nodeList').textContent.includes('报告-0') && !document.querySelector('#loraNote').textContent.includes('来源读取期间发生切换')",timeout=15000)
  assert not errors,errors
  page.screenshot(path=str(OUT/'browser.png'));browser.close()
  (OUT/'RESULT.json').write_text(json.dumps({'status':'passed','cases':['real_e2_source_manager_and_http_handlers','manual_switch','aba_epoch_reject','recovery'],'epoch_before':epoch,'epoch_after':sources.sources()['selection_epoch'],'page_errors':errors,'physical_devices':False},ensure_ascii=False,indent=2),encoding='utf-8')
finally:
 server.shutdown();server.server_close();thread.join();sources.close();(OUT/'PROCESS_END.json').write_text(json.dumps({'server_thread_stopped':not thread.is_alive()}),encoding='utf-8')
