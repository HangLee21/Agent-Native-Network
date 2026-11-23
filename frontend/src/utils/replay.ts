/**
 * Flight replay helpers (D-19): turn recorded samples, events and commands into what the replay
 * shows at a given time. Pure functions so they can be tested without a map.
 */
import type { FlightCommand, FlightEvent, Sample } from '@/api/history'
import { t, tc } from '@/i18n'

/**
 * Reference of the DRC `height` field (field test U-05 / U-36). Confirmed ellipsoid height on 2026-11-07 from six
 * recorded field flights (10-30, 11-04, 11-05; about 1250 airborne samples): DRC height equals the normal OSD
 * ellipsoid height (median difference 0.00 m), and DRC height minus the take-off ellipsoid height equals the OSD
 * relative height. So the replay charts a 2 Hz relative height for every recorded flight, with no data migration.
 * UNKNOWN charts only the 0.5 Hz OSD relative height.
 */
export type DrcHeightReference = 'UNKNOWN' | 'ELLIPSOID' | 'RELATIVE'
export const DRC_HEIGHT_REFERENCE: DrcHeightReference = 'ELLIPSOID'

/** Sample with every field carried forward from earlier rows (DRC rows lack most fields). */
export type FilledSample = Sample & { height: number | null }

const FILL_KEYS: (keyof Sample)[] = [
  'lat', 'lon', 'ellipsoidHeight', 'relativeHeight', 'horizontalSpeed', 'verticalSpeed', 'attitudeHead', 'attitudePitch',
  'attitudeRoll', 'gimbalPitch', 'gimbalYaw', 'gimbalRoll', 'zoomFactor', 'battery', 'remainFlightTime', 'returnHomePower',
  'modeCode', 'gpsNumber', 'rtkNumber', 'windSpeed', 'windDirection', 'homeDistance', 'heightLimit',
]

/** Height above take-off shown in the replay for one sample, by the DRC height policy. */
export function sampleHeight(s: Sample, takeoffEllipsoid: number | null, ref: DrcHeightReference = DRC_HEIGHT_REFERENCE): number | null {
  if (s.relativeHeight !== null) return s.relativeHeight
  if (s.drcHeight === null) return null
  if (ref === 'RELATIVE') return s.drcHeight
  if (ref === 'ELLIPSOID' && takeoffEllipsoid !== null) return s.drcHeight - takeoffEllipsoid
  return null
}

export function fillForward(samples: Sample[], takeoffEllipsoid: number | null, ref: DrcHeightReference = DRC_HEIGHT_REFERENCE): FilledSample[] {
  const sorted = [...samples].sort((a, b) => a.ts - b.ts)
  const out: FilledSample[] = []
  let prev: FilledSample | null = null
  for (const s of sorted) {
    const f = { ...s, height: sampleHeight(s, takeoffEllipsoid, ref) } as FilledSample
    if (prev) {
      for (const k of FILL_KEYS) {
        if (f[k] === null || f[k] === undefined) (f as unknown as Record<string, unknown>)[k] = prev[k]
      }
      if (f.height === null) f.height = prev.height
    }
    out.push(f)
    prev = f
  }
  return out
}

/** Index of the last sample at or before t (-1 before the first). */
export function indexAt(samples: { ts: number }[], t: number): number {
  let lo = 0
  let hi = samples.length - 1
  let ans = -1
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    if (samples[mid]!.ts <= t) {
      ans = mid
      lo = mid + 1
    } else {
      hi = mid - 1
    }
  }
  return ans
}

function lerp(a: number | null, b: number | null, k: number): number | null {
  if (a === null) return b
  if (b === null) return a
  return a + (b - a) * k
}

function lerpAngle(a: number | null, b: number | null, k: number): number | null {
  if (a === null || b === null) return a ?? b
  const d = ((b - a + 540) % 360) - 180
  return a + d * k
}

/** State at time t: carried-forward values, with position, height and heading interpolated between samples. */
export function stateAt(filled: FilledSample[], t: number): FilledSample | null {
  const i = indexAt(filled, t)
  if (i < 0) return filled[0] ?? null
  const a = filled[i]!
  const b = filled[i + 1]
  if (!b || b.ts === a.ts || b.ts - a.ts > 10_000) return a
  const k = (t - a.ts) / (b.ts - a.ts)
  return {
    ...a,
    ts: t,
    lat: lerp(a.lat, b.lat, k),
    lon: lerp(a.lon, b.lon, k),
    height: lerp(a.height, b.height, k),
    attitudeHead: lerpAngle(a.attitudeHead, b.attitudeHead, k),
  }
}

// ------------------------------------------------------------------ timeline lanes

