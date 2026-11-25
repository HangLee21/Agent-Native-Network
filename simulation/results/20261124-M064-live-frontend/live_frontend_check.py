"""Current baseline GUI versus existing real gateway. GET-only, no response fulfillments."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect

ROOT = Path(r'D:\Multi-Agent Network')
spec = importlib.util.spec_from_file_location('live_observer', ROOT / 'scripts/network-studio/live_check.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
ap = argparse.ArgumentParser()
ap.add_argument('--output', required=True)
a = ap.parse_args()
out = Path(a.output)
out.mkdir(parents=True, exist_ok=False)
base, gateway = 'http://127.0.0.1:10518', 'http://127.0.0.1:8780'
report = {'started_at': datetime.datetime.now().astimezone().isoformat(), 'passed': False,
          'frontend': base, 'gateway': gateway, 'fixtures_used': False, 'api_fulfillments': 0,
          'control_requests_sent': 0, 'blocked_requests': [], 'page_errors': [],
          'data_requests': [], 'snapshots': [], 'checks': []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='msedge')
    context = browser.new_context(viewport={'width': 1600, 'height': 1250})
    def guard(route):
        req = route.request
        parsed = urlsplit(req.url)
        allowed = req.url.startswith(base + '/') and req.method == 'GET'
        if parsed.path.startswith(('/__network_mock', '/api/')):
            allowed = False
        if parsed.path == '/__network_gateway':
            allowed = allowed and parse_qs(parsed.query) == {'base': [gateway], 'resource': ['/api/v1/lora/topology']}
            if allowed:
                report['data_requests'].append({'method': req.method, 'url': req.url})
        if not allowed:
            report['blocked_requests'].append({'method': req.method, 'url': req.url})
            return route.abort()
        route.continue_()  # No fabricated API response, not even for errors.
    context.route('**/*', guard)
    page = context.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    def received(response):
        if urlsplit(response.url).path != '/__network_gateway':
            return
        raw = response.json()
        live.reject_fake(raw)
        assert response.status == 200 and raw.get('schema') == 'lora.topology.v1'
        report['snapshots'].append({'at': datetime.datetime.now().astimezone().isoformat(), 'body': raw})
    page.on('response', received)
    def rows():
        return page.locator('[data-list-node]').evaluate_all('els => els.map(el => ({id:el.dataset.listNode,label:el.querySelector("strong").textContent.trim(),state:el.querySelector(".node-state").textContent.trim(),stateClass:el.querySelector(".node-state").className}))')
    try:
        metadata = context.request.get(base + '/FRAMEWORK_SOURCE.json').json()
        assert metadata['schema'] == 'baseline.frontend.import.v1'
        assert metadata['upstream_commit'] == 'bdadc989decf4d383b49dff2def4aa1aa0aa59b5'
        report['baseline_source_metadata_verified'] = True
        page.goto(base + '/studio.html', wait_until='networkidle')
        expect(page.locator('[data-test="real-connection"]')).to_be_visible()
        expect(page.locator('[data-list-node]')).to_have_count(0)
        assert not report['data_requests'], 'Unexpected automatic gateway reads before operator connection'
        page.get_by_role('button', name='本地网关', exact=True).click()
        page.get_by_role('textbox', name='数据服务地址', exact=True).fill(gateway)
        page.get_by_role('combobox', name='网关协议', exact=True).select_option('lora-v1')
        page.get_by_role('button', name='保存并连接', exact=True).click()
        expect(page.locator('.connection-state')).to_have_text('观测服务已连接', timeout=12000)
        expect(page.locator('[data-test="unverified-gateway"]')).to_be_visible()
        expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
        expect(page.locator('.demo-ribbon')).to_have_count(0)
        expect(page.locator('.network-error')).to_have_count(0)
        report['checks'].append('baseline source, disconnected default, explicit real gateway connection, no Mock, legacy provenance warning retained')
        report['gps_summary'] = page.locator('[data-test="gps-summary"]').inner_text()
        report['gps_drawn_nodes'] = page.locator('[data-node]').count()
        report['initial_rows'] = rows()
        report['metrics_initial'] = page.locator('.metrics').inner_text()
        page.screenshot(path=str(out / 'live-gps.png'), full_page=True)
        first_clock = page.locator('.observation-clock').inner_text()
        page.wait_for_function('(prior) => document.querySelector(".observation-clock").textContent !== prior', arg=first_clock, timeout=12000)
        report['snapshot_clock_advanced'] = True

        page.get_by_role('button', name='清晰布局', exact=True).click()
        expect(page.locator('[data-node]').first).to_be_visible()
        report['logical_drawn_nodes'] = page.locator('[data-node]').count()
        report['wifi_edges'] = page.locator('.edge:not(.lora)').count()
        report['lora_edges'] = page.locator('.edge.lora').count()
        report['logical_rows'] = rows()
        raw = report['snapshots'][-1]['body']
        expected = {str(raw['receiver']['gateway_id']).lower()}
        reporters = set()
        for item in raw['reports']:
            observer = item['report']['observer_id'].lower()
            reporters.add(observer)
            expected.add(observer)
            expected.update(n['peer_id'].lower() for n in item['report']['neighbors'])
        assert expected == {r['id'] for r in report['logical_rows']}, (expected, report['logical_rows'])
        assert report['logical_drawn_nodes'] == len(expected)
        report['reporting_ids_at_crosscheck'] = sorted(reporters)
        report['neighbor_only_ids_at_crosscheck'] = sorted(expected - reporters - {raw['receiver']['gateway_id']})
        labels = raw.get('labels') or {}
        for item in report['logical_rows']:
            label = labels.get(item['id'])
            if str(label).isdigit():
                assert item['label'] == 'NODE ' + str(label).zfill(2), item
            if item['id'] in report['neighbor_only_ids_at_crosscheck']:
                assert 'unknown' in item['stateClass'], item
        report['checks'].append('actual gateway/reporter/neighbor member IDs, numeric label mapping and unknown peer-only state match raw payload')
        page.screenshot(path=str(out / 'live-topology.png'), full_page=True)
        report['inspectors'] = {}
        for ident in sorted(expected):
            page.locator('[data-list-node="' + ident + '"]').click()
            text = page.locator('.inspector').inner_text()
            assert ident in text
            report['inspectors'][ident] = text
        if report['wifi_edges']:
            page.locator('.edge:not(.lora)').first.press('Enter')
            report['wifi_inspector'] = page.locator('.inspector').inner_text()
            assert 'LINK INSPECTOR' in report['wifi_inspector'] and '历史或未知' in report['wifi_inspector']
            page.screenshot(path=str(out / 'live-wifi-direction.png'), full_page=True)
        if report['lora_edges']:
            page.locator('.edge.lora').first.press('Enter')
            report['lora_inspector'] = page.locator('.inspector').inner_text()
            assert 'LoRa 上行' in report['lora_inspector']
            page.screenshot(path=str(out / 'live-lora-uplink.png'), full_page=True)
        expect(page.get_by_role('button', name='开始记录', exact=True)).to_be_disabled()
        expect(page.get_by_role('combobox', name='接收来源', exact=True)).to_have_count(0)
        report['checks'].append('live member and direction inspectors open; LoRa uplink is not Wi-Fi signal quality; unsupported legacy source/recording controls remain unavailable')
        page.get_by_role('button', name='暂停观测', exact=True).click()
        expect(page.locator('.connection-state')).to_have_text('观测已暂停')
        paused_clock = page.locator('.observation-clock').inner_text()
        page.wait_for_timeout(2200)  # Bounded UI pause assertion, not background-job polling.
        assert page.locator('.observation-clock').inner_text() == paused_clock
        report['pause_snapshot_stable'] = True
        page.get_by_role('button', name='继续观测', exact=True).click()
        expect(page.locator('.connection-state')).to_have_text('观测服务已连接')
        page.wait_for_function('(prior) => document.querySelector(".observation-clock").textContent !== prior', arg=paused_clock, timeout=12000)
        report['checks'].append('UI-only pause freezes snapshot and resume reads actual gateway again; no device control')
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert page.locator('.network-workspace').evaluate('(el) => el.scrollWidth <= el.clientWidth + 1')
        page.screenshot(path=str(out / 'live-mobile.png'), full_page=True)
        report['checks'].append('390px real connection and live topology remain within viewport width')
        page.set_viewport_size({'width': 1600, 'height': 1250})
        report['final_rows'] = rows()
        report['metrics_final'] = page.locator('.metrics').inner_text()
        report['source_identity'] = page.locator('.source-identity').inner_text()
        report['actual_gateway_frame_counts'] = [s['body']['receiver']['frames'] for s in report['snapshots']]
        assert len(report['snapshots']) >= 2
        assert not report['blocked_requests'] and not report['page_errors']
        report['passed'] = True
    except Exception as error:
        import traceback
        report['failure'] = traceback.format_exc()
        try:
            page.screenshot(path=str(out / 'failure.png'), full_page=True)
        except Exception:
            pass
    finally:
        report['browser_version'] = browser.version
        report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        context.close()
        browser.close()
        (out / 'REPORT.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps({'output': str(out), 'passed': report['passed'], 'members': report.get('final_rows'), 'metrics': report.get('metrics_final'), 'failure': report.get('failure'), 'frame_counts': report.get('actual_gateway_frame_counts')}, ensure_ascii=True))
assert report['passed'], report.get('failure')
