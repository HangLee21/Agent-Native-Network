/**
 * Replay of several records together (D-33, D-40; ui-design.md 2.6.1, 2.7.1): drones' flights and dogs' records on
 * one time axis, in any combination. Pure functions on top of the single-flight helpers in ./replay, so they can be
 * tested without a map. A dog record comes with the flight record's field names (see api/dogRecords.ts).
 */
import { historyApi, type FlightCommand, type FlightEvent, type Sample, type SessionDetail } from '@/api/history'
import { dogRecordsApi, type DogRecordDetail, type DogSample } from '@/api/dogRecords'
import { distance } from './geo'
import { alertMarks, commandMarks, fillForward, jumpTimes, phases, photoMarks, stateAt, type FilledSample, type Mark, type Phase } from './replay'
import type { LatLon } from './coord'

export type TrackKind = 'drone' | 'dog'

export interface DogReplayRoute {
  id: string
  number: number
  start: number
  end: number | null
  points: LatLon[]
}

/** One device's record in a joint replay: a drone's flight or a dog's record. */
export interface Track {
  id: string
  kind: TrackKind
  label: string
  color: string
  detail: SessionDetail
  filled: FilledSample[]
  events: FlightEvent[]
  dogRoutes: DogReplayRoute[]
  commands: FlightCommand[]
  phases: Phase[]
  marks: Mark[]
  photos: Mark[]
  /** Address of the record's archived video part. */
  videoUrl: (index: number) => string
}

/** Track colours when a drone is not (any more) in the fleet: A blue, B orange, as the defaults (ui-design.md 2.7). */
export const TRACK_COLORS = ['#378ADD', '#D85A30', '#1D9E75', '#BA7517']
/** Dog track colours: the first is the dogs' colour on the live map (DogV2Layer). */
export const DOG_TRACK_COLORS = ['#a3e635', '#b794f6', '#4fd1c5', '#f472b6']

/** Dog events shown with the commands and alerts (mode switch, GNSS fix, link back). */
const DOG_STATE_EVENTS = new Set(['MODE', 'GNSS', 'LINK_RESTORED'])

/** Older events may contain compact [lat, lon] pairs instead of named points. */
function dogRoutePoint(value: unknown): LatLon | null {
  if (!value || typeof value !== 'object') return null
  const [lat, lon] = Array.isArray(value)
    ? value
    : [(value as Partial<LatLon>).lat, (value as Partial<LatLon>).lon]
  if (typeof lat !== 'number' || typeof lon !== 'number' || !Number.isFinite(lat) || !Number.isFinite(lon)
    || Math.abs(lat) > 90 || Math.abs(lon) > 180) return null
  return { lat, lon }
}

function dogRoutes(recordId: string, events: FlightEvent[]): DogReplayRoute[] {
  const endings = new Map<string, number>()
  for (const event of events) {
    const taskId = event.payload?.taskId
    if (event.eventType === 'NAV_END' && typeof taskId === 'string' && !endings.has(taskId)) {
      endings.set(taskId, event.ts)
    }
  }
  const routes: DogReplayRoute[] = []
  for (const event of events) {
    const points = event.payload?.points
    if (event.eventType !== 'NAV_START' || !Array.isArray(points) || !points.length) continue
    const coordinates = points.map(dogRoutePoint)
    if (!coordinates.every((point) => point !== null)) continue
    const taskId = event.payload?.taskId
    const end = typeof taskId === 'string' ? endings.get(taskId) : undefined
    routes.push({
      id: `${recordId}:${event.id}`, number: routes.length + 1, start: event.ts,
      end: end != null && end >= event.ts ? end : null, points: coordinates,
    })
  }
  return routes
}

export function buildTrack(id: string, label: string, color: string, detail: SessionDetail, samples: Parameters<typeof fillForward>[0],
                           events: FlightEvent[], commands: FlightCommand[], kind: TrackKind = 'drone',
                           videoUrl: (index: number) => string = (i) => historyApi.videoUrl(id, i)): Track {
  const filled = fillForward(samples, detail.takeoffEllipsoidHeight ?? null)
  const stateMarks: Mark[] = kind === 'dog'
    ? events.filter((e) => DOG_STATE_EVENTS.has(e.eventType)).map((e) => ({ ts: e.ts, kind: e.eventType, level: e.eventLevel, label: e.title }))
    : []
  return {
    id, kind, label, color, detail, filled, events, commands, videoUrl,
    dogRoutes: kind === 'dog' ? dogRoutes(id, events) : [],
    phases: kind === 'dog' ? [] : phases(filled, events),
    marks: [...commandMarks(commands), ...alertMarks(events), ...stateMarks].sort((a, b) => a.ts - b.ts),
    photos: photoMarks(commands),
  }
}