export type PhaseKind = 'takeoff' | 'route' | 'flight' | 'rth' | 'landing'
export interface Phase {
  kind: PhaseKind
  start: number
  end: number
}

export const PHASE_LABELS: Record<PhaseKind, string> = {
  takeoff: tc('phase', '起飞'), route: tc('phase', '航线'), flight: tc('phase', '飞行'), rth: tc('phase', '返航'), landing: tc('phase', '降落'),
}

function phaseOfMode(mode: number | null): PhaseKind | null {
  if (mode === null || mode === 0 || mode === 14) return null
  if (mode === 1 || mode === 2 || mode === 4) return 'takeoff'
  if (mode === 9) return 'rth'
  if (mode === 10 || mode === 11 || mode === 12) return 'landing'
  return 'flight'
}

/** Route execution windows from EXECUTION events (from take-off/flying until it completes, fails or stops). */
export function executionWindows(events: FlightEvent[]): [number, number][] {
  const out: [number, number][] = []
  let start: number | null = null
  for (const e of events) {
    if (e.eventType !== 'EXECUTION') continue
    const state = String(e.payload?.state ?? '')
    if (start === null && ['TAKING_OFF', 'FLYING', 'AT_WAYPOINT'].includes(state)) start = e.ts
    if (start !== null && ['FINISHING', 'COMPLETED', 'FAILED', 'ABORTED'].includes(state)) {
      out.push([start, e.ts])
      start = null
    }
  }
  if (start !== null) out.push([start, Number.MAX_SAFE_INTEGER])
  return out
}

/** Flight phases from the flight mode; plain flight inside a route execution window counts as route. */
export function phases(filled: FilledSample[], events: FlightEvent[]): Phase[] {
  const windows = executionWindows(events)
  const inRoute = (t: number) => windows.some(([a, b]) => t >= a && t <= b)
  const out: Phase[] = []
  let cur: Phase | null = null
  for (const s of filled) {
    let kind = phaseOfMode(s.modeCode)
    if (kind === 'flight' && inRoute(s.ts)) kind = 'route'
    if (cur && kind === cur.kind) {
      cur.end = s.ts
      continue
    }
    if (cur) cur.end = s.ts // a phase lasts until the next mode starts
    cur = kind ? { kind, start: s.ts, end: s.ts } : null
    if (cur) out.push(cur)
  }
  return out.filter((p) => p.end > p.start)
}

export interface Mark {
  ts: number
  kind: string
  level: 'INFO' | 'WARNING' | 'CRITICAL'
  label: string
}

const PHOTO_COMMANDS: Record<string, string> = {
  TakePhoto: t('拍照'), StartRecording: t('开始录像'), StopRecording: t('停止录像'),
}

export function commandMarks(commands: FlightCommand[]): Mark[] {
  return commands.map((c) => ({
    ts: c.createdAt,
    kind: c.commandType,
    level: c.status === 'FAILED' || c.status === 'TIMEOUT' || c.status === 'REJECTED' ? ('CRITICAL' as const) : ('INFO' as const),
    label: t('{label}：{message}', { label: c.label, message: c.message ?? c.status }),
  }))
}

export function photoMarks(commands: FlightCommand[]): Mark[] {
  return commands
    .filter((c) => PHOTO_COMMANDS[c.commandType] && c.status === 'ACKED')
    .map((c) => ({ ts: c.completedAt ?? c.createdAt, kind: c.commandType, level: 'INFO' as const, label: PHOTO_COMMANDS[c.commandType]! }))
}

export function alertMarks(events: FlightEvent[]): Mark[] {
  return events
    .filter((e) => e.eventType === 'ALERT_RAISED' || e.eventType === 'OBSTACLE' || (e.eventType === 'DEVICE_MESSAGE' && e.eventLevel !== 'INFO'))
    .map((e) => ({ ts: e.ts, kind: e.eventType, level: e.eventLevel, label: e.title }))
}

/** Periods with no telemetry: sample gaps longer than minGapMs, and LINK_LOST → LINK_RESTORED events. */
export function linkGaps(filled: { ts: number }[], events: FlightEvent[], minGapMs = 5000): [number, number][] {
  const gaps: [number, number][] = []
  for (let i = 1; i < filled.length; i++) {
    if (filled[i]!.ts - filled[i - 1]!.ts > minGapMs) gaps.push([filled[i - 1]!.ts, filled[i]!.ts])
  }
  let lost: number | null = null
  for (const e of events) {
    if (e.eventType === 'LINK_LOST') lost = e.ts
    if (e.eventType === 'LINK_RESTORED' && lost !== null) {
      if (!gaps.some(([a, b]) => a <= lost! && b >= e.ts)) gaps.push([lost, e.ts])
      lost = null
    }
  }
  return gaps.sort((a, b) => a[0] - b[0])
}

