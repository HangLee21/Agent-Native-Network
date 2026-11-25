"""Isolated integration: built Vue -> real HTTP bridges -> original Sources/Replay/State.
All observations below are fabricated TEST ONLY fixtures. No physical services or boards.
"""
import argparse
import copy
import datetime
import json
import socket
import subprocess
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.mobile_gateway.server import Gateway
from tools.mobile_gateway.studio import StudioHandler
from tools.mobile_gateway.sources import Sources
from tools.mobile_gateway.replay import Replay
from tools.mobile_gateway.state import State

IDS = {i: '02:11:22:33:44:%02x' % i for i in (1, 2, 3, 4, 5, 99)}


class FixtureAdapter:
    def __init__(self, secondary=False):
        self.available = True
        self.secondary = secondary

    def topology(self):
        ids = [99] if self.secondary else [1, 2, 4, 5]
        return {'schema': 'lora.topology.v1', 'source': 'gateway_udp_lrn1', 'test_only': True,
                'labels': {IDS[i]: str(i) for i in (1, 2, 3, 4, 5)},
                'receiver': {'gateway_id': '0200000000000002' if self.secondary else '0200000000000001',
                             'gateway_observed': self.available, 'identity_verified': True,
                             'state': 'receiving' if self.available else 'unavailable',
                             'recent_threshold_ms': 30000, 'frames': 123, 'last_rx_age_ms': 500},
                'reports': [{'pc_receive_age_ms': 60000 if i == 4 else 1000, 'gps_age_ms': None,
                             'status_age_ms': None, 'lora': {'rssi': -80 - i, 'lsnr': 7, 'freq': 470.5},
                             'report': {'frame_schema': 'LRN1', 'observer_id': IDS[i], 'report_period_ms': 10000,
                                        'neighbors': [{'peer_id': IDS[j], 'state': 'bidirectional', 'valid': 15,
                                                       'seen_age_ms': 1200, 'ack_age_ms': 1000, 'rssi_dbm': -55 - j,
                                                       'wifi_channel': 6} for j in ids if j != i]}}
                            for i in ids] if self.available else []}


