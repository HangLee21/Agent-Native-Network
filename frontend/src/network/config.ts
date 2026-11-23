import type { ConnectionMode, ConnectionProfile, NetworkConfig, Workspace } from './types'

export function defaultNetworkConfig(): NetworkConfig {
  return { schema: 'network.config.v2', enabled: false, mode: 'server', profiles: {
    server: { apiBaseUrl: '', protocol: 'network-v1' },
    gateway: { apiBaseUrl: 'http://127.0.0.1:8794', protocol: 'lora-v1' },
  } }
}

/** No credentials, query, fragment or mixed content in operator-configured endpoints. */
export function validateProfile(raw: unknown, mode: ConnectionMode): ConnectionProfile {
  const r = raw as Partial<ConnectionProfile> | null
  if (!r || typeof r.apiBaseUrl !== 'string' || !['network-v1', 'lora-v1'].includes(r.protocol ?? '') || (mode === 'server' && r.protocol !== 'network-v1')) throw new Error('NETWORK_CONFIG_INVALID')
  const base = r.apiBaseUrl.trim().replace(/\/+$/, '')
  const url = new URL(base || '/', location.origin)
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) throw new Error('NETWORK_CONFIG_INVALID')
  // A local, same-origin relay can read HTTP without an HTTPS page making mixed-content requests.
  return { apiBaseUrl: base, protocol: r.protocol! }
}

export function parseNetworkConfig(raw: unknown): NetworkConfig {
  const r = raw as Partial<NetworkConfig> | null
  if (!r || r.schema !== 'network.config.v2' || typeof r.enabled !== 'boolean' || !['server', 'gateway'].includes(r.mode ?? '') || !r.profiles) throw new Error('NETWORK_CONFIG_INVALID')
  if (r.gatewayRelayPath !== undefined && (typeof r.gatewayRelayPath !== 'string' || !/^\/[a-zA-Z0-9/_-]+$/.test(r.gatewayRelayPath))) throw new Error('NETWORK_CONFIG_INVALID')
  return { schema: 'network.config.v2', enabled: r.enabled, mode: r.mode!, profiles: {
    server: validateProfile(r.profiles.server, 'server'), gateway: validateProfile(r.profiles.gateway, 'gateway'),
  }, ...(r.gatewayRelayPath ? { gatewayRelayPath: r.gatewayRelayPath } : {}) }
}

const SETTINGS = 'network.real.connections.v2'
export function savedConnections(config: NetworkConfig): NetworkConfig {
  try {
    const saved = JSON.parse(localStorage.getItem(SETTINGS) || 'null') as NetworkConfig | null
    if (!saved) return config
    const parsed = parseNetworkConfig({ ...saved, enabled: config.enabled, gatewayRelayPath: config.gatewayRelayPath })
    // An explicit deployment config wins; browser settings do not authorize automatic connections.
    return config.enabled ? config : parsed
  } catch { return config }
}
export function saveConnections(config: NetworkConfig) {
  try { localStorage.setItem(SETTINGS, JSON.stringify({ ...config, enabled: false, gatewayRelayPath: undefined })) } catch { /* storage optional */ }
}
export const configPath = (workspace: Workspace) => workspace === 'mock' ? '/network-mock-config.json' : '/network-config.json'
