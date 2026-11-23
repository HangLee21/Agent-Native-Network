import type { NetworkLink, NetworkNode, NetworkSnapshot, ObservationState, Point } from './types'

const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const nullableNumber = (v: unknown) => v === null || finite(v)
const time = (v: unknown) => finite(v) && v >= 0 && v <= 8640000000000000
const nullableTime = (v: unknown) => v === null || time(v)
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** Reject a malformed snapshot as a whole; never disguise it as a healthy empty network. */
export function parseSnapshot(raw: unknown): NetworkSnapshot {
  if (!object(raw) || raw.schema !== 'network.snapshot.v1' || !['synthetic', 'measured', 'unknown'].includes(String(raw.provenance)) ||
    !text(raw.instanceId) || !text(raw.sourceId) || !Number.isSafeInteger(raw.epoch) || Number(raw.epoch) < 0 || !time(raw.observedAt) ||
    !finite(raw.reportTimeoutMs) || raw.reportTimeoutMs <= 0 || !object(raw.receiver) || !text(raw.receiver.id) || !text(raw.receiver.label) ||
    !['receiving', 'waiting', 'unavailable'].includes(String(raw.receiver.state)) || !Number.isSafeInteger(raw.receiver.receivedCount) || Number(raw.receiver.receivedCount) < 0 ||
    !Array.isArray(raw.nodes) || !Array.isArray(raw.links) || !Array.isArray(raw.events)) throw new Error('NETWORK_SCHEMA_INVALID')
  const ids = new Set<string>()
  for (const n of raw.nodes) {
    if (!object(n) || !text(n.id) || ids.has(n.id) || !text(n.label) || !['gateway', 'node', 'aircraft', 'robot', 'relay'].includes(String(n.role)) ||
      (n.tag !== undefined && !['node', 'drone', 'robot'].includes(String(n.tag))) ||
      !nullableTime(n.reportedAt) || !nullableNumber(n.batteryPercent) || (finite(n.batteryPercent) && (n.batteryPercent < 0 || n.batteryPercent > 100)) ||
      !object(n.radio) || !['rssiDbm', 'snrDb', 'channel', 'frequencyHz'].every(k => nullableNumber(n.radio && (n.radio as Record<string, unknown>)[k]))) throw new Error('NETWORK_NODE_INVALID')
    if (n.position !== null && (!object(n.position) || !finite(n.position.lat) || Math.abs(n.position.lat) > 90 || !finite(n.position.lon) || Math.abs(n.position.lon) > 180 || !time(n.position.observedAt) || !text(n.position.source))) throw new Error('NETWORK_POSITION_INVALID')
    if (n.binding !== null && (!object(n.binding) || !['drone', 'dog'].includes(String(n.binding.kind)) || !text(n.binding.id))) throw new Error('NETWORK_BINDING_INVALID')
    ids.add(n.id)
  }
  const links = new Set<string>()
  for (const e of raw.links) {
    if (!object(e) || !text(e.id) || links.has(e.id) || !text(e.from) || !ids.has(e.from) || !text(e.to) || !ids.has(e.to) || e.from === e.to ||
      !['wifi', 'lora'].includes(String(e.kind)) || !['mutual', 'oneway', 'lost', 'unknown'].includes(String(e.state)) || !nullableTime(e.sampledAt) ||
      !nullableNumber(e.validForMs) || (finite(e.validForMs) && e.validForMs < 0) || !nullableNumber(e.rssiDbm) || !nullableNumber(e.snrDb) || !nullableNumber(e.channel)) throw new Error('NETWORK_LINK_INVALID')
    links.add(e.id)
  }
  for (const e of raw.events) if (!object(e) || !text(e.id) || !time(e.at) || !['report', 'link', 'receiver'].includes(String(e.kind)) ||
    !(e.nodeId === null || (text(e.nodeId) && ids.has(e.nodeId))) || !['report_received', 'link_changed', 'receiver_recovered', 'receiver_interrupted'].includes(String(e.code))) throw new Error('NETWORK_EVENT_INVALID')
  const parsed = raw as unknown as NetworkSnapshot
  return { ...parsed, nodes: parsed.nodes.map(n => ({ ...n, label: nodeName(n), role: n.role === 'gateway' ? 'gateway' : 'node' })) }
}

