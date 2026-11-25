import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { resolve } from 'node:path'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import NetworkEngineering from '@/components/network/NetworkEngineering.vue'
import { NetworkClient } from '@/network/api'
import { checkedFleet, LegacyEngineering } from '@/network/legacy'
import { gatewaySnapshot, rejectSyntheticMarkers } from '@/network/gateway'
import { nativeSnapshot } from '@/network/native'
import { linkHistorical, nodeState } from '@/network/model'
import { PacketLog, packets, destinationEvidence, timelineEvents, type PacketEvent } from '@/network/packet-evidence'
import { useNetworkStore } from '@/stores/network'
import { legacyGatewayFixture } from './fixtures/network'
const a = '90:da:72:48:a4:f8', b = '90:da:72:48:a5:cc', missing = '90:da:72:48:a4:e0'
const at = 1800000000000
const reply = (value: unknown, status = 200) => ({ ok: status >= 200 && status < 300, status, json: async () => structuredClone(value) })
const topology = () => { const v = legacyGatewayFixture(); return { ...v, labels: { [a]: '1', [b]: '2' } as Record<string, string>, reports: v.reports.map(r => ({ ...r, report: { ...r.report, observer_id: a, neighbors: r.report.neighbors.map(n => ({ ...n, peer_id: b })) } })) } }
function event(overrides: Partial<PacketEvent> = {}): PacketEvent { return { event: 'tx_submit', origin: a, origin_boot: 17, seq: 3, dst: b, reporter: a, node_id: a, observer_id: a, next_hop: b, payload_hex: '6869', ...overrides } }
const receipt = (overrides: Partial<PacketEvent> = {}) => event({ event: 'rx_local', reporter: b, node_id: b, observer_id: b, previous_hop: a, ...overrides })
const sourceState = () => ({ schema: 'lora.sources.v1', selection: 'auto', preferred_source_id: null, selected_source_id: 'legacy:configured', selection_epoch: 3, sources: [{ id: 'legacy:configured', label: 'TEST ONLY', kind: 'legacy', available: true, verified: true, selected: true, state: 'connected' }, { id: 'serial:unverified', label: 'TEST UNVERIFIED', kind: 'serial', available: true, verified: false, selected: false, state: 'connected' }] })
let sessionActive: string | null, instance: string, requests: { resource: string; init?: RequestInit }[], fetcher: ReturnType<typeof vi.fn>
const options = { mode: 'gateway' as const, protocol: 'lora-v1' as const, gatewayRelayPath: '/__network_gateway', engineeringRelayPath: '/__baseline_engineering' }
beforeEach(() => {
  localStorage.clear(); setActivePinia(createPinia()); sessionActive = null; instance = 'test-service-1'; requests = []
  fetcher = vi.fn(async (url: string, init?: RequestInit) => {
    const resource = new URL(url, 'http://localhost').searchParams.get('resource') || url
    requests.push({ resource, init })
    if (resource === '/health') return reply({ status: 'ok', role: 'observation_only', gateway_instance: instance })
    if (resource === '/api/v1/lora/sources') return reply(sourceState())
    if (resource === '/api/v1/fleet') return reply({ schema_version: 1, nodes: [{ mac: a, node_id: 1 }, { mac: b, node_id: 2 }, { mac: missing, node_id: 3 }] })
    if (resource === '/api/v1/recovery') return reply({ schema: 'studio.recovery.v1', state: 'unknown', reason: 'test no supervisor' }, 503)
    if (resource === '/api/v1/replay/sessions') return reply({ sessions: [{ id: 'saved', started_ms: at, count: 103, active: false }], active_id: sessionActive, error: null })
    if (resource === '/api/v1/lora/topology') return reply(topology())
    if (resource === '/api/v1/lora/sources/select') return reply({ ...sourceState(), selection: 'manual', preferred_source_id: 'legacy:configured', selection_epoch: 4 })
    if (resource === '/api/v1/replay/start') { sessionActive = 'recorded'; return reply({ id: 'recorded' }) }
    if (resource === '/api/v1/replay/stop') { const id = sessionActive; sessionActive = null; return reply({ id }) }
    if (resource.startsWith('/api/v1/replay/session?')) {
      const q = new URL(resource, 'http://localhost').searchParams, offset = Number(q.get('offset'))
      const raw = topology(); raw.labels = {}; raw.reports.forEach(r => { r.report.neighbors = [] })
      return reply({ id: 'saved', total: 103, offset, frames: Array.from({ length: Math.min(25, 103 - offset) }, (_, i) => ({ t_ms: at + (offset + i) * 1000, topology: raw })) })
    }
    throw new Error('unexpected request ' + resource)
  })
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers(); localStorage.clear() })

