"""Owned loopback fixtures only. No real gateway, Studio observer, serial, UDP or field data."""
import copy
import json
import pathlib
import sqlite3
import sys
import threading
import traceback
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(r'D:\Multi-Agent Network')
OUT = pathlib.Path(sys.argv[1]).resolve()
OUT.mkdir(parents=True, exist_ok=False)
sys.path.insert(0, str(ROOT))
from tools.mobile_gateway.server import Handler
from tools.mobile_gateway.replay import Replay, PaginationRequired
from playwright.sync_api import sync_playwright, expect

DEV, STATIC, FIXTURE = 'http://127.0.0.1:10521', 'http://127.0.0.1:10524', 'http://127.0.0.1:10523'
state = {'mode': 'normal'}
calls, checks, gaps, errors, blocked, console = [], [], [], [], [], []
fixture = {
    'schema': 'lora.topology.v1', 'source': 'gateway_udp_lrn1',
    'source_id': 'AUDIT-TEST-ONLY', 'selection_epoch': 7, 'labels': {},
    'receiver': {'gateway_id': 'audit-test-gateway', 'gateway_observed': True,
                 'state': 'receiving', 'frames': 42, 'recent_threshold_ms': 30000},
    'reports': [{'pc_receive_age_ms': 100, 'status_age_ms': 100,
                 'status': {'battery_pct': 82},
                 'lora': {'rssi': -80, 'lsnr': 7.5, 'freq': 470.5, 'chan': 1},
                 'report': {'frame_schema': 'LRN1', 'observer_id': '02:00:00:77:00:01',
                            'report_period_ms': 1000,
                            'neighbors': [{'peer_id': '02:00:00:77:00:02', 'state': 'oneway',
                                           'valid': 3, 'seen_age_ms': 200, 'rssi_dbm': -65}]}}],
}

class FixtureHandler(Handler):
    protocol_version = 'HTTP/1.0'  # Short owned-fixture connections avoid idle reset noise.
    # Use the actual legacy response writer: deliberately no CORS header.
    def do_GET(self):
        calls.append({'method': 'GET', 'path': self.path})
        if self.path != '/api/v1/lora/topology':
            return self.reply(404, {'error': 'TEST ONLY: legacy fixture has no Network v1 backend'})
        if state['mode'] == 'down':
            return self.reply(503, {'error': 'TEST ONLY injected outage'})
        value = copy.deepcopy(fixture)
        if state['mode'] == 'fake':
            value['fake_gps'] = True
        return self.reply(200, value)

    def do_POST(self):
        calls.append({'method': 'POST', 'path': self.path})
        self.reply(405, {'error': 'Fixture read only'})


def sqlite_checks():
    db = OUT / 'isolated-replay.sqlite3'
    assert not db.exists()
    store = Replay(db, lambda: copy.deepcopy(fixture), interval=3600)
    try:
        ident = store.start()
        assert store.start() == ident
        store.sample()
        def offline():
            raise OSError('TEST ONLY injected source interruption')
        store.source = offline
        store.sample()
        assert store.session(ident)['frames'][1]['topology']['source'] == 'unavailable'
        assert store.stop() == ident
        assert store.session(ident, 1, 1)['total'] == 2
    finally:
        store.close()
    store = Replay(db, lambda: copy.deepcopy(fixture), interval=3600)
    try:
        assert store.session(ident)['total'] == 2 and store.sessions()['active_id'] is None
        old = store.start()
        with store.lock:
            store.db.execute('INSERT INTO frames VALUES(?,?,?)', (old, 1, json.dumps(fixture)))
            store.db.commit()
        assert store.session(old)['frames'][0]['topology']['source_id'] == 'AUDIT-TEST-ONLY'
        store.stop()
        large = store.start()
        for _ in range(101):
            store.sample()
        try:
            store.session(large)
            raise AssertionError('Missing bounded pagination')
        except PaginationRequired as error:
            assert error.total == 101
        assert len(store.session(large, 100, 1)['frames']) == 1
        store.stop()
    finally:
        store.close()
    checks.append('legacy SQLite: idempotent start, outage frame, persistence across reopen, pagination, old TEXT compatibility')