export interface PlannedPath {
  ts: number
  kind: string
  points: { lat: number; lon: number }[]
}

export function plannedPaths(events: FlightEvent[]): PlannedPath[] {
  return events
    .filter((e) => e.eventType === 'PLANNED_PATH' && Array.isArray(e.payload?.points))
    .map((e) => ({
      ts: e.ts,
      kind: String(e.payload?.kind ?? ''),
      points: (e.payload!.points as number[][]).map((p) => ({ lat: p[0]!, lon: p[1]! })),
    }))
}

/** Target selection and AI auto-mode events (D-21 ~ D-24), one mark each. */
export function targetMarks(events: FlightEvent[]): Mark[] {
  return events
    .filter((e) => e.eventType.startsWith('TARGET_') || e.eventType.startsWith('AI_'))
    .map((e) => ({ ts: e.ts, kind: e.eventType, level: e.eventLevel, label: e.title }))
}

export interface ReplayTarget {
  id: string
  ts: number
  label: string
  state: string
  pos: { lat: number; lon: number }
  accuracyM: number | null
  stop: { lat: number; lon: number } | null
}

/** Each target's last recorded snapshot at or before t (TARGET_* events carry the whole target), grouped by targetId. */
export function targetsAt(events: FlightEvent[], at: number): ReplayTarget[] {
  const byId = new Map<string, ReplayTarget>()
  for (const e of events) {
    if (e.ts > at) break
    if (!e.eventType.startsWith('TARGET_') && e.eventType !== 'AI_PROPOSAL') continue
    const tg = e.payload?.target as Record<string, unknown> | undefined
    const id = (e.payload?.targetId as string | undefined) ?? (tg?.id as string | undefined)
    if (!id || !tg) continue
    if (tg.lat == null || tg.lon == null) {
      byId.delete(id)
      continue
    }
    const stop = tg.stopPoint as { lat: number; lon: number } | null | undefined
    byId.set(id, {
      id,
      ts: e.ts,
      label: String(tg.label ?? (tg.input === 'MAP' ? t('地图目标') : t('目标'))),
      state: String(tg.state ?? ''),
      pos: { lat: Number(tg.lat), lon: Number(tg.lon) },
      accuracyM: typeof tg.accuracyM === 'number' ? tg.accuracyM : null,
      stop: stop ? { lat: Number(stop.lat), lon: Number(stop.lon) } : null,
    })
  }
  return [...byId.values()].filter((x) => x.state !== 'CANCELLED' && x.state !== 'EXPIRED')
}

/** Times to jump to with [ and ]: commands, alerts, phases, lifecycle and target events. */
export function jumpTimes(marks: Mark[], phaseList: Phase[], events: FlightEvent[]): number[] {
  const lifecycle = events
    .filter((e) => ['SESSION_START', 'SESSION_END', 'EXECUTION', 'CONTROL', 'LINK_LOST'].includes(e.eventType)
      || ['TARGET_SELECTED', 'TARGET_ACTION', 'TARGET_ARRIVED', 'TARGET_END', 'AI_COUNTDOWN'].includes(e.eventType))
    .map((e) => e.ts)
  return [...new Set([...marks.map((m) => m.ts), ...phaseList.map((p) => p.start), ...lifecycle])].sort((a, b) => a - b)
}

export function nextTime(times: number[], t: number): number | null {
  return times.find((x) => x > t + 1) ?? null
}

export function prevTime(times: number[], t: number): number | null {
  for (let i = times.length - 1; i >= 0; i--) if (times[i]! < t - 1) return times[i]!
  return null
}

/** Elapsed mm:ss (or h:mm:ss). */
export function elapsed(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

/** Blue (low) to red (high) for track colouring. */
export function rampColor(v: number | null, min: number, max: number): string {
  if (v === null || max <= min) return 'hsl(200 90% 55%)'
  const k = Math.min(1, Math.max(0, (v - min) / (max - min)))
  return `hsl(${Math.round(200 - 200 * k)} 85% 52%)`
}

/** Video part and position (seconds) for a timeline time, or null when no part covers it. */
export function videoAt(parts: { index: number; startAt: number; durationMs: number }[], t: number, offsetMs: number): { index: number; seconds: number } | null {
  const vt = t - offsetMs
  const p = parts.find((x) => vt >= x.startAt && vt <= x.startAt + x.durationMs)
  return p ? { index: p.index, seconds: (vt - p.startAt) / 1000 } : null
}