describe('typed original Studio engineering adapter', () => {
  it('does not overlay current engineering health or registry metadata on a historical frame', () => {
    const store = useNetworkStore(); store.mode = 'replay'
    store.capabilities = { schema: 'network.capabilities.v1', mock: false, recording: true, sourceSelection: true, sources: [], selectedSourceId: '', scenario: null, engineering: true }
    const wrapper = mount(NetworkEngineering)
    try { expect(wrapper.find('.core-health').exists()).toBe(false); expect(wrapper.text()).toContain('实时来源、登记与健康信息不叠加') }
    finally { wrapper.unmount(); store.stop() }
  })
  it('enables only the explicit separate engineering bridge, preserving read-only topology transport', async () => {
    const client = new NetworkClient('http://127.0.0.1:8794', options)
    const caps = await client.capabilities(); expect(caps.engineering).toBe(true); expect(caps.recording).toBe(true)
    expect(caps.sources.find(s => s.id === 'serial:unverified')?.selectable).toBe(false)
    const s = await client.snapshot(); expect(s.provenance).toBe('unknown')
    expect(s.nodes.find(n => n.id === missing)).toMatchObject({ registration: 'fleet', reportedAt: null, label: 'NODE 03' })
    expect(s.links.some(e => e.from === missing || e.to === missing)).toBe(false)
    const topologyRequest = requests.find(r => r.resource === '/api/v1/lora/topology')!
    expect(topologyRequest.init?.headers).toEqual({ 'X-Network-Gateway': 'readonly' })
    expect(requests.filter(r => r.init?.method === 'POST')).toEqual([])
  })
  it('does not silently enable engineering writes for direct or non-loopback gateways', async () => {
    for (const client of [new NetworkClient('http://127.0.0.1:8794', { mode: 'gateway', protocol: 'lora-v1' }), new NetworkClient('http://192.168.1.20:8794', options)]) {
      expect((await client.capabilities()).recording).toBe(false)
      await expect(client.record('start')).rejects.toThrow('NETWORK_GATEWAY_READ_ONLY')
    }
    expect(requests).toEqual([])
  })
  it('maps the legacy stop returned ID to an inactive recorder, and recovers an existing active recording', async () => {
    sessionActive = 'already-running'
    const client = new NetworkClient('http://127.0.0.1:8794', options)
    expect((await client.capabilities()).recordingActiveId).toBe('already-running')
    expect(await client.record('stop')).toEqual({ id: null })
    expect(await client.record('start')).toEqual({ id: 'recorded' })
    expect(requests.filter(r => r.init?.method === 'POST').every(r => (r.init?.headers as Record<string, string>)['X-Baseline-Engineering'] === 'operator')).toBe(true)
  })
  it('does not let an older sessions poll resurrect a recording after its stop response', async () => {
    sessionActive = 'recorded'
    const engine = new LegacyEngineering('http://127.0.0.1:8794', '/__baseline_engineering'); await engine.initialize()
    let finish: ((v: unknown) => void) | undefined
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const older = engine.sessions()
    await engine.record('stop')
    finish!(reply({ sessions: [], active_id: 'recorded', error: null })); await older
    expect(engine.state.recordingId).toBeNull()
  })
  it('preserves original frame timestamps and paginates without applying the current fleet to history', async () => {
    const client = new NetworkClient('http://127.0.0.1:8794', options); await client.capabilities()
    const page = await client.replay('saved', 100)
    expect(page).toMatchObject({ total: 103, offset: 100, paginated: true })
    expect(page.frames).toHaveLength(3); expect(page.frames[0]?.observedAt).toBe(at + 100000)
    expect(page.frames.every(s => s.provenance === 'unknown' && !s.nodes.some(n => n.id === missing))).toBe(true)
    expect(requests.some(r => r.resource.endsWith('offset=100&limit=25'))).toBe(true)
  })
  it('retains known but now absent reporters only within the exact source epoch', async () => {
    const raw = topology(), client = new NetworkClient('http://127.0.0.1:8794', { mode: 'gateway', protocol: 'lora-v1' })
    fetcher.mockImplementation(async () => reply(raw))
    const first = await client.snapshot(), id = first.nodes.find(n => n.role !== 'gateway' && n.reportedAt !== null)!.id
    raw.reports = []; raw.labels = {}; await new Promise(resolve => setTimeout(resolve, 1))
    const second = await client.snapshot(); expect(second.nodes.find(n => n.id === id)?.reportedAt).toBe(first.nodes.find(n => n.id === id)?.reportedAt)
    Object.assign(raw, { selection_epoch: 10, source_id: 'other-source' })
    expect((await client.snapshot()).nodes.some(n => n.id === id)).toBe(false)
  })
  it('surfaces missing fleet/recovery evidence rather than presenting a healthy registry or successful recovery', async () => {
    const engine = new LegacyEngineering('http://127.0.0.1:8794', '/__baseline_engineering')
    await engine.initialize(); expect(engine.state.recovery?.state).toBe('unknown')
    expect(() => checkedFleet({ schema_version: 1, nodes: [{ mac: a, node_id: 1 }, { mac: b, node_id: 1 }] })).toThrow('BASELINE_FLEET_CONFLICT')
    expect(() => checkedFleet({ schema_version: 1, nodes: [{ mac: a, node_id: 0 }] })).toThrow()
  })
  it('does not turn a late aborted engineering response into current metadata', async () => {
    const engine = new LegacyEngineering('http://127.0.0.1:8794', '/__baseline_engineering'), controller = new AbortController()
    let finish: ((v: unknown) => void) | undefined
    fetcher.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const initializing = engine.initialize(controller.signal); controller.abort()
    finish!(reply({ status: 'ok', role: 'observation_only', gateway_instance: 'late' }))
    await expect(initializing).rejects.toThrow(); expect(engine.state.available).toBe(false)
  })
  it('bounds native timeline bootstrap and explicitly exposes the skipped observation window', async () => {
    const client = new NetworkClient('http://127.0.0.1:8794', options); await client.capabilities()
    fetcher.mockImplementation(async (url: string) => {
      const resource = new URL(url, 'http://localhost').searchParams.get('resource')
      if (resource === '/api/v1/state') return reply({ schema_version: 1, gateway_instance: 'native-test', cursor: 5000, nodes: [], edges: [] })
      expect(resource).toBe('/api/v1/timeline?after=4488')
      return reply({ schema_version: 1, gateway_instance: 'native-test', cursor: 5000, events: [], oldest_cursor: 1 })
    })
    const evidence = await client.evidence(0)
    expect(evidence.windowTruncated).toBe(true); expect(evidence.timeline.oldest_cursor).toBe(1)
  })
  it('supports bounded global seeking across persistent replay pages', async () => {
    const store = useNetworkStore()
    try {
      await store.start('real', { schema: 'network.config.v2', enabled: true, mode: 'gateway', gatewayRelayPath: options.gatewayRelayPath, engineeringRelayPath: options.engineeringRelayPath, profiles: { server: { apiBaseUrl: '', protocol: 'network-v1' }, gateway: { apiBaseUrl: 'http://127.0.0.1:8794', protocol: 'lora-v1' } } })
      await store.openReplay('saved'); expect(store.replayTotal).toBe(103); expect(store.replay?.frames).toHaveLength(25)
      await store.seek(102); expect(store.frame).toBe(102); expect(store.now).toBe(at + 102000); expect(store.replay?.frames).toHaveLength(3)
      await store.seek(0); expect(store.frame).toBe(0); expect(store.now).toBe(at)
    } finally { store.stop() }
  })
})

