import hashlib, json, shutil, socket, subprocess, sys, time, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path.cwd()
out = Path(__file__).resolve().parent
source = root / 'simulation/results/20261119-M058-studio-replay/historical-controlled.sqlite3'
db = out / 'history.sqlite3'
if db.exists():
    raise SystemExit('output database already exists')
shutil.copy2(source, db)
def freeport():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
port, pc, topo = freeport(), freeport(), freeport()
cmd = [sys.executable, '-X', 'utf8', '-m', 'tools.mobile_gateway.studio', '--port', str(port), '--pc-port', str(pc), '--topology-port', str(topo), '--output', str(out / 'studio'), '--replay-db', str(db), '--stop-file', str(out / 'stop')]
with (out / 'studio.log').open('xb') as log:
    process = subprocess.Popen(cmd, cwd=root, stdout=log, stderr=subprocess.STDOUT)
try:
    url = f'http://127.0.0.1:{port}'
    for _ in range(60):
        if process.poll() is not None: raise RuntimeError('studio exited')
        try:
            with urllib.request.urlopen(url + '/api/v1/replay/sessions', timeout=1) as response:
                sessions = json.load(response)
            break
        except OSError: time.sleep(.2)
    else: raise RuntimeError('studio failed to start')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=r'C:\Program Files\Google\Chrome\Application\chrome.exe', headless=True, args=['--disable-background-networking', '--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1'])
        page = browser.new_page(viewport={'width': 1366, 'height': 768}, locale='zh-CN')
        errors = []
        page.on('pageerror', lambda err: errors.append(str(err)))
        page.goto(url)
        ident = sessions['sessions'][0]['id']
        page.locator(f'#replaySessions option[value="{ident}"]').wait_for(state='attached', timeout=15000)
        page.locator('.recordTools > summary').click()
        page.select_option('#replaySessions', ident)
        page.click('#replayOpen')
        page.wait_for_function("() => +document.querySelector('#replayTime').max >= 42")
        page.locator('#replayTime').evaluate("e=>{e.value='42';e.dispatchEvent(new Event('input'))}")
        page.wait_for_function("() => document.querySelector('#replayStatus').textContent.includes('第 43 /')")
        summary = page.locator('#uplinkSummary').inner_text()
        assert all(s in summary for s in ('CH 5', '470.500 MHz', '-45 dBm', '10.8 dB')), summary
        page.get_by_text('逐方向无线记录', exact=True).first.click()
        buttons = page.locator('#directions button')
        found = None
        for i in range(buttons.count()):
            buttons.nth(i).click()
            detail = page.locator('#edgeDetail').inner_text()
            if 'Wi-Fi 信道：11' in detail and '-46 dBm' in detail:
                found = detail
                break
        assert found is not None, 'frame 43: Wi-Fi CH11/-46dBm not found in edge details'
        page.screenshot(path=str(out / 'wifi-detail.png'), full_page=True)
        assert not errors, errors
        paths = ['view.js','index.html','lora-model.js','map.css']
        assets = root / 'research/agent_native_network/mobile_gateway'
        hashes = {p: hashlib.sha256((assets / p).read_bytes()).hexdigest() for p in paths}
        (out / 'RESULT.json').write_text(json.dumps({'status':'passed','session':ident,'frame':43,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'frontend_sha256':hashes,'lora_summary':summary,'wifi_detail':found,'errors':errors}, ensure_ascii=False, indent=2),encoding='utf-8')
        browser.close()
finally:
    (out / 'stop').touch()
    try: process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.terminate(); process.wait(timeout=5)
    (out / 'PROCESS_END.json').write_text(json.dumps({'studio_exit': process.returncode}), encoding='utf-8')
