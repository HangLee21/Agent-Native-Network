import { parseSnapshot } from './model'
import type { NetworkLink, NetworkNode, NetworkSnapshot } from './types'

type Row = Record<string, unknown>
const obj = (v: unknown): v is Row => !!v && typeof v === 'object' && !Array.isArray(v)
const number = (v: unknown): number | null => typeof v === 'number' && Number.isFinite(v) ? v : null
const age = (v: unknown) => { const n = number(v); return n !== null && n >= 0 ? n : null }
const mac = (v: unknown): v is string => typeof v === 'string' && /^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(v)

/** Legacy has no provenance attestation. Reject explicit fake markers; never promote it to measured. */
export function rejectSyntheticMarkers(raw: unknown): void {
  const pending: unknown[] = [raw]
  while (pending.length) {
    const value = pending.pop()
    if (!value || typeof value !== 'object') continue
    if (Array.isArray(value)) { pending.push(...value); continue }
    const v = value as Row
    if (v.mock === true || v.synthetic === true || v.fake_gps === true || v.provenance === 'synthetic' ||
      [v.mode, v.view_mode].some(x => typeof x === 'string' && /^(mock|demo|simulation|replay)$/i.test(x)) ||
      [v.source, v.rf_source, v.radio_source, v.business_source].some(x => typeof x === 'string' && (/^(synthetic|mock|demo|simulat)/i.test(x) || /(?:fake_agent|host_model)/i.test(x)))) throw new Error('NETWORK_SYNTHETIC_REJECTED')
    pending.push(...Object.values(v))
  }
}

