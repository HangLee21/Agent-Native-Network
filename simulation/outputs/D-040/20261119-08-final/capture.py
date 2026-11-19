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
  page=browser.new_page(viewport={'width':1440,'height':900},locale='zh-CN');errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(url);page.locator(f'#replaySessions option[value="{session}"]').wait_for(state='attached',timeout=15000)
  page.select_option('#replaySessions',session);page.click('#replayOpen');page.wait_for_function("() => +document.querySelector('#replayTime').max>=42")
  page.locator('#replayTime').evaluate("e=>{e.value='42';e.dispatchEvent(new Event('input'))}")
  page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('第 43 /')")
  page.select_option('#layoutMode','clear');page.select_option('#edgeMode','all')
  page.locator('#map').screenshot(path=str(OUT/'history-map.png'))
  result=page.evaluate("() => ({scope:document.querySelector('#mapScope').textContent,status:document.querySelector('#replayStatus').textContent,nodes:document.querySelectorAll('#nodeLayer .mapNode').length,paths:[...document.querySelectorAll('#linkLayer .mapLink')].map(e=>({pair:e.dataset.pair,state:e.dataset.pairState,d:e.getAttribute('d')}))})")
  assert not errors,errors;result.update(session=session,frame=42,errors=errors,source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest())
  (OUT/'BROWSER.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');browser.close()
finally:
 (OUT/'stop').touch()
 try:process.wait(timeout=8)
 except subprocess.TimeoutExpired:process.terminate();process.wait(timeout=5)
 (OUT/'PROCESS_END.json').write_text(json.dumps({'studio_exit':process.returncode}),encoding='utf-8')
