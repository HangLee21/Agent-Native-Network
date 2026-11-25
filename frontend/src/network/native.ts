/** Original /api/v1/state Wi-Fi evidence, kept separate from LoRa's legacy neighbor samples. */
import { parseSnapshot } from './model'
import { rejectSyntheticMarkers } from './gateway'
import { row, type FleetNode } from './legacy'
import type { NetworkLink, NetworkNode, NetworkSnapshot } from './types'
const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const age = (v: unknown): v is number => number(v) && v >= 0
const mac = (v: unknown): v is string => typeof v === 'string' && /^(?:[a-f0-9]{2}:){5}[a-f0-9]{2}$/i.test(v)
export function nativeSnapshot(raw: unknown, at: number, fleet: FleetNode[] = []): NetworkSnapshot {
  rejectSyntheticMarkers(raw)
  if (!row(raw) || raw.schema_version !== 1 || typeof raw.gateway_instance !== 'string' || !Array.isArray(raw.nodes) || !Array.isArray(raw.edges) || !age(raw.offline_after_ms) || raw.offline_after_ms === 0 || !age(raw.stale_after_ms) || raw.stale_after_ms === 0) throw new Error('BASELINE_WIFI_SCHEMA_INVALID')
  const nodes = new Map<string, NetworkNode>(), seen = new Set<string>()
  const member = (id: string) => {
    id = id.toLowerCase()
    if (!nodes.has(id)) nodes.set(id, { id, label: id, role: 'node', registration: 'observed', reportedAt: null, position: null, batteryPercent: null, radio: { rssiDbm: null, snrDb: null, channel: null, frequencyHz: null }, binding: null })
    return nodes.get(id)!
  }
  for (const f of fleet) { const n = member(f.mac); n.label = String(f.node_id); n.registration = 'fleet' }
  for (const item of raw.nodes) {
    if (!row(item) || !mac(item.node_id) || seen.has(item.node_id.toLowerCase())) throw new Error('BASELINE_WIFI_NODE_INVALID')
    seen.add(item.node_id.toLowerCase())
    const n = member(item.node_id)
    if (typeof item.label === 'string' && n.registration !== 'fleet') n.label = item.label
    n.reportedAt = age(item.report_age_ms) ? Math.max(0, at - item.report_age_ms) : null
    const p = item.position
    if (row(p) && p.valid !== false && p.fix !== false && age(p.age_ms) && number(p.lat) && number(p.lon) && Math.abs(p.lat) <= 90 && Math.abs(p.lon) <= 180 && typeof p.source === 'string') n.position = { lat: p.lat, lon: p.lon, observedAt: Math.max(0, at - p.age_ms), source: p.source }
  }
  const links: NetworkLink[] = raw.edges.map(item => {
    if (!row(item) || !mac(item.from) || !mac(item.to) || item.from.toLowerCase() === item.to.toLowerCase() || !['heard', 'confirmed', 'lost', 'unknown'].includes(String(item.state)) || !['fresh', 'stale', 'unknown'].includes(String(item.sample_freshness))) throw new Error('BASELINE_WIFI_EDGE_INVALID')
    const from = member(item.from).id, to = member(item.to).id
    const exact = age(item.sample_age_ms) && item.age_is_lower_bound !== true
    const reporterAt = nodes.get(to)?.reportedAt ?? null
    const fresh = exact && Number(item.sample_age_ms) <= Number(raw.stale_after_ms) && item.sample_freshness === 'fresh' && item.invalidated_reason === null && item.telemetry_status === 'online' && reporterAt !== null && at - reporterAt <= Number(raw.offline_after_ms)
    const sampledAt = exact ? Math.max(0, at - Number(item.sample_age_ms)) : null
    // Preserve a KNOWN deadline even after it expires; null means unknown, not stale.
    const validity = sampledAt !== null && reporterAt !== null && item.invalidated_reason === null ? Math.max(0, Math.min(Number(raw.stale_after_ms), reporterAt + Number(raw.offline_after_ms) - sampledAt)) : null
    return { id: `wifi:${from}:${to}`, from, to, kind: 'wifi', state: item.state === 'lost' ? 'lost' : fresh && item.state === 'confirmed' && item.mutual_confirmed === true ? 'mutual' : fresh && ['heard', 'confirmed'].includes(String(item.state)) ? 'oneway' : 'unknown', sampledAt, validForMs: validity, rssiDbm: item.rf_source === 'measured' && number(item.rssi_dbm) ? item.rssi_dbm : null, snrDb: null, channel: number(item.channel) ? item.channel : null }
  })
  const pairs = new Map(links.map(e => [`${e.from}:${e.to}`, { ...e }]))
  for (const e of links) if (e.state === 'mutual') {
    const reverse = pairs.get(`${e.to}:${e.from}`)
    if (!reverse || reverse.state !== 'mutual' || reverse.sampledAt === null || reverse.validForMs === null || e.sampledAt === null || e.validForMs === null) e.state = 'oneway'
    else e.validForMs = Math.max(0, Math.min(e.sampledAt + e.validForMs, reverse.sampledAt + reverse.validForMs) - e.sampledAt)
  }
  const error = row(raw.studio) && !!raw.studio.error
  const counters = row(raw.counters) ? raw.counters : {}
  const count = Number.isSafeInteger(counters.accepted) && Number(counters.accepted) >= 0 ? Number(counters.accepted) : 0
  return parseSnapshot({ schema: 'network.snapshot.v1', provenance: 'unknown', instanceId: `wifi:${raw.gateway_instance}`, sourceId: 'wifi-ip-state', epoch: 0, observedAt: at, reportTimeoutMs: raw.offline_after_ms,
    receiver: { id: 'wifi-ip-observer', label: 'IP / RAM observer', state: error ? 'unavailable' : raw.nodes.length ? 'receiving' : 'waiting', receivedCount: count }, nodes: [...nodes.values()], links, events: [] })
}
