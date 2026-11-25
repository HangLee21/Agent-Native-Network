/** Operator graph projection. Raw observations remain untouched; drawing policy is not an RF TTL. */
import { linkEvidenceState } from './model'
import type { NetworkLink, NetworkNode, NetworkSnapshot, Point } from './types'
export type GraphLinkState = 'fresh' | 'impaired' | 'hidden'
export const IMPAIRED_GRACE_MS = 10000
export interface GraphEdge {
  id: string; from: string; to: string; kind: NetworkLink['kind']; state: Exclude<GraphLinkState, 'hidden'>
  primary: NetworkLink; directions: NetworkLink[]; forward: boolean; reverse: boolean
}
export interface TopologyFrame { edges: GraphEdge[]; states: Record<string, GraphLinkState> }

/** Keep the FIRST soft failure, so repeating an unknown/bad report cannot renew a ghost edge. */
export class TopologyProjector {
  private scope = ''
  private lastObservedAt = -Infinity
  private failures = new Map<string, number>()
  project(snapshot: NetworkSnapshot, now: number, namespace = '', interrupted = false): TopologyFrame {
    const scope = JSON.stringify([namespace, snapshot.instanceId, snapshot.sourceId, snapshot.epoch])
    // Seek detection uses the frame clock, not a live extrapolated clock that can jitter at each poll.
    if (scope !== this.scope || snapshot.observedAt < this.lastObservedAt) { this.failures.clear(); this.scope = scope }
    this.lastObservedAt = snapshot.observedAt
    const present = new Set(snapshot.links.map(e => e.id))
    for (const id of this.failures.keys()) if (!present.has(id)) this.failures.delete(id)
    const states: Record<string, GraphLinkState> = Object.create(null)
    const groups = new Map<string, NetworkLink[]>()
    for (const e of snapshot.links) {
      const evidence = linkEvidenceState(e, snapshot, now, interrupted)
      let state: GraphLinkState
      if (e.state === 'lost' || e.sampledAt === null) state = 'hidden'
      else if (evidence === 'current' || evidence === 'recent-sample') { state = 'fresh'; this.failures.delete(e.id) }
      else {
        const reporter = snapshot.nodes.find(n => n.id === (e.kind === 'wifi' ? e.to : e.from))
        const window = reporter?.reportTimeoutMs ?? snapshot.reportTimeoutMs
        const deadlines = [e.sampledAt + (e.validForMs ?? window)]
        if (reporter?.reportedAt !== null && reporter?.reportedAt !== undefined) deadlines.push(reporter.reportedAt + window)
        const first = Math.min(this.failures.get(e.id) ?? now, now, ...deadlines)
        this.failures.set(e.id, first)
        state = now - first < IMPAIRED_GRACE_MS ? 'impaired' : 'hidden'
      }
      states[e.id] = state
      if (state === 'hidden') continue
      const ends = [e.from, e.to].sort()
      const key = JSON.stringify([e.kind, ...ends])
      if (!groups.has(key)) groups.set(key, [])
      groups.get(key)!.push(e)
    }
    const edges: GraphEdge[] = [...groups.entries()].map(([id, directions]): GraphEdge => {
      const fresh = directions.filter(e => states[e.id] === 'fresh')
      const active = fresh.length ? fresh : directions
      active.sort((a, b) => a.id.localeCompare(b.id))
      const primary = active[0]!, [from, to] = [primary.from, primary.to].sort() as [string, string]
      return { id, from, to, kind: primary.kind, state: fresh.length ? 'fresh' : 'impaired', primary, directions,
        forward: fresh.some(e => e.from === from), reverse: fresh.some(e => e.from === to) }
    }).sort((a, b) => a.id.localeCompare(b.id))
    return { edges, states }
  }
}

