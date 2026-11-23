/** Disposable HTTP-only development fixture. No hardware libraries, device sockets or flight endpoints. */
import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'
import { pathToFileURL } from 'node:url'

export const SCENARIOS = ['nominal', 'dense', 'empty', 'interrupted', 'stale', 'no-gps']
const SOURCES = [{ id: 'synthetic-lab', label: 'Lab gateway / MOCK' }, { id: 'synthetic-field', label: 'Field gateway / MOCK' }]
const PREFIX = '/api/v1/network'

export function makeSnapshot({ scenario = 'nominal', sourceId = SOURCES[0].id, epoch = 0, instanceId = 'fixture', at = Date.now(), frame = 0 } = {}) {
  const count = scenario === 'empty' ? 0 : scenario === 'dense' ? 30 : 5
  const nodes = []
  const gatewayId = sourceId + ':gateway'
  if (count) nodes.push({ id: gatewayId, label: 'Gateway', role: 'gateway', reportedAt: at - 150, position: scenario === 'no-gps' ? null : { lat: 40.001, lon: 116.326, observedAt: at - 150, source: 'synthetic' }, batteryPercent: null, radio: { rssiDbm: null, snrDb: null, channel: null, frequencyHz: null }, binding: null })
  for (let i = 1; i <= count; i++) {
    const id = `02:00:00:${sourceId === SOURCES[0].id ? '01' : '02'}:00:${i.toString(16).padStart(2, '0')}`
    const age = scenario === 'stale' && i % 2 ? 45000 + i * 300 : 500 + (i * 773 + frame * 53) % 3500
    const angle = i / Math.max(1, count) * Math.PI * 2 + frame * .01
    nodes.push({
      id, label: `NODE ${String(i).padStart(2, '0')}`,
      role: 'node', reportedAt: i === count && scenario === 'dense' ? null : at - age,
      position: scenario === 'no-gps' || i % 5 === 0 ? null : { lat: 40.001 + Math.sin(angle) * .0012, lon: 116.326 + Math.cos(angle) * .0018, observedAt: at - age, source: 'synthetic' },
      batteryPercent: i <= 3 ? 92 - i * 9 : null,
      radio: { rssiDbm: i % 7 === 0 ? null : -63 - (i * 7 + frame) % 31, snrDb: i % 7 === 0 ? null : Number((8.5 - i % 7 * .8).toFixed(1)), channel: i % 3, frequencyHz: 470300000 + i % 3 * 200000 },
      binding: null,
    })
  }
  const links = []
  for (let i = 1; i < nodes.length; i++) {
    const n = nodes[i]
    links.push({ id: `lora:${n.id}`, from: n.id, to: gatewayId, kind: 'lora', state: 'oneway', sampledAt: n.reportedAt, validForMs: 30000, rssiDbm: n.radio.rssiDbm, snrDb: n.radio.snrDb, channel: n.radio.channel })
    const next = nodes[i === nodes.length - 1 ? 1 : i + 1]
    if (next && next.id !== n.id) {
      links.push({ id: `wifi:${next.id}:${n.id}`, from: next.id, to: n.id, kind: 'wifi', state: scenario === 'stale' && i % 2 ? 'lost' : frame >= 12 && frame <= 23 && i === 2 ? 'lost' : 'mutual', sampledAt: n.reportedAt, validForMs: 12000, rssiDbm: i % 4 === 0 ? null : -49 - (i * 9) % 28, snrDb: null, channel: 6 })
      if (count >= 10) for (let j = i + 2; j <= Math.min(i + 4, nodes.length - 1); j++) links.push({ id: `wifi:${nodes[j].id}:${n.id}`, from: nodes[j].id, to: n.id, kind: 'wifi', state: 'oneway', sampledAt: n.reportedAt, validForMs: 12000, rssiDbm: -74, snrDb: null, channel: 6 })
    }
  }
  const events = nodes.slice(1, 5).map((n, i) => ({ id: `${frame}:report:${n.id}`, at: at - 7000 + i * 1500, kind: 'report', nodeId: n.id, code: 'report_received' }))
  if (nodes[2]) events.push({ id: `${frame}:link`, at: at - 700, kind: 'link', nodeId: nodes[2].id, code: 'link_changed' })
  if (scenario === 'interrupted') events.push({ id: `${frame}:receiver`, at: at - 100, kind: 'receiver', nodeId: null, code: 'receiver_interrupted' })
  return { schema: 'network.snapshot.v1', provenance: 'synthetic', instanceId, sourceId, epoch, observedAt: at, reportTimeoutMs: 30000,
    receiver: { id: gatewayId, label: sourceId === SOURCES[0].id ? 'Lab gateway / MOCK' : 'Field gateway / MOCK', state: scenario === 'interrupted' ? 'unavailable' : scenario === 'empty' ? 'waiting' : 'receiving', receivedCount: count ? 1280 + frame * count : 0 }, nodes, links, events }
}