/** A dog record's detail in the flight record's shape (the fields a dog has no use for are empty). */
export function dogDetail(d: DogRecordDetail): SessionDetail {
  return {
    ...d, droneSn: null, gatewaySn: null, takeoffLat: null, takeoffLon: null, maxHomeDistance: null, sampleCount: d.sampleCount,
    droppedItems: 0, delayMinMs: null, delayAvgMs: null, delayMaxMs: null, clockOffsetMs: null, rawAtTakeoff: null, rawAtLanding: null,
    videoQuality: null, videoBytes: d.videoBytes,
  } as unknown as SessionDetail      // outcome stays the dog's (DOG_OUTCOME_LABELS)
}

/** A dog sample as a flight sample: what it does not have is null, its own fields come along. */
export function dogSample(s: DogSample): Sample {
  return {
    deviceTs: null, ellipsoidHeight: null, relativeHeight: null, drcHeight: null, verticalSpeed: null, gimbalPitch: null,
    gimbalYaw: null, gimbalRoll: null, zoomFactor: null, remainFlightTime: null, returnHomePower: null, modeCode: null,
    gpsNumber: s.sats, rtkNumber: null, windSpeed: null, windDirection: null, homeDistance: null, heightLimit: null,
    ...s, sampleSource: 'OSD',
  } as unknown as Sample
}

/** Loads a dog record as a replay track. */
export async function loadDogTrack(id: string, color: string, label: (d: DogRecordDetail) => string): Promise<Track> {
  const [d, s, e, c] = await Promise.all([dogRecordsApi.get(id), dogRecordsApi.samples(id), dogRecordsApi.events(id), dogRecordsApi.commands(id)])
  return buildTrack(id, label(d), color, dogDetail(d), s.map(dogSample), e, c, 'dog', (i) => dogRecordsApi.videoUrl(id, i))
}

/** The dog's own values carried in a replay state (absent for a drone). */
export type DogExtras = Partial<Omit<DogSample, keyof Sample | 'sampleSource'>>

export function dogState(s: FilledSample | null): (FilledSample & DogExtras) | null {
  return s as (FilledSample & DogExtras) | null
}

/** The first two drone tracks: the separation and the proximity alarm are about two drones (S-05). */
export function dronePair(tracks: Track[]): readonly [Track, Track] | null {
  const d = tracks.filter((t) => t.kind === 'drone')
  return d.length >= 2 ? [d[0]!, d[1]!] as const : null
}

/**
 * Shared axis: from shortly before the earliest take-off (or first command) to the latest end. Like the single
 * replay, standby telemetry recorded before that is left off so the flights are not squeezed into a corner.
 */
export function axis(tracks: Track[]): { start: number; end: number } {
  let start = Infinity
  let end = 0
  for (const t of tracks) {
    const first = Math.min(t.detail.startedAt, t.filled[0]?.ts ?? Infinity)
    const lead = Math.min(t.detail.takeoffAt ?? Infinity, t.commands[0]?.createdAt ?? Infinity)
    start = Math.min(start, Number.isFinite(lead) ? Math.max(first, lead - 5000) : first)
    end = Math.max(end, t.detail.endedAt ?? 0, t.filled[t.filled.length - 1]?.ts ?? 0)
  }
  if (!Number.isFinite(start)) start = 0
  return { start, end: Math.max(end, start + 1000) }
}

/** Whether t lies within the drone's recorded samples (the map shows it only then). */
export function recordedAt(track: Track, t: number): boolean {
  const f = track.filled
  return f.length > 0 && t >= f[0]!.ts && t <= f[f.length - 1]!.ts
}

/** The drone's state at t, or null outside its recording. */
export function trackState(track: Track, t: number): FilledSample | null {
  return recordedAt(track, t) ? stateAt(track.filled, t) : null
}

export function position(s: FilledSample | null): LatLon | null {
  return s && s.lat !== null && s.lon !== null ? { lat: s.lat, lon: s.lon } : null
}

/**
 * Height on a common reference: each drone's relative height counts from its own take-off point, so it is put on
 * the ellipsoid (take-off ellipsoid height + relative height); the recorded ellipsoid height otherwise.
 */
export function ellipsoidOf(track: Track, s: FilledSample | null): number | null {
  if (!s) return null
  const base = track.detail.takeoffEllipsoidHeight
  if (base != null && s.height !== null) return base + s.height
  return s.ellipsoidHeight ?? null
}

