import { describe, expect, it } from 'vitest'
import { gatewaySnapshot } from '@/network/gateway'
import { gpsLayout, linkHistorical, nodeState } from '@/network/model'
import { legacyGatewayFixture } from './fixtures/network'

describe('read-only legacy gateway observation adapter', () => {
  it('keeps legacy provenance unknown and names generic instead of claiming device types', () => {
    const s = gatewaySnapshot(legacyGatewayFixture(), 100000, 'test-client')
    expect(s.provenance).toBe('unknown'); expect(s.sourceId).toBe('test-gateway'); expect(s.epoch).toBe(2)
    expect(s.nodes.map(n => n.label)).toEqual(['GATEWAY', 'NODE 01', 'NODE 02'])
    expect(s.nodes[1]!.role).toBe('node'); expect(s.nodes[1]!.tag).toBeUndefined(); expect(s.nodes[1]!.binding).toBeNull()
    expect(s.nodes[1]!.reportedAt).toBe(99500); expect(s.nodes[1]!.position?.observedAt).toBe(98500)
  })
  it('maps the gateway heartbeat age without borrowing a node report timestamp', () => {
    for (const field of ['last_rx_age_ms', 'gateway_last_pull_age_ms']) {
      for (const heartbeatAge of [0, 350]) {
        const raw = legacyGatewayFixture()
        const s = gatewaySnapshot({ ...raw, receiver: { ...raw.receiver, [field]: heartbeatAge } }, 100000, 'test-client')
        expect(s.nodes[0]!.reportedAt).toBe(100000 - heartbeatAge)
        expect(nodeState(s.nodes[0]!, s, 100000)).toBe('recent')
        expect(s.nodes[1]!.reportedAt).toBe(99500)
      }
    }
  })
  it('does not invent a fresh gateway heartbeat when age is missing, invalid or stale', () => {
    for (const heartbeatAge of [undefined, null, -1]) {
      const raw = legacyGatewayFixture()
      const s = gatewaySnapshot({ ...raw, receiver: { ...raw.receiver, last_rx_age_ms: heartbeatAge } }, 100000, 'test-client')
      expect(s.nodes[0]!.reportedAt).toBeNull()
      expect(nodeState(s.nodes[0]!, s, 100000)).toBe('unknown')
    }
    const raw = legacyGatewayFixture()
    const s = gatewaySnapshot({ ...raw, receiver: { ...raw.receiver, last_rx_age_ms: 45000 } }, 100000, 'test-client')
    expect(nodeState(s.nodes[0]!, s, 100000)).toBe('stale')
    const interrupted = gatewaySnapshot({ ...raw, receiver: { ...raw.receiver, gateway_observed: false, last_rx_age_ms: 350 } }, 100000, 'test-client')
    expect(nodeState(interrupted.nodes[0]!, interrupted, 100000)).toBe('interrupted')
  })
  it('separates observer-directed ESP-NOW samples from LoRa uplink RF', () => {
    const s = gatewaySnapshot(legacyGatewayFixture(), 100000, 'test-client')
    const wifi = s.links.find(e => e.kind === 'wifi')!, lora = s.links.find(e => e.kind === 'lora')!
    expect(wifi.from).toBe('02:00:00:01:00:02'); expect(wifi.to).toBe('02:00:00:01:00:01')
    expect(wifi.rssiDbm).toBe(-65); expect(lora.rssiDbm).toBe(-88); expect(lora.snrDb).toBe(7.5)
    expect(wifi.sampledAt).toBe(99300); expect(wifi.validForMs).toBeNull(); expect(linkHistorical(wifi, s, 100000)).toBe(true)
    expect(s.nodes[1]!.radio.frequencyHz).toBe(470500000)
  })
  it('does not reuse node report age as GPS or battery evidence age', () => {
    const raw = legacyGatewayFixture(); raw.reports[0]!.gps_age_ms = undefined as never; raw.reports[0]!.status_age_ms = undefined as never
    const s = gatewaySnapshot(raw, 100000, 'test-client')
    expect(s.nodes[1]!.reportedAt).toBe(99500); expect(s.nodes[1]!.position).toBeNull(); expect(s.nodes[1]!.batteryPercent).toBeNull()
  })
  it('retains expired GPS as historical evidence but omits its geographic marker', () => {
    const raw = legacyGatewayFixture(); raw.reports[0]!.gps_age_ms = 45000
    const s = gatewaySnapshot(raw, 100000, 'test-client')
    expect(s.nodes[1]!.position).not.toBeNull(); expect(gpsLayout(s.nodes, 100000, s.reportTimeoutMs)).toEqual({})
    expect(s.nodes).toHaveLength(3)
  })
  it('does not infer RF or mutual proof when legacy validity bits are absent', () => {
    const raw = legacyGatewayFixture(); raw.reports[0]!.report.neighbors[0]!.valid = 0
    const s = gatewaySnapshot(raw, 100000, 'test-client'), wifi = s.links.find(e => e.kind === 'wifi')!
    expect(wifi.rssiDbm).toBeNull(); expect(wifi.channel).toBeNull(); expect(wifi.state).toBe('unknown')
    expect(s.nodes[2]!.reportedAt).toBeNull(); expect(s.nodes[2]!.position).toBeNull()
  })
  it('separates receiver interruption from individual node report timeout', () => {
    const raw = legacyGatewayFixture(); raw.receiver.gateway_observed = false
    const s = gatewaySnapshot(raw, 100000, 'test-client')
    expect(s.receiver.state).toBe('unavailable'); expect(nodeState(s.nodes[1]!, s, 100000)).toBe('interrupted')
  })
  it('rejects explicit synthetic/fake markers anywhere in legacy payloads', () => {
    for (const marker of [{ mock: true }, { fake_gps: true }, { view_mode: 'demo' }, { provenance: 'synthetic' }]) {
      const raw = { ...legacyGatewayFixture(), metadata: marker }
      expect(() => gatewaySnapshot(raw, 100000, 'test-client')).toThrow('NETWORK_SYNTHETIC_REJECTED')
    }
    const fake = legacyGatewayFixture(); fake.source = 'synthetic-gateway'
    expect(() => gatewaySnapshot(fake, 100000, 'test-client')).toThrow('NETWORK_SYNTHETIC_REJECTED')
  })
  it('rejects malformed reports and invalid coordinates instead of returning a healthy empty network', () => {
    expect(() => gatewaySnapshot({}, 100000, 'test-client')).toThrow('NETWORK_GATEWAY_SCHEMA_INVALID')
    const raw = legacyGatewayFixture(); raw.reports[0]!.report.observer_id = 'invalid'
    expect(() => gatewaySnapshot(raw, 100000, 'test-client')).toThrow('NETWORK_GATEWAY_REPORT_INVALID')
    const gps = legacyGatewayFixture(); gps.reports[0]!.gps.lat_e7 = 1900000000
    expect(() => gatewaySnapshot(gps, 100000, 'test-client')).toThrow('NETWORK_POSITION_INVALID')
  })
  it('keeps an unavailable, unidentified receiver empty without inventing a gateway', () => {
    const s = gatewaySnapshot({ schema: 'lora.topology.v1', source: 'unavailable', reports: [], receiver: { state: 'unavailable' } }, 100000, 'test-client')
    expect(s.receiver.state).toBe('unavailable'); expect(s.nodes).toEqual([]); expect(s.provenance).toBe('unknown')
  })
})
