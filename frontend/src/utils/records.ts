/**
 * References to records of any device in a URL (D-40): a flight by its id, a dog record as `dog:<id>`, so
 * `/history/together?ids=<flight>,<flight>,dog:<record>` replays two drones and a dog together.
 */
export interface RecordRef {
  kind: 'drone' | 'dog'
  id: string
}

export function parseRefs(s: string): RecordRef[] {
  const out: RecordRef[] = []
  for (const part of s.split(',').map((x) => x.trim()).filter(Boolean)) {
    const ref: RecordRef = part.startsWith('dog:') ? { kind: 'dog', id: part.slice(4) } : { kind: 'drone', id: part }
    if (ref.id && !out.some((r) => r.kind === ref.kind && r.id === ref.id)) out.push(ref)
  }
  return out
}

export function refsParam(refs: RecordRef[]): string {
  return refs.map((r) => (r.kind === 'dog' ? `dog:${r.id}` : r.id)).join(',')
}

/** The replay page of these records together (also one dog record on its own). */
export function togetherPath(refs: RecordRef[]): { path: string; query: { ids: string } } {
  return { path: '/history/together', query: { ids: refsParam(refs) } }
}