/** Names are generic; firmware roles never infer an operator's device tag or flight identity. */
export function nodeName(n: Pick<NetworkNode, 'id' | 'label' | 'role'>): string {
  if (n.role === 'gateway') return 'GATEWAY'
  if (/^NODE(?:[ _-]+[a-z0-9:._-]+)?$/i.test(n.label.trim())) return n.label.trim().toUpperCase()
  if (/^\d+$/.test(n.label.trim())) return `NODE ${n.label.trim().padStart(2, '0')}`
  if (/^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(n.id)) return `NODE ${n.id.slice(-5).replace(':', '').toUpperCase()}`
  let hash = 2166136261
  for (const c of n.id) hash = Math.imul(hash ^ c.charCodeAt(0), 16777619)
  return `NODE ${(hash >>> 0).toString(16).slice(-6).toUpperCase()}`
}

/** Advance ages by browser elapsed time, not by subtracting clocks on two devices. */
export function nodeState(n: NetworkNode, snapshot: NetworkSnapshot, now: number, interrupted = false): ObservationState {
  if (interrupted || snapshot.receiver.state === 'unavailable') return 'interrupted'
  if (n.reportedAt === null) return 'unknown'
  return Math.max(0, now - n.reportedAt) > snapshot.reportTimeoutMs ? 'stale' : 'recent'
}
export function linkHistorical(e: NetworkLink, snapshot: NetworkSnapshot, now: number, interrupted = false): boolean {
  if (interrupted || snapshot.receiver.state === 'unavailable' || e.state === 'unknown' || e.sampledAt === null || e.validForMs === null) return true
  return Math.max(0, now - e.sampledAt) >= e.validForMs
}
export function hasPosition(n: NetworkNode, now: number, timeoutMs: number): boolean {
  return n.position !== null && Math.max(0, now - n.position.observedAt) <= timeoutMs
}
export function clearLayout(nodes: NetworkNode[], selected = ''): Record<string, Point> {
  const out: Record<string, Point> = Object.create(null) as Record<string, Point>
  const gateway = nodes.find(n => n.role === 'gateway')
  if (gateway) out[gateway.id] = { x: 490, y: 290 }
  const rest = nodes.filter(n => n !== gateway)
  rest.forEach((n, i) => {
    const ring = rest.length > 12 && i >= 10 ? 1 : 0
    const start = ring ? 10 : 0
    const count = ring ? rest.length - 10 : Math.min(rest.length, 10)
    const angle = -Math.PI / 2 + (i - start) * Math.PI * 2 / Math.max(1, count)
    const rx = ring ? 370 : rest.length > 12 ? 195 : 275
    const ry = ring ? 215 : rest.length > 12 ? 110 : 175
    out[n.id] = { x: 490 + Math.cos(angle) * rx, y: 290 + Math.sin(angle) * ry }
  })
  // A selected node is highlighted, never moved to a fictitious physical location.
  void selected
  return out
}
export function gpsProjection(nodes: NetworkNode[], now: number, timeout: number): { positions: Record<string, Point>; metersPerUnit: number } {
  const positioned = nodes.filter(n => hasPosition(n, now, timeout))
  if (!positioned.length) return { positions: {}, metersPerUnit: 1 }
  const lat = positioned.reduce((s, n) => s + n.position!.lat, 0) / positioned.length
  // Circular longitude mean keeps a local group across ±180° adjacent, rather than a world apart.
  const lon = Math.atan2(positioned.reduce((s, n) => s + Math.sin(n.position!.lon * Math.PI / 180), 0), positioned.reduce((s, n) => s + Math.cos(n.position!.lon * Math.PI / 180), 0)) * 180 / Math.PI
  const raw = positioned.map(n => ({ id: n.id, x: ((n.position!.lon - lon + 540) % 360 - 180) * Math.cos(lat * Math.PI / 180) * 111320, y: -(n.position!.lat - lat) * 111320 }))
  const spanX = Math.max(80, ...raw.map(p => Math.abs(p.x)))
  const spanY = Math.max(60, ...raw.map(p => Math.abs(p.y)))
  const scale = Math.min(370 / spanX, 200 / spanY)
  return { positions: Object.fromEntries(raw.map(p => [p.id, { x: 490 + p.x * scale, y: 290 + p.y * scale }])), metersPerUnit: 1 / scale }
}
export function gpsLayout(nodes: NetworkNode[], now: number, timeout: number): Record<string, Point> {
  return gpsProjection(nodes, now, timeout).positions
}

export function readPositions(key: string): Record<string, Point> {
  try {
    const raw: unknown = JSON.parse(localStorage.getItem(key) || '{}')
    if (!object(raw)) return {}
    return Object.fromEntries(Object.entries(raw).filter(([, p]) => object(p) && finite(p.x) && finite(p.y) && Math.abs(p.x) < 100000 && Math.abs(p.y) < 100000)) as Record<string, Point>
  } catch { return {} }
}
