// All inputs are fabricated unit fixtures, not measurements or current hardware acceptance.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import NetworkTopology from '@/components/network/NetworkTopology.vue'
import NetworkRelations from '@/components/network/NetworkRelations.vue'
import NetworkView from '@/views/NetworkView.vue'
import { gatewaySnapshot } from '@/network/gateway'
import { nativeSnapshot } from '@/network/native'
import { linkEvidenceState, linkHistorical, nodeState, parseSnapshot } from '@/network/model'
import { linkEvidenceLabel } from '@/network/presentation'
import { useNetworkStore } from '@/stores/network'
import { legacyGatewayFixture } from './fixtures/network'

const at = 100000
const sample = () => gatewaySnapshot(legacyGatewayFixture(), at, 'TEST-ONLY-client')
const wifi = (s = sample()) => s.links.find(e => e.kind === 'wifi')!
const props = (s = sample()) => ({ snapshot: s, now: at, interrupted: false, selected: wifi(s).to, selectedLink: '', layout: 'clear' as const, linkFilter: 'all', namespace: 'TEST-ONLY', demo: false })
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(at); localStorage.clear() })
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

describe('link display evidence is not a fabricated validity contract', () => {
  it('marks a recent legacy neighbor blue without declaring its validity or provenance', () => {
    const s = sample(), e = wifi(s)
    expect(linkEvidenceState(e, s, at)).toBe('recent-sample')
    expect(linkEvidenceLabel(e, s, at)).toBe('近期邻居采样 · 有效期未知')
    expect(e.validForMs).toBeNull(); expect(s.provenance).toBe('unknown')
    expect(linkHistorical(e, s, at)).toBe(true) // It still fails the current-connectivity proof gate.
    expect(nodeState(s.nodes.find(n => n.id === e.from)!, s, at)).toBe('unknown') // A neighbor sighting is not its own report.
  })
  it('does not infer the legacy origin from a generic unbounded network-v1 edge', () => {
    const s = sample(), e = { ...wifi(s) }; delete e.sampleOrigin
    expect(linkEvidenceState(e, s, at)).toBe('unknown')
    expect(linkEvidenceLabel(e, s, at)).toBe('有效性未知')
  })
  it('ages legacy samples using browser elapsed time but never labels the unknown TTL expired', () => {
    const s = sample(), e = wifi(s)
    expect(linkEvidenceState(e, s, at + 31000)).toBe('report-stale')
    expect(linkEvidenceLabel(e, s, at + 31000)).toBe('报告超时 · 仅保留采样')
    expect(e.validForMs).toBeNull()
  })
  it('distinguishes an old neighbor sample inside a new report from a timed-out report', () => {
    const raw = legacyGatewayFixture(); raw.reports[0]!.report.neighbors[0]!.seen_age_ms = 45000
    const s = gatewaySnapshot(raw, at, 'TEST-ONLY')
    expect(nodeState(s.nodes.find(n => n.id === wifi(s).to)!, s, at)).toBe('recent')
    expect(linkEvidenceState(wifi(s), s, at)).toBe('older-sample')
    expect(linkEvidenceLabel(wifi(s), s, at)).toBe('较早邻居采样 · 有效期未知')
  })
  it('honors the observer-specific reporting window without inventing a Wi-Fi TTL', () => {
    const s = sample(), e = wifi(s), reporter = s.nodes.find(n => n.id === e.to)!
    reporter.reportTimeoutMs = 1000
    expect(linkEvidenceState(e, s, at + 400)).toBe('older-sample') // Sample age1100, report age900.
    expect(linkEvidenceState(e, s, at + 501)).toBe('report-stale')
    expect(e.validForMs).toBeNull()
  })
  it('requires a known sample time and reporter time for blue recent samples', () => {
    const s = sample(), e = wifi(s)
    expect(linkEvidenceState({ ...e, sampledAt: null }, s, at)).toBe('unknown')
    s.nodes.find(n => n.id === e.to)!.reportedAt = null
    expect(linkEvidenceState(e, s, at)).toBe('unknown')
  })
  it('does not turn missing legacy validity bits into a blue or green relationship', () => {
    const raw = legacyGatewayFixture(); raw.reports[0]!.report.neighbors[0]!.valid = 0
    const s = gatewaySnapshot(raw, at, 'TEST-ONLY')
    expect(linkEvidenceState(wifi(s), s, at)).toBe('unknown')
  })
  it('reserves red for an explicitly reported loss, then ages it into retained history', () => {
    const s = sample(), e = wifi(s); e.state = 'lost'
    expect(linkEvidenceState(e, s, at)).toBe('lost')
    expect(linkEvidenceLabel(e, s, at)).toBe('节点上报失效')
    expect(linkEvidenceState(e, s, at + 31000)).toBe('report-stale')
    expect(linkEvidenceState(e, s, at, true)).toBe('interrupted')
  })
  it('expires a known deadline precisely, including a zero validity window', () => {
    const s = sample(), e = s.links.find(e => e.kind === 'lora')!
    const deadline = e.sampledAt! + e.validForMs!
    expect(linkEvidenceState(e, s, deadline - 1)).toBe('current')
    expect(linkEvidenceState(e, s, deadline)).toBe('expired')
    expect(linkEvidenceLabel(e, s, deadline)).toBe('采样已过期')
    expect(linkEvidenceState({ ...e, validForMs: 0 }, s, e.sampledAt!)).toBe('expired')
  })
  it('does not call a missing TTL expired, even when the sample is old', () => {
    const s = sample(), e = { ...wifi(s), sampleOrigin: undefined, sampledAt: 1 }
    expect(linkEvidenceState(e, s, at)).toBe('unknown')
  })
  it('does not present an interrupted observer as live mutual connectivity or node loss', () => {
    const s = sample(), e = wifi(s)
    expect(linkEvidenceState(e, s, at, true)).toBe('interrupted')
    s.receiver.state = 'unavailable'
    expect(linkEvidenceState(e, s, at)).toBe('interrupted')
  })
  it('preserves the optional legacy marker across parsing and rejects unknown origin kinds', () => {
    const s = sample(); expect(wifi(parseSnapshot(s)).sampleOrigin).toBe('legacy-neighbor')
    wifi(s).sampleOrigin = 'assert-current' as never
    expect(() => parseSnapshot(s)).toThrow('NETWORK_LINK_INVALID')
  })
})