export async function createNetworkMock({ port = 18081, webPort = 5188 } = {}) {
  const instanceId = 'mock-' + randomUUID()
  const state = { scenario: 'nominal', sourceId: SOURCES[0].id, epoch: 0, frame: 0 }
  const sessions = new Map()
  let recording = null
  const baseTime = Date.now() - 45000
  sessions.set('sample-session', { id: 'sample-session', label: 'Sample observation / MOCK', startedAt: baseTime,
    frames: Array.from({ length: 41 }, (_, frame) => makeSnapshot({ ...state, instanceId: instanceId + '-sample', at: baseTime + frame * 1000, frame, scenario: frame >= 24 && frame <= 29 ? 'interrupted' : frame >= 12 && frame <= 23 ? 'stale' : 'nominal' })) })
  let actualPort = port
  const localHosts = () => new Set([`127.0.0.1:${actualPort}`, `localhost:${actualPort}`, `127.0.0.1:${webPort}`, `localhost:${webPort}`])
  const allowedOrigins = () => new Set([...localHosts()].map(host => 'http://' + host))
  const capabilities = () => ({ schema: 'network.capabilities.v1', mock: true, recording: true, sourceSelection: true, sources: SOURCES, selectedSourceId: state.sourceId, scenario: state.scenario })
  const takeSnapshot = () => {
    const snapshot = makeSnapshot({ ...state, instanceId, frame: state.frame++ })
    if (recording) {
      const session = sessions.get(recording)
      if (session.frames.length < 600) session.frames.push(snapshot)
    }
    return snapshot
  }
  const server = createServer(async (req, res) => {
    const origin = req.headers.origin
    const send = (code, value) => {
      if (res.writableEnded) return
      res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
        ...(origin && allowedOrigins().has(origin) ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {}) })
      res.end(JSON.stringify(value))
    }
    if (!localHosts().has(req.headers.host)) return send(403, { error: 'Loopback development host required' })
    const path = new URL(req.url, `http://127.0.0.1:${actualPort}`).pathname
    if (!path.startsWith(PREFIX + '/')) return send(404, { error: 'Network fixture only; no flight or device control endpoint' })
    if (req.method === 'OPTIONS') {
      if (!origin || !allowedOrigins().has(origin)) return send(403, { error: 'Origin not allowed' })
      res.writeHead(204, { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Methods': 'GET, POST', 'Access-Control-Allow-Headers': 'Content-Type', Vary: 'Origin' }); return res.end()
    }
    if (req.method === 'GET') {
      if (path === PREFIX + '/capabilities') return send(200, capabilities())
      if (path === PREFIX + '/snapshot') return send(200, takeSnapshot())
      if (path === PREFIX + '/replays') return send(200, [...sessions.values()].map(s => ({ id: s.id, label: s.label, startedAt: s.startedAt, frames: s.frames.length, synthetic: true })))
      if (path.startsWith(PREFIX + '/replays/')) {
        let id
        try { id = decodeURIComponent(path.slice((PREFIX + '/replays/').length)) } catch { return send(400, { error: 'Malformed replay identity' }) }
        const session = sessions.get(id)
        return session ? send(200, { schema: 'network.replay.v1', id, frames: session.frames }) : send(404, { error: 'Unknown replay' })
      }
      return send(404, { error: 'Unknown network endpoint' })
    }
    if (req.method !== 'POST') return send(405, { error: 'Method not allowed' })
    if (!origin || !allowedOrigins().has(origin) || new URL(origin).host !== req.headers.host) return send(403, { error: 'Explicit loopback same-origin request required' })
    if (req.headers['content-type']?.split(';')[0] !== 'application/json' || req.headers['transfer-encoding']) return send(415, { error: 'Bounded JSON required' })
    const length = Number(req.headers['content-length'])
    if (!Number.isSafeInteger(length) || length < 2 || length > 2048) return send(413, { error: 'JSON limit is 2048 bytes' })
    let body
    try {
      let data = ''; for await (const chunk of req) { data += chunk; if (Buffer.byteLength(data) > 2048) return send(413, { error: 'JSON too large' }) }
      body = JSON.parse(data)
      if (!body || Array.isArray(body) || typeof body !== 'object' || Object.keys(body).length !== 1) throw new Error('object required')
    } catch { return send(400, { error: 'Invalid JSON object' }) }
    if (path === PREFIX + '/source') {
      if (!SOURCES.some(s => s.id === body.sourceId)) return send(400, { error: 'Unknown synthetic source' })
      state.sourceId = body.sourceId; state.epoch++; return send(200, capabilities())
    }
    if (path === PREFIX + '/scenario') {
      if (!SCENARIOS.includes(body.scenario)) return send(400, { error: 'Unknown synthetic scenario' })
      state.scenario = body.scenario; state.epoch++; return send(200, capabilities())
    }
    if (path === PREFIX + '/recording') {
      if (body.action === 'start') {
        if (recording) return send(409, { error: 'Already recording' })
        const id = 'recording-' + randomUUID()
        sessions.set(id, { id, label: `Local capture ${new Date().toISOString().slice(11, 19)} / MOCK`, startedAt: Date.now(), frames: [] })
        recording = id; takeSnapshot(); return send(200, { id })
      }
      if (body.action === 'stop') { recording = null; return send(200, { id: null }) }
      return send(400, { error: 'Unknown recording action' })
    }
    return send(404, { error: 'Unknown network endpoint' })
  })
  server.requestTimeout = 8000
  server.headersTimeout = 8000
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', resolve) })
  actualPort = server.address().port
  return { server, url: `http://127.0.0.1:${actualPort}`, close: () => new Promise((resolve, reject) => { server.closeAllConnections(); server.close(e => e ? reject(e) : resolve()) }) }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const mock = await createNetworkMock({ port: Number(process.env.NETWORK_MOCK_PORT || 18081) })
  console.log('SYNTHETIC NETWORK ONLY: ' + mock.url)
  const stop = async () => { await mock.close(); process.exit(0) }
  process.once('SIGINT', stop); process.once('SIGTERM', stop)
}
