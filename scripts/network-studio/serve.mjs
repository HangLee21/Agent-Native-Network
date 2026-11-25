/** Built-artifact local operator server. Same-origin bridges, no Vite or backend startup. */
import { createServer } from 'node:http'
import { readFile, realpath, stat } from 'node:fs/promises'
import { resolve, join, relative, isAbsolute, extname } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { gatewayReadHandler } from './gateway-relay.mjs'
import { engineeringHandler } from './engineering-relay.mjs'
const frontend = fileURLToPath(new URL('../../frontend/', import.meta.url))
const metadata = join(frontend, 'FRAMEWORK_SOURCE.json')
const mime = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp', '.woff': 'font/woff', '.woff2': 'font/woff2', '.ttf': 'font/ttf', '.ico': 'image/x-icon' }
const inside = (root, target) => { const part = relative(root, target); return part === '' || (!part.startsWith('..') && !isAbsolute(part)) }
export async function createBaselineStatic({ port = 10518, dist = join(frontend, 'dist') } = {}) {
  if (!Number.isInteger(port) || (port !== 0 && (port < 1024 || port > 65535))) throw new Error('Local UI port must be 1024..65535')
  const root = await realpath(resolve(dist))
  await stat(join(root, 'studio.html'))
  const config = JSON.parse(await readFile(join(root, 'network-config.json'), 'utf8'))
  const server = createServer((req, res) => {
    const send = (code, value, type = 'application/json; charset=utf-8') => {
      const data = Buffer.isBuffer(value) ? value : Buffer.from(typeof value === 'string' ? value : JSON.stringify(value))
      res.writeHead(code, { 'Content-Type': type, 'Content-Length': data.length, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' })
      res.end(req.method === 'HEAD' ? undefined : data)
    }
    void (async () => {
      let host, decoded
      try {
        host = new URL('http://' + req.headers.host)
        if (!['127.0.0.1', 'localhost', '[::1]'].includes(host.hostname) || Number(host.port || 80) !== req.socket.localPort || req.rawHeaders.filter((v, i) => i % 2 === 0 && v.toLowerCase() === 'host').length !== 1) return send(403, { error: 'Loopback Host required' })
        if (!req.url.startsWith('/') || req.url.startsWith('//')) return send(400, { error: 'Local request target required' })
        decoded = decodeURIComponent(req.url.split('?')[0])
      } catch { return send(400, { error: 'Invalid URL' }) }
      const search = req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''
      if (decoded === '/__network_gateway') { req.url = search || '/'; return gatewayReadHandler(req, res) }
      if (decoded === '/__baseline_engineering') { req.url = search || '/'; return engineeringHandler(req, res) }
      if (!['GET', 'HEAD'].includes(req.method)) return send(405, { error: 'No control endpoint' })
      if (decoded === '/network-config.json') return send(200, { ...config, gatewayRelayPath: '/__network_gateway', engineeringRelayPath: '/__baseline_engineering' })
      if (decoded === '/network-mock-config.json') return send(200, { ...config, enabled: false, gatewayRelayPath: undefined, engineeringRelayPath: undefined })
      if (decoded === '/FRAMEWORK_SOURCE.json' || decoded === '/@fs/' + metadata.replaceAll('\\', '/')) return send(200, await readFile(metadata), mime['.json'])
      if (decoded === '/mock-studio.html') return send(404, { error: 'This is the real-only baseline service; no Mock is started' })
      if (/[\\:%\u0000-\u001f]/.test(decoded) || decoded.split('/').some(p => p.startsWith('.'))) return send(400, { error: 'Invalid static path' })
      if (decoded.startsWith('/api/') || decoded.startsWith('/__')) return send(404, { error: 'Unknown local API; no fallback' })
      const name = decoded === '/' ? '/index.html' : decoded
      let target
      try { target = await realpath(resolve(root, '.' + name)) } catch { return send(404, { error: 'Not found' }) }
      if (!inside(root, target) || !(await stat(target)).isFile()) return send(404, { error: 'Not found' })
      const type = mime[extname(target).toLowerCase()]
      if (!type) return send(404, { error: 'Unsupported asset' })
      return send(200, await readFile(target), type)
    })().catch(() => { if (!res.headersSent) send(500, { error: 'Local asset unavailable' }); else res.destroy() })
  })
  await new Promise((accept, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', accept) })
  const url = `http://127.0.0.1:${server.address().port}`
  return { server, url, close: () => new Promise(resolve => { server.closeAllConnections(); server.close(resolve) }) }
}
if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const args = process.argv.slice(2)
  if (args.some((v, i) => v !== '--port' && args[i - 1] !== '--port') || args.filter(v => v === '--port').length > 1 || (args.includes('--port') && !/^\d+$/.test(args[args.indexOf('--port') + 1] || ''))) throw new Error('Usage: node scripts/network-studio/serve.mjs [--port 10518]')
  const port = args.includes('--port') ? Number(args[args.indexOf('--port') + 1]) : 10518
  const app = await createBaselineStatic({ port })
  console.log(`Baseline Vue built UI: ${app.url}/studio.html\nReal-only, initially disconnected. No backend, Mock, serial, UDP or device startup.`)
  for (const signal of ['SIGINT', 'SIGTERM']) process.once(signal, () => { void app.close().then(() => process.exit(0)) })
}
