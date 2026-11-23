"""Synthetic browser validation. Server/gateway responses are intercepted, never field data."""
import copy
import datetime
import json
import os
import re
import traceback
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get('NETWORK_EVIDENCE_DIR', str(ROOT / 'docs/network-studio/evidence' / datetime.datetime.now().strftime('browser-%Y%m%d-%H%M%S'))))
BASE = os.environ.get('NETWORK_PREVIEW_URL', 'http://127.0.0.1:5188').rstrip('/')
STATIC = os.environ.get('NETWORK_STATIC_URL', '').rstrip('/')
SERVER = 'https://network-fixture.invalid'
OUT.mkdir(parents=True, exist_ok=False)
checks, errors, blocked = [], [], []
behavior = {'server': 'measured', 'gateway': 'normal'}
report = {'passed': False, 'synthetic_only': True, 'hardware_access': False, 'real_endpoints_intercepted': True, 'backend': BASE}

def shot(page, name):
    page.screenshot(path=str(OUT / name), full_page=True)

def tracked(context):
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(error.stack or str(error)))
    return page

def connect(page, base=SERVER):
    page.get_by_role('textbox', name='数据服务地址', exact=True).fill(base)
    page.get_by_role('button', name='保存并连接', exact=True).click()

def gps(page):
    return page.get_by_role('button', name=re.compile('GPS 布局'))

