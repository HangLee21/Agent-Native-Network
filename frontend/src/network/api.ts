import type { ConnectionMode, MockScenario, NetworkCapabilities, NetworkConfig, NetworkProtocol, NetworkSnapshot, ReplayData, ReplaySummary, Workspace } from './types'
import { parseSnapshot } from './model'
import { configPath, parseNetworkConfig, validateProfile } from './config'
import { gatewaySnapshot, rejectSyntheticMarkers } from './gateway'
import { LegacyEngineering, row } from './legacy'
import { nativeSnapshot } from './native'

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
interface ClientOptions { workspace?: Workspace; mode?: ConnectionMode; protocol?: NetworkProtocol; gatewayRelayPath?: string; engineeringRelayPath?: string }
let clientSequence = 0

export class NetworkClient {
  private readonly workspace: Workspace
  private readonly mode: ConnectionMode
  private readonly protocol: NetworkProtocol
  private readonly relay: string | undefined
  private readonly base: string
  private readonly instance = `legacy-${Date.now()}-${++clientSequence}`
  readonly engineering: LegacyEngineering | null
  private previous: NetworkSnapshot | null = null
  constructor(base: string, options: ClientOptions = {}) {
    this.workspace = options.workspace ?? 'real'; this.mode = options.mode ?? 'server'; this.protocol = options.protocol ?? 'network-v1'
    this.base = validateProfile({ apiBaseUrl: base, protocol: this.protocol }, this.mode).apiBaseUrl
    this.relay = this.workspace === 'real' && this.mode === 'gateway' ? options.gatewayRelayPath : undefined
    const target = new URL(this.base || '/', location.origin)
    this.engineering = this.workspace === 'real' && this.mode === 'gateway' && this.protocol === 'lora-v1' && options.engineeringRelayPath && ['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname) && target.protocol === 'http:' && target.pathname === '/'
      ? new LegacyEngineering(this.base, options.engineeringRelayPath) : null
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
    if (this.protocol !== 'lora-v1') return this.checkedSnapshot(await this.request<unknown>('/snapshot', signal))
    const raw = await this.request<unknown>('/topology', signal, undefined, true)
    const at = Date.now()
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (this.engineering && !this.engineering.state.available) await this.engineering.initialize(signal)
    if (this.engineering?.state.available) {
      const epoch = row(raw) ? raw.selection_epoch : undefined
      await this.engineering.refresh(signal, typeof epoch === 'number' && !!this.previous && epoch < this.previous.epoch)
      if (row(raw) && row(raw.receiver)) this.engineering.state.receiver = raw.receiver
    }
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    const value = gatewaySnapshot(raw, at, this.instance + (this.engineering?.state.instance ? ':' + this.engineering.state.instance : ''), this.engineering?.state.fleet)
    const old = this.previous
    if (old && old.instanceId === value.instanceId && old.sourceId === value.sourceId && old.epoch === value.epoch) {
      const prior = new Map(old.nodes.filter(n => n.role !== 'gateway' && n.reportedAt !== null).map(n => [n.id, n]))
      value.nodes = value.nodes.map(n => n.reportedAt === null && prior.has(n.id) ? { ...prior.get(n.id)!, label: n.label, registration: n.registration } : n)
      for (const n of prior.values()) if (!value.nodes.some(v => v.id === n.id)) value.nodes.push(n)
    }
    if (old && old.instanceId === value.instanceId && old.sourceId === value.sourceId && value.epoch < old.epoch) throw new Error('NETWORK_EPOCH_REGRESSION')
    value.observedAt = Date.now() // Include metadata-read elapsed time without refreshing report/sample timestamps.
    this.previous = value
    return value
  }
  async wifiSnapshot(signal?: AbortSignal): Promise<NetworkSnapshot> {
    if (!this.engineering?.state.available) throw new Error('BASELINE_WIFI_UNAVAILABLE')
    await this.engineering.refresh(signal)
    return nativeSnapshot(await this.engineering.request('/api/v1/state', signal), Date.now(), this.engineering.state.fleet)
  }
  private checkedCapabilities(raw: NetworkCapabilities) {
    const caps = validateCapabilities(raw)
    if (caps.mock !== (this.workspace === 'mock')) throw new Error(this.workspace === 'mock' ? 'NETWORK_REAL_DATA_IN_MOCK' : 'NETWORK_SYNTHETIC_REJECTED')
    return this.mode === 'gateway' ? { ...caps, recording: false, sourceSelection: false } : caps
  }
  async capabilities(signal?: AbortSignal): Promise<NetworkCapabilities> {
    if (this.protocol === 'lora-v1') {
      if (this.engineering && await this.engineering.initialize(signal)) return this.engineering.capabilities()
      return { schema: 'network.capabilities.v1', mock: false, recording: false, sourceSelection: false, sources: [], selectedSourceId: '', scenario: null }
    }
    return this.checkedCapabilities(await this.request<NetworkCapabilities>('/capabilities', signal))
  }
  selectSource(sourceId: string) {
    if (this.engineering?.state.available) { this.previous = null; return this.engineering.selectSource(sourceId) }
    return this.request<NetworkCapabilities>('/source', undefined, { sourceId }).then(r => this.checkedCapabilities(r))
  }
  setScenario(scenario: MockScenario) {
    if (this.workspace !== 'mock') return Promise.reject(new Error('NETWORK_MOCK_ONLY'))
    return this.request<NetworkCapabilities>('/scenario', undefined, { scenario }).then(r => this.checkedCapabilities(r))
  }
  async sessions() {
    if (this.protocol === 'lora-v1') return this.engineering?.state.available ? this.engineering.sessions() : []
    const r = await this.request<ReplaySummary[]>('/replays')
    if (!Array.isArray(r) || !r.every(s => s && typeof s.id === 'string' && typeof s.label === 'string' && Number.isFinite(s.startedAt) && Number.isSafeInteger(s.frames) && s.frames >= 0 && typeof s.synthetic === 'boolean')) throw new Error('NETWORK_REPLAYS_INVALID')
    if (r.some(s => s.synthetic !== (this.workspace === 'mock'))) throw new Error('NETWORK_REPLAY_PROVENANCE_MISMATCH')
    return r
  }
  async replay(id: string, offset = 0): Promise<ReplayData> {
    if (this.protocol === 'lora-v1') {
      if (this.engineering?.state.available) return this.engineering.replay(id, offset)
      throw new Error('NETWORK_GATEWAY_REPLAY_UNAVAILABLE')
    }
    const raw = await this.request<ReplayData>('/replays/' + encodeURIComponent(id))
    if (!raw || raw.schema !== 'network.replay.v1' || raw.id !== id || !Array.isArray(raw.frames)) throw new Error('NETWORK_REPLAY_INVALID')
    const frames = raw.frames.map(f => this.checkedSnapshot(f))
    if (frames.some((f, i) => i > 0 && f.observedAt < frames[i - 1]!.observedAt)) throw new Error('NETWORK_REPLAY_ORDER_INVALID')
    return { ...raw, frames }
  }
  record(action: 'start' | 'stop') {
    if (this.engineering?.state.available) return this.engineering.record(action)
    return this.request<{ id: string | null }>('/recording', undefined, { action })
  }
  async evidence(after = 0, signal?: AbortSignal) {
    if (!this.engineering?.state.available || !Number.isSafeInteger(after) || after < 0) throw new Error('BASELINE_EVIDENCE_UNAVAILABLE')
    const state = await this.engineering.request('/api/v1/state', signal)
    if (state.schema_version !== 1 || typeof state.gateway_instance !== 'string' || !Number.isSafeInteger(state.cursor) || Number(state.cursor) < 0 || !Array.isArray(state.nodes) || !Array.isArray(state.edges)) throw new Error('BASELINE_EVIDENCE_SCHEMA_INVALID')
    // The original API has no limit parameter. Bound bootstrap/catch-up to the latest 512
    // cursors before fetching, instead of downloading its entire 8192-event RAM window.
    const previous = after > Number(state.cursor) ? 0 : after
    const requestedAfter = Math.max(previous, Number(state.cursor) - 512, 0)
    const timeline = await this.engineering.request('/api/v1/timeline?after=' + requestedAfter, signal)
    if (timeline.schema_version !== 1 || state.gateway_instance !== timeline.gateway_instance || !Array.isArray(timeline.events) || !Number.isSafeInteger(timeline.cursor)) throw new Error('BASELINE_EVIDENCE_SCHEMA_INVALID')
    return { state, timeline, windowTruncated: requestedAfter > previous }
  }
}