describe('honest roster and Wi-Fi observation semantics', () => {
  it('shows label-only absentees without inventing reports, GPS, RF or links', () => {
    const v = topology(); v.labels[missing] = '3'
    const s = gatewaySnapshot(v, at, 'test'), n = s.nodes.find(n => n.id === missing)!
    expect(nodeState(n, s, at)).toBe('unknown'); expect(n).toMatchObject({ registration: 'label', reportedAt: null, position: null })
    expect(s.links.some(e => e.from === missing || e.to === missing)).toBe(false)
  })
  it('applies a reporters own validity window rather than another slower node period', () => {
    const v = topology(); Object.assign(v.receiver, { mode: 'node_serial' })
    const first = v.reports[0]!; Object.assign(first, { recent_threshold_ms: 35000, pc_receive_age_ms: 40000 }); Object.assign(first.report, { report_period_ms: 10000 })
    const s = gatewaySnapshot(v, at, 'test'), n = s.nodes.find(n => n.id === first.report.observer_id)!
    expect(nodeState(n, s, at)).toBe('stale'); expect(s.links.find(e => e.from === n.id && e.kind === 'lora')?.validForMs).toBe(35000)
  })
  it('rejects explicit synthetic RF and host/fake-Agent evidence even when nested', () => {
    for (const marker of [{ rf_source: 'simulated' }, { radio_source: 'host_model_simulated' }, { agent: { source: 'actual_E2_fake_agent_function_processes' } }]) expect(() => rejectSyntheticMarkers(marker)).toThrow('NETWORK_SYNTHETIC_REJECTED')
  })
  it('honors Wi-Fi sample freshness, reboot invalidation and exact/lower-bound ages', () => {
    const value = { schema_version: 1, gateway_instance: 'isolated-state', offline_after_ms: 30000, stale_after_ms: 30000, nodes: [{ node_id: a, report_age_ms: 1000 }, { node_id: b, report_age_ms: 1500 }], edges: [{ from: a, to: b, state: 'confirmed', sample_age_ms: 2000, age_is_lower_bound: false, sample_freshness: 'fresh', invalidated_reason: null as string | null, telemetry_status: 'online', mutual_confirmed: true, rf_source: 'measured', rssi_dbm: -55 }] }
    expect(nativeSnapshot(value, at).links[0]?.state).toBe('oneway') // A lone direction cannot be mutual, even if its raw flag says so.
    value.edges.push({ ...value.edges[0]!, from: b, to: a, sample_age_ms: 29000 })
    const s = nativeSnapshot(value, at); expect(s.provenance).toBe('unknown'); expect(s.links[0]?.state).toBe('mutual'); expect(linkHistorical(s.links[0]!, s, at)).toBe(false)
    expect(linkHistorical(s.links[0]!, s, at + 1001)).toBe(true) // Reverse evidence expires first.
    value.edges[0]!.invalidated_reason = 'peer_boot_mismatch'
    const invalid = nativeSnapshot(value, at); expect(invalid.links[0]?.state).toBe('unknown'); expect(linkHistorical(invalid.links[0]!, invalid, at)).toBe(true)
    value.edges[0]!.age_is_lower_bound = true
    expect(nativeSnapshot(value, at).links[0]?.sampledAt).toBeNull()
  })
})

