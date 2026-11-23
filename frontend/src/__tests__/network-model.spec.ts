import { afterEach, describe, expect, it } from 'vitest'
import { clearLayout, gpsLayout, hasPosition, linkHistorical, nodeState, parseSnapshot, readPositions } from '@/network/model'
import type { NetworkSnapshot } from '@/network/types'
// Development fixture is plain JavaScript and deliberately uses no production device transport.
// @ts-expect-error plain JavaScript development fixture
import { makeSnapshot, SCENARIOS } from '../../../scripts/network-studio/mock.mjs'
const fixture = (scenario = 'nominal') => makeSnapshot({ scenario, at: 100000 }) as NetworkSnapshot
afterEach(() => localStorage.clear())

describe('versioned network observation contract', () => {
  it('accepts every synthetic scenario, including empty and missing GPS', () => {
    for (const scenario of SCENARIOS) expect(parseSnapshot(fixture(scenario)).schema).toBe('network.snapshot.v1')
  })
  it('does not accept an unversioned or malformed response as an empty network', () => {
    expect(() => parseSnapshot({ nodes: [] })).toThrow('NETWORK_SCHEMA_INVALID')
    const bad = fixture(); bad.provenance = 'live' as never
    expect(() => parseSnapshot(bad)).toThrow()
  })
  it('rejects duplicate identity, non-finite RF and invalid positions', () => {
    const duplicates = fixture(); duplicates.nodes.push(duplicates.nodes[0]!)
    expect(() => parseSnapshot(duplicates)).toThrow('NETWORK_NODE_INVALID')
    const invalidRF = fixture(); invalidRF.nodes[1]!.radio.rssiDbm = Number.NaN
    expect(() => parseSnapshot(invalidRF)).toThrow('NETWORK_NODE_INVALID')
    const invalidGPS = fixture(); invalidGPS.nodes[1]!.position!.lat = 190
    expect(() => parseSnapshot(invalidGPS)).toThrow('NETWORK_POSITION_INVALID')
  })
  it('normalizes legacy device names/roles to NODE without assigning a type tag', () => {
    const s = fixture(); s.nodes[1]!.label = 'UAV 01'; s.nodes[1]!.role = 'aircraft'
    const parsed = parseSnapshot(s)
    expect(parsed.nodes[1]!.label).toMatch(/^NODE /); expect(parsed.nodes[1]!.role).toBe('node')
    expect(parsed.nodes[1]!.tag).toBeUndefined(); expect(parsed.nodes[1]!.id).toBe(s.nodes[1]!.id)
    const invalid = fixture(); invalid.nodes[1]!.tag = 'plane' as never
    expect(() => parseSnapshot(invalid)).toThrow('NETWORK_NODE_INVALID')
  })
  it('rejects direction endpoints without member identity', () => {
    const bad = fixture(); bad.links[0]!.to = 'invented-member'
    expect(() => parseSnapshot(bad)).toThrow('NETWORK_LINK_INVALID')
  })
  it('rejects invalid event and binding identities', () => {
    const badEvent = fixture(); badEvent.events[0]!.nodeId = 'absent'
    expect(() => parseSnapshot(badEvent)).toThrow('NETWORK_EVENT_INVALID')
    const badBinding = fixture(); badBinding.nodes[1]!.binding = { kind: 'plane' as never, id: 'x' }
    expect(() => parseSnapshot(badBinding)).toThrow('NETWORK_BINDING_INVALID')
  })
})

