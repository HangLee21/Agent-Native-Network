import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { request } from 'node:http'
import { createBaselineStatic } from './serve.mjs'
let app
before(async () => { app = await createBaselineStatic({ port: 0 }) })
after(async () => { await app?.close() })
const raw = (path, headers = {}, method = 'GET') => new Promise((accept, reject) => {
  const req = request(app.url, { path, method, headers }, res => { const chunks = []; res.on('data', c => chunks.push(c)); res.on('end', () => accept({ status: res.statusCode, headers: res.headers, text: Buffer.concat(chunks).toString() })) })
  req.once('error', reject); req.end()
})
test('serves built Vue and hashed assets without a Vite or Mock server', async () => {
  const response = await fetch(app.url + '/studio.html'); assert.equal(response.status, 200)
  assert.match(response.headers.get('content-type'), /text\/html/)
  const html = await response.text(), script = html.match(/src="([^"]+\.js)"/)[1]
  const js = await fetch(app.url + script); assert.equal(js.status, 200); assert.match(js.headers.get('content-type'), /javascript/)
  assert.equal(response.headers.get('access-control-allow-origin'), null)
  assert.equal(response.headers.get('cache-control'), 'no-store')
})
test('built real config advertises same-origin bridges but does not auto-connect', async () => {
  const config = await (await fetch(app.url + '/network-config.json')).json()
  assert.equal(config.enabled, false); assert.equal(config.gatewayRelayPath, '/__network_gateway'); assert.equal(config.engineeringRelayPath, '/__baseline_engineering')
  assert.equal((await (await fetch(app.url + '/network-mock-config.json')).json()).enabled, false)
  assert.equal((await fetch(app.url + '/mock-studio.html')).status, 404)
})
test('HEAD serves metadata only and the original import identity remains accessible', async () => {
  const head = await fetch(app.url + '/studio.html', { method: 'HEAD' }); assert.equal(head.status, 200); assert.equal(await head.text(), ''); assert.ok(Number(head.headers.get('content-length')) > 0)
  const metadata = await fetch(app.url + '/FRAMEWORK_SOURCE.json'); assert.equal(metadata.status, 200); assert.equal(typeof await metadata.json(), 'object')
})
test('unknown API and control paths never fall back to a successful SPA page', async () => {
  for (const path of ['/api/v1/network/snapshot', '/api/pc/send', '/__unknown']) { const response = await fetch(app.url + path); assert.equal(response.status, 404); assert.match(response.headers.get('content-type'), /application\/json/) }
  assert.equal((await raw('/api/v1/flight/takeoff', {}, 'POST')).status, 405)
})
test('raw, encoded and double-encoded traversal, hidden paths and absolute URLs are rejected', async () => {
  for (const path of ['/../package.json', '/assets/%2e%2e/%2e%2e/package.json', '/assets/%252e%252e/package.json', '/assets/..%5c..%5cpackage.json', '/.git/config', '/%00', '/bad%encoding', 'http://evil.test/studio.html']) assert.equal((await raw(path)).status, 400, path)
})
test('a forged DNS-rebinding Host is denied even for static assets', async () => {
  assert.equal((await raw('/studio.html', { Host: 'evil.test:' + app.server.address().port })).status, 403)
})
test('built UI retains both independent bridge permission boundaries', async () => {
  const q = '?base=http%3A%2F%2F127.0.0.1%3A8794&resource=%2Fapi%2Fv1%2Flora%2Ftopology'
  assert.equal((await raw('/__network_gateway' + q, { 'X-Network-Gateway': 'readonly' }, 'POST')).status, 405)
  assert.equal((await raw('/__baseline_engineering' + q)).status, 403)
  assert.equal((await raw('/__baseline_engineering?base=http%3A%2F%2F127.0.0.1%3A8794&resource=%2Fapi%2Fv1%2Freplay%2Fstart', { 'X-Baseline-Engineering': 'operator' }, 'POST')).status, 403)
})
