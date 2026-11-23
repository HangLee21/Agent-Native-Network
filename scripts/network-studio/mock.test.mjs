import { after, before, test } from 'node:test'
import assert from 'node:assert/strict'
import { createNetworkMock, makeSnapshot, SCENARIOS } from './mock.mjs'
let fixture
before(async () => { fixture = await createNetworkMock({ port: 0 }) })
after(async () => { await fixture.close() })
const get = path => fetch(fixture.url + '/api/v1/network' + path)
const post = (path, data, origin) => fetch(fixture.url + '/api/v1/network' + path, { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin ?? fixture.url }, body: JSON.stringify(data) })

test('all fixtures are synthetic and include no default physical bindings', () => {
  for (const scenario of SCENARIOS) {
    const snapshot = makeSnapshot({ scenario })
    assert.equal(snapshot.provenance, 'synthetic')
    assert.ok(snapshot.nodes.every(n => n.binding === null))
    assert.ok(snapshot.nodes.filter(n => n.role !== 'gateway').every(n => n.role === 'node' && /^NODE \d+$/.test(n.label) && n.tag === undefined))
    assert.equal(snapshot.nodes.length, scenario === 'empty' ? 0 : scenario === 'dense' ? 31 : 6)
    if (scenario === 'no-gps') assert.ok(snapshot.nodes.every(n => n.position === null))
    if (scenario === 'interrupted') assert.equal(snapshot.receiver.state, 'unavailable')
  }
})
test('capabilities and snapshots carry source identity and instance', async () => {
  const cap = await (await get('/capabilities')).json(), snapshot = await (await get('/snapshot')).json()
  assert.equal(cap.mock, true); assert.equal(snapshot.sourceId, cap.selectedSourceId)
  assert.match(snapshot.instanceId, /^mock-/)
})
test('unknown state and external-origin writes fail without side effects', async () => {
  assert.equal((await post('/scenario', { scenario: 'real-hardware' })).status, 400)
  assert.equal((await post('/scenario', { scenario: 'dense' }, 'https://evil.example')).status, 403)
  assert.equal((await fetch(fixture.url + '/api/v1/network/scenario', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"scenario":"dense"}' })).status, 403)
  assert.equal((await (await get('/capabilities')).json()).scenario, 'nominal')
})
test('source changes increment epoch and never keep old-source nodes', async () => {
  const first = await (await get('/snapshot')).json()
  assert.equal((await post('/source', { sourceId: 'synthetic-field' })).status, 200)
  const next = await (await get('/snapshot')).json()
  assert.ok(next.epoch > first.epoch); assert.notEqual(next.sourceId, first.sourceId)
  assert.ok(next.nodes.filter(n => n.role !== 'gateway').every(n => n.id.startsWith('02:00:00:02:')))
})
test('scenarios provide explicit empty and interrupted observations', async () => {
  await post('/scenario', { scenario: 'empty' })
  assert.deepEqual((await (await get('/snapshot')).json()).nodes, [])
  await post('/scenario', { scenario: 'interrupted' })
  assert.equal((await (await get('/snapshot')).json()).receiver.state, 'unavailable')
  await post('/scenario', { scenario: 'nominal' })
})
test('recordings and replay are in-memory snapshots, not flight actions', async () => {
  const before = await (await get('/replays')).json()
  assert.ok(before.find(s => s.id === 'sample-session').frames > 0)
  const r = await (await post('/recording', { action: 'start' })).json()
  assert.match(r.id, /^recording-/)
  await get('/snapshot')
  assert.equal((await post('/recording', { action: 'start' })).status, 409)
  assert.equal((await (await post('/recording', { action: 'stop' })).json()).id, null)
  const replay = await (await get('/replays/' + r.id)).json()
  assert.ok(replay.frames.length >= 2); assert.ok(replay.frames.every(s => s.provenance === 'synthetic'))
  assert.equal((await get('/replays/missing')).status, 404)
})
test('bounded single-field JSON and valid content type are mandatory', async () => {
  assert.equal((await post('/scenario', { scenario: 'nominal', extra: true })).status, 400)
  assert.equal((await post('/scenario', [])).status, 400)
  const plain = await fetch(fixture.url + '/api/v1/network/scenario', { method: 'POST', headers: { Origin: fixture.url, 'Content-Type': 'text/plain' }, body: '{"scenario":"dense"}' })
  assert.equal(plain.status, 415)
  const large = await post('/scenario', { scenario: 'x'.repeat(3000) })
  assert.equal(large.status, 413)
  const broken = await fetch(fixture.url + '/api/v1/network/scenario', { method: 'POST', headers: { Origin: fixture.url, 'Content-Type': 'application/json' }, body: '{broken}' })
  assert.equal(broken.status, 400)
})
test('preflight is restricted to exact loopback origins without wildcard', async () => {
  const good = await fetch(fixture.url + '/api/v1/network/scenario', { method: 'OPTIONS', headers: { Origin: fixture.url } })
  assert.equal(good.status, 204); assert.equal(good.headers.get('Access-Control-Allow-Origin'), fixture.url)
  const evil = await fetch(fixture.url + '/api/v1/network/scenario', { method: 'OPTIONS', headers: { Origin: 'https://evil.example' } })
  assert.equal(evil.status, 403); assert.equal(evil.headers.get('Access-Control-Allow-Origin'), null)
})
test('malformed replay escapes cannot crash the mock server', async () => {
  assert.equal((await get('/replays/%E0%A4%A')).status, 400)
  assert.equal((await get('/snapshot')).status, 200)
})
test('no non-network API, hardware or flight endpoint is exposed', async () => {
  for (const path of ['/api/v1/flight/takeoff', '/api/v1/drones', '/api/v1/lora/sources/select', '/health']) {
    assert.equal((await fetch(fixture.url + path)).status, 404)
  }
})
