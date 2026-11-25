/** Local operator API. Separate from the immutable GET-only gateway bridge. No device control. */
const MAX = 2 * 1024 * 1024
const reads = new Set(['/health', '/api/v1/lora/topology', '/api/v1/lora/sources', '/api/v1/fleet', '/api/v1/recovery', '/api/studio/status', '/api/v1/state', '/api/pc/status', '/api/pc/inbox', '/api/pc/events', '/api/v1/replay/sessions'])
const writes = new Set(['/api/v1/lora/sources/select', '/api/v1/replay/start', '/api/v1/replay/stop'])
export function allowedEngineeringResource(resource, method) {
  if (typeof resource !== 'string' || !resource.startsWith('/') || /[\\\u0000-\u0020#]|%2f|%5c|%2e|\.\./i.test(resource)) return false
  const url = new URL(resource, 'http://local')
  if (method === 'POST') return writes.has(resource)
  if (method !== 'GET') return false
  if (reads.has(resource)) return true
  const q = url.searchParams
  if ([...q.keys()].some(k => q.getAll(k).length !== 1)) return false
  if (url.pathname === '/api/v1/timeline') return [...q.keys()].every(k => k === 'after') && /^\d{1,15}$/.test(q.get('after') || '0')
  if (url.pathname === '/api/v1/replay/session') return [...q.keys()].sort().join(',') === 'id,limit,offset' && /^[a-zA-Z0-9_-]{1,128}$/.test(q.get('id') || '') && /^\d{1,12}$/.test(q.get('offset') || '') && /^(?:[1-9]|1\d|2[0-5])$/.test(q.get('limit') || '')
  return false
}
async function jsonBody(response, controller) {
  if (Number(response.headers.get('content-length') || 0) > MAX) { controller.abort(); throw new Error('Response limit') }
  const chunks = []; let total = 0
  if (!response.body) throw new Error('Empty JSON')
  for await (const chunk of response.body) {
    total += chunk.length
    if (total > MAX) { controller.abort(); throw new Error('Response limit') }
    chunks.push(chunk)
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8'))
}
export function engineeringHandler(req, res) {
  const send = (code, value) => {
    if (res.destroyed || res.writableEnded) return
    res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Connection': 'close' })
    res.end(JSON.stringify(value))
  }
  let base, resource, origin
  try {
    const local = new URL('http://' + req.headers.host)
    origin = local.origin
    const count = name => req.rawHeaders.filter((v, i) => i % 2 === 0 && v.toLowerCase() === name).length
    if (count('host') !== 1 || count('origin') > 1 || !['127.0.0.1', 'localhost', '[::1]'].includes(local.hostname) || Number(local.port || 80) !== req.socket.localPort || req.headers['x-baseline-engineering'] !== 'operator' || (req.headers.origin && req.headers.origin !== origin) || req.headers['sec-fetch-site'] === 'cross-site') return send(403, { error: 'Loopback same-origin operator required' })
    if (!['GET', 'POST'].includes(req.method)) return send(405, { error: 'Unsupported method' })
    if (req.method === 'POST' && req.headers.origin !== origin) return send(403, { error: 'Explicit same-origin action required' })
    const query = new URL(req.url, origin).searchParams
    if (query.getAll('base').length !== 1 || query.getAll('resource').length !== 1 || [...query.keys()].some(k => !['base', 'resource'].includes(k))) throw new Error('Parameters')
    base = new URL(query.get('base')); resource = query.get('resource')
    if (base.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(base.hostname) || !base.port || Number(base.port) < 1024 || base.username || base.password || base.search || base.hash || !['', '/'].includes(base.pathname) || !allowedEngineeringResource(resource, req.method)) throw new Error('Target')
    if (base.hostname === 'localhost') base.hostname = '127.0.0.1'
    if (req.headers['transfer-encoding'] || (req.method === 'GET' && Number(req.headers['content-length'] || 0) !== 0)) throw new Error('Body')
    if (req.method === 'POST' && (req.headers['content-type']?.split(';')[0] !== 'application/json' || !/^\d+$/.test(req.headers['content-length'] || '') || Number(req.headers['content-length']) > 4096)) throw new Error('Bounded JSON required')
  } catch { return send(400, { error: 'Invalid engineering target, resource or body' }) }
  const controller = new AbortController()
  const timer = setTimeout(() => { controller.abort(); send(504, { error: 'Engineering request timed out' }) }, 6500)
  const disconnected = () => { if (!res.writableEnded) controller.abort() }
  res.once('close', disconnected)
  void (async () => {
    try {
      let body
      if (req.method === 'POST') {
        const chunks = []; let size = 0
        for await (const chunk of req) { size += chunk.length; if (size > 4096) return send(413, { error: 'Action body limit' }); chunks.push(chunk) }
        const value = JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}')
        if (!value || Array.isArray(value) || typeof value !== 'object') return send(400, { error: 'JSON object required' })
        if (resource.endsWith('/select')) {
          if (Object.keys(value).join(',') !== 'source_id' || !(value.source_id === null || (typeof value.source_id === 'string' && value.source_id.length > 0 && value.source_id.length <= 256))) return send(400, { error: 'Only source_id accepted' })
        } else if (Object.keys(value).length) return send(400, { error: 'Recording action takes no parameters' })
        // Never forge a trusted Origin toward an arbitrary local service. Check Studio identity first.
        const healthResponse = await fetch(base.origin + '/health', { redirect: 'error', signal: controller.signal, headers: { Accept: 'application/json' } })
        const health = await jsonBody(healthResponse, controller)
        if (!healthResponse.ok || health.status !== 'ok' || health.role !== 'observation_only' || typeof health.gateway_instance !== 'string') return send(403, { error: 'Unrecognized observation service' })
        body = JSON.stringify(value)
      }
      const response = await fetch(base.origin + resource, { method: req.method, redirect: 'error', signal: controller.signal,
        // The original recording handler replies without consuming its JSON body. Close action
        // connections so unread bytes cannot corrupt the next pooled HTTP request.
        headers: { Accept: 'application/json', ...(body === undefined ? {} : { 'Content-Type': 'application/json', Origin: base.origin, Connection: 'close' }) },
        ...(body === undefined ? {} : { body }) })
      const value = await jsonBody(response, controller)
      send(response.status, value)
    } catch { send(502, { error: 'Engineering API unavailable; no fallback or device action' }) }
    finally { clearTimeout(timer); res.off('close', disconnected) }
  })()
}
