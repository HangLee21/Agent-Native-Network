import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request } from 'node:http'
import { gatewayReadHandler } from './gateway-relay.mjs'
let upstream, reader, upstreamUrl, readerUrl
let behavior = 'json'
const received = []
const listen = server => new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
const close = server => new Promise(resolve => { server.closeAllConnections(); server.close(resolve) })
before(async () => {
  upstream = createServer((req, res) => {
    received.push({ method: req.method, url: req.url, cookie: req.headers.cookie, auth: req.headers.authorization })
    if (behavior === 'redirect') { res.writeHead(302, { Location: upstreamUrl + '/blocked' }); return res.end() }
    if (behavior === 'down') { res.writeHead(503); return res.end('unavailable') }
    if (behavior === 'invalid') return res.end('<html>not JSON</html>')
    if (behavior === 'chunked-large') { res.write('{"value":"'); return res.end('x'.repeat(2 * 1024 * 1024) + '"}') }
    if (behavior === 'large') { const data = JSON.stringify({ value: 'x'.repeat(2 * 1024 * 1024) }); res.setHeader('Content-Length', Buffer.byteLength(data)); return res.end(data) }
    res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify({ schema: 'test.only', path: req.url }))
  })
  reader = createServer(gatewayReadHandler)
  await listen(upstream); await listen(reader)
  upstreamUrl = `http://127.0.0.1:${upstream.address().port}`; readerUrl = `http://127.0.0.1:${reader.address().port}`
})
after(async () => { await close(reader); await close(upstream) })
const read = (resource = '/api/v1/lora/topology', options = {}, base = upstreamUrl) => fetch(readerUrl + '/__network_gateway?base=' + encodeURIComponent(base) + '&resource=' + encodeURIComponent(resource), { headers: { 'X-Network-Gateway': 'readonly' }, ...options })

// fetch normalizes/ignores Host; use HTTP request when testing exact wire headers.
const rawRead = headers => new Promise((resolve, reject) => {
  const req = request(readerUrl + '/__network_gateway?base=' + encodeURIComponent(upstreamUrl) + '&resource=%2Fapi%2Fv1%2Flora%2Ftopology', { headers: { 'X-Network-Gateway': 'readonly', ...headers } }, res => { res.resume(); resolve(res.statusCode) })
  req.once('error', reject); req.end()
})

test('reader startup does not contact anything and a permitted read is GET-only', async () => {
  assert.deepEqual(received, [])
  const res = await read(); assert.equal(res.status, 200); assert.equal((await res.json()).path, '/api/v1/lora/topology')
  assert.equal(received.at(-1).method, 'GET'); assert.equal(res.headers.get('access-control-allow-origin'), null)
})
test('cross-origin, missing opt-in and forged Host requests never reach upstream', async () => {
  const count = received.length
  assert.equal((await read(undefined, { headers: {} })).status, 403)
  assert.equal((await read(undefined, { headers: { 'X-Network-Gateway': 'readonly', Origin: 'https://evil.test' } })).status, 403)
  assert.equal(await rawRead({ Host: 'evil.test' }), 403)
  assert.equal(await rawRead({ 'Sec-Fetch-Site': 'cross-site' }), 403)
  assert.equal(received.length, count)
})
test('POST and all flight/source/recording/serial endpoints are rejected before forwarding', async () => {
  const count = received.length
  assert.equal((await read(undefined, { method: 'POST', body: '{}' })).status, 405)
  for (const resource of ['/api/v1/flight/takeoff', '/api/v1/lora/sources/select', '/api/v1/network/recording', '/api/v1/network/scenario', '/api/serial', '/api/v1/network/replays/../secrets', '/api/v1/network/replays/%2Fetc', '/api/v1/network/replays/%2e%2e', '/api/v1/network/replays/foo\\bar', '/api/v1/network/replays/id\n']) {
    assert.equal((await read(resource)).status, 400, resource)
  }
  assert.equal(received.length, count)
})
test('credential URLs, unsupported schemes, duplicate parameters and query targets are rejected', async () => {
  const count = received.length
  for (const base of ['file:///etc', 'http://user:pass@127.0.0.1', upstreamUrl + '?action=send', upstreamUrl + '#fragment']) assert.equal((await read(undefined, {}, base)).status, 400)
  const params = '?base=' + encodeURIComponent(upstreamUrl) + '&base=' + encodeURIComponent(upstreamUrl) + '&resource=%2Fapi%2Fv1%2Flora%2Ftopology'
  assert.equal((await fetch(readerUrl + params, { headers: { 'X-Network-Gateway': 'readonly' } })).status, 400)
  assert.equal(received.length, count)
})
test('browser cookies and authorization never reach the gateway', async () => {
  const res = await read('/api/v1/network/snapshot', { headers: { 'X-Network-Gateway': 'readonly', Cookie: 'test-only=private', Authorization: 'Bearer test-only' } })
  assert.equal(res.status, 200); assert.equal(received.at(-1).cookie, undefined); assert.equal(received.at(-1).auth, undefined)
})
test('redirects are not followed and never silently change a configured target', async () => {
  behavior = 'redirect'; const count = received.length
  assert.equal((await read()).status, 502); assert.equal(received.length, count + 1); behavior = 'json'
})
test('invalid JSON, oversized responses and upstream errors remain explicit failures', async () => {
  behavior = 'invalid'; assert.equal((await read()).status, 502)
  behavior = 'large'; assert.equal((await read()).status, 413)
  behavior = 'chunked-large'; assert.equal((await read()).status, 413)
  behavior = 'down'; assert.equal((await read()).status, 503)
  behavior = 'json'
})
test('normalized capabilities and replay are read-only allowed resources', async () => {
  for (const resource of ['/api/v1/network/capabilities', '/api/v1/network/replays', '/api/v1/network/replays/test-id']) assert.equal((await read(resource)).status, 200)
})
