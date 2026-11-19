import hashlib,json,shutil,socket,subprocess,sys,time,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path.cwd();OUT=Path(__file__).resolve().parent
SOURCE=ROOT/'simulation/results/20261119-M058-studio-replay/historical-controlled.sqlite3'
db=OUT/'history.sqlite3';shutil.copy2(SOURCE,db)
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
studio,pc,topo=port(),port(),port()
cmd=[sys.executable,'-X','utf8','-m','tools.mobile_gateway.studio','--port',str(studio),'--pc-port',str(pc),'--topology-port',str(topo),'--output',str(OUT/'studio'),'--replay-db',str(db),'--stop-file',str(OUT/'stop')]
with (OUT/'studio.log').open('wb') as log:
 process=subprocess.Popen(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
try:
 url=f'http://127.0.0.1:{studio}'
 for _ in range(60):
  if process.poll() is not None:raise RuntimeError('studio exited')
  try:
   with urllib.request.urlopen(url+'/api/v1/replay/sessions',timeout=1) as r:sessions=json.load(r)
   break
  except OSError:time.sleep(.2)
 else:raise RuntimeError('studio failed to start')
 session=sessions['sessions'][0]['id']
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe',headless=True)
  page=browser.new_page(viewport={'width':1366,'height':768},locale='zh-CN');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(url);page.locator(f'#replaySessions option[value="{session}"]').wait_for(state='attached',timeout=15000)
  page.screenshot(path=str(OUT/'live.png'));assert '实时' in page.locator('#contextMode').inner_text()
  page.locator('.recordTools > summary').click();page.select_option('#replaySessions',session);page.click('#replayOpen');page.wait_for_function("() => +document.querySelector('#replayTime').max>=42")
  page.locator('#replayTime').evaluate("e=>{e.value='42';e.dispatchEvent(new Event('input'))}")
  page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('第 43 /')")
  page.locator('.recordTools > summary').click();page.select_option('#layoutMode','clear');page.select_option('#edgeMode','all')
  assert '历史' in page.locator('#contextMode').inner_text();rect=page.locator('#map').bounding_box();timeline=page.locator('#replayPanel').bounding_box();assert rect['y']<=220 and timeline['y']+timeline['height']<=768,(rect,timeline);assert 'MHz' in page.locator('#uplinkSummary').inner_text() and '接收信号' in page.locator('#uplinkSummary').inner_text();history_summary=page.locator('#uplinkSummary').inner_text();page.screenshot(path=str(OUT/'history.png'));page.locator('#map').screenshot(path=str(OUT/'history-map.png'))
  page.evaluate('window.scrollTo(0,document.body.scrollHeight)');assert page.locator('#replayLive').is_visible();assert page.locator('header').bounding_box()['y']>=0;page.click('#replayLive');page.wait_for_function("() => document.querySelector('#contextMode').textContent.includes('实时')");page.evaluate('window.scrollTo(0,0)')
  result=page.evaluate("() => ({scope:document.querySelector('#mapScope').textContent,status:document.querySelector('#replayStatus').textContent,nodes:document.querySelectorAll('#nodeLayer .mapNode').length,paths:[...document.querySelectorAll('#linkLayer .mapLink')].map(e=>({pair:e.dataset.pair,state:e.dataset.pairState,d:e.getAttribute('d')}))})")
  assert not errors,errors;result.update(map_rect=rect,time_rect=timeline,historical_summary=history_summary,session=session,frame=42,errors=errors,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest())
  (OUT/'BROWSER.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
finally:
 (OUT/'stop').touch()
 try:process.wait(timeout=8)
 except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
 (OUT/'PROCESS_END.json').write_text(json.dumps({'studio_exit':process.returncode}),encoding='utf-8')
