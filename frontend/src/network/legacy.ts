/** Typed baseline Studio contract, not a replacement recording engine or a hardware controller. */
import { gatewaySnapshot, rejectSyntheticMarkers } from './gateway'
import { t } from '@/i18n'
import type { NetworkCapabilities, ReplayData, ReplaySummary } from './types'
export type LegacyRow = Record<string, unknown>
export const row = (v: unknown): v is LegacyRow => !!v && typeof v === 'object' && !Array.isArray(v)
const integer = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0
const mac = (v: unknown): v is string => typeof v === 'string' && /^(?:[a-f0-9]{2}:){5}[a-f0-9]{2}$/i.test(v)
export interface FleetNode { mac: string; node_id: number }
export interface LegacySource { id: string; label: string; kind: string; available: boolean; verified: boolean; selected: boolean; state: string }
export interface LegacySources { schema: 'lora.sources.v1'; selection: 'auto' | 'manual'; preferred_source_id: string | null; selected_source_id: string | null; selection_epoch: number; sources: LegacySource[]; udp_error?: string | null }
export interface EngineeringStatus {
  available: boolean; instance: string; sources: LegacySources | null; fleet: FleetNode[]; fleetError: string
  recovery: LegacyRow | null; receiver: LegacyRow; recordingId: string | null; recordingError: string; error: string; readAt: number
}
export const emptyEngineering = (): EngineeringStatus => ({ available: false, instance: '', sources: null, fleet: [], fleetError: '', recovery: null, receiver: {}, recordingId: null, recordingError: '', error: '', readAt: 0 })
function checkedSources(value: unknown): LegacySources {
  if (!row(value) || value.schema !== 'lora.sources.v1' || !['auto', 'manual'].includes(String(value.selection)) || !integer(value.selection_epoch) || !Array.isArray(value.sources) || value.sources.length > 256 || ![value.preferred_source_id, value.selected_source_id].every(v => v === null || typeof v === 'string')) throw new Error('BASELINE_SOURCES_INVALID')
  const ids = new Set<string>()
  for (const s of value.sources) {
    if (!row(s) || typeof s.id !== 'string' || !s.id || ids.has(s.id) || typeof s.label !== 'string' || typeof s.kind !== 'string' || typeof s.state !== 'string' || !['available', 'verified', 'selected'].every(k => typeof s[k] === 'boolean')) throw new Error('BASELINE_SOURCES_INVALID')
    ids.add(s.id)
  }
  return value as unknown as LegacySources
}
export function checkedFleet(value: unknown): FleetNode[] {
  if (!row(value) || value.schema_version !== 1 || !Array.isArray(value.nodes) || value.nodes.length > 4096) throw new Error('BASELINE_FLEET_INVALID')
  const ids = new Set<number>(), macs = new Set<string>()
  return value.nodes.map(n => {
    if (!row(n) || !mac(n.mac) || !integer(n.node_id) || n.node_id < 1 || n.node_id > 0xffffffff || ids.has(n.node_id) || macs.has(n.mac.toLowerCase())) throw new Error('BASELINE_FLEET_CONFLICT')
    ids.add(n.node_id); macs.add(n.mac.toLowerCase()); return { mac: n.mac.toLowerCase(), node_id: n.node_id }
  })
}
export class LegacyEngineering {
  state = emptyEngineering()
  private lastStatus = 0
  private enabled = false
  private recordingRevision = 0
  private lastProbe = -Infinity
  constructor(private base: string, private relay: string) {}
  async request(path: string, signal?: AbortSignal, body?: unknown): Promise<LegacyRow> {
    const url = `${this.relay}?base=${encodeURIComponent(this.base)}&resource=${encodeURIComponent(path)}`
    const response = await fetch(url, { method: body === undefined ? 'GET' : 'POST', cache: 'no-store', signal: signal ?? AbortSignal.timeout(6000),
      headers: { 'X-Baseline-Engineering': 'operator', ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) })
    const value: unknown = await response.json()
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    if (!response.ok) throw new Error(`BASELINE_HTTP_${response.status}: ${row(value) && typeof value.error === 'string' ? value.error : path}`)
    if (!row(value)) throw new Error('BASELINE_RESPONSE_INVALID')
    rejectSyntheticMarkers(value)
    return value
  }
  async initialize(signal?: AbortSignal) {
    if (this.state.available) return true
    if (Date.now() - this.lastProbe < 5000) return false
    this.lastProbe = Date.now()
    try {
      const health = await this.request('/health', signal)
      if (health.status !== 'ok' || health.role !== 'observation_only' || typeof health.gateway_instance !== 'string') return false
      this.enabled = true; this.state.available = true; this.state.instance = health.gateway_instance
      await this.refresh(signal, true)
      return true
    } catch (error) {
      if (signal?.aborted || (error instanceof Error && error.message === 'NETWORK_SYNTHETIC_REJECTED')) throw error
      this.state.error = error instanceof Error ? error.message : 'BASELINE_UNAVAILABLE'
      return false
    }
  }
  async refresh(signal?: AbortSignal, force = false) {
    if (!this.enabled || (!force && Date.now() - this.lastStatus < 5000)) return
    this.lastStatus = Date.now()
    const errors: string[] = []
    const health = await this.request('/health', signal)
    if (health.role !== 'observation_only' || typeof health.gateway_instance !== 'string') throw new Error('BASELINE_IDENTITY_CHANGED')
    if (this.state.instance !== health.gateway_instance) { this.state = { ...emptyEngineering(), available: true, instance: health.gateway_instance }; this.recordingRevision++ }
    await Promise.all([
      (async () => { try { this.state.sources = checkedSources(await this.request('/api/v1/lora/sources', signal)) } catch (e) { errors.push(String(e)) } })(),
      (async () => { try { this.state.fleet = checkedFleet(await this.request('/api/v1/fleet', signal)); this.state.fleetError = '' } catch (e) { this.state.fleetError = String(e) } })(),
      (async () => { try { this.state.recovery = await this.request('/api/v1/recovery', signal) } catch (e) { this.state.recovery = { state: 'unknown', reason: String(e) } } })(),
      (async () => { try { await this.sessions(signal) } catch (e) { this.state.recordingError = String(e) } })(),
    ])
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    this.state.error = errors.join('; '); this.state.readAt = Date.now()
  }
  capabilities(): NetworkCapabilities {
    const s = this.state.sources
    return { schema: 'network.capabilities.v1', mock: false, recording: this.enabled, sourceSelection: !!s,
      sources: s ? [{ id: '__auto__', label: t('自动选择 / 故障回退') }, ...s.sources.map(v => ({ id: v.id, label: `${v.label} · ${v.available ? t('可用') : t('不可用')}${v.verified ? '' : ' / ' + t('身份未验证')}`, selectable: v.verified }))] : [],
      selectedSourceId: s ? s.selection === 'manual' ? s.preferred_source_id ?? '__auto__' : '__auto__' : '', scenario: null,
      engineering: this.enabled, recordingActiveId: this.state.recordingId }
  }
  async selectSource(id: string) {
    this.state.sources = checkedSources(await this.request('/api/v1/lora/sources/select', undefined, { source_id: id === '__auto__' ? null : id }))
    return this.capabilities()
  }
  async sessions(signal?: AbortSignal): Promise<ReplaySummary[]> {
    const revision = this.recordingRevision
    const value = await this.request('/api/v1/replay/sessions', signal)
    if (!Array.isArray(value.sessions) || !(value.active_id === null || typeof value.active_id === 'string')) throw new Error('BASELINE_REPLAYS_INVALID')
    const summaries = value.sessions.map(s => {
      if (!row(s) || typeof s.id !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(s.id) || !integer(s.started_ms) || !integer(s.count) || typeof s.active !== 'boolean') throw new Error('BASELINE_REPLAYS_INVALID')
      return { id: s.id, startedAt: s.started_ms, frames: s.count, synthetic: false, provenance: 'unknown' as const, active: s.active, label: `SQLite · ${new Date(s.started_ms).toLocaleString()}${s.active ? ' · ' + t('记录进行中') : ''}` }
    })
    if (revision === this.recordingRevision) {
      this.state.recordingId = value.active_id as string | null
      this.state.recordingError = typeof value.error === 'string' ? value.error : ''
    }
    return summaries
  }
  async record(action: 'start' | 'stop') {
    this.recordingRevision++
    try {
      const value = await this.request('/api/v1/replay/' + action, undefined, {})
      if (!(value.id === null || typeof value.id === 'string')) throw new Error('BASELINE_RECORDING_INVALID')
      this.state.recordingId = action === 'start' ? value.id as string | null : null
      return { id: this.state.recordingId }
    } finally { this.recordingRevision++ }
  }
  async replay(id: string, offset = 0): Promise<ReplayData> {
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(id) || !integer(offset)) throw new Error('BASELINE_REPLAY_ID_INVALID')
    const value = await this.request(`/api/v1/replay/session?id=${encodeURIComponent(id)}&offset=${offset}&limit=25`)
    if (value.id !== id || !integer(value.total) || value.offset !== offset || !Array.isArray(value.frames) || value.frames.length > 25 || value.frames.length > value.total - offset) throw new Error('BASELINE_REPLAY_INVALID')
    const frames = value.frames.map(f => {
      if (!row(f) || !integer(f.t_ms)) throw new Error('BASELINE_REPLAY_INVALID')
      // Recorded topology already carries its original fleet/labels. Never apply today's roster to history.
      return gatewaySnapshot(f.topology, f.t_ms, `sqlite:${id}`)
    })
    if (frames.some((f, i) => i > 0 && f.observedAt < frames[i - 1]!.observedAt)) throw new Error('NETWORK_REPLAY_ORDER_INVALID')
    return { schema: 'network.replay.v1', id, frames, total: value.total, offset, paginated: true }
  }
}
