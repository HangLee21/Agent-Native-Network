"""Real-only UI observation. Never intercepts/fulfills API data and never sends a control request."""
import argparse
import datetime
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument('--output', required=True)
args = ap.parse_args()
out = Path(args.output)
out.mkdir(parents=True, exist_ok=False)
base = 'http://127.0.0.1:5188'
report = {'started_at': datetime.datetime.now().astimezone().isoformat(), 'passed': False,
          'fixtures_used': False, 'api_fulfillments': 0, 'control_requests_sent': 0,
          'gateway': 'http://127.0.0.1:8780', 'page_errors': [], 'blocked_requests': [], 'data_requests': []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='msedge')
    context = browser.new_context(viewport={'width': 1600, 'height': 1550})
    def guard(route):
        req = route.request
        if not req.url.startswith(base + '/') or req.method != 'GET':
            report['blocked_requests'].append({'method': req.method, 'url': req.url})
            return route.abort()
        parsed = urlsplit(req.url)
        if parsed.path.startswith('/__network_mock') or parsed.path.startswith('/api/'):
            report['blocked_requests'].append({'method': req.method, 'url': req.url})
            return route.abort()
        if parsed.path == '/__network_gateway':
            query = parse_qs(parsed.query)
            if query != {'base': ['http://127.0.0.1:8780'], 'resource': ['/api/v1/lora/topology']}:
                report['blocked_requests'].append({'method': req.method, 'url': req.url})
                return route.abort()
            report['data_requests'].append({'method': req.method, 'url': req.url})
        route.continue_()
    context.route('**/*', guard)
    page = context.new_page()
    page.on('pageerror', lambda err: report['page_errors'].append(str(err)))
    try:
        page.goto(base + '/studio.html', wait_until='networkidle')
        expect(page.locator('[data-test="real-connection"]')).to_be_visible()
        expect(page.locator('[data-list-node]')).to_have_count(0)
        page.get_by_role('button', name='本地网关', exact=True).click()
        page.get_by_role('textbox', name='数据服务地址', exact=True).fill(report['gateway'])
        page.get_by_role('button', name='保存并连接', exact=True).click()
        expect(page.locator('.connection-state')).to_have_text('观测服务已连接', timeout=12000)
        expect(page.locator('[data-test="unverified-gateway"]')).to_be_visible()
        expect(page.locator('[data-test="network-synthetic"]')).to_have_count(0)
        expect(page.locator('.demo-ribbon')).to_have_count(0)
        expect(page.locator('.network-error')).to_have_count(0)
        report['gps_summary'] = page.locator('[data-test="gps-summary"]').inner_text()
        report['gps_drawn_nodes'] = page.locator('[data-node]').count()
        report['members'] = [name.strip() for name in page.locator('[data-list-node] .node-identity strong').all_text_contents()]
        report['recent_member_count_including_gateway'] = page.locator('.node-state.recent').count()
        report['unobserved_member_count_including_gateway'] = page.locator('.node-state.unknown').count()
        report['source_identity'] = page.locator('.source-identity').inner_text()
        assert len(report['members']) > 1, 'No network members observed'
        assert all(n == 'GATEWAY' or n.startswith('NODE ') for n in report['members'])
        page.screenshot(path=str(out / 'live-gps.png'), full_page=True)
        clock = page.locator('.observation-clock').inner_text()
        page.wait_for_function('(prior) => document.querySelector(".observation-clock").textContent !== prior', arg=clock, timeout=12000)
        report['live_clock_advanced'] = True
        page.get_by_role('button', name='清晰布局', exact=True).click()
        report['logical_drawn_nodes'] = page.locator('[data-node]').count()
        report['wifi_edges'] = page.locator('.edge:not(.lora)').count()
        report['lora_edges'] = page.locator('.edge.lora').count()
        page.locator('[data-list-node]').nth(1).click()
        report['node_inspector'] = page.locator('.inspector').inner_text()
        page.screenshot(path=str(out / 'live-logical.png'), full_page=True)
        if page.locator('.edge:not(.lora)').count():
            page.locator('.edge:not(.lora)').first.press('Enter')
            report['wifi_inspector'] = page.locator('.inspector').inner_text()
            assert 'LINK INSPECTOR' in report['wifi_inspector'], 'Wi-Fi sample details did not open'
            page.screenshot(path=str(out / 'live-wifi-sample.png'), full_page=True)
        assert report['data_requests'] and not report['blocked_requests'] and not report['page_errors']
        report['passed'] = True
    except Exception as error:
        report['error'] = '%s: %r' % (type(error).__name__, error)
        try:
            page.screenshot(path=str(out / 'failure.png'), full_page=True)
        except Exception:
            pass
    finally:
        report['browser_version'] = browser.version
        context.close()
        browser.close()
        (out / 'REPORT.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'report': str(out / 'REPORT.json'), 'passed': report['passed'], 'error': report.get('error'), 'members': report.get('members'), 'gps': report.get('gps_summary')}, ensure_ascii=True))
assert report['passed'], report.get('error')