export function gatewaySnapshot(raw: unknown, at: number, instanceId: string, fleet: { mac: string; node_id: number }[] = []): NetworkSnapshot {
  rejectSyntheticMarkers(raw)
  if (!obj(raw) || raw.schema !== 'lora.topology.v1' || !obj(raw.receiver) || !Array.isArray(raw.reports) ||
    !['gateway_udp_lrn1', 'lora_received_snapshot', 'unavailable'].includes(String(raw.source))) throw new Error('NETWORK_GATEWAY_SCHEMA_INVALID')
  const receiver = raw.receiver
  const gatewayId = typeof receiver.gateway_id === 'string' && receiver.gateway_id.trim() ? receiver.gateway_id.toLowerCase() : null
  const labels = obj(raw.labels) ? raw.labels : {}
  const threshold = age(receiver.recent_threshold_ms)
  const periods = raw.reports.filter(obj).map(item => obj(item.report) ? number(item.report.report_period_ms) : null).filter((v): v is number => v !== null && v > 0)
  const timeout = receiver.mode === 'node_serial' ? Math.max(35000, ...periods.map(n => n * 3 + 5000)) : threshold && threshold > 0 ? threshold : 30000
  const members = new Map<string, NetworkNode>()
  const links = new Map<string, NetworkLink>()
  function member(id: string, gateway = false) {
    if (!members.has(id)) members.set(id, { id, label: typeof labels[id] === 'string' ? labels[id] as string : id,
      role: gateway ? 'gateway' : 'node', registration: 'observed', reportedAt: null, position: null, batteryPercent: null,
      radio: { rssiDbm: null, snrDb: null, channel: null, frequencyHz: null }, binding: null })
    if (gateway) members.get(id)!.role = 'gateway'
    return members.get(id)!
  }
  if (gatewayId) {
    const gateway = member(gatewayId, true)
    // Gateway heartbeat age is independent of every member's report age.
    const gatewayAge = age(receiver.last_rx_age_ms) ?? age(receiver.gateway_last_pull_age_ms)
    if (gatewayAge !== null) gateway.reportedAt = Math.max(0, at - gatewayAge)
  }
  for (const [id, label] of Object.entries(labels)) if (mac(id) && typeof label === 'string' && label.trim()) { const n = member(id.toLowerCase()); n.registration = 'label'; n.label = label }
  for (const registered of fleet) if (mac(registered.mac) && Number.isSafeInteger(registered.node_id) && registered.node_id > 0) {
    const n = member(registered.mac.toLowerCase()); n.label = String(registered.node_id); n.registration = 'fleet'
  }
  for (const item of raw.reports) {
    if (!obj(item) || !obj(item.report) || item.report.frame_schema !== 'LRN1' || !mac(item.report.observer_id)) throw new Error('NETWORK_GATEWAY_REPORT_INVALID')
    const r = item.report, id = (r.observer_id as string).toLowerCase(), n = member(id)
    const receivedAge = age(item.pc_receive_age_ms)
    const ownThreshold = age(item.recent_threshold_ms), ownPeriod = number(r.report_period_ms)
    n.reportTimeoutMs = ownThreshold && ownThreshold > 0 ? ownThreshold : receiver.mode === 'node_serial' && ownPeriod !== null && ownPeriod > 0 ? Math.max(35000, ownPeriod * 3 + 5000) : timeout
    n.reportedAt = receivedAge === null ? null : Math.max(0, at - receivedAge)
    const radio = obj(item.lora) ? item.lora : {}
    const mhz = number(radio.freq), hz = number(radio.frequency_hz)
    n.radio = { rssiDbm: number(radio.rssi_dbm ?? radio.rssi), snrDb: number(radio.snr_db ?? radio.lsnr), channel: number(radio.channel ?? radio.chan),
      frequencyHz: hz !== null && hz > 0 ? hz : mhz !== null && mhz > 0 ? Math.round(mhz * 1e6) : null }
    const gps = obj(item.gps) ? item.gps : obj(r.gps) ? r.gps : null
    const gpsAge = age(item.gps_age_ms)
    if (gps?.valid === true && gpsAge !== null && number(gps.lat_e7) !== null && number(gps.lon_e7) !== null) {
      const lat = Number(gps.lat_e7) / 1e7, lon = Number(gps.lon_e7) / 1e7
      if (Math.abs(lat) > 90 || Math.abs(lon) > 180) throw new Error('NETWORK_POSITION_INVALID')
      n.position = { lat, lon, observedAt: Math.max(0, at - gpsAge), source: 'gateway-lrn1-unattested' }
    }
    const status = obj(item.status) ? item.status : obj(r.status) ? r.status : null
    const statusAge = age(item.status_age_ms), battery = number(status?.battery_pct)
    if (statusAge !== null && statusAge <= timeout && battery !== null && battery >= 0 && battery <= 100) n.batteryPercent = battery
    if (gatewayId && gatewayId !== id) {
      const key = `lora:${id}:${gatewayId}`
      links.set(key, { id: key, from: id, to: gatewayId, kind: 'lora', state: 'oneway', sampledAt: n.reportedAt, validForMs: n.reportTimeoutMs,
        rssiDbm: n.radio.rssiDbm, snrDb: n.radio.snrDb, channel: n.radio.channel })
    }
    if (!Array.isArray(r.neighbors)) throw new Error('NETWORK_GATEWAY_REPORT_INVALID')
    for (const row of r.neighbors) {
      if (!obj(row) || !mac(row.peer_id)) throw new Error('NETWORK_GATEWAY_REPORT_INVALID')
      const peer = row.peer_id.toLowerCase()
      if (peer === id) continue
      member(peer)
      const flags = Number.isInteger(row.valid) ? Number(row.valid) : Number.isInteger(row.valid_flags) ? Number(row.valid_flags) : null
      const present = (bit: number) => flags !== null && (flags & bit) !== 0
      const seenAge = age(row.seen_age_ms), key = `wifi:${peer}:${id}`
      const mutual = row.state === 'bidirectional' && present(1) && age(row.ack_age_ms) !== null
      links.set(key, { id: key, from: peer, to: id, kind: 'wifi', state: row.state === 'lost' ? 'lost' : mutual ? 'mutual' : row.state === 'oneway' ? 'oneway' : 'unknown',
        sampledAt: receivedAge !== null && seenAge !== null ? Math.max(0, at - receivedAge - seenAge) : null,
        // The old wire contract has no validity window for current Wi-Fi. Do not invent one.
        validForMs: null, sampleOrigin: 'legacy-neighbor', rssiDbm: present(2) ? number(row.rssi_dbm ?? row.wifi_rssi_dbm) : null, snrDb: null,
        channel: present(8) ? number(row.wifi_channel ?? row.channel) : null })
    }
  }
  const receivedCount = number(receiver.lrn1_frames ?? receiver.frames)
  const epoch = number(raw.selection_epoch)
  return parseSnapshot({ schema: 'network.snapshot.v1', provenance: 'unknown', instanceId,
    sourceId: typeof raw.source_id === 'string' && raw.source_id ? raw.source_id : `${String(raw.source)}:${gatewayId ?? 'unidentified'}`,
    epoch: epoch !== null && Number.isSafeInteger(epoch) && epoch >= 0 ? epoch : 0,
    observedAt: at, reportTimeoutMs: timeout,
    receiver: { id: gatewayId ?? 'gateway-unidentified', label: 'GATEWAY',
      state: receiver.gateway_observed !== true || receiver.state === 'unavailable' ? 'unavailable' : raw.reports.length ? 'receiving' : 'waiting',
      receivedCount: receivedCount !== null && Number.isSafeInteger(receivedCount) && receivedCount >= 0 ? receivedCount : 0 },
    nodes: [...members.values()], links: [...links.values()], events: [],
  })
}