export interface TopologyGroup { id: string; members: string[]; x: number; y: number; width: number; height: number }
export interface GraphLayout { positions: Record<string, Point>; groups: TopologyGroup[]; width: number; height: number }
/** Fresh Wi-Fi adjacency ONLY. LoRa observation uplinks and failed links cannot hold a mesh together. */
export function topologyLayout(nodes: NetworkNode[], edges: GraphEdge[]): GraphLayout {
  const peers = nodes.filter(n => n.role !== 'gateway').map(n => n.id).sort()
  const adjacency = new Map(peers.map(id => [id, new Set<string>()]))
  for (const e of edges) if (e.kind === 'wifi' && e.state === 'fresh' && adjacency.has(e.from) && adjacency.has(e.to)) {
    adjacency.get(e.from)!.add(e.to); adjacency.get(e.to)!.add(e.from)
  }
  const unseen = new Set(peers), components: string[][] = []
  for (const seed of peers) if (unseen.has(seed)) {
    const queue = [seed]; unseen.delete(seed)
    for (let i = 0; i < queue.length; i++) for (const next of [...adjacency.get(queue[i]!)!].sort()) if (unseen.delete(next)) queue.push(next)
    components.push(queue.sort())
  }
  components.sort((a, b) => b.length - a.length || a[0]!.localeCompare(b[0]!))
  const local = components.map(members => {
    const root = [...members].sort((a, b) => adjacency.get(a)!.size - adjacency.get(b)!.size || a.localeCompare(b))[0]!
    const depths = new Map([[root, 0]]), queue = [root]
    for (let i = 0; i < queue.length; i++) for (const next of [...adjacency.get(queue[i]!)!].sort()) if (!depths.has(next)) { depths.set(next, depths.get(queue[i]!)! + 1); queue.push(next) }
    const levels: string[][] = []
    for (const id of members) { const depth = depths.get(id)!; (levels[depth] ??= []).push(id) }
    const positions: Record<string, Point> = Object.create(null)
    const minDegree = Math.min(...members.map(id => adjacency.get(id)!.size))
    const layerRows = (level: string[]) => level.length <= 2 ? level.length : Math.min(5, Math.ceil(level.length / 2))
    if (members.length <= 12 && minDegree >= 2) {
      const radius = members.length <= 3 ? 145 : 195
      members.forEach((id, i) => { const angle = -Math.PI / 2 + i * Math.PI * 2 / members.length; positions[id] = { x: radius + 90 + Math.cos(angle) * radius, y: radius + 100 + Math.sin(angle) * radius } })
    } else if (levels.length > 6) {
      // Long chains fold, rather than expanding the drawing to thousands of pixels wide.
      queue.forEach((id, i) => { const row = Math.floor(i / 6), col = i % 6; positions[id] = { x: 90 + (row % 2 ? 5 - col : col) * 180, y: 100 + row * 155 } })
    } else {
      let x = 90
      for (const level of levels) {
        const rows = layerRows(level), columns = Math.ceil(level.length / rows)
        level.forEach((id, i) => { positions[id] = { x: x + Math.floor(i / rows) * 155, y: 100 + (i % rows) * 140 } })
        x += Math.max(1, columns) * 155 + 55
      }
      // Center each layer vertically. A triangle becomes an actual 3--4--5 chain when3--5 is gone.
      const tallest = Math.max(1, ...levels.map(layerRows))
      for (const level of levels) for (const id of level) positions[id]!.y += (tallest - layerRows(level)) * 70
    }
    return { members, positions, width: Math.max(...Object.values(positions).map(p => p.x)) + 90, height: Math.max(...Object.values(positions).map(p => p.y)) + 120 }
  })
  const positions: Record<string, Point> = Object.create(null), groups: TopologyGroup[] = []
  const gateways = nodes.filter(n => n.role === 'gateway').sort((a, b) => a.id.localeCompare(b.id))
  const targetWidth = Math.max(980, ...local.map(c => c.width + 40))
  let x = 20, y = gateways.length ? 165 : 20, rowHeight = 0
  for (const component of local) {
    if (x > 20 && x + component.width > targetWidth - 20) { x = 20; y += rowHeight + 25; rowHeight = 0 }
    for (const [id, point] of Object.entries(component.positions)) positions[id] = { x: x + point.x, y: y + point.y }
    groups.push({ id: component.members[0]!, members: component.members, x, y, width: component.width, height: component.height })
    x += component.width + 25; rowHeight = Math.max(rowHeight, component.height)
  }
  const height = Math.max(580, y + rowHeight + 20), usedWidth = Math.max(0, ...groups.map(g => g.x + g.width))
  const offset = Math.max(0, (targetWidth - usedWidth) / 2)
  for (const p of Object.values(positions)) { p.x += offset; p.y += Math.max(0, (height - y - rowHeight) / 2) }
  for (const g of groups) { g.x += offset; g.y += Math.max(0, (height - y - rowHeight) / 2) }
  gateways.forEach((n, i) => { positions[n.id] = { x: 110 + i * 180, y: 60 } })
  return { positions, groups, width: targetWidth, height }
}
