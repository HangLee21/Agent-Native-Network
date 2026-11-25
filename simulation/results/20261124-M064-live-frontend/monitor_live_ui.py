"""Bounded passive live UI state correlation. No source fixtures and no device controls."""
import datetime
import importlib.util
import json
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from playwright.sync_api import sync_playwright, expect

root = Path(r'D:\Multi-Agent Network')
spec = importlib.util.spec_from_file_location('live_reader', root / 'scripts/network-studio/live_check.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=False)
base, gateway = 'http://127.0.0.1:10518', 'http://127.0.0.1:8780'
report = {'started_at': datetime.datetime.now().astimezone().isoformat(), 'passed': False,
          'duration_s': 90, 'fixtures_used': False, 'api_fulfillments': 0, 'control_requests_sent': 0,
          'samples': [], 'blocked': [], 'page_errors': [], 'raw_responses': []}
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel='msedge')
    context = browser.new_context(viewport={'width': 1600, 'height': 1250})
    def guard(route):
        req = route.request
        u = urlsplit(req.url)
        ok = req.method == 'GET' and req.url.startswith(base + '/') and not u.path.startswith(('/api/', '/__network_mock'))
        if u.path == '/__network_gateway':
            ok = ok and parse_qs(u.query) == {'base': [gateway], 'resource': ['/api/v1/lora/topology']}
        if not ok:
            report['blocked'].append({'method': req.method, 'url': req.url})
            return route.abort()
        route.continue_()
    context.route('**/*', guard)
    page = context.new_page()
    page.on('pageerror', lambda error: report['page_errors'].append(str(error)))
    def received(response):
        if urlsplit(response.url).path == '/__network_gateway':
            raw = response.json()
            live.reject_fake(raw)
            assert response.status == 200 and raw['schema'] == 'lora.topology.v1'
            report['raw_responses'].append({'mono': time.monotonic(), 'at': datetime.datetime.now().astimezone().isoformat(), 'body': raw})
    page.on('response', received)
    stale_shot = False
    try:
        page.goto(base + '/studio.html', wait_until='networkidle')
        page.get_by_role('button', name='本地网关', exact=True).click()
        page.get_by_role('textbox', name='数据服务地址', exact=True).fill(gateway)
        page.get_by_role('button', name='保存并连接', exact=True).click()
        expect(page.locator('.connection-state')).to_have_text('观测服务已连接', timeout=12000)
        page.get_by_role('button', name='清晰布局', exact=True).click()
        start = time.monotonic()
        for index in range(19):
            wait = max(0, start + index * 5 - time.monotonic())
            page.wait_for_timeout(wait * 1000)
            # Let the fulfilled *real* response render; no response is fabricated by this script.
            page.evaluate('() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
            response_version = len(report['raw_responses'])
            latest = report['raw_responses'][-1]
            raw = latest['body']
            age_since_response_ms = max(0, (time.monotonic() - latest['mono']) * 1000)
            rows = page.locator('[data-list-node]').evaluate_all('els => els.map(el => ({id:el.dataset.listNode,label:el.querySelector("strong").textContent.trim(),state:el.querySelector(".node-state").textContent.trim(),stateClass:el.querySelector(".node-state").className}))')
            by_id = {r['id']: r for r in rows}
            item = {'at': datetime.datetime.now().astimezone().isoformat(), 'elapsed_s': round(time.monotonic()-start, 3), 'gateway_frames': raw['receiver']['frames'], 'rows': rows, 'reporters': [], 'metrics': page.locator('.metrics').inner_text()}
            for record in raw['reports']:
                n = record['report']; ident = n['observer_id']; age = record.get('pc_receive_age_ms')
                assert ident in by_id
                comparable = len(report['raw_responses']) == response_version and raw['receiver'].get('gateway_observed') is True and isinstance(age, (int,float))
                # Only assert away from the 30s boundary; response/render timing gets a 2s safety margin.
                corrected = age + age_since_response_ms if comparable else None
                timeout = raw['receiver'].get('recent_threshold_ms',30000)
                if comparable and corrected > timeout + 2000:
                    assert 'stale' in by_id[ident]['stateClass'], (ident, corrected, by_id[ident])
                    if not stale_shot:
                        page.locator('[data-list-node="'+ident+'"]').click()
                        page.screenshot(path=str(out/'observed-stale-node.png'), full_page=True)
                        stale_shot = True
                if comparable and corrected < timeout - 2000:
                    assert 'recent' in by_id[ident]['stateClass'], (ident, corrected, by_id[ident])
                item['reporters'].append({'id': ident, 'node_number': n.get('node_number'), 'boot':n.get('observer_boot'), 'sequence':n.get('report_seq'), 'raw_report_age_ms':age, 'ui':by_id[ident]})
            report['samples'].append(item)
            print(json.dumps({'sample':index,'frames':item['gateway_frames'],'nodes':[(n['node_number'],n['ui']['state'],n['raw_report_age_ms']) for n in item['reporters']]},ensure_ascii=True),flush=True)
        page.screenshot(path=str(out/'live-final-topology.png'),full_page=True)
        report['stale_ui_observed'] = stale_shot
        assert not report['blocked'] and not report['page_errors']
        report['passed'] = True
    except Exception:
        import traceback
        report['failure'] = traceback.format_exc()
        try: page.screenshot(path=str(out/'failure.png'),full_page=True)
        except Exception: pass
    finally:
        report['finished_at'] = datetime.datetime.now().astimezone().isoformat()
        context.close();browser.close()
        (out/'REPORT.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({'passed':report['passed'],'stale_ui_observed':report.get('stale_ui_observed'),'failure':report.get('failure'),'samples':len(report['samples'])},ensure_ascii=True))
assert report['passed'],report.get('failure')