export interface Separation {
  horizontalM: number
  /** null: a height is unknown */
  verticalM: number | null
}

export function separationAt(a: Track, b: Track, t: number): Separation | null {
  const sa = trackState(a, t)
  const sb = trackState(b, t)
  const pa = position(sa)
  const pb = position(sb)
  if (!pa || !pb) return null
  const ha = ellipsoidOf(a, sa)
  const hb = ellipsoidOf(b, sb)
  return { horizontalM: distance(pa, pb), verticalM: ha === null || hb === null ? null : Math.abs(ha - hb) }
}

/** Horizontal separation over the axis, n points (gaps where either drone is not recorded). */
export function separationSeries(a: Track, b: Track, start: number, end: number, n = 400): { t: number; s: Separation | null }[] {
  const out: { t: number; s: Separation | null }[] = []
  const step = Math.max(1, (end - start) / (n - 1))
  for (let t = start; t <= end + 1e-6; t += step) out.push({ t, s: separationAt(a, b, t) })
  return out
}

const isProximity = (e: FlightEvent) => e.payload?.code === 'PROXIMITY'

/**
 * Periods with a two-drone proximity alarm (ALERT_RAISED → ALERT_CLEARED, code PROXIMITY). The alarm is in both
 * drones' records, so the periods of all tracks are merged.
 */
export function proximitySpans(tracks: Track[]): [number, number][] {
  const spans: [number, number][] = []
  for (const t of tracks) {
    let open: number | null = null
    for (const e of t.events) {
      if (!isProximity(e)) continue
      if (e.eventType === 'ALERT_RAISED' && open === null) open = e.ts
      if (e.eventType === 'ALERT_CLEARED' && open !== null) {
        spans.push([open, e.ts])
        open = null
      }
    }
    if (open !== null) spans.push([open, t.filled[t.filled.length - 1]?.ts ?? open])
  }
  spans.sort((x, y) => x[0] - y[0])
  const merged: [number, number][] = []
  for (const s of spans) {
    const last = merged[merged.length - 1]
    if (last && s[0] <= last[1]) last[1] = Math.max(last[1], s[1])
    else merged.push([s[0], s[1]])
  }
  return merged
}

export const within = (spans: [number, number][], t: number) => spans.some(([a, b]) => t >= a && t <= b)

/** One row of the merged event list. */
export interface JointItem {
  ts: number
  /** Index of the track, or -1 for a two-drone event (proximity alarm). */
  track: number
  kind: 'command' | 'alert'
  level: Mark['level']
  text: string
}

/** Every device's commands and alerts by time; a proximity alarm recorded by both drones is one row, marked as two-drone. */
export function mergedItems(tracks: Track[]): JointItem[] {
  const out: JointItem[] = []
  const proximity: number[] = []
  tracks.forEach((t, i) => {
    for (const c of commandMarks(t.commands)) out.push({ ts: c.ts, track: i, kind: 'command', level: c.level, text: c.label })
    for (const e of t.events) {
      if (isProximity(e) && e.eventType === 'ALERT_RAISED' && !proximity.some((p) => Math.abs(p - e.ts) < 3000)) {
        proximity.push(e.ts)
        out.push({ ts: e.ts, track: -1, kind: 'alert', level: e.eventLevel, text: String(e.payload?.message ?? e.title) })
      }
    }
    for (const m of alertMarks(t.events.filter((e) => !isProximity(e)))) out.push({ ts: m.ts, track: i, kind: 'alert', level: m.level, text: m.label })
    // a dog's mode switch, GNSS fix and link back (D-40)
    for (const m of t.marks.filter((x) => DOG_STATE_EVENTS.has(x.kind))) out.push({ ts: m.ts, track: i, kind: 'alert', level: m.level, text: m.label })
  })
  return out.sort((a, b) => a.ts - b.ts)
}

/** Times for [ and ]: every device's events and phases. */
export function jointJumpTimes(tracks: Track[]): number[] {
  const all = tracks.flatMap((t) => jumpTimes([...t.marks, ...t.photos], t.phases, t.events))
  return [...new Set(all)].sort((a, b) => a - b)
}

/** Alert and photo pins of one track at the position the drone had at that moment. */
export function pinsOf(track: Track): (Mark & { pos: LatLon })[] {
  return [...alertMarks(track.events), ...track.photos].flatMap((m) => {
    const pos = position(stateAt(track.filled, m.ts))
    return pos ? [{ ...m, pos }] : []
  })
}