describe('ported packet evidence and bounded coverage', () => {
  it('unwraps the original State timeline envelope without replacing its reporter or losing byte identity', () => {
    const raw = [event(), receipt()].map((e, i) => ({ cursor: i + 1, received_ms: at, node_id: e.reporter, type: e.event, data: e }))
    const flattened = timelineEvents(raw, 'instance-1')
    expect(flattened[1]).toMatchObject({ reporter: b, event: 'rx_local', event_id: 'gateway/instance-1/2', payload_hex: '6869' })
    expect(packets(flattened)[0]?.state).toBe('destination_received')
    expect(timelineEvents(raw, 'instance-2')[1]?.event_id).not.toBe(flattened[1]?.event_id)
    expect(destinationEvidence(timelineEvents([{ ...raw[1], node_id: a }], 'instance-1')[0]!)).toBe(false)
    expect(packets(timelineEvents([{ ...raw[1], type: 'tx_submit' }], 'instance-1'))).toEqual([])
    expect(raw[1]?.data).toEqual(receipt())
  })
  it('requires destination self-report, matching observer identity, original packet identity and complete raw bytes', () => {
    expect(destinationEvidence(receipt())).toBe(true)
    for (const v of [receipt({ reporter: a }), receipt({ observer_id: a }), receipt({ node_id: a }), receipt({ origin_boot: 0 }), receipt({ seq: 0 }), receipt({ payload_hex: undefined })]) expect(destinationEvidence(v)).toBe(false)
    expect(packets([event()])[0]?.state).toBe('awaiting_receipt')
    expect(packets([event({ event: 'tx_link_ok' })])[0]?.delivery).toBe('unconfirmed')
  })
  it('preserves destination receipt despite later local failures and keeps conflicting original bytes', () => {
    expect(packets([event(), receipt(), event({ event: 'tx_link_fail' })])[0]?.state).toBe('destination_received')
    expect(packets([event(), receipt({ payload_hex: '627965' })])[0]?.state).toBe('payload_conflict')
    expect(packets([event({ event: 'route_selected', path: [a, b] })])[0]?.state).toBe('observed')
  })
  it('never merges packet identities across origin boots, route requests or control envelopes', () => {
    expect(packets([event(), event({ origin_boot: 18 })])).toHaveLength(2)
    for (const e of [event({ kind: 'control' }), event({ packet_kind: 'ND' }), event({ sequence_scope: 'route_request' }), event({ event: 'field_pc_envelope' })]) expect(packets([e])).toEqual([])
  })
  it('retains receipt and conflicting bytes after 48-event pruning with explicit incompleteness notes', () => {
    const log = new PacketLog()
    log.merge([event(), receipt({ event_id: 'receipt', payload_hex: '627965' })])
    const rows = log.merge(Array.from({ length: 70 }, (_, i) => event({ event: 'tx_link_fail', event_id: 'late-' + i })), { timelineTruncated: true, nodes: [{ node_id: b, agent: { record_overwritten: 1, sampled_records_skipped: 2 } }] })
    expect(rows[0]?.state).toBe('payload_conflict'); expect(rows[0]?.payloads).toHaveLength(2); expect(rows[0]?.coverageNotes.length).toBeGreaterThanOrEqual(3)
  })
  it('matches the original model state/delivery/raw-byte decisions for adversarial event sequences', () => {
    const original = readFileSync(resolve(process.cwd(), '../research/agent_native_network/mobile_gateway/studio-model.js'), 'utf8')
    const model = vm.runInNewContext(original + '\nMobileStudioModel', { TextDecoder, Uint8Array })
    const mapSource = readFileSync(resolve(process.cwd(), '../research/agent_native_network/mobile_gateway/map.js'), 'utf8')
    const originalMap = vm.runInNewContext(mapSource + '\nMobileMapModel')
    const sequences = [[event()], [event({ event: 'tx_queued' })], [event({ event: 'route_no_route', reason: 2 })], [event({ event: 'route_no_route', reason: 6 })], [event({ event: 'send_rejected' })], [event({ event: 'route_selected', path: [a, b] })], [event(), receipt()], [event(), receipt({ payload_hex: '627965' })], [event(), receipt(), event({ event: 'tx_api_failed' })], [event(), event({ event: 'rx_relay', reporter: b })], [receipt({ observer_id: a })]]
    for (const sequence of sequences) {
      const old = model.packets(sequence, originalMap.eventInfo)[0], current = packets(sequence)[0]!
      expect({ state: current.state, delivery: current.delivery, received: current.received, bytes: current.payloads }).toEqual({ state: old.state, delivery: old.delivery, received: old.received, bytes: old.payloads })
    }
  })
})
