import type { ConnectionMode, MockScenario, NetworkCapabilities, NetworkConfig, NetworkProtocol, NetworkSnapshot, ReplayData, ReplaySummary, Workspace } from './types'
import { parseSnapshot } from './model'
import { configPath, parseNetworkConfig, validateProfile } from './config'
import { gatewaySnapshot, rejectSyntheticMarkers } from './gateway'

export async function loadNetworkConfig(workspace: Workspace = 'real'): Promise<NetworkConfig> {
  const response = await fetch(configPath(workspace), { cache: 'no-store', signal: AbortSignal.timeout(5000) })
  if (!response.ok) throw new Error('NETWORK_CONFIG_UNAVAILABLE')
  return parseNetworkConfig(await response.json())
}

function validateCapabilities(r: NetworkCapabilities): NetworkCapabilities {
  if (!r || r.schema !== 'network.capabilities.v1' || typeof r.mock !== 'boolean' || typeof r.recording !== 'boolean' || typeof r.sourceSelection !== 'boolean' ||
    !Array.isArray(r.sources) || !r.sources.every(s => s && typeof s.id === 'string' && !!s.id && typeof s.label === 'string') ||
    new Set(r.sources.map(s => s.id)).size !== r.sources.length || typeof r.selectedSourceId !== 'string' ||
    (r.sources.length > 0 && !r.sources.some(s => s.id === r.selectedSourceId)) ||
    (r.scenario !== null && !['nominal', 'dense', 'empty', 'interrupted', 'stale', 'no-gps'].includes(r.scenario))) throw new Error('NETWORK_CAPABILITIES_INVALID')
  return r
}
interface ClientOptions { workspace?: Workspace; mode?: ConnectionMode; protocol?: NetworkProtocol; gatewayRelayPath?: string }
let clientSequence = 0

export class NetworkClient {
  private readonly workspace: Workspace
  private readonly mode: ConnectionMode
  private readonly protocol: NetworkProtocol
  private readonly relay: string | undefined
  private readonly base: string
  private readonly instance = `legacy-${Date.now()}-${++clientSequence}`
  constructor(base: string, options: ClientOptions = {}) {
    this.workspace = options.workspace ?? 'real'; this.mode = options.mode ?? 'server'; this.protocol = options.protocol ?? 'network-v1'
    this.base = validateProfile({ apiBaseUrl: base, protocol: this.protocol }, this.mode).apiBaseUrl
    this.relay = this.workspace === 'real' && this.mode === 'gateway' ? options.gatewayRelayPath : undefined
    if (this.workspace === 'mock' && (this.mode !== 'server' || this.protocol !== 'network-v1')) throw new Error('NETWORK_MOCK_CONFIG_INVALID')
    if (!this.relay && location.protocol === 'https:' && new URL(this.base || '/', location.origin).protocol !== 'https:') throw new Error('NETWORK_MIXED_CONTENT')
  }
  private async request<T>(path: string, signal?: AbortSignal, body?: unknown, legacy = false): Promise<T> {
    if (this.mode === 'gateway' && body !== undefined) throw new Error('NETWORK_GATEWAY_READ_ONLY')
    const resource = (legacy ? '/api/v1/lora' : '/api/v1/network') + path
    const url = this.relay ? `${this.relay}?base=${encodeURIComponent(new URL(this.base || '/', location.origin).href.replace(/\/+$/, ''))}&resource=${encodeURIComponent(resource)}` : this.base + resource
    const res = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST', cache: 'no-store', signal: signal ?? AbortSignal.timeout(6000),
      headers: { ...(this.relay ? { 'X-Network-Gateway': 'readonly' } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
    if (!res.ok) throw new Error(`NETWORK_HTTP_${res.status}`)
    return res.json() as Promise<T>
  }
  private checkedSnapshot(raw: unknown) {
    const parsed = parseSnapshot(raw)
    if (this.workspace === 'mock') {
      if (parsed.provenance !== 'synthetic') throw new Error('NETWORK_REAL_DATA_IN_MOCK')
    } else {
      if (parsed.provenance === 'synthetic') throw new Error('NETWORK_SYNTHETIC_REJECTED')
      if (parsed.provenance !== 'measured') throw new Error('NETWORK_PROVENANCE_UNVERIFIED')
      rejectSyntheticMarkers(raw)
    }
    return parsed
  }
  async snapshot(signal?: AbortSignal): Promise<NetworkSnapshot> {
    return this.protocol === 'lora-v1'
      ? gatewaySnapshot(await this.request<unknown>('/topology', signal, undefined, true), Date.now(), this.instance)
      : this.checkedSnapshot(await this.request<unknown>('/snapshot', signal))
  }
  private checkedCapabilities(raw: NetworkCapabilities) {
    const caps = validateCapabilities(raw)
    if (caps.mock !== (this.workspace === 'mock')) throw new Error(this.workspace === 'mock' ? 'NETWORK_REAL_DATA_IN_MOCK' : 'NETWORK_SYNTHETIC_REJECTED')
    return this.mode === 'gateway' ? { ...caps, recording: false, sourceSelection: false } : caps
  }
  async capabilities(signal?: AbortSignal): Promise<NetworkCapabilities> {
    if (this.protocol === 'lora-v1') return { schema: 'network.capabilities.v1', mock: false, recording: false, sourceSelection: false, sources: [], selectedSourceId: '', scenario: null }
    return this.checkedCapabilities(await this.request<NetworkCapabilities>('/capabilities', signal))
  }
  selectSource(sourceId: string) { return this.request<NetworkCapabilities>('/source', undefined, { sourceId }).then(r => this.checkedCapabilities(r)) }
  setScenario(scenario: MockScenario) {
    if (this.workspace !== 'mock') return Promise.reject(new Error('NETWORK_MOCK_ONLY'))
    return this.request<NetworkCapabilities>('/scenario', undefined, { scenario }).then(r => this.checkedCapabilities(r))
  }
  async sessions() {
    if (this.protocol === 'lora-v1') return []
    const r = await this.request<ReplaySummary[]>('/replays')
    if (!Array.isArray(r) || !r.every(s => s && typeof s.id === 'string' && typeof s.label === 'string' && Number.isFinite(s.startedAt) && Number.isSafeInteger(s.frames) && s.frames >= 0 && typeof s.synthetic === 'boolean')) throw new Error('NETWORK_REPLAYS_INVALID')
    if (r.some(s => s.synthetic !== (this.workspace === 'mock'))) throw new Error('NETWORK_REPLAY_PROVENANCE_MISMATCH')
    return r
  }
  async replay(id: string): Promise<ReplayData> {
    if (this.protocol === 'lora-v1') throw new Error('NETWORK_GATEWAY_REPLAY_UNAVAILABLE')
    const raw = await this.request<ReplayData>('/replays/' + encodeURIComponent(id))
    if (!raw || raw.schema !== 'network.replay.v1' || raw.id !== id || !Array.isArray(raw.frames)) throw new Error('NETWORK_REPLAY_INVALID')
    const frames = raw.frames.map(f => this.checkedSnapshot(f))
    if (frames.some((f, i) => i > 0 && f.observedAt < frames[i - 1]!.observedAt)) throw new Error('NETWORK_REPLAY_ORDER_INVALID')
    return { ...raw, frames }
  }
  record(action: 'start' | 'stop') { return this.request<{ id: string | null }>('/recording', undefined, { action }) }
}