def browser_checks():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel='msedge')
        context = browser.new_context(viewport={'width': 1500, 'height': 1000})
        def guard(route):
            if any(route.request.url.startswith(base + '/') for base in (DEV, STATIC, FIXTURE)):
                route.continue_()
            else:
                blocked.append(route.request.url)
                route.abort()
        context.route('**/*', guard)
        def page_new():
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda item: console.append(item.text) if item.type == 'error' else None)
            return page
        def connect(page, base):
            page.get_by_role('textbox', name='数据服务地址', exact=True).fill(base)
            page.get_by_role('button', name='保存并连接', exact=True).click()
        try:
            page = page_new()
            page.goto(DEV + '/studio.html', wait_until='networkidle')
            page.get_by_role('button', name='本地网关', exact=True).click()
            connect(page, FIXTURE)
            expect(page.locator('[data-list-node]')).to_have_count(3)
            expect(page.locator('[data-test="unverified-gateway"]')).to_be_visible()
            expect(page.locator('[data-node]')).to_have_count(0)
            assert any(c['path'] == '/api/v1/lora/topology' for c in calls)
            checks.append('actual HTTP chain browser -> Vite read bridge -> owned legacy fixture, no response interception')
            expect(page.get_by_role('button', name='开始记录', exact=True)).to_be_disabled()
            expect(page.get_by_role('combobox', name='接收来源', exact=True)).to_have_count(0)
            assert page.get_by_role('combobox', name='选择网络记录', exact=True).locator('option').count() == 1
            gaps.append('Legacy gateway has no new Vue source management or SQLite recording/replay integration; controls absent/disabled.')
            page.screenshot(path=str(OUT / 'TEST-ONLY-development-legacy-chain.png'), full_page=True)
            state['mode'] = 'fake'
            expect(page.locator('.network-error')).to_contain_text('NETWORK_SYNTHETIC_REJECTED', timeout=12000)
            expect(page.locator('[data-list-node]')).to_have_count(3)
            state['mode'] = 'normal'
            page.get_by_role('button', name='重试读取', exact=True).click()
            expect(page.locator('.network-error')).to_have_count(0)
            state['mode'] = 'down'
            expect(page.locator('.connection-state')).to_have_text('数据服务连接中断', timeout=12000)
            expect(page.locator('[data-list-node]')).to_have_count(3)
            expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
            state['mode'] = 'normal'
            page.get_by_role('button', name='重试读取', exact=True).click()
            expect(page.locator('.connection-state')).to_have_text('观测服务已连接')
            checks.append('real HTTP fake rejection, outage/history retention and recovery without Mock fallback')
            page.close()

            second = page_new()
            second.goto(DEV + '/studio.html', wait_until='networkidle')
            second.get_by_role('button', name='服务器', exact=True).click()
            connect(second, FIXTURE)
            # The browser first sees CORS, not the HTTP 404 body. Verify the contract separately.
            probe = context.request.get(FIXTURE + '/api/v1/network/capabilities')
            assert probe.status == 404
            expect(second.locator('.network-error')).to_contain_text('Failed to fetch')
            expect(second.locator('[data-list-node]')).to_have_count(0)
            gaps.append('Server profile requires Network v1 (owned legacy fixture returns 404); direct browser connection also lacks CORS. Legacy cannot substitute for the missing backend.')
            second.close()

            production = page_new()
            production.goto(STATIC + '/studio.html', wait_until='networkidle')
            config = context.request.get(STATIC + '/network-config.json').json()
            assert not config.get('gatewayRelayPath')
            production.get_by_role('button', name='本地网关', exact=True).click()
            connect(production, FIXTURE)
            expect(production.locator('.network-error')).to_be_visible(timeout=12000)
            expect(production.locator('[data-list-node]')).to_have_count(0)
            assert any('CORS' in line for line in console), console
            gaps.append('Static build direct connection to existing no-CORS legacy service fails; dev bridge is not packaged as production backend/proxy.')
            production.screenshot(path=str(OUT / 'KNOWN-GAP-static-legacy-CORS.png'), full_page=True)
            checks.append('static deployment limitation reproduced as an expected failure, not reported as a working feature')
        finally:
            context.close()
            browser.close()

report = {'passed': False, 'synthetic_only': True, 'hardware_access': False,
          'intercepted_fixture_responses': False, 'fixture_port': 10523}
server = ThreadingHTTPServer(('127.0.0.1', 10523), FixtureHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    sqlite_checks()
    browser_checks()
    target = DEV + '/__network_gateway?' + urllib.parse.urlencode({'base': FIXTURE, 'resource': '/api/v1/lora/topology'})
    req = urllib.request.Request(target, data=b'{}', headers={'X-Network-Gateway': 'readonly', 'Origin': DEV, 'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(req)
        raise AssertionError('Bridge accepted POST')
    except urllib.error.HTTPError as error:
        assert error.code == 405
    assert all(c['method'] == 'GET' for c in calls)
    checks.append('POST rejected by real development bridge before forwarding to fixture')
    assert not errors and not blocked, (errors, blocked)
    report['passed'] = True
except Exception:
    report['failure'] = traceback.format_exc()
finally:
    server.shutdown()
    thread.join(3)
    server.server_close()
    report.update(checks=checks, observed_gaps=gaps, fixture_requests=calls,
                  page_errors=errors, unexpected_requests=blocked, console_errors=console)
    (OUT / 'EXTENDED-REPORT.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))
assert report['passed'], report.get('failure')