function nativeFixture() {
  const a = '02:00:00:01:00:01', b = '02:00:00:01:00:02'
  return { schema_version: 1, gateway_instance: 'TEST-ONLY', offline_after_ms: 30000, stale_after_ms: 30000,
    nodes: [{ node_id: a, report_age_ms: 500 }, { node_id: b, report_age_ms: 500 }],
    edges: [{ from: a, to: b, state: 'confirmed', sample_age_ms: 31000, age_is_lower_bound: false,
      sample_freshness: 'stale', invalidated_reason: null as string | null, telemetry_status: 'online', mutual_confirmed: false, rf_source: 'measured', rssi_dbm: -55 }] }
}
describe('known native expiry is not discarded when reloading an already-stale sample', () => {
  it('retains a known expired deadline instead of converting expiry into an unknown TTL', () => {
    const s = nativeSnapshot(nativeFixture(), at), e = s.links[0]!
    expect(e.state).toBe('unknown'); expect(e.validForMs).toBe(30000)
    expect(linkEvidenceState(e, s, at)).toBe('expired')
  })
  it('keeps invalidated and lower-bound-only evidence unknown, never current', () => {
    const raw = nativeFixture(); raw.edges[0]!.invalidated_reason = 'peer_boot_changed'
    let s = nativeSnapshot(raw, at); expect(s.links[0]!.validForMs).toBeNull()
    expect(linkEvidenceState(s.links[0]!, s, at)).toBe('unknown')
    raw.edges[0]!.invalidated_reason = null; raw.edges[0]!.age_is_lower_bound = true
    s = nativeSnapshot(raw, at); expect(s.links[0]!.sampledAt).toBeNull()
    expect(linkEvidenceState(s.links[0]!, s, at)).toBe('unknown')
  })
})

