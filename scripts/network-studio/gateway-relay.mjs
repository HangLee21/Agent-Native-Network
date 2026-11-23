/** Local development read bridge. No device connections on startup and no write/flight endpoints. */
const LIMIT = 2 * 1024 * 1024
const allowed = resource => resource === '/api/v1/lora/topology' || /^\/api\/v1\/network\/(snapshot|capabilities|replays(?:\/[^/?#]+)?)$/.test(resource)

export function gatewayReadHandler(req, res) {
  const send = (code, body) => {
    res.writeHead(code, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
    res.end(JSON.stringify(body))
  }
  let local, query, base, resource, target
  try {
    local = new URL('http://' + req.headers.host)
    const origin = local.origin
    if (!['127.0.0.1', 'localhost', '[::1]'].includes(local.hostname) || Number(local.port || 80) !== req.socket.localPort ||
      req.headers['x-network-gateway'] !== 'readonly' || (req.headers.origin && req.headers.origin !== origin) ||
      req.headers['sec-fetch-site'] === 'cross-site') return send(403, { error: 'Local same-origin reader required' })
    if (req.method !== 'GET') return send(405, { error: 'Read only' })
    query = new URL(req.url, origin).searchParams
    if (query.getAll('base').length !== 1 || query.getAll('resource').length !== 1 || [...query.keys()].some(k => !['base', 'resource'].includes(k))) throw new Error('Invalid parameters')
    base = new URL(query.get('base'))
    resource = query.get('resource')
    if (!['http:', 'https:'].includes(base.protocol) || base.username || base.password || base.search || base.hash || !allowed(resource)) throw new Error('Invalid read target')
    if (/%2f|%5c|%2e|\\|[\u0000-\u0020]|\.\./i.test(resource)) throw new Error('Invalid resource')
    target = new URL(base.href.replace(/\/+$/, '') + resource)
    if (target.origin !== base.origin || target.pathname !== base.pathname.replace(/\/+$/, '') + resource) throw new Error('Normalized path escape')
  } catch { return send(400, { error: 'Invalid read target or parameters' }) }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 5000)
  const disconnected = () => { if (!res.writableEnded) controller.abort() }
  res.once('close', disconnected)
  void (async () => {
    try {
      const upstream = await fetch(target.href, { method: 'GET', redirect: 'error', signal: controller.signal,
        headers: { Accept: 'application/json' } })
      if (!upstream.ok) { await upstream.body?.cancel(); return send(upstream.status, { error: 'Gateway read failed' }) }
      if (Number(upstream.headers.get('content-length') || 0) > LIMIT) { controller.abort(); return send(413, { error: 'Gateway response too large' }) }
      const chunks = []; let total = 0
      if (!upstream.body) throw new Error('Empty response')
      for await (const chunk of upstream.body) {
        total += chunk.length
        if (total > LIMIT) { controller.abort(); return send(413, { error: 'Gateway response too large' }) }
        chunks.push(chunk)
      }
      const value = JSON.parse(Buffer.concat(chunks).toString('utf8'))
      send(200, value)
    } catch { if (!res.destroyed && !res.writableEnded) send(502, { error: 'Gateway JSON unavailable; no fallback' }) }
    finally { clearTimeout(timer); res.off('close', disconnected) }
  })()
}