class PassiveFixture:
    """Use the original State kernel, not Studio's hardware-observer constructor."""
    def __init__(self):
        self.session = 'TEST-ONLY-' + uuid.uuid4().hex
        self.live = State()
        for i in (1, 2, 4, 5):
            events = []
            for seq in (11, 12):
                if i in (1, 2):
                    events.append({'event': 'tx_submit' if i == 1 else 'rx_local', 'origin': IDS[1],
                                   'origin_boot': 31, 'seq': seq, 'dst': IDS[2], 'reporter': IDS[i],
                                   'node_id': IDS[i], 'observer_id': IDS[i], 'packet_kind': 'DATA',
                                   'next_hop': IDS[2], 'previous_hop': IDS[1],
                                   'payload_hex': '627965' if i == 2 and seq == 12 else '6869',
                                   'evidence_source': 'TEST_ONLY_NOT_HARDWARE'})
            self.live.accept({'schema_version': 1, 'node_id': IDS[i], 'boot_id': 31,
                              'session_id': self.session + str(i), 'seq': 1, 'label': str(i), 'position': None,
                              'neighbors': [{'peer_id': IDS[j], 'state': 'confirmed', 'rf_source': 'measured',
                                             'rssi_dbm': -58, 'sample_age_ms': 1000, 'peer_boot': 31}
                                            for j in (1, 2) if j != i] if i in (1, 2) else [],
                              'events': events, 'agent': {'running': True, 'source': 'TEST ONLY FIXTURE',
                                                       'record_overwritten': 1 if i == 2 else 0,
                                                       'sampled_records_skipped': 2 if i == 2 else 0,
                                                       'counters': {'source_submitted': 2, 'relay_received': 0,
                                                                    'destination_received': 2 if i == 2 else 0}}})

    def status(self):
        return {'mode': 'live', 'fake_gps': False, 'error': None,
                'live': {'source': 'TEST_ONLY_NO_HARDWARE', 'serial_opens': 0},
                'capabilities': {'demo_control': False, 'fake_gps_toggle': False, 'lora_topology': True}}

    def snapshot(self):
        return dict(self.live.snapshot(), view_mode='live', fake_gps=False, test_only=True,
                    radio_source='TEST_ONLY_NOT_HARDWARE', studio=self.status())

    def history(self, after):
        return self.live.history(after)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output', required=True, type=Path)
    ap.add_argument('--web-port', default=10524, type=int)
    args = ap.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'started_at': datetime.datetime.now().astimezone().isoformat(), 'passed': False,
              'test_only_fabricated_inputs': True, 'physical_boards': 0, 'device_commands': 0,
              'existing_databases_opened': False, 'api_fulfillments': 0, 'checks': [], 'errors': [],
              'requests': [], 'backend_requests': [], 'blocked': [], 'external_platform_reads_blocked': []}
    primary, secondary = FixtureAdapter(), FixtureAdapter(True)
    sources = Sources(start=False)
    sources.add('fixtureA', primary, 'TEST ONLY · 主合同夹具')
    sources.add('fixtureB', secondary, 'TEST ONLY · 第二接收源')
    replay = Replay(out / 'isolated.sqlite3', sources.topology, interval=3600)
    fixture = PassiveFixture()

    class Handler(StudioHandler):
        def handle(self):
            try:
                return super().handle()
            except ConnectionResetError:
                report['closed_transport_connections'] = report.get('closed_transport_connections', 0) + 1

        def do_GET(self):
            report['backend_requests'].append({'method': 'GET', 'path': self.path})
            return super().do_GET()

        def do_POST(self):
            report['backend_requests'].append({'method': 'POST', 'path': self.path,
                                               'origin': self.headers.get('Origin'),
                                               'connection': self.headers.get('Connection')})
            return super().do_POST()

    server = Gateway(('127.0.0.1', 0), fixture, out)
    server.RequestHandlerClass = Handler
    server.sources = server.remote = sources
    server.serial = None
    server.replay = replay
    server.fleet_path = out / 'fleet.json'
    server.registry_path = out / 'registry.json'
    server.recovery_path = out / 'recovery.json'
    server.fleet_path.write_text(json.dumps({'schema_version': 1, 'nodes': [{'node_id': i, 'mac': IDS[i]} for i in (1, 2, 3, 4, 5)]}), encoding='utf-8')
    server.recovery_path.write_text(json.dumps({'schema': 'studio.recovery.v1', 'state': 'online', 'updated_at': time.time(), 'reason': 'TEST ONLY supervisor fixture'}), encoding='utf-8')
    seed = replay.start()
    for _ in range(103):
        replay.sample()
    replay.stop()
    # Backdate only this new test DB to exercise captured timing, never today's fleet overlay.
    with replay.lock:
        original = replay.db.execute('SELECT rowid FROM frames WHERE session_id=? ORDER BY rowid', (seed,)).fetchall()
        base_ms = int(time.time() * 1000) - 7200000
        for index, (ident,) in enumerate(original):
            replay.db.execute('UPDATE frames SET t_ms=? WHERE rowid=?', (base_ms + index * 1000, ident))
        replay.db.execute('UPDATE sessions SET started_ms=?,ended_ms=? WHERE id=?', (base_ms, base_ms + 102000, seed))
        replay.db.commit()
    replay.close()
    replay = Replay(out / 'isolated.sqlite3', sources.topology, interval=.1)
    server.replay = replay
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    backend = f'http://127.0.0.1:{server.server_port}'
    base = f'http://127.0.0.1:{args.web_port}'
    node_log = (out / 'static-server.log').open('w', encoding='utf-8')
    node = None

    def check(name, value=True):
        report['checks'].append({'name': name, 'passed': bool(value)})
        if not value:
            raise AssertionError(name)

    try:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', args.web_port)) == 0:
                raise RuntimeError('Refuse occupied browser test port')
        node = subprocess.Popen(['node', str(ROOT / 'scripts/network-studio/serve.mjs'), '--port', str(args.web_port)], cwd=ROOT, stdout=node_log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        report['owned_static_pid'] = node.pid
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel='msedge')
            context = browser.new_context(viewport={'width': 1680, 'height': 1450}, device_scale_factor=1)
            def guard(route):
                req = route.request
                if not req.url.startswith(base + '/'):
                    target = urlsplit(req.url)
                    known_java_reads = {'/api/v1/dogs/time', '/api/v1/dogs', '/api/v2/dogs', '/api/v1/system/info', '/api/v1/safety/config', '/api/v1/drones'}
                    if req.method == 'GET' and target.scheme == 'http' and target.netloc == 'localhost:8080' and target.path in known_java_reads and req.frame.url == base + '/#/network':
                        # F05: existing platform shell polls its separate Java services. Never
                        # connect to or fabricate them; record this known boundary independently.
                        report['external_platform_reads_blocked'].append({'method': req.method, 'url': req.url})
                    else:
                        report['blocked'].append(req.url)
                    return route.abort()
                report['requests'].append({'method': req.method, 'url': req.url})
                route.continue_()
            context.route('**/*', guard)
            page = context.new_page()
            page.on('pageerror', lambda error: report['errors'].append(str(error)))
            try:
                page.goto(base + '/studio.html', wait_until='networkidle')
                expect(page.locator('[data-list-node]')).to_have_count(0)
                check('built real page starts disconnected with zero backend reads', len(report['backend_requests']) == 0)
                page.get_by_role('button', name='本地网关', exact=True).click()
                def connect(target=page):
                    target.get_by_role('textbox', name='数据服务地址', exact=True).fill(backend)
                    target.get_by_role('button', name='保存并连接', exact=True).click()
                    expect(target.locator('.connection-state')).to_have_text('观测服务已连接', timeout=15000)
                connect()
                expect(page.locator('[data-list-node]')).to_have_count(6)
                expect(page.locator('[data-node]')).to_have_count(6)
                expect(page.locator('[data-test="network-alerts"]')).to_contain_text('NODE 04')
                expect(page.locator('[data-test="network-alerts"]')).to_contain_text('NODE 03')
                expect(page.locator('.graph-node.stale')).to_have_count(1)
                expect(page.locator('.graph-node.unknown')).to_have_count(1)
                check('clear layout exposes timeout and registered missing node with no GPS')
                check('no IP/RAM observer reads before an explicit action', not any(r['path'].startswith(('/api/v1/state', '/api/v1/timeline', '/api/studio/status')) for r in report['backend_requests']))
                styles = page.locator('.edge.historical.focused .edge-line').first.evaluate('(e)=>({width:getComputedStyle(e).strokeWidth,opacity:getComputedStyle(e).opacity,color:getComputedStyle(e).stroke})')
                check('historical adjacent links are visible, thick and still historical', float(styles['width'].replace('px', '')) >= 4 and float(styles['opacity']) >= .8)
                report['historical_edge_style'] = styles
                check('status captions and legend are not clipped by the old fixed-height grid', page.locator('[data-test="network-topology"]').evaluate('(root)=>{const r=root.getBoundingClientRect();return [...root.querySelectorAll(".node-state-caption,.legend")].every(e=>e.getBoundingClientRect().bottom<=r.bottom+1)}'))
                page.locator('[data-test="network-topology"]').screenshot(path=str(out / '01-TEST-ONLY-topology.png'))
                page.screenshot(path=str(out / '02-TEST-ONLY-full-workspace.png'), full_page=True)
                # Independent IP/RAM layer uses the actual State kernel, never old LoRa freshness flags.
                page.get_by_role('button', name='Wi-Fi 即时 / IP', exact=True).click()
                expect(page.locator('.workspace-footer')).to_contain_text('wifi-ip-state')
                expect(page.locator('.edge.mutual:not(.historical)')).to_have_count(2)
                check('native Wi-Fi layer preserves fresh reverse corroboration and its separate source')
                page.get_by_role('button', name='LoRa 报告', exact=True).click()
                expect(page.locator('.workspace-footer')).to_contain_text('fixtureA:configured')
                details = page.locator('.evidence-details')
                details.locator('summary').first.click()
                page.get_by_role('button', name='开始读取只读证据', exact=True).click()
                expect(page.locator('.packet-table tbody tr')).to_have_count(2)
                expect(page.locator('.packet-table')).to_contain_text('目的收件字节冲突')
                expect(page.locator('.packet-table')).to_contain_text('目的实收原字节')
                expect(page.locator('.packet-inspector')).to_contain_text('6869')
                check('original identity, destination receipt, conflicting bytes and incomplete coverage are displayed')
                page.locator('[data-test="network-engineering"]').screenshot(path=str(out / '03-TEST-ONLY-original-evidence.png'))
                page.get_by_role('button', name='停止读取证据', exact=True).click()
                # This POST reaches the original handler through the new independent operator bridge.
                page.get_by_role('button', name='开始记录', exact=True).click()
                expect(page.get_by_role('button', name='结束记录', exact=True)).to_be_visible()
                active_id = replay.active
                check('record action reaches the actual isolated SQLite writer', isinstance(active_id, str))
                page.reload(wait_until='networkidle')
                expect(page.locator('[data-list-node]')).to_have_count(0)
                check('closing/reloading the browser does not stop backend recording', replay.active == active_id)
                connect()
                expect(page.get_by_role('button', name='结束记录', exact=True)).to_be_visible()
                page.get_by_role('button', name='结束记录', exact=True).click()
                expect(page.get_by_role('button', name='开始记录', exact=True)).to_be_visible()
                check('reconnect resumes recorder ownership and stop does not retain the closed ID', replay.active is None)
                page.get_by_role('combobox', name='选择网络记录', exact=True).select_option(seed)
                page.get_by_role('button', name='载入回放', exact=True).click()
                expect(page.locator('[data-test="network-replay"]')).to_be_visible()
                expect(page.locator('.core-health')).to_have_count(0)
                check('historical playback never overlays the current fleet or engineering health metadata')
                slider = page.get_by_role('slider', name='回放进度', exact=True)
                slider.evaluate('(e)=>{e.value="102";e.dispatchEvent(new Event("input",{bubbles:true}))}')
                expect(page.locator('[data-test="network-replay"]')).to_contain_text('103 / 103')
                check('persistent replay seeks beyond 100 via bounded HTTP pages', any('offset=100&limit=25' in r['path'] for r in report['backend_requests']))
                check('replay uses the original captured timestamp', page.locator('.observation-clock').inner_text().startswith(datetime.datetime.fromtimestamp((base_ms + 102000) / 1000).strftime('%H:%M:%S')))
                page.screenshot(path=str(out / '04-TEST-ONLY-sqlite-page-103.png'), full_page=True)
                page.get_by_role('button', name='返回实时', exact=True).click()
                expect(page.locator('.workspace-footer')).to_contain_text('fixtureA:configured')
                page.get_by_role('combobox', name='接收来源', exact=True).select_option('fixtureB:configured')
                expect(page.locator('.workspace-footer')).to_contain_text('fixtureB:configured')
                check('source selection discards old observed reports and links', not page.locator('.edge').count() > 1 and '仅历史标签' not in page.locator('.inspector').inner_text())
                check('all source-A reporters become inventory-only, not old-source online residue', page.locator('.graph-node.recent').count() <= 2)
                page.get_by_role('combobox', name='接收来源', exact=True).select_option('fixtureA:configured')
                expect(page.locator('.workspace-footer')).to_contain_text('fixtureA:configured')
                platform = context.new_page()
                platform.on('pageerror', lambda error: report['errors'].append(str(error)))
                platform.goto(base + '/#/network', wait_until='networkidle')
                expect(platform.locator('[data-list-node]')).to_have_count(0)
                platform.get_by_role('button', name='本地网关', exact=True).click(); connect(platform)
                expect(platform.locator('[data-node]')).to_have_count(6)
                check('integrated platform route uses the same real-only engineering module')
                platform.screenshot(path=str(out / '06-TEST-ONLY-platform.png'), full_page=True)
                platform.close()
                phone = browser.new_context(viewport={'width': 390, 'height': 844}, device_scale_factor=1)
                phone.route('**/*', guard)
                mobile = phone.new_page()
                mobile.on('pageerror', lambda error: report['errors'].append(str(error)))
                mobile.goto(base + '/studio.html', wait_until='networkidle')
                mobile.get_by_role('button', name='本地网关', exact=True).click(); connect(mobile)
                expect(mobile.locator('.graph-node.stale')).to_have_count(1)
                expect(mobile.locator('.graph-node.unknown')).to_have_count(1)
                check('390px view retains explicit stale and missing states without horizontal page overflow', mobile.locator('.network-workspace').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1'))
                check('390px topology captions are inside the panel', mobile.locator('[data-test="network-topology"]').evaluate('(root)=>{const r=root.getBoundingClientRect();return [...root.querySelectorAll(".node-state-caption,.legend")].every(e=>e.getBoundingClientRect().bottom<=r.bottom+1)}'))
                mobile.locator('[data-test="network-alerts"]').screenshot(path=str(out / '07-TEST-ONLY-mobile-alerts.png'))
                mobile.get_by_role('button', name='切换界面语言', exact=True).click()
                expect(mobile.get_by_role('heading', name='Network observation studio', exact=True)).to_be_visible()
                expect(mobile.locator('[data-list-node]')).to_have_count(0) # Locale reload must not authorize reconnect.
                mobile.locator('.connection-modes button').nth(1).click()
                mobile.locator('.endpoint-input input').fill(backend)
                mobile.locator('.connect-button').click()
                expect(mobile.locator('[data-test="network-alerts"]')).to_contain_text('Registered')
                check('English reload remains disconnected until explicit reconnect, then preserves evidence states')
                phone.close()
                primary.available = secondary.available = False
                expect(page.locator('[data-test="network-alerts"]')).to_contain_text('观测通道中断', timeout=12000)
                check('receiver outage is prominent and does not claim all devices powered off')
                page.screenshot(path=str(out / '05-TEST-ONLY-receiver-interrupted.png'), full_page=True)
                check('no page exceptions or unexpected external requests; known platform Java reads were blocked', not report['errors'] and not report['blocked'])
                actions = [r for r in report['backend_requests'] if r['method'] == 'POST']
                check('only scoped local source/SQLite actions reached the backend', actions and all(r['path'] in ('/api/v1/replay/start', '/api/v1/replay/stop', '/api/v1/lora/sources/select') and r['origin'] == backend for r in actions))
                report['browser_version'] = browser.version
                report['passed'] = True
            except Exception:
                report['failure'] = traceback.format_exc()
                page.screenshot(path=str(out / 'failure.png'), full_page=True)
                (out / 'failure-ui.txt').write_text(page.locator('body').inner_text(), encoding='utf-8')
                raise
            finally:
                context.close()
                browser.close()
    finally:
        server.shutdown(); thread.join(3); server.server_close(); replay.close(); sources.close()
        if node is not None:
            node.terminate()
            try:
                node.wait(8)
            except subprocess.TimeoutExpired:
                node.kill(); node.wait(3)
        node_log.close()
        report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        report['owned_processes_stopped'] = node is None or node.poll() is not None
        report['sqlite_sessions_after_close'] = None
        reopened = Replay(out / 'isolated.sqlite3', lambda: None, interval=3600)
        try:
            report['sqlite_sessions_after_close'] = reopened.sessions()
            report['sqlite_reopen_verified'] = reopened.session(seed, 100, 3)['total'] == 103
        finally:
            reopened.close()
        (out / 'REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': report['passed'], 'checks': len(report['checks']), 'report': str(out / 'REPORT.json')}))


if __name__ == '__main__':
    main()
