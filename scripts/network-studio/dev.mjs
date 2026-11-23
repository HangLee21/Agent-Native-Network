import { fileURLToPath } from 'node:url'
import { access } from 'node:fs/promises'
import { createNetworkMock } from './mock.mjs'

const root = fileURLToPath(new URL('../../frontend/', import.meta.url))
const demo = !process.argv.includes('--real')
const webPort = Number(process.env.NETWORK_WEB_PORT || 5188)
const mockPort = Number(process.env.NETWORK_MOCK_PORT || 18081)
for (const port of [webPort, mockPort]) if (!Number.isInteger(port) || port < 1024 || port > 65535) throw new Error('Network preview ports must be 1024..65535')
const viteModule = new URL('../../frontend/node_modules/vite/dist/node/index.js', import.meta.url)
try { await access(viteModule) } catch { console.error('Install dependencies first: cd frontend && npm ci'); process.exit(1) }
let mock, vite
async function close() { await vite?.close(); await mock?.close() }
try {
  process.env.NETWORK_GATEWAY_BRIDGE = '1'
  if (demo) { mock = await createNetworkMock({ port: mockPort, webPort }); process.env.NETWORK_MOCK_TARGET = mock.url }
  else delete process.env.NETWORK_MOCK_TARGET
  const { createServer } = await import(viteModule.href)
  vite = await createServer({ root, configFile: fileURLToPath(new URL('../../frontend/vite.config.ts', import.meta.url)), server: { host: '127.0.0.1', port: webPort, strictPort: true } })
  await vite.listen()
  console.log(`\nEmboNet Network Studio\n  REAL standalone: http://127.0.0.1:${webPort}/studio.html\n  REAL platform:   http://127.0.0.1:${webPort}/#/network\n${demo ? `  ISOLATED MOCK:  http://127.0.0.1:${webPort}/mock-studio.html\n  Synthetic API:  ${mock.url}/api/v1/network/snapshot\n` : '  Mock service is NOT started.\n'}\nReal workspace starts disconnected. Server / local gateway are operator-selected.\nNo hardware connections on startup. No flight, UDP, SSH, serial or MQTT.\nCtrl+C stops this dedicated preview only.\n`)
  let stopping = false
  const stop = async () => { if (stopping) return; stopping = true; await close(); process.exit(0) }
  process.once('SIGINT', stop); process.once('SIGTERM', stop)
} catch (e) {
  console.error('Network preview did not start; existing services were not stopped:', e.message)
  await close(); process.exitCode = 1
}
