import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { engineeringHandler, allowedEngineeringResource } from './engineering-relay.mjs'
let upstream, bridge, upstreamUrl, bridgeUrl, mode = 'json', health = 'good'
const received = []
const listen = server => new Promise((accept, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', accept) })
const close = server => new Promise(accept => { server.closeAllConnections(); server.close(accept) })
before(async () => {
  upstream = createServer(async (req, res) => {
    const chunks = []; for await (const c of req) chunks.push(c)
    received.push({ method: req.method, url: req.url, origin: req.headers.origin, cookie: req.headers.cookie, auth: req.headers.authorization, body: Buffer.concat(chunks).toString() })
    res.setHeader('Content-Type', 'application/json')
    if (req.url === '/health') return res.end(JSON.stringify({ status: 'ok', role: health === 'good' ? 'observation_only' : 'unknown_service', gateway_instance: 'isolated-test-only' }))
    if (mode === 'redirect') { res.writeHead(302, { Location: upstreamUrl + '/must-not-follow' }); return res.end() }
    if (mode === 'invalid') return res.end('<html>not JSON</html>')
    if (mode === 'large') { const body = JSON.stringify({ data: 'x'.repeat(2 * 1024 * 1024) }); res.setHeader('Content-Length', Buffer.byteLength(body)); return res.end(body) }
    if (mode === 'chunked-large') { res.write('{"data":"'); return res.end('x'.repeat(2 * 1024 * 1024) + '"}') }
    if (mode === 'down') res.statusCode = 503
    res.end(JSON.stringify({ path: req.url, error: mode === 'down' ? 'TEST_ONLY_UNAVAILABLE' : undefined, id: req.method === 'POST' ? 'test-session' : undefined }))
  })
  bridge = createServer(engineeringHandler)
  await listen(upstream); await listen(bridge)
  upstreamUrl = `http://127.0.0.1:${upstream.address().port}`; bridgeUrl = `http://127.0.0.1:${bridge.address().port}`
})
after(async () => { await close(bridge); await close(upstream) })
function call(resource = '/api/v1/lora/sources', options = {}, base = upstreamUrl) {
  return fetch(bridgeUrl + '/__baseline_engineering?base=' + encodeURIComponent(base) + '&resource=' + encodeURIComponent(resource), { ...options, headers: { 'X-Baseline-Engineering': 'operator', ...options.headers } })
}
function action(resource, value = {}, options = {}) { return call(resource, { method: 'POST', ...options, headers: { 'Content-Type': 'application/json', Origin: bridgeUrl, ...options.headers }, body: JSON.stringify(value) }) }
function raw(headers = {}, method = 'GET') {
  return new Promise((accept, reject) => {
    const req = request(bridgeUrl + '/?base=' + encodeURIComponent(upstreamUrl) + '&resource=%2Fapi%2Fv1%2Flora%2Fsources', { method, headers: { 'X-Baseline-Engineering': 'operator', ...headers } }, res => { res.resume(); accept(res.statusCode) })
    req.once('error', reject); req.end()
  })
}
test('module/server startup performs no upstream or device I/O', async () => {
  assert.equal(received.length, 0)
  const response = await call(); assert.equal(response.status, 200)
  assert.equal((await response.json()).path, '/api/v1/lora/sources')
  assert.equal(received[0].method, 'GET'); assert.equal(response.headers.get('access-control-allow-origin'), null)
})
test('only the exact observation and bounded pagination reads are admitted', async () => {
  for (const path of ['/health', '/api/v1/lora/topology', '/api/v1/fleet', '/api/v1/recovery', '/api/studio/status', '/api/v1/state', '/api/v1/timeline?after=123', '/api/pc/status', '/api/pc/inbox', '/api/pc/events', '/api/v1/replay/sessions', '/api/v1/replay/session?id=test-session&offset=100&limit=25']) assert.equal((await call(path)).status, 200, path)
})
test('source selection and recording require explicit operator origin and validated Studio health', async () => {
  for (const [path, body] of [['/api/v1/lora/sources/select', { source_id: null }], ['/api/v1/replay/start', {}], ['/api/v1/replay/stop', {}]]) {
    const before = received.length
    assert.equal((await action(path, body)).status, 200)
    assert.equal(received[before].url, '/health'); assert.equal(received[before + 1].url, path)
    assert.equal(received[before + 1].origin, upstreamUrl); assert.deepEqual(JSON.parse(received[before + 1].body), body)
  }
})
test('missing/mismatched origin, cross-site requests and wrong Host never reach the backend', async () => {
  const before = received.length
  assert.equal((await call(undefined, { headers: { 'X-Baseline-Engineering': '' } })).status, 403)
  assert.equal((await call(undefined, { headers: { Origin: 'https://evil.test' } })).status, 403)
  assert.equal((await call(undefined, { headers: { 'Sec-Fetch-Site': 'cross-site' } })).status, 403)
  assert.equal(await raw({ Host: 'evil.test' }), 403)
  assert.equal(await raw({ Host: '127.0.0.1:1' }), 403)
  assert.equal((await action('/api/v1/replay/start', {}, { headers: { Origin: '' } })).status, 403)
  assert.equal((await action('/api/v1/replay/start', {}, { headers: { Origin: 'http://localhost:' + bridge.address().port } })).status, 403)
  assert.equal(received.length, before)
})
test('flight, serial, command, Agent/demo and arbitrary POST APIs are not a part of this bridge', async () => {
  const before = received.length
  for (const path of ['/api/pc/send', '/api/v1/flight/takeoff', '/api/serial/open', '/api/studio/demo/start', '/api/studio/mode', '/api/v1/lora/send', '/api/v1/network/recording', '/api/v1/reports']) {
    assert.equal((await call(path)).status, 400, path)
    assert.equal((await action(path)).status, 400, path)
  }
  assert.equal((await call(undefined, { method: 'DELETE' })).status, 405)
  assert.equal(received.length, before)
})
test('non-loopback, credentials, prefixes and alternate transport targets are rejected', async () => {
  const before = received.length
  for (const base of ['https://127.0.0.1:8794', 'http://192.168.1.10:8794', 'http://example.test:8794', 'http://user:pass@127.0.0.1:8794', upstreamUrl + '/prefix', upstreamUrl + '?secret=1', upstreamUrl + '#frag', 'file:///secret', 'http://127.0.0.1:80']) assert.equal((await call(undefined, {}, base)).status, 400, base)
  assert.equal(received.length, before)
})
test('malformed resources, duplicated parameters and unbounded replay reads are rejected before I/O', async () => {
  const before = received.length
  for (const path of ['/api/v1/replay/session?id=x', '/api/v1/replay/session?id=x&offset=0&limit=100', '/api/v1/replay/session?id=x&id=y&offset=0&limit=25', '/api/v1/replay/session?id=../secret&offset=0&limit=25', '/api/v1/timeline?after=-1', '/api/v1/timeline?after=1&after=2', '/api/v1/fleet?unexpected=1', '/api/v1/replay/%2e%2e', '/api/v1/replay/session?id=%252fsecret&offset=0&limit=1']) assert.equal((await call(path)).status, 400, path)
  assert.equal((await fetch(bridgeUrl + '/?base=' + encodeURIComponent(upstreamUrl) + '&base=' + encodeURIComponent(upstreamUrl) + '&resource=%2Fhealth', { headers: { 'X-Baseline-Engineering': 'operator' } })).status, 400)
  assert.equal(received.length, before)
})
test('write payload shape and content type cannot tunnel a device action', async () => {
  const before = received.length
  for (const body of [{ command: 'send' }, { source_id: null, command: 'send' }, { source_id: {} }, [], null]) assert.equal((await action('/api/v1/lora/sources/select', body)).status, 400)
  assert.equal((await action('/api/v1/replay/start', { command: 'send' })).status, 400)
  assert.equal((await action('/api/v1/replay/start', {}, { headers: { 'Content-Type': 'text/plain' } })).status, 400)
  assert.equal((await action('/api/v1/lora/sources/select', { source_id: 'x'.repeat(5000) })).status, 400)
  assert.equal(received.length, before)
})
test('unknown local service does not receive a forwarded write', async () => {
  const before = received.length; health = 'bad'
  assert.equal((await action('/api/v1/replay/start')).status, 403)
  assert.equal(received.length, before + 1); assert.equal(received.at(-1).url, '/health'); health = 'good'
})
test('cookies and authorization are never copied to the local backend', async () => {
  const response = await action('/api/v1/replay/start', {}, { headers: { Cookie: 'test-private=1', Authorization: 'Bearer test-private' } })
  assert.equal(response.status, 200)
  for (const request of received.slice(-2)) { assert.equal(request.cookie, undefined); assert.equal(request.auth, undefined) }
})
test('redirects, invalid JSON and response limits are failures without fallback', async () => {
  const before = received.length; mode = 'redirect'; assert.equal((await call()).status, 502); assert.equal(received.length, before + 1)
  for (const behavior of ['invalid', 'large', 'chunked-large']) { mode = behavior; assert.equal((await call()).status, 502, behavior) }
  mode = 'down'; const response = await call(); assert.equal(response.status, 503); assert.equal((await response.json()).error, 'TEST_ONLY_UNAVAILABLE'); mode = 'json'
})
test('resource predicate is method-specific, never a catch-all proxy', () => {
  assert.equal(allowedEngineeringResource('/api/v1/replay/start', 'GET'), false)
  assert.equal(allowedEngineeringResource('/api/v1/state', 'POST'), false)
  assert.equal(allowedEngineeringResource('//example.test/api/v1/state', 'GET'), false)
})
