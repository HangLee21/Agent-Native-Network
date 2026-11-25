/** Port of the original pure studio-model packet evidence rules. No routes are computed here. */
import { t } from '@/i18n'
import type { LegacyRow } from './legacy'
export interface PacketEvent extends LegacyRow {
  event?: string; type?: string; kind?: string; packet_kind?: string; sequence_scope?: string
  origin?: string; dst?: string; origin_boot?: number; boot?: number; seq?: number
  reporter?: string; node_id?: string; observer_id?: string; next_hop?: string; previous_hop?: string
  payload_hex?: string; path?: string[]; observer_boot?: number; entry_boot?: number; boot_id?: number
  reason?: number; record_overwritten?: number; _key?: string; event_id?: string
}
export interface PacketRow {
  key: string; origin: string; origin_boot: number; seq: number; dst: string; events: PacketEvent[]
  segments: { from: string; to: string; event: PacketEvent; type: string }[]
  routes: { path: string[]; event: PacketEvent }[]; payloads: string[]; received: boolean; last: PacketEvent
  delivery: string; state: string; stateLabel: string; reason: string; bytesMatch: boolean; coverageNotes: string[]
}
const clean = (v: unknown) => String(v ?? '').trim().toLowerCase()
const object = (v: unknown): v is LegacyRow => !!v && typeof v === 'object' && !Array.isArray(v)
/** Original /timeline envelopes are not packet events: preserve their gateway reporter and cursor. */
export function timelineEvents(values: unknown[], instance: string): PacketEvent[] {
  return values.filter(object).map(envelope => {
    const data = object(envelope.data) ? envelope.data : envelope
    const wire = object(data.raw) ? data.raw : {}
    const event = envelope.type || data.event || data.type
    const conflict = typeof envelope.type === 'string' && typeof data.event === 'string' && envelope.type !== data.event
    return { ...wire, ...data, event: conflict ? 'invalid_envelope' : event,
      reporter: clean(envelope.reporter || envelope.node_id || envelope.observer_id || data.observer_id || data.reporter),
      received_ms: envelope.received_ms ?? data.received_ms, gateway_cursor: envelope.cursor,
      gateway_event_type_conflict: conflict,
      event_id: Number.isSafeInteger(envelope.cursor) ? `gateway/${instance}/${envelope.cursor}` : String(envelope.event_id || envelope.id || `gateway/${instance}/${JSON.stringify(envelope)}`),
    } as PacketEvent
  })
}
const isMAC = (v: unknown) => /^(?:[a-f0-9]{2}:){5}[a-f0-9]{2}$/.test(clean(v))
const kind = (e: PacketEvent) => e.event || e.type || ''
const validHex = (v: unknown): v is string => typeof v === 'string' && /^(?:[a-f0-9]{2}){0,160}$/i.test(v)
export function packetKey(e: PacketEvent) {
  const boot = e.origin_boot ?? e.boot
  return isMAC(e.origin) && isMAC(e.dst) && Number.isInteger(boot) && Number(boot) > 0 && Number.isInteger(e.seq) && Number(e.seq) > 0 ? [clean(e.origin), boot, e.seq, clean(e.dst)].join('/') : null
}
export function destinationEvidence(e: PacketEvent): boolean {
  const reporter = clean(e.reporter || e.node_id)
  return kind(e) === 'rx_local' && reporter === clean(e.dst) && isMAC(reporter) && !!packetKey(e) && (!e.node_id || clean(e.node_id) === reporter) && (!e.observer_id || clean(e.observer_id) === reporter) && validHex(e.payload_hex)
}
export function decodePayload(hex: string): string | null {
  if (!validHex(hex)) return null
  try { return new TextDecoder('utf-8', { fatal: true }).decode(Uint8Array.from(hex.match(/../g) || [], x => parseInt(x, 16))) } catch { return null }
}
const packetKinds = new Set(['tx_queued', 'tx_submit', 'tx_link_ok', 'rx_relay', 'rx_local', 'route_selected', 'route_no_route', 'route_drop', 'delivery_unknown', 'tx_link_fail', 'tx_api_failed', 'send_rejected', 'route_rejected'])
function usable(e: PacketEvent) { return e.kind !== 'control' && (!e.packet_kind || e.packet_kind === 'DATA') && e.sequence_scope !== 'route_request' && packetKinds.has(kind(e)) && !!packetKey(e) }
function packetState(row: PacketRow) {
  const has = (value: string) => row.events.some(e => kind(e) === value)
  const source = row.events.filter(e => clean(e.reporter || e.node_id) === row.origin && ((e.observer_boot ?? e.entry_boot ?? e.boot_id) == null || (e.observer_boot ?? e.entry_boot ?? e.boot_id) === row.origin_boot))
  const submitted = has('tx_submit') || has('rx_relay') || has('tx_link_ok')
  if (row.delivery === 'payload_conflict') return { state: 'payload_conflict', stateLabel: t('目的收件字节冲突'), reason: t('同一原包身份出现不同载荷，保留冲突原字节，不标为一致交付。') }
  if (row.delivery === 'destination_received') return { state: 'destination_received', stateLabel: t('目的实收原字节'), reason: t('目的节点自己的 rx_local 含完整原包身份和载荷；后到的本跳失败不会撤销这条收件证据。') }
  const noRoute = source.find(e => kind(e) === 'route_no_route' && e.reason !== 6)
  const rejected = source.some(e => ['send_rejected', 'route_rejected', 'route_drop'].includes(kind(e)))
  if (noRoute && !submitted) return { state: 'no_route', stateLabel: t('板端本轮无路'), reason: t('源端明确报告该包本轮未找到路；未据此推断后续新业务。') }
  if (rejected && !submitted) return { state: 'rejected', stateLabel: t('源端拒绝 / 本地丢弃'), reason: t('仅代表源端本地记录，不证明沿途或后续业务永久失败。') }
  if (has('delivery_unknown') || has('tx_link_fail') || has('tx_api_failed') || has('route_drop') || noRoute || rejected || source.some(e => kind(e) === 'route_no_route' && e.reason === 6)) return { state: 'delivery_unknown', stateLabel: t('最终交付未知'), reason: t('存在本跳失败、局部无路或丢弃记录，但不能据此证明目的端从未收到。') }
  if (has('rx_relay') || has('tx_submit') || has('tx_link_ok')) return { state: 'awaiting_receipt', stateLabel: has('rx_relay') ? t('已见中继，待目的收件') : t('已提交，待目的收件'), reason: t('本地提交、中继收到或链路回调都不等于目的端交付。') }
  if (source.some(e => kind(e) === 'tx_queued')) return { state: 'queued', stateLabel: t('仅排队，未见提交'), reason: t('源端仅接纳入队，未观测到提交或中继收件。') }
  return { state: 'observed', stateLabel: t('仅见选路，未见提交'), reason: t('板端选路不证明沿途实际收到。') }
}
export function packets(events: PacketEvent[]): PacketRow[] {
  const result = new Map<string, PacketRow>()
  for (const e of events) {
    if (!usable(e)) continue
    const key = packetKey(e)!, reporter = clean(e.reporter || e.node_id), type = kind(e)
    if (!result.has(key)) result.set(key, { key, origin: clean(e.origin), origin_boot: (e.origin_boot ?? e.boot)!, seq: e.seq!, dst: clean(e.dst), events: [], segments: [], routes: [], payloads: [], received: false, last: e, delivery: '', state: '', stateLabel: '', reason: '', bytesMatch: false, coverageNotes: [] })
    const r = result.get(key)!; r.events.push(e); r.last = e
    if (validHex(e.payload_hex) && !r.payloads.includes(e.payload_hex.toLowerCase())) r.payloads.push(e.payload_hex.toLowerCase())
    if (type === 'route_selected' && Array.isArray(e.path) && e.path.length > 1 && e.path.every(isMAC)) r.routes.push({ path: e.path.map(clean), event: e })
    const from = type === 'tx_submit' ? reporter : ['rx_relay', 'rx_local'].includes(type) ? clean(e.previous_hop) : ''
    const to = type === 'tx_submit' ? clean(e.next_hop) : ['rx_relay', 'rx_local'].includes(type) ? reporter : ''
    if (isMAC(from) && isMAC(to) && from !== to) r.segments.push({ from, to, event: e, type })
    if (destinationEvidence(e)) r.received = true
  }
  return [...result.values()].slice(-64).reverse().map(r => {
    r.bytesMatch = r.payloads.length === 1; r.delivery = r.received ? r.payloads.length > 1 ? 'payload_conflict' : 'destination_received' : 'unconfirmed'
    return { ...r, ...packetState(r) }
  })
}
interface RecordEntry { events: PacketEvent[]; gaps: Set<string>; ordinal: number; payloadEvidence: Map<string, PacketEvent>; receipt: PacketEvent | null }
export class PacketLog {
  private rows = new Map<string, RecordEntry>()
  private seen = new Set<string>()
  private seenOrder: string[] = []
  private ordinal = 0
  merge(events: PacketEvent[], coverage: { timelineTruncated?: boolean; nodes?: LegacyRow[]; pinnedKey?: string } = {}): PacketRow[] {
    for (const e of events) {
      if (!usable(e)) continue
      const key = packetKey(e)!, identity = e._key || e.event_id || JSON.stringify(e)
      if (this.seen.has(identity)) continue
      this.seen.add(identity); this.seenOrder.push(identity)
      if (this.seenOrder.length > 8192) this.seen.delete(this.seenOrder.shift()!)
      if (!this.rows.has(key)) this.rows.set(key, { events: [], gaps: new Set(), ordinal: 0, payloadEvidence: new Map(), receipt: null })
      const record = this.rows.get(key)!
      if (destinationEvidence(e)) record.receipt = e
      if (validHex(e.payload_hex) && !record.payloadEvidence.has(e.payload_hex.toLowerCase())) {
        if (record.payloadEvidence.size < 2) record.payloadEvidence.set(e.payload_hex.toLowerCase(), e)
        else record.gaps.add(t('不同原字节超过两种，仅保留前两种冲突样本'))
      }
      record.events.push(e)
      if (record.events.length > 48) { record.events.splice(1, 1); record.gaps.add(t('本页该包观察记录已达48条保留上限')) }
      record.ordinal = ++this.ordinal
      if ((e.record_overwritten ?? 0) > 0) record.gaps.add(t('观察节点 RAM 有累计覆盖，是否影响本条无法确定'))
      if (coverage.timelineTruncated) record.gaps.add(t('网关较早时间线超出保留范围'))
      const ids = new Set([clean(e.origin), clean(e.dst), ...record.events.map(v => clean(v.reporter || v.node_id))])
      for (const n of coverage.nodes ?? []) {
        if (!ids.has(clean(n.id || n.node_id))) continue
        const a = n.agent && typeof n.agent === 'object' ? n.agent as LegacyRow : {}
        if (Number(a.record_overwritten) > 0) record.gaps.add(t('相关节点 RAM 有累计覆盖，是否影响本条无法确定'))
        if (Number(a.sampled_records_skipped) > 0) record.gaps.add(t('相关节点报告含抽样跳过，观察不完整'))
        if (Number(n.events_dropped) > 0) record.gaps.add(t('节点事件报告有溢出计数'))
      }
      if (this.rows.size > 128) { const oldest = [...this.rows].filter(([k]) => k !== coverage.pinnedKey).sort((a, b) => a[1].ordinal - b[1].ordinal)[0]; if (oldest) this.rows.delete(oldest[0]) }
    }
    return [...this.rows.values()].sort((a, b) => b.ordinal - a.ordinal).map(record => {
      const evidence = [...new Set([...record.events, ...record.payloadEvidence.values(), ...(record.receipt ? [record.receipt] : [])])]
      return { ...packets(evidence)[0]!, coverageNotes: [...record.gaps], last: record.events[record.events.length - 1]! }
    })
  }
}
