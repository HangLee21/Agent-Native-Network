"""Open an archived recording through the normal Studio UI on isolated local ports."""
from pathlib import Path
import importlib.util,json,shutil,socket,sys,time
from playwright.sync_api import sync_playwright

root=Path.cwd()
here=Path(__file__).resolve().parent
source=root/'simulation/outputs/M-058/20261119074002Z-delivery/capture'
spec=importlib.util.spec_from_file_location('capture',source/'acceptance.py')
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
c.HERE=here
rid=json.loads((source/'ACCEPTANCE.json').read_text())['endpoint']
db=here/'recording.sqlite3'
shutil.copy2(source/'recording.sqlite3',db)
port=c.unused(socket.SOCK_STREAM)
try:
    c.launch('browser-studio','tools.mobile_gateway.studio','--port',port,'--pc-port',c.unused(socket.SOCK_STREAM),'--topology-port',c.unused(socket.SOCK_STREAM),'--output',here/'studio','--replay-db',db,'--stop-file',here/'stop')
    c.ready(port,'/api/v1/replay/sessions')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe',headless=True)
        page=browser.new_page(viewport={'width':1440,'height':900},locale='zh-CN')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto('http://127.0.0.1:%d/'%port)
        page.locator('#replaySessions option[value="%s"]'%rid).wait_for(state='attached',timeout=10000)
        page.locator('#replaySessions').select_option(rid)
        page.locator('#replayOpen').click()
        page.wait_for_function("Number(document.getElementById('replayTime').max)>40")
        page.locator('#replayIndex').click()
        page.wait_for_function("document.getElementById('replayEvents').options.length > 1")
        labels=page.locator('#replayEvents option').all_text_contents()
        choices=page.locator('#replayEvents option').evaluate_all('(opts)=>opts.map(o=>[o.value,o.textContent])')
        stale=next((x for x in choices if '超时' in x[1] and 'a4:e0' in x[1]),None)
        back=next((x for x in choices if '报告恢复' in x[1] and 'a4:e0' in x[1]),None)
        assert stale and back and int(back[0])>int(stale[0]),choices
        # Compare the visible timeout instant against the age and threshold from the recorded data.
        import sqlite3,zlib
        with sqlite3.connect(db) as history:
            payloads=history.execute('SELECT topology FROM frames WHERE session_id=? ORDER BY rowid',(rid,)).fetchall()
        expected=None
        for i,(encoded,) in enumerate(payloads):
            snap=json.loads(zlib.decompress(encoded))
            threshold=snap['receiver'].get('recent_threshold_ms',30000)
            if snap['receiver'].get('gateway_observed') and any(r.get('pc_receive_age_ms',0)>threshold for r in snap.get('reports',[])):
                expected=i
                break
        assert expected is not None and int(stale[0])==expected,(stale,expected,choices)
        recovered=None
        for i,(encoded,) in enumerate(payloads):
            if i<=expected:continue
            snap=json.loads(zlib.decompress(encoded))
            if snap['receiver'].get('gateway_observed') and any(r['report']['observer_id']=='90:da:72:48:a4:e0' and r['pc_receive_age_ms']<30000 for r in snap.get('reports',[])):
                recovered=i
                break
        assert int(back[0])==recovered,(recovered,back)
        pages=[]
        for tag,choice in [('stale',stale),('recovered',back)]:
            page.locator('#replayEvents').select_option(label=choice[1])
            page.wait_for_function("document.getElementById('replayTime').value===%s"%json.dumps(choice[0]))
            page.wait_for_timeout(400)
            pages.append([tag,choice,page.locator('#replayStatus').inner_text(),page.locator('.mapNode').count()])
            page.screenshot(path=here/(tag+'.png'))
            page.locator('#map').screenshot(path=here/(tag+'-graph.png'))
        page.locator('#replayLive').click()
        page.wait_for_timeout(300)
        assert not errors,errors
        assert all(v[-1]>0 for v in pages),pages
        (here/'BROWSER.json').write_text(json.dumps({'session':rid,'events':labels,'observations':pages,'errors':errors,'source':'Archived RF frames with controlled silence'},ensure_ascii=False,indent=2),encoding='utf-8')
        print('browser results',len(labels)-1,'events',len(pages),'jumps')
        browser.close()
        import subprocess
        edge=Path(r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')
        try:
            res=subprocess.run([str(edge),'--headless=new','--disable-gpu','--no-sandbox','--disable-extensions','--no-first-run','--user-data-dir='+str(here/'edge-profile'),'--dump-dom','http://127.0.0.1:%d/'%port],capture_output=True,timeout=15)
            hydrated=b'id="replayPanel"' in res.stdout
            (here/'EDGE.json').write_text(json.dumps({'exit_code':res.returncode,'dom_bytes':len(res.stdout),'replay_panel':hydrated}),encoding='utf-8')
        except subprocess.TimeoutExpired:
            (here/'EDGE.json').write_text('{"timeout":true}',encoding='utf-8')
finally:
    (here/'stop').touch()
    for child in c.children:
        try:child.wait(timeout=5)
        except Exception:
            child.terminate()
            child.wait(timeout=5)