def run(browser):
    context = browser.new_context(viewport={'width': 1600, 'height': 1550}, device_scale_factor=1)
    probe = context.request.get(BASE + '/__network_mock/api/v1/network/snapshot')
    assert probe.ok, 'Use the isolated demo launcher for this browser validation.'
    synthetic = probe.json()
    measured = copy.deepcopy(synthetic)
    measured.update(provenance='measured', instanceId='BROWSER-TEST-NOT-HARDWARE', sourceId='browser-test-only')
    for node in measured['nodes']:
        if node['position']:
            node['position']['source'] = 'browser-test-declared-gnss'
    caps = {'schema': 'network.capabilities.v1', 'mock': False, 'recording': False, 'sourceSelection': False,
            'sources': [{'id': 'browser-test-only', 'label': 'BROWSER TEST FIXTURE'}], 'selectedSourceId': 'browser-test-only', 'scenario': None}
    gateway = {'schema': 'lora.topology.v1', 'source': 'gateway_udp_lrn1', 'source_id': 'browser-test-gateway', 'selection_epoch': 0,
               'labels': {'02:00:00:01:00:01': '1', '02:00:00:01:00:02': '2'},
               'receiver': {'gateway_id': 'browser-test-gateway-eui', 'gateway_observed': True, 'state': 'receiving', 'frames': 12, 'recent_threshold_ms': 30000},
               'reports': [{'pc_receive_age_ms': 500, 'gps_age_ms': 1500, 'status_age_ms': 500,
                            'gps': {'valid': True, 'lat_e7': 400010000, 'lon_e7': 1163260000}, 'status': {'battery_pct': 83},
                            'lora': {'rssi': -88, 'lsnr': 7.5, 'freq': 470.5, 'chan': 1},
                            'report': {'frame_schema': 'LRN1', 'observer_id': '02:00:00:01:00:01', 'report_period_ms': 10000,
                                       'neighbors': [{'peer_id': '02:00:00:01:00:02', 'state': 'bidirectional', 'valid': 15, 'seen_age_ms': 200, 'ack_age_ms': 100, 'rssi_dbm': -65, 'rf_age_ms': 200, 'wifi_channel': 6}]}}]}
    real_requests = []

    def guard(route):
        url = route.request.url
        if url.startswith(SERVER + '/'):
            real_requests.append(url)
            headers = {'Access-Control-Allow-Origin': BASE, 'Access-Control-Allow-Methods': 'GET, OPTIONS'}
            path = urlsplit(url).path
            if route.request.method == 'OPTIONS':
                return route.fulfill(status=204, headers=headers)
            if path.endswith('/capabilities'):
                return route.fulfill(json={**caps, 'mock': behavior['server'] == 'mock-caps'}, headers=headers)
            if path.endswith('/snapshot'):
                if behavior['server'] == 'down':
                    return route.fulfill(status=503, json={'error': 'TEST INJECTED outage'}, headers=headers)
                value = copy.deepcopy(measured)
                if behavior['server'] == 'synthetic':
                    value = synthetic
                elif behavior['server'] == 'unknown':
                    value['provenance'] = 'unknown'
                elif behavior['server'] == 'nested-fake':
                    value['nodes'][1]['position']['source'] = 'synthetic'
                return route.fulfill(json=value, headers=headers)
            if path.endswith('/replays/mixed'):
                return route.fulfill(json={'schema': 'network.replay.v1', 'id': 'mixed', 'frames': [measured, synthetic]}, headers=headers)
            if path.endswith('/replays'):
                value = [{'id': 'mixed', 'label': 'TEST ONLY mixed replay', 'startedAt': measured['observedAt'], 'frames': 2, 'synthetic': behavior['server'] == 'mixed-list'}] if behavior['server'] in ('mixed-replay', 'mixed-list') else []
                return route.fulfill(json=value, headers=headers)
            return route.fulfill(status=404, json={'error': 'Unknown test endpoint'}, headers=headers)
        if url.startswith(BASE + '/__network_gateway'):
            real_requests.append(url)
            assert route.request.method == 'GET' and route.request.headers.get('x-network-gateway') == 'readonly'
            query = parse_qs(urlsplit(url).query)
            assert query.get('base') == ['http://127.0.0.1:8794']
            assert query.get('resource') == ['/api/v1/lora/topology']
            if behavior['gateway'] == 'down':
                return route.fulfill(status=503, json={'error': 'TEST INJECTED gateway unavailable'})
            value = copy.deepcopy(gateway)
            if behavior['gateway'] == 'fake':
                value['fake_gps'] = True
            return route.fulfill(json=value)
        if url == BASE + '/config.json':
            return route.fulfill(json={'apiBaseUrl': BASE, 'wsUrl': BASE.replace('http', 'ws', 1) + '/ws/telemetry'})
        if url.startswith(BASE + '/api/'):
            return route.fulfill(status=503, json={'message': 'Platform backend intentionally unavailable in network-only browser checks'})
        if url.startswith(BASE + '/') or (STATIC and url.startswith(STATIC + '/')):
            return route.continue_()
        blocked.append(url)
        return route.abort('blockedbyclient')

    context.route('**/*', guard)
    context.route_web_socket('**/ws/telemetry', lambda ws: None)
    page = tracked(context)
    first_requests = []
    page.on('request', lambda req: first_requests.append(req.url))
    page.goto(BASE + '/studio.html?mock=1', wait_until='networkidle')
    expect(page.locator('[data-test="real-connection"]')).to_be_visible()
    expect(page.locator('[data-list-node]')).to_have_count(0)
    expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
    assert not any('/api/v1/' in u or '/__network_gateway' in u or '/network-mock-config.json' in u for u in first_requests), first_requests
    assert page.locator('.connection-modes button').all_text_contents() == ['服务器', '本地网关']
    expect(gps(page)).to_have_attribute('aria-pressed', 'true')
    shot(page, '01-real-disconnected.png')
    checks.append('real entry: server/gateway only, no automatic backend reads, query cannot enable Mock, GPS default')

    connect(page)
    expect(page.locator('[data-list-node]')).to_have_count(6)
    expect(page.locator('[data-node]')).to_have_count(5)
    expect(page.locator('[data-test="gps-map-guide"]')).to_be_visible()
    expect(page.locator('.source-identity')).to_contain_text(SERVER)
    expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
    page.locator('[data-list-node="02:00:00:01:00:01"]').click()
    expect(page.get_by_role('combobox', name='NODE 类型标签')).to_have_value('node')
    page.get_by_role('combobox', name='NODE 类型标签').select_option('robot')
    expect(page.locator('.inspector h3')).to_have_text('NODE 01')
    expect(page.locator('[data-list-node="02:00:00:01:00:01"]')).to_contain_text('标签：机器人')
    shot(page, '02-TEST-ONLY-server-gps.png')
    checks.append('server profile: intercepted Network v1, NODE names, optional robot tag, GPS projection and scale')
    page.reload(wait_until='networkidle')
    expect(page.locator('[data-list-node]')).to_have_count(0)
    expect(page.get_by_role('textbox', name='数据服务地址')).to_have_value(SERVER)
    connect(page)
    page.locator('[data-list-node="02:00:00:01:00:01"]').click()
    expect(page.get_by_role('combobox', name='NODE 类型标签')).to_have_value('robot')
    checks.append('real profile and tag persist, but saved URL never authorizes automatic connection on reload')

    page.get_by_role('button', name='本地网关', exact=True).click()
    expect(page.locator('[data-list-node]')).to_have_count(0)
    expect(page.get_by_role('textbox', name='数据服务地址')).to_have_value('http://127.0.0.1:8794')
    page.get_by_role('button', name='保存并连接', exact=True).click()
    expect(page.locator('[data-list-node]')).to_have_count(3)
    expect(page.locator('[data-node]')).to_have_count(1)
    expect(page.locator('[data-test="unverified-gateway"]')).to_be_visible()
    page.locator('[data-list-node="02:00:00:01:00:01"]').click()
    expect(page.get_by_role('combobox', name='NODE 类型标签')).to_have_value('node')
    expect(page.get_by_role('button', name='开始记录', exact=True)).to_be_disabled()
    shot(page, '03-TEST-ONLY-local-gateway.png')
    checks.append('gateway profile: intercepted legacy read, no source/recording writes, provenance remains undeclared, tags isolated')
    behavior['gateway'] = 'down'
    expect(page.locator('.connection-state')).to_have_text('数据服务连接中断', timeout=12000)
    expect(page.locator('[data-list-node]')).to_have_count(3)
    expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
    behavior['gateway'] = 'normal'; page.get_by_role('button', name='重试读取', exact=True).click()
    expect(page.locator('.connection-state')).to_have_text('观测服务已连接')
    behavior['gateway'] = 'fake'
    expect(page.locator('.network-error')).to_contain_text('NETWORK_SYNTHETIC_REJECTED', timeout=12000)
    behavior['gateway'] = 'normal'; page.get_by_role('button', name='重试读取', exact=True).click()
    expect(page.locator('.network-error')).to_have_count(0)
    checks.append('gateway outage retains only historical evidence; fake GPS rejected; recovery never falls back to Mock')

    page.get_by_role('button', name='服务器', exact=True).click()
    expect(page.get_by_role('textbox', name='数据服务地址')).to_have_value(SERVER)
    connect(page, BASE + '/__network_mock')
    expect(page.locator('.network-error')).to_contain_text('已阻止模拟数据进入真实工作区')
    expect(page.locator('[data-list-node]')).to_have_count(0)
    shot(page, '04-real-blocks-mock.png')
    checks.append('real workspace rejects the actually running isolated mock service before displaying nodes')
    for state, code in [('mock-caps', 'NETWORK_SYNTHETIC_REJECTED'), ('synthetic', 'NETWORK_SYNTHETIC_REJECTED'), ('unknown', 'NETWORK_PROVENANCE_UNVERIFIED'), ('nested-fake', 'NETWORK_SYNTHETIC_REJECTED')]:
        behavior['server'] = state; connect(page)
        expect(page.locator('.network-error')).to_contain_text(code)
        expect(page.locator('[data-list-node]')).to_have_count(0)
    checks.append('server rejects wrong capabilities, synthetic root, undeclared provenance and nested fake GPS')
    behavior['server'] = 'mixed-replay'; connect(page)
    expect(page.locator('[data-list-node]')).to_have_count(6)
    page.get_by_role('combobox', name='选择网络记录', exact=True).select_option('mixed')
    page.get_by_role('button', name='载入回放', exact=True).click()
    expect(page.locator('.network-error')).to_contain_text('NETWORK_SYNTHETIC_REJECTED')
    expect(page.locator('[data-test="network-replay"]')).to_have_count(0)
    behavior['server'] = 'mixed-list'; connect(page)
    expect(page.locator('.network-error')).to_contain_text('NETWORK_REPLAY_PROVENANCE_MISMATCH')
    assert page.get_by_role('combobox', name='选择网络记录', exact=True).locator('option').count() == 1
    behavior['server'] = 'measured'; connect(page)
    expect(page.locator('.network-error')).to_have_count(0)
    checks.append('real workspace rejects mixed-provenance replay frames and recording lists without replacing live data')

    page.set_viewport_size({'width': 390, 'height': 844})
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.locator('.network-workspace').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
    shot(page, '05-real-mobile.png')
    page.set_viewport_size({'width': 1600, 'height': 1550})
    checks.append('real connection controls and GPS toolbar fit 390px without horizontal overflow')

    demo = tracked(context)
    demo.goto(BASE + '/mock-studio.html?apiBaseUrl=' + SERVER, wait_until='networkidle')
    expect(demo.locator('[data-test="mock-entry"]')).to_be_visible()
    expect(demo.locator('[data-test="real-connection"]')).to_have_count(0)
    expect(demo.locator('[data-test="network-synthetic"]')).to_be_visible()
    demo.get_by_role('combobox', name='接收来源', exact=True).select_option('synthetic-lab')
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('nominal')
    expect(demo.locator('[data-list-node]')).to_have_count(6)
    expect(demo.locator('[data-test="mock-watermark"]')).to_be_visible()
    expect(gps(demo)).to_have_attribute('aria-pressed', 'true')
    demo.locator('[data-list-node="02:00:00:01:00:01"]').click()
    expect(demo.get_by_role('combobox', name='NODE 类型标签')).to_have_value('node')
    demo.get_by_role('combobox', name='NODE 类型标签').select_option('drone')
    expect(demo.locator('.inspector h3')).to_have_text('NODE 01')
    shot(demo, '06-mock-gps-node-tags.png')
    checks.append('isolated Mock: separate entry/config/API, permanent ribbon and graph watermark, NODE/tag isolation, query ignored')
    demo.route(BASE + '/__network_mock/api/v1/network/snapshot', lambda route: route.fulfill(json=measured))
    expect(demo.locator('.network-error')).to_contain_text('NETWORK_REAL_DATA_IN_MOCK', timeout=12000)
    expect(demo.locator('[data-list-node]')).to_have_count(6)
    expect(demo.locator('[data-test="mock-entry"]')).to_be_visible()
    demo.unroute(BASE + '/__network_mock/api/v1/network/snapshot')
    demo.get_by_role('button', name='重试读取', exact=True).click()
    expect(demo.locator('.network-error')).to_have_count(0)
    checks.append('Mock rejects intercepted measured snapshots and retains only prior synthetic evidence')

    demo.get_by_role('button', name='切换主题', exact=True).click()
    expect(demo.locator('html')).to_have_attribute('data-theme', 'outdoor')
    shot(demo, '07-mock-outdoor.png')
    demo.get_by_role('button', name='切换主题', exact=True).click()
    demo.get_by_role('searchbox', name='搜索网络成员').fill('NODE 02')
    expect(demo.locator('[data-list-node]')).to_have_count(1)
    demo.get_by_role('searchbox', name='搜索网络成员').fill('')
    # A curved SVG group's bounding-box center need not lie on its stroke. Click the actual path.
    point = demo.locator('.edge .edge-line').first.evaluate('(path) => { const p=path.getPointAtLength(path.getTotalLength()/2); const q=new DOMPoint(p.x,p.y).matrixTransform(path.getScreenCTM()); return {x:q.x,y:q.y} }')
    demo.mouse.click(point['x'], point['y'])
    expect(demo.locator('.inspector h2')).to_have_text('方向详情')
    checks.append('shared dark/outdoor themes, generic NODE search and directed link inspection')
    demo.get_by_role('button', name='手动布局', exact=True).click()
    node = demo.locator('[data-node="02:00:00:01:00:01"] .node-body')
    bounds = node.bounding_box()
    x, y = bounds['x'] + bounds['width'] / 2, bounds['y'] + bounds['height'] / 2
    demo.mouse.move(x, y); demo.mouse.down(); demo.mouse.move(x + 70, y + 30, steps=8); demo.mouse.up()
    saved = demo.evaluate("Object.keys(localStorage).filter(k=>k.startsWith('network.layout.v2:mock:')).map(k=>localStorage[k])")
    assert saved and any('02:00:00:01:00:01' in value for value in saved), saved
    demo.reload(wait_until='networkidle')
    expect(demo.get_by_role('button', name='手动布局', exact=True)).to_have_attribute('aria-pressed', 'true')
    checks.append('manual drag and reload persistence use full workspace/endpoint/source namespace')
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('dense')
    expect(demo.locator('[data-list-node]')).to_have_count(31)
    demo.get_by_role('button', name='清晰布局', exact=True).click()
    shot(demo, '08-mock-dense-30.png')
    checks.append('30 generic NODE members plus gateway, dense link focus remains available')
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('no-gps')
    expect(demo.locator('[data-list-node]')).to_have_count(6)
    gps(demo).click()
    expect(demo.get_by_text('没有可用的 GPS 位置', exact=True)).to_be_visible()
    expect(demo.locator('[data-node]')).to_have_count(0)
    checks.append('GPS absent: no invented geographic points, all members retained')
    demo.get_by_role('button', name='清晰布局', exact=True).click()
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('empty')
    expect(demo.locator('[data-list-node]')).to_have_count(0)
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('interrupted')
    expect(demo.locator('.node-state.interrupted')).to_have_count(6)
    expect(demo.locator('.connection-state')).to_have_text('接收器观测中断')
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('stale')
    expect(demo.locator('.node-state.stale')).to_have_count(3)
    checks.append('empty, receiver interruption and stale reports remain distinct')
    demo.get_by_role('combobox', name='模拟场景', exact=True).select_option('nominal')
    demo.get_by_role('combobox', name='接收来源', exact=True).select_option('synthetic-field')
    expect(demo.locator('[data-list-node="02:00:00:02:00:01"]')).to_be_visible()
    expect(demo.locator('[data-list-node="02:00:00:01:00:01"]')).to_have_count(0)
    demo.get_by_role('button', name='暂停观测', exact=True).click()
    expect(demo.get_by_role('button', name='继续观测', exact=True)).to_be_visible()
    demo.get_by_role('button', name='继续观测', exact=True).click()
    checks.append('demo source identity change, explicit pause/resume')
    demo.get_by_role('button', name='开始记录', exact=True).click()
    expect(demo.get_by_role('button', name='结束记录', exact=True)).to_be_visible()
    demo.get_by_role('button', name='结束记录', exact=True).click()
    demo.get_by_role('combobox', name='选择网络记录', exact=True).select_option('sample-session')
    demo.get_by_role('button', name='载入回放', exact=True).click()
    expect(demo.locator('[data-test="network-replay"]')).to_be_visible()
    demo.get_by_role('slider', name='回放进度').fill('26')
    expect(demo.locator('.node-state.interrupted')).to_have_count(6)
    demo.get_by_role('combobox', name='回放倍速').select_option('4')
    demo.get_by_role('button', name='播放回放', exact=True).click()
    expect(demo.get_by_role('button', name='暂停回放', exact=True)).to_be_visible()
    demo.get_by_role('button', name='暂停回放', exact=True).click()
    shot(demo, '09-mock-replay.png')
    demo.get_by_role('button', name='返回实时', exact=True).click()
    checks.append('isolated demo recording, replay timeline/speed/play/pause/live retain global MOCK marking')
    demo.get_by_role('button', name='切换界面语言', exact=True).click()
    expect(demo.get_by_role('heading', name='Network observation studio')).to_be_visible()
    expect(demo.locator('[data-test="mock-entry"]')).to_contain_text('Isolated simulation')
    shot(demo, '10-mock-english.png')
    demo.get_by_role('button', name='Switch interface language', exact=True).click()
    demo.set_viewport_size({'width': 390, 'height': 844})
    assert demo.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert demo.locator('.network-workspace').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
    shot(demo, '11-mock-mobile.png')
    checks.append('English and 390px demo layout keep isolation warnings visible without horizontal overflow')

    page.goto(BASE + '/#/network', wait_until='networkidle')
    expect(page.locator('[data-test="real-connection"]')).to_be_visible()
    expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
    expect(page.locator('[data-list-node]')).to_have_count(0)
    connect(page)
    expect(page.locator('[data-list-node]')).to_have_count(6)
    page.locator('[data-list-node="02:00:00:01:00:01"]').click()
    expect(page.get_by_role('combobox', name='NODE 类型标签')).to_have_value('robot')
    shot(page, '12-TEST-ONLY-integrated.png')
    checks.append('integrated platform route is real-only, shares profiles/tags and GPS; other platform APIs isolated as 503')
    assert real_requests, 'Real-mode routing was not exercised'
    assert not blocked, blocked
    if STATIC:
        for entry, heading in [('studio.html', '网络数据服务尚未启用'), ('mock-studio.html', '独立模拟服务尚未启用')]:
            static = tracked(context)
            requests = []
            static.on('request', lambda req: requests.append(req.url))
            static.goto(STATIC + '/' + entry, wait_until='networkidle')
            expect(static.get_by_text(heading, exact=True)).to_be_visible()
            expect(static.locator('[data-list-node]')).to_have_count(0)
            assert not any('/api/v1/' in u or '/api/v2/' in u or '/__network_gateway' in u for u in requests), requests
            if entry == 'mock-studio.html':
                expect(static.locator('[data-test="mock-entry"]')).to_be_visible()
            shot(static, '13-production-' + entry.replace('.html', '.png'))
            static.close()
        checks.append('built real and demo entries both default disconnected; no backend reads; Mock remains clearly marked')
    report['browser_version'] = browser.version
    report['intercepted_real_requests'] = len(real_requests)
    context.close()

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel=os.environ.get('NETWORK_BROWSER_CHANNEL', 'msedge'))
    try:
        run(browser)
        assert not errors, errors
        report['passed'] = True
    except Exception:
        report['failure'] = traceback.format_exc()
    finally:
        browser.close()
        report.update(checks=checks, page_errors=errors, blocked_unexpected_requests=blocked)
        (OUT / 'REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(OUT), **report}, ensure_ascii=True, indent=2))
assert report['passed'], report.get('failure', errors)
