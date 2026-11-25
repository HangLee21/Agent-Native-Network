import { fileURLToPath, URL } from 'node:url'
import { readFile } from 'node:fs/promises'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
// @ts-expect-error development-only Node module, covered by native Node tests
import { gatewayReadHandler } from '../scripts/network-studio/gateway-relay.mjs'
// @ts-expect-error local Node operator adapter, covered by native HTTP tests
import { engineeringHandler } from '../scripts/network-studio/engineering-relay.mjs'

const networkMockTarget = process.env.NETWORK_MOCK_TARGET
const gatewayBridge = process.env.NETWORK_GATEWAY_BRIDGE === '1' || !!networkMockTarget

export default defineConfig({
  plugins: [vue(), ...(gatewayBridge || networkMockTarget ? [{
    name: 'isolated-network-development',
    configureServer(server: import('vite').ViteDevServer) {
      if (gatewayBridge) {
        server.middlewares.use('/__network_gateway', gatewayReadHandler)
        if (!networkMockTarget) server.middlewares.use('/__baseline_engineering', engineeringHandler)
        server.middlewares.use('/network-config.json', (_req, res, next) => {
          void readFile(new URL('./public/network-config.json', import.meta.url), 'utf8').then(text => {
            const config = JSON.parse(text)
            res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store')
            res.end(JSON.stringify({ ...config, gatewayRelayPath: '/__network_gateway', ...(!networkMockTarget ? { engineeringRelayPath: '/__baseline_engineering' } : {}) }))
          }).catch(next)
        })
      }
      if (networkMockTarget) server.middlewares.use('/network-mock-config.json', (_req, res) => {
        res.setHeader('Content-Type', 'application/json'); res.setHeader('Cache-Control', 'no-store')
        res.end(JSON.stringify({ schema: 'network.config.v2', enabled: true, mode: 'server', profiles: {
          server: { apiBaseUrl: '/__network_mock', protocol: 'network-v1' }, gateway: { apiBaseUrl: '', protocol: 'network-v1' },
        } }))
      })
    },
  }] : [])],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  build: {
    chunkSizeWarningLimit: 600,
    rollupOptions: { input: {
      platform: fileURLToPath(new URL('./index.html', import.meta.url)),
      studio: fileURLToPath(new URL('./studio.html', import.meta.url)),
      demo: fileURLToPath(new URL('./mock-studio.html', import.meta.url)),
    } },
  },
  server: {
    port: 5173, strictPort: true,
    ...(networkMockTarget ? { proxy: { '/__network_mock': { target: networkMockTarget, rewrite: (path: string) => path.replace(/^\/__network_mock/, '') } } } : {}),
  },
  preview: { port: 4173, strictPort: true },
})
