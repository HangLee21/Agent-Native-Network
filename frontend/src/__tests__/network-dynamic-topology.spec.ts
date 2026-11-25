// TEST ONLY: fabricated mobility, never a claim about the live devices or actual forwarding.
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import NetworkTopology from '@/components/network/NetworkTopology.vue'
import { IMPAIRED_GRACE_MS, topologyLayout, TopologyProjector } from '@/network/topology'
import type { NetworkLink, NetworkSnapshot } from '@/network/types'
const at = 100000
function scene(): NetworkSnapshot {
  const nodes = ['3', '4', '5'].map(id => ({ id, label: `NODE 0${id}`, role: 'node' as const, reportedAt: at, batteryPercent: null, position: null, radio: { rssiDbm: null, snrDb: null, channel: null, frequencyHz: null }, binding: null }))
  const links: NetworkLink[] = []
  for (const [a, b] of [['3', '4'], ['4', '5'], ['3', '5']] as [string, string][]) for (const [from, to] of [[a, b], [b, a]] as [string, string][]) links.push({ id: `${from}>${to}`, from, to, kind: 'wifi', state: 'mutual', sampledAt: at, validForMs: null, sampleOrigin: 'legacy-neighbor', rssiDbm: -50, snrDb: null, channel: 11 })
  return { schema: 'network.snapshot.v1', provenance: 'synthetic', instanceId: 'TEST-ONLY', sourceId: 'TEST-ONLY', epoch: 0, observedAt: at, reportTimeoutMs: 30000, receiver: { id: 'receiver', label: 'TEST ONLY', state: 'receiving', receivedCount: 1 }, nodes, links, events: [] }
}
function cut(s: NetworkSnapshot, a = '3', b = '5') { for (const e of s.links) if ([e.from, e.to].sort().join() === [a, b].sort().join()) e.state = 'lost' }
describe('effective dynamic topology, not a static ring of historical directions', () => {
  it('merges reciprocal directions into one line with two fresh arrows, without modifying source', () => {
    const s = scene(), before = JSON.stringify(s), frame = new TopologyProjector().project(s, at)
    expect(frame.edges).toHaveLength(3); expect(frame.edges.every(e => e.forward && e.reverse)).toBe(true)
    expect(JSON.stringify(s)).toBe(before); expect(s.links.every(e => e.validForMs === null)).toBe(true)
  })
  it('turns the3/4/5 triangle into3--4--5 immediately when3--5 is explicitly lost', () => {
    const s = scene(), p = new TopologyProjector(), before = topologyLayout(s.nodes, p.project(s, at).edges)
    cut(s); const frame = p.project(s, at + 1), after = topologyLayout(s.nodes, frame.edges)
    expect(frame.edges).toHaveLength(2); expect(frame.states['3>5']).toBe('hidden')
    expect(after.positions).not.toEqual(before.positions)
    expect(after.positions['3']!.x).toBeLessThan(after.positions['4']!.x); expect(after.positions['4']!.x).toBeLessThan(after.positions['5']!.x)
    expect(new Set(Object.values(after.positions).map(p => p.y)).size).toBe(1)
  })
  it('separates an isolated5 after4--5 also breaks, retaining the node rather than deleting it', () => {
    const s = scene(); cut(s); cut(s, '4', '5'); const f = new TopologyProjector().project(s, at), g = topologyLayout(s.nodes, f.edges)
    expect(g.groups.map(g => g.members)).toEqual([['3', '4'], ['5']]); expect(g.positions['5']).toBeDefined()
  })
  it('hides removed directions immediately rather than retaining a ghost from old snapshots', () => {
    const s = scene(), p = new TopologyProjector(); p.project(s, at)
    s.links = s.links.filter(e => !['3>5', '5>3'].includes(e.id)); expect(p.project(s, at + 1).edges).toHaveLength(2)
  })
  it('shows a soft timeout briefly, but it cannot hold the layout together and then disappears', () => {
    const s = scene(), p = new TopologyProjector(); s.links.filter(e => ['3>5', '5>3'].includes(e.id)).forEach(e => { e.validForMs = 1000 })
    const f = p.project(s, at + 1000)
    expect(f.edges.filter(e => e.state === 'impaired')).toHaveLength(1)
    const g = topologyLayout(s.nodes, f.edges); expect(g.positions['4']!.y).toBe(g.positions['5']!.y)
    expect(p.project(s, at + 1000 + IMPAIRED_GRACE_MS).edges).toHaveLength(2)
  })
  it('does not revive a repeated unknown report by refreshing its timestamps', () => {
    const s = scene(), p = new TopologyProjector(); s.links.forEach(e => { e.state = 'unknown' })
    expect(p.project(s, at).edges).toHaveLength(3)
    s.links.forEach(e => { e.sampledAt = at + 11000 }); s.nodes.forEach(n => { n.reportedAt = at + 11000 })
    expect(p.project(s, at + 11000).edges).toHaveLength(0)
  })
  it('does not reset a failing edge when the live display clock jitters backwards at a poll', () => {
    const s = scene(), p = new TopologyProjector(); s.links.forEach(e => { e.state = 'unknown' })
    p.project(s, at); p.project(s, at + 9999)
    s.observedAt = at + 9999; p.project(s, at + 9990)
    expect(p.project(s, at + 10001).edges).toHaveLength(0)
  })
  it('restores a reconnected edge and never expires healthy links by the bad-state timer', () => {
    const s = scene(), p = new TopologyProjector(); cut(s); expect(p.project(s, at).edges).toHaveLength(2)
    s.links.forEach(e => { e.state = 'mutual'; e.sampledAt = at + 12000 }); s.nodes.forEach(n => { n.reportedAt = at + 12000 })
    expect(p.project(s, at + 12000).edges).toHaveLength(3)
  })
  it('resets failed-state clocks on epoch/source changes and backwards replay seeks', () => {
    const s = scene(), p = new TopologyProjector(); s.links.forEach(e => { e.state = 'unknown' }); p.project(s, at)
    s.observedAt = at + 11000; expect(p.project(s, at + 11000).edges).toHaveLength(0)
    s.observedAt = at; expect(p.project(s, at).edges).toHaveLength(3)
    s.observedAt = at + 11000; p.project(s, at + 11000); s.epoch++; expect(p.project(s, at + 11001).edges).toHaveLength(3)
  })
  it('does not make one fresh direction look bidirectional when the reverse direction is lost', () => {
    const s = scene(); s.links.find(e => e.id === '5>3')!.state = 'lost'
    const edge = new TopologyProjector().project(s, at).edges.find(e => e.from === '3' && e.to === '5')!
    expect(edge.forward).toBe(true); expect(edge.reverse).toBe(false)
  })
  it('does not use LoRa uplinks as mesh shortcuts or to merge disconnected groups', () => {
    const s = scene(); cut(s); cut(s, '4', '5'); s.nodes.push({ ...s.nodes[0]!, id: 'gateway', role: 'gateway' })
    s.links.push({ ...s.links[0]!, id: '5>gw', from: '5', to: 'gateway', kind: 'lora', sampleOrigin: undefined, validForMs: 30000, state: 'oneway' })
    const g = topologyLayout(s.nodes, new TopologyProjector().project(s, at).edges)
    expect(g.groups.map(g => g.members)).toEqual([['3', '4'], ['5']])
  })
  it('keeps coordinates stable across report order/RSSI changes', () => {
    const s = scene(), p = new TopologyProjector(), before = topologyLayout(s.nodes, p.project(s, at).edges)
    s.nodes.reverse(); s.links.reverse(); s.links.forEach(e => { e.rssiDbm = -70 })
    expect(topologyLayout(s.nodes, p.project(s, at + 1).edges)).toEqual(before)
  })
  it('retains finite bounded layouts for empty, isolated and30-node long chains', () => {
    expect(topologyLayout([], []).positions).toEqual({})
    const s = scene(); s.nodes = Array.from({ length: 30 }, (_, i) => ({ ...s.nodes[0]!, id: String(i).padStart(2, '0') })); s.links = []
    for (let i = 1; i < s.nodes.length; i++) s.links.push({ ...scene().links[0]!, id: `edge${i}`, from: s.nodes[i - 1]!.id, to: s.nodes[i]!.id })
    const g = topologyLayout(s.nodes, new TopologyProjector().project(s, at).edges)
    expect(Object.keys(g.positions)).toHaveLength(30)
    for (const v of Object.values(g.positions)) { expect(Number.isFinite(v.x + v.y)).toBe(true); expect(v.x).toBeLessThan(g.width); expect(v.y + 100).toBeLessThanOrEqual(g.height) }
  })
  it('does not call an observer-only peer graph a GPS failure', () => {
    const s = scene(); s.nodes = [{ ...s.nodes[0]!, id: 'gateway', role: 'gateway' }]; s.links = []
    const w = mount(NetworkTopology, { props: { snapshot: s, now: at, interrupted: false, selected: '', selectedLink: '', layout: 'clear', linkFilter: 'wifi', namespace: 'TEST-ONLY', demo: true } })
    expect(w.find('.graph-empty').text()).toContain('等待节点报告'); expect(w.find('.graph-empty').text()).not.toContain('GPS'); w.unmount()
  })
  it('updates the actual SVG line count and positions, and has only a3-behavior legend', async () => {
    const s = scene(), w = mount(NetworkTopology, { props: { snapshot: s, now: at, interrupted: false, selected: '', selectedLink: '', layout: 'clear', linkFilter: 'wifi', namespace: 'TEST-ONLY', demo: true } })
    expect(w.findAll('.edge')).toHaveLength(3); const before = w.find('[data-node="5"]').attributes('transform')
    const next = structuredClone(s); cut(next); await w.setProps({ snapshot: next, now: at + 1 })
    expect(w.findAll('.edge')).toHaveLength(2); expect(w.find('[data-node="5"]').attributes('transform')).not.toBe(before)
    expect(w.find('[data-test="link-evidence-legend"]').findAll('span')).toHaveLength(3)
    expect(w.findAll('.edge.lost')).toHaveLength(0); w.unmount()
  })
})