describe('topology, adjacency and inspector share one evidence label', () => {
  it('does not render reported bidirectionality as a green current mutual link', () => {
    const s = sample(), w = mount(NetworkTopology, { props: props(s) })
    const e = w.find('.edge[data-evidence="recent-sample"]')
    expect(e.exists()).toBe(true); expect(e.classes()).not.toContain('mutual')
    expect(e.classes()).not.toContain('lost'); expect(e.classes()).not.toContain('historical')
    expect(e.attributes('aria-label')).toContain('新鲜链路')
    expect(e.find('title').text()).toBe('近期邻居采样 · 有效期未知')
    expect(w.find('[data-test="link-evidence-legend"]').text()).not.toContain('过期或无法确认')
    expect(w.find('[data-test="link-recency-note"]').text()).toContain('不证明当前互通')
    w.unmount()
  })
  it('updates the topology and adjacency to report timeout without relabeling it as a lost link', async () => {
    const s = sample(), p = props(s)
    const graph = mount(NetworkTopology, { props: p })
    const table = mount(NetworkRelations, { props: p })
    expect(table.find('[data-evidence="recent-sample"] .evidence-state').text()).toBe('新鲜')
    expect(table.find('[data-evidence="recent-sample"]').attributes('data-kind')).toBe('wifi')
    expect(table.find('[data-evidence="current"]').attributes('data-kind')).toBe('lora')
    expect(table.find('[data-evidence="current"]').attributes('data-state')).toBe('oneway')
    await graph.setProps({ now: at + 31000 }); await table.setProps({ now: at + 31000 })
    expect(graph.find('.edge.impaired[data-evidence="report-stale"]').exists()).toBe(true)
    expect(graph.find('.edge.lost').exists()).toBe(false)
    expect(table.find('[data-evidence="report-stale"] .evidence-state').text()).toBe('暂时失效')
    expect(table.find('[data-evidence="report-stale"] .evidence-state').attributes('title')).toBe('报告超时 · 仅保留采样')
    graph.unmount(); table.unmount()
  })
  it('does not keep a pink loss after the observer is interrupted', async () => {
    const s = sample(); wifi(s).state = 'lost'
    const w = mount(NetworkTopology, { props: props(s) })
    expect(w.find('.edge.lost').exists()).toBe(false)
    expect(w.find(`[data-link="${wifi(s).id}"]`).exists()).toBe(false)
    await w.setProps({ interrupted: true })
    expect(w.findAll('.edge.impaired')).toHaveLength(1)
    expect(w.find('.observer-note').exists()).toBe(true)
    await w.setProps({ now: at + 10000 })
    expect(w.findAll('.edge')).toHaveLength(0)
    w.unmount()
  })
  it('shows the same recent-but-unbounded status and raw reported state in the link inspector', async () => {
    setActivePinia(createPinia()); const store = useNetworkStore()
    vi.spyOn(store, 'start').mockResolvedValue(); vi.spyOn(store, 'stop').mockImplementation(() => undefined)
    const s = sample(); store.snapshot = s; store.receivedAt = at; store.status = 'online'; store.workspace = 'real'
    const w = mount(NetworkView, { props: { workspace: 'real' } })
    await w.find('.edge[data-evidence="recent-sample"]').trigger('click')
    expect(w.find('[data-test="link-evidence-state"]').text()).toBe(linkEvidenceLabel(wifi(s), s, at))
    expect(w.find('[data-test="link-validity"]').text()).toBe('未提供')
    expect(w.find('.inspector').text()).toContain('报告中双向')
    expect(w.find('[data-test="unknown-validity-note"]').text()).toContain('未知也不等于已经过期')
    expect(w.find('[data-evidence="recent-sample"] .evidence-state').text()).toBe('新鲜')
    w.unmount()
  })
})