describe('evidence ages and receiver health', () => {
  it('separates interrupted observation from offline or stale node reports', () => {
    const s = fixture('interrupted')
    expect(nodeState(s.nodes[1]!, s, 100000)).toBe('interrupted')
    const healthy = fixture()
    expect(nodeState(healthy.nodes[1]!, healthy, 100000, true)).toBe('interrupted')
  })
  it('ages a report without fresh HTTP responses and retains unknown fields', () => {
    const s = fixture(), n = s.nodes[1]!
    expect(nodeState(n, s, 100000)).toBe('recent')
    expect(nodeState(n, s, 140000)).toBe('stale')
    expect(nodeState({ ...n, reportedAt: null }, s, 100000)).toBe('unknown')
  })
  it('expires link evidence independently of the next network request', () => {
    const s = fixture(), e = s.links[0]!
    expect(linkHistorical(e, s, e.sampledAt! + e.validForMs! - 1)).toBe(false)
    expect(linkHistorical(e, s, e.sampledAt! + e.validForMs!)).toBe(true)
    expect(linkHistorical({ ...e, sampledAt: null }, s, 100000)).toBe(true)
    expect(linkHistorical({ ...e, validForMs: null }, s, 100000)).toBe(true)
    expect(linkHistorical({ ...e, state: 'unknown' }, s, 100000)).toBe(true)
  })
  it('never upgrades a LoRa uplink into a Wi-Fi relation or end-to-end receipt', () => {
    const s = fixture()
    const uplink = s.links.find(e => e.kind === 'lora')!
    expect(s.nodes.find(n => n.id === uplink.to)?.role).toBe('gateway')
    expect(uplink.snrDb).not.toBeNull()
    expect(s.links.find(e => e.kind === 'wifi')!.snrDb).toBeNull()
  })
})

describe('logical and geographic layouts', () => {
  it('lays out all 30 members plus the receiver without geographic assumptions', () => {
    const s = fixture('dense'), points = clearLayout(s.nodes)
    expect(Object.keys(points)).toHaveLength(31)
    expect(Object.values(points).every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true)
  })
  it('does not invent coordinates for absent or expired GPS', () => {
    expect(gpsLayout(fixture('no-gps').nodes, 100000, 30000)).toEqual({})
    const s = fixture()
    expect(Object.keys(gpsLayout(s.nodes, 100000, 30000))).toHaveLength(5)
    expect(gpsLayout(s.nodes, 140000, 30000)).toEqual({})
    expect(hasPosition(s.nodes[5]!, 100000, 30000)).toBe(false)
  })
  it('places east to the right and north above, without making physical positions into node slots', () => {
    const s = fixture(); const original = s.nodes[1]!
    const south = { ...original, id: 'south', position: { lat: 40, lon: 116, observedAt: 100000, source: 'test' } }
    const north = { ...south, id: 'north', position: { ...south.position, lat: 40.001 } }
    const east = { ...south, id: 'east', position: { ...south.position, lon: 116.001 } }
    const p = gpsLayout([south, north, east], 100000, 30000)
    expect(p.north!.y).toBeLessThan(p.south!.y); expect(p.east!.x).toBeGreaterThan(p.south!.x)
    expect(p.north!.x).toBeCloseTo(p.south!.x); expect(p.east!.y).toBeCloseTo(p.south!.y)
  })
  it('keeps a local GPS group crossing the antimeridian adjacent', () => {
    const n = fixture().nodes[1]!
    const nodes = [{ ...n, id: 'a', position: { ...n.position!, lon: 179.999 } }, { ...n, id: 'b', position: { ...n.position!, lon: -179.999 } }]
    const p = gpsLayout(nodes, 100000, 30000)
    expect(p.b!.x).toBeGreaterThan(p.a!.x); expect(Math.abs(p.b!.x - p.a!.x)).toBeLessThanOrEqual(740.01)
  })
  it('validates browser-saved manual positions and isolates sources', () => {
    localStorage.setItem('a', JSON.stringify({ good: { x: 5, y: 8 }, bad: { x: '5', y: 8 }, huge: { x: 9999999, y: 0 } }))
    expect(readPositions('a')).toEqual({ good: { x: 5, y: 8 } })
    expect(readPositions('b')).toEqual({})
    localStorage.setItem('a', '{bad')
    expect(readPositions('a')).toEqual({})
  })
})
