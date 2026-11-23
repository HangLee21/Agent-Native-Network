/**
 * 监视台 data model (docs/demo-redesign/monitor-station-design.md). Pure functions, no Vue, no DOM: builds per-flight
 * typed arrays from a flight record (or live telemetry), audience phases, the event feeds, two-drone separation and the
 * camera footprint. Ported from the 「飞行记录复盘」 prototype and the 11-09 mock.
 *
 * Coordinates: local east/north metres around `Scene.origin` (WGS84), heights above the lowest take-off point.
 */
import type { FlightCommand, FlightEvent, Sample, SessionDetail } from '@/api/history'
import type { Route } from '@/api/routes'
import { t, tb, tc } from '@/i18n'

export const D2R = Math.PI / 180
export const R_EARTH = 6378137

export const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
export const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v))
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const lerpAng = (a: number, b: number, t: number) => { const d = ((b - a + 540) % 360) - 180; return a + d * t }
const median = (a: number[]) => { if (!a.length) return NaN; const s = [...a].sort((x, y) => x - y); return s[s.length >> 1]! }

export const MODE: Record<number, string> = { 0: t('待机'), 1: t('起飞准备'), 2: t('起飞准备完毕'), 3: t('手动飞行'), 4: t('自动起飞'), 5: t('航线飞行'), 6: t('全景拍照'), 7: t('智能跟随'), 8: t('ADS-B 躲避'), 9: t('自动返航'), 10: t('自动降落'), 11: t('强制降落'), 12: t('三桨叶降落'), 13: t('升级中'), 14: t('未连接'), 15: 'APAS', 16: t('虚拟摇杆'), 17: t('指令飞行'), 18: t('空中 RTK 收敛'), 19: t('机场选址中'), 20: t('兴趣点环绕') }
export const GROUND_MODES = new Set([0, 1, 2, 13, 14, 19])
export const RTH_MODES = new Set([9, 10, 11, 12])
export const EXEC_LABEL: Record<string, string> = { PREPARING: t('准备执行'), ACQUIRING_CONTROL: t('等待云端控制权'), TAKING_OFF: t('一键起飞'), FLYING: t('飞往航点'), AT_WAYPOINT: t('到达航点'), PAUSED: t('悬停等待确认'), FINISHING: t('执行结束动作'), COMPLETED: t('航线完成'), STOPPED: t('已停止'), FAILED: t('执行失败') }
const CMD_STATUS: Record<string, string> = { ACKED: t('设备已确认'), SENT: t('已发送'), PENDING: t('待发送'), FAILED: t('失败'), TIMEOUT: t('超时'), REJECTED: t('被拒绝') }
const HIDDEN_EVENTS = new Set(['PLANNED_PATH', 'RC_POSITION'])

/** Audience phases: derived from the flight mode only, nothing about routes. A dog (D-40) is still or walking. */
export type Phase = 'nodata' | 'offline' | 'ground' | 'ready' | 'takeoff' | 'fly' | 'avoid' | 'rth' | 'land' | 'still' | 'walk'
export const PHASE_LABEL: Record<Phase, string> = { nodata: t('无数据'), offline: t('离线'), ground: t('地面待机'), ready: t('准备起飞'), takeoff: tc('phase', '起飞'), fly: t('飞行中'), avoid: t('自动避障'), rth: tc('phase', '返航'), land: tc('phase', '降落'), still: t('静止'), walk: t('走动中') }
/** A dog counts as walking at or above this speed (m/s). */
export const DOG_WALK_MPS = 0.2
export function phaseOf(m: number | null | undefined): Phase {
  if (!isNum(m)) return 'nodata'
  if (m === 14) return 'offline'
  if (m === 0 || m === 13 || m === 19) return 'ground'
  if (m === 1 || m === 2) return 'ready'
  if (m === 4) return 'takeoff'
  if (m === 15 || m === 8) return 'avoid'
  if (m === 9) return 'rth'
  if (m === 10 || m === 11 || m === 12) return 'land'
  return 'fly'
}

export interface Scene {
  origin: { lat: number; lon: number; cos: number }
  /** Lowest take-off ellipsoid height: the ground plane of the scene. */
  datum: number
  /** 'device': aircraft clock (positions of two drones line up best); 'server': platform receive time. */
  clock: 'device' | 'server'
}

export interface LogRow { t: number; f: WatchFlight; kind: 'ev' | 'cmd' | 'ph'; lvl: '' | 'warn' | 'crit'; title: string; detail: string }
export interface ExecMark { t: number; state: string; idx: number | null; total: number | null }
export interface Plan { t: number; kind: string; pts: [number, number, number][] }

/** Input for one flight: a flight record (live or closed) plus the device it belongs to; or a dog's record / live trail. */
export interface FlightInput {
  /** 'dog': a robot dog of the new dog system (D-40): on the ground, its own readings; default a drone. */
  kind?: 'drone' | 'dog'
  id: string
  /** RC serial (gateway) — the device the flight belongs to. */
  gatewaySn: string
  label: string
  color: string
  devName: string
  droneSn: string
  detail: Pick<SessionDetail, 'takeoffLat' | 'takeoffLon' | 'takeoffEllipsoidHeight' | 'homeLat' | 'homeLon' | 'takeoffAt' | 'clockOffsetMs' | 'routeName' | 'routeSnapshot' | 'outcome' | 'rawAtTakeoff'> & { videoParts?: SessionDetail['videoParts']; videoOffsetMs?: number; videoStatus?: SessionDetail['videoStatus']; status?: SessionDetail['status'] } | null
  samples: Sample[]
  events: FlightEvent[]
  commands: FlightCommand[]
  /** Live flights keep their last state instead of turning into "record ended" past the last sample. */
  live: boolean
  /** Session id when there is a flight record (live review clips, replay video). */
  sessionId: string | null
}

export interface WatchFlight {
  input: FlightInput
  kind: 'drone' | 'dog'
  /** The samples in time order (index i of every array): a dog's own fields (GNSS fix, state, mode, control) are read here. */
  src: Sample[]
  id: string
  label: string
  color: string
  devName: string
  routeName: string
  sn: string
  live: boolean
  off: number
  ell0: number
  takeoffLat: number; takeoffLon: number
  route: { lat: number; lon: number; relativeHeight?: number | null; waitForConfirm?: boolean }[]
  routeDefH: number | null
  batLow: number; batCrit: number
  shift: number
  n: number
  t: Float64Array; x: Float64Array; y: Float64Array; z: Float64Array; rel: Float64Array; hs: Float64Array; vs: Float64Array
  head: Float64Array; gp: Float64Array; gy: Float64Array; bat: Float64Array; mode: Float64Array; gps: Float64Array; wind: Float64Array; cum: Float64Array
  tx: number; ty: number
  t0: number; t1: number; liftT: number; landT: number
  modeSegs: { m: number; t0: number; t1: number }[]
  phaseSegs: { ph: Phase; t0: number; t1: number }[]
  exec: ExecMark[]; wps: { t: number; n: number }[]; holds: { t0: number; t1: number; n: number | null }[]
  alerts: { t0: number; t1: number; msg: string }[]
  rc: { t: number; x: number; y: number }[]
  plans: Plan[]
  cmds: { t: number; label: string; msg: string; lat: number | null; bad: boolean }[]
  log: LogRow[]
  plog: LogRow[]
  // drawing caches (filled by the map)
  _sx?: Float32Array; _sy?: Float32Array; _ok?: Uint8Array; _gx?: Float32Array; _gy?: Float32Array; _gok?: Uint8Array

}

export function makeScene(inputs: FlightInput[], clock: Scene['clock'] = 'device'): Scene {
  let la = 0, lo = 0, k = 0, datum = Infinity
  // the drones place the scene; dogs only when there is no drone (a dog has no take-off height for the datum)
  const placing = inputs.some((f) => f.kind !== 'dog') ? inputs.filter((f) => f.kind !== 'dog') : inputs
  for (const f of placing) {
    const first = f.samples.find((p) => isNum(p.lat) && isNum(p.lon))
    const lat = f.detail?.takeoffLat ?? first?.lat, lon = f.detail?.takeoffLon ?? first?.lon
    if (isNum(lat) && isNum(lon)) { la += lat; lo += lon; k++ }
    if (f.kind !== 'dog') datum = Math.min(datum, ell0Of(f))
  }
  if (!k) return { origin: { lat: 0, lon: 0, cos: 1 }, datum: 0, clock }
  la /= k; lo /= k
  return { origin: { lat: la, lon: lo, cos: Math.cos(la * D2R) }, datum: isFinite(datum) ? datum : 0, clock }
}

function ell0Of(f: FlightInput): number {
  if (isNum(f.detail?.takeoffEllipsoidHeight)) return f.detail!.takeoffEllipsoidHeight!
  const first = f.samples.find((p) => isNum(p.ellipsoidHeight))
  return first ? first.ellipsoidHeight! - (first.relativeHeight ?? 0) : 0
}

export function enu(sc: Scene, lat: number, lon: number): [number, number] {
  const o = sc.origin
  return [(lon - o.lon) * D2R * R_EARTH * o.cos, (lat - o.lat) * D2R * R_EARTH]
}

function sampleTime(sc: Scene, off: number, p: Sample): number {
  if (sc.clock === 'device') return isNum(p.deviceTs) ? p.deviceTs : p.ts - off
  return isNum(p.ts) ? p.ts : (p.deviceTs ?? 0) + off
}

function ffill(a: Float64Array): void {
  let last = NaN
  for (let i = 0; i < a.length; i++) { if (isNaN(a[i]!)) a[i] = last; else last = a[i]! }
  let firstV = NaN
  for (let i = 0; i < a.length; i++) if (!isNaN(a[i]!)) { firstV = a[i]!; break }
  for (let i = 0; i < a.length && isNaN(a[i]!); i++) a[i] = firstV
}

export function bsearch(arr: ArrayLike<number>, T: number): number {
  const n = arr.length
  if (!n || T < arr[0]!) return -1
  if (T >= arr[n - 1]!) return n - 1
  let lo = 0, hi = n - 1
  while (hi - lo > 1) { const m = (lo + hi) >> 1; if (arr[m]! <= T) lo = m; else hi = m }
  return lo
}

const validSample = (p: Sample) => p && isNum(p.lat) && isNum(p.lon) && !(p.lat === 0 && p.lon === 0) && (isNum(p.deviceTs) || isNum(p.ts))

/** Builds (or rebuilds) one flight in the given scene. `shift` moves every timestamp (take-off alignment). */
export function buildFlight(sc: Scene, input: FlightInput, shift = 0): WatchFlight | null {
  const raw = input.samples.filter(validSample)
  if (!raw.length) return null
  const d = input.detail
  const offs = raw.filter((p) => isNum(p.ts) && isNum(p.deviceTs)).map((p) => p.ts - p.deviceTs!)
  const off = isNum(d?.clockOffsetMs) ? d!.clockOffsetMs! : (offs.length ? median(offs.slice(-200)) : 0)
  const ell0 = ell0Of(input)
  const ta = (d?.rawAtTakeoff ?? {}) as Record<string, unknown>
  const first = raw[0]!
  const list = raw.map((p) => [sampleTime(sc, off, p) + shift, p] as const).filter(([t]) => isNum(t)).sort((a, b) => a[0] - b[0])
  const n = list.length
  const F = () => new Float64Array(n).fill(NaN)
  const route = ((d?.routeSnapshot as Route | null)?.waypoints ?? []).filter((w) => w && isNum(w.lat) && isNum(w.lon))
  const dog = input.kind === 'dog'
  const f: WatchFlight = {
    input, kind: dog ? 'dog' : 'drone', src: list.map(([, p]) => p),
    id: input.id, label: input.label, color: input.color, devName: input.devName, routeName: d?.routeName || t('未命名航线'),
    sn: input.droneSn, live: input.live, off, ell0,
    takeoffLat: isNum(d?.takeoffLat) ? d!.takeoffLat! : first.lat!, takeoffLon: isNum(d?.takeoffLon) ? d!.takeoffLon! : first.lon!,
    route: route as WatchFlight['route'],
    routeDefH: isNum((d?.routeSnapshot as Route | null)?.defaultHeight) ? (d!.routeSnapshot as Route).defaultHeight : null,
    batLow: isNum(ta.low_battery_warning_threshold) ? ta.low_battery_warning_threshold : 30,
    batCrit: isNum(ta.serious_low_battery_warning_threshold) ? ta.serious_low_battery_warning_threshold : 15,
    shift, n,
    t: new Float64Array(n), x: F(), y: F(), z: F(), rel: F(), hs: F(), vs: F(), head: F(), gp: F(), gy: F(), bat: F(), mode: F(), gps: F(), wind: F(), cum: new Float64Array(n),
    tx: 0, ty: 0, t0: 0, t1: 0, liftT: 0, landT: 0,
    modeSegs: [], phaseSegs: [], exec: [], wps: [], holds: [], alerts: [], rc: [], plans: [], cmds: [], log: [], plog: [],
  }
  ;[f.tx, f.ty] = enu(sc, f.takeoffLat, f.takeoffLon)
  for (let i = 0; i < n; i++) {
    const [t, p] = list[i]!
    f.t[i] = t
    const [x, y] = enu(sc, p.lat!, p.lon!); f.x[i] = x; f.y[i] = y
    const ell = isNum(p.ellipsoidHeight) ? p.ellipsoidHeight : isNum(p.relativeHeight) ? ell0 + p.relativeHeight : NaN
    f.rel[i] = ell - ell0; f.z[i] = ell - sc.datum
    if (isNum(p.horizontalSpeed)) f.hs[i] = p.horizontalSpeed
    if (isNum(p.verticalSpeed)) f.vs[i] = p.verticalSpeed
    if (isNum(p.attitudeHead)) f.head[i] = p.attitudeHead
    if (isNum(p.gimbalPitch)) f.gp[i] = p.gimbalPitch
    if (isNum(p.gimbalYaw)) f.gy[i] = p.gimbalYaw
    if (isNum(p.battery)) f.bat[i] = p.battery
    if (isNum(p.modeCode)) f.mode[i] = p.modeCode
    if (isNum(p.gpsNumber)) f.gps[i] = p.gpsNumber
    if (isNum(p.windSpeed)) f.wind[i] = p.windSpeed
  }
  if (dog) { f.z.fill(0); f.rel.fill(0) }      // on the ground of the scene
  for (const a of [f.z, f.rel, f.hs, f.vs, f.head, f.gp, f.gy, f.bat, f.mode, f.gps, f.wind]) ffill(a)
  for (let i = 0; i < n; i++) { if (isNaN(f.z[i]!)) { f.z[i] = ell0 - sc.datum; f.rel[i] = 0 } if (isNaN(f.hs[i]!)) f.hs[i] = 0 }
  if (dog) return dogFlight(f, input, sc, shift)
  for (let i = 1; i < n; i++) f.cum[i] = f.cum[i - 1]! + ((f.rel[i]! > 0.5 || f.rel[i - 1]! > 0.5) ? Math.hypot(f.x[i]! - f.x[i - 1]!, f.y[i]! - f.y[i - 1]!) : 0)
  f.t0 = f.t[0]!; f.t1 = f.t[n - 1]!
  let li = -1; for (let i = 0; i < n; i++) if (f.rel[i]! > 0.8) { li = i; break }
  f.liftT = li >= 0 ? f.t[Math.max(0, li - 1)]! : (isNum(d?.takeoffAt) ? d!.takeoffAt! + shift : f.t1 + 1)
  let ld = -1; for (let i = n - 1; i >= 0; i--) if (f.rel[i]! > 0.8) { ld = i; break }
  f.landT = ld >= 0 ? (input.live && ld === n - 1 ? Infinity : f.t[Math.min(n - 1, ld + 1)]!) : f.liftT

  let cur = f.mode[0]!, s0 = f.t0
  for (let i = 1; i < n; i++) if (f.mode[i] !== cur && !(isNaN(f.mode[i]!) && isNaN(cur))) { f.modeSegs.push({ m: cur, t0: s0, t1: f.t[i]! }); cur = f.mode[i]!; s0 = f.t[i]! }
  f.modeSegs.push({ m: cur, t0: s0, t1: f.t1 })
  for (const sg of f.modeSegs) {
    const ph = phaseOf(sg.m), last = f.phaseSegs[f.phaseSegs.length - 1]
    if (last && last.ph === ph) last.t1 = sg.t1; else f.phaseSegs.push({ ph, t0: sg.t0, t1: sg.t1 })
  }

  const ev = input.events.filter((e) => e && isNum(e.ts)).map((e) => ({ ...e, t: e.ts - (sc.clock === 'device' ? off : 0) + shift })).sort((a, b) => a.t - b.t)
  let holdOpen: { t0: number; n: number | null } | null = null
  const openAlerts: Record<string, { t0: number; t1: number; msg: string }> = {}
  for (const e of ev) {
    const p = (e.payload ?? {}) as Record<string, unknown>
    if (e.eventType === 'EXECUTION') {
      const idx = isNum(p.currentIndex) ? p.currentIndex : null
      f.exec.push({ t: e.t, state: String(p.state ?? ''), idx, total: isNum(p.total) ? p.total : null })
      if (p.state === 'AT_WAYPOINT' && idx !== null) f.wps.push({ t: e.t, n: idx + 1 })
      if (p.state === 'PAUSED') holdOpen = { t0: e.t, n: idx }
      else if (holdOpen) { f.holds.push({ ...holdOpen, t1: e.t }); holdOpen = null }
    } else if (e.eventType === 'ALERT_RAISED') {
      const a = { t0: e.t, t1: NaN, msg: String(p.message ?? e.title) }
      f.alerts.push(a); openAlerts[String(p.code)] = a
    } else if (e.eventType === 'ALERT_CLEARED') {
      const a = openAlerts[String(p.code)]; if (a) { a.t1 = e.t; delete openAlerts[String(p.code)] }
    } else if (e.eventType === 'RC_POSITION' && isNum(p.lat) && isNum(p.lon)) {
      const [x, y] = enu(sc, p.lat, p.lon); f.rc.push({ t: e.t, x, y })
    } else if (e.eventType === 'PLANNED_PATH' && Array.isArray(p.points) && p.points.length >= 2) {
      const pts = (p.points as unknown[]).filter((q): q is number[] => Array.isArray(q) && isNum(q[0]) && isNum(q[1]) && isNum(q[2]))
      if (pts.length >= 2 && pts.every((q) => q[2]! - ell0 > -20 && q[2]! - ell0 < 1500)) {
        f.plans.push({ t: e.t, kind: String(p.kind ?? ''), pts: pts.map((q) => { const [x, y] = enu(sc, q[0]!, q[1]!); return [x, y, q[2]! - sc.datum] as [number, number, number] }) })
      }
    }
  }
  if (holdOpen) f.holds.push({ ...holdOpen, t1: f.t1 })
  for (const a of f.alerts) if (isNaN(a.t1)) a.t1 = a.t0 + 1500
  const ct = (c: FlightCommand) => (isNum(c.sentAt) ? c.sentAt : c.createdAt) - (sc.clock === 'device' ? off : 0) + shift
  f.cmds = input.commands.filter((c) => c && (isNum(c.sentAt) || isNum(c.createdAt))).map((c) => ({
    t: ct(c), label: c.label || c.commandType || t('指令'),
    msg: c.message || CMD_STATUS[c.status] || c.status || '',
    lat: isNum(c.completedAt) && isNum(c.sentAt) ? c.completedAt - c.sentAt : null,
    bad: !!c.status && !['ACKED', 'SENT', 'PENDING'].includes(c.status),
  })).sort((a, b) => a.t - b.t)

  // engineering feed: every event + command (the prototype)
  for (const e of ev) {
    if (HIDDEN_EVENTS.has(e.eventType)) continue
    if (e.eventType === 'DEVICE_MESSAGE' && (/未解析/.test(e.title || '') || e.title === tb('设备消息（未解析）'))) continue // i18n-ignore (matching backend text; tb() covers English mode)
    const lvl = e.eventLevel === 'WARNING' ? 'warn' : e.eventLevel === 'CRITICAL' ? 'crit' : ''
    f.log.push({ t: e.t, f, kind: 'ev', lvl, title: e.title || e.eventType, detail: eventDetail(e) })
  }
  for (const c of f.cmds) f.log.push({ t: c.t, f, kind: 'cmd', lvl: c.bad ? 'crit' : '', title: c.label, detail: c.msg + (c.lat != null ? ' · ' + t('回执 {ms} ms', { ms: c.lat }) : '') })
  f.log.sort((a, b) => a.t - b.t)

  // audience feed: only the aircraft's own state changes — no routes, no platform commands
  let prev: Phase | null = null
  for (const sg of f.phaseSegs) {
    const ph = sg.ph
    let title: string | null = null
    if (ph === 'takeoff') title = tc('phase', '起飞')
    else if (ph === 'avoid') title = t('遇到障碍，自动避障')
    else if (ph === 'fly' && prev === 'avoid') title = t('避开障碍，继续飞行')
    else if (ph === 'rth') title = t('开始返航')
    else if (ph === 'land') title = t('开始降落')
    else if (ph === 'ground' && (prev === 'land' || prev === 'fly')) title = t('已降落')
    if (title) f.plog.push({ t: sg.t0, f, kind: 'ph', lvl: '', title, detail: '' })
    prev = ph
  }
  const vid = ev.find((e) => e.eventType === 'VIDEO')
  if (vid) f.plog.push({ t: vid.t, f, kind: 'ph', lvl: '', title: t('视频已开启'), detail: '' })
  f.plog.sort((a, b) => a.t - b.t)
  return f
}

function eventDetail(e: FlightEvent): string {
  const p = (e.payload ?? {}) as Record<string, unknown>
  switch (e.eventType) {
    case 'EXECUTION': return ['PAUSED', 'ACQUIRING_CONTROL', 'FAILED', 'STOPPED'].includes(String(p.state)) ? String(p.message ?? '') : ''
    case 'CONTROL': case 'ALERT_RAISED': return String(p.message ?? '')
    case 'FLYTO': return isNum(p.remainingDistance) && p.remainingDistance > 0 ? t('剩余 {d} m', { d: p.remainingDistance.toFixed(1) }) : (p.result ? t('结果码 {code}', { code: String(p.result) }) : '')
    case 'OBSTACLE': return (['horizontal', 'up', 'down'] as const).filter((k) => isNum(p[k])).map((k) => ({ horizontal: t('水平'), up: t('上方'), down: t('下方') }[k] + ' ' + (p[k] as number).toFixed(1) + ' m')).join(' · ')
    case 'DEVICE_MESSAGE': return String(p.text ?? '')
    default: return typeof p.message === 'string' ? p.message : ''
  }
}

export interface FlightState {
  before: boolean; after: boolean; inside: boolean; i: number
  x: number; y: number; z: number; rel: number; hs: number; vs: number; head: number; gp: number; gy: number
  bat: number; mode: number; gps: number; wind: number; cum: number; home: number
  /** ms since the last sample for a live flight (link freshness); 0 otherwise. */
  stale: number
}

export function stateAt(f: WatchFlight, T: number, o: Partial<FlightState> = {}): FlightState {
  const n = f.n
  let i = bsearch(f.t, T), j: number, a = 0
  o.before = T < f.t0
  o.after = !f.live && T > f.t1
  o.inside = !o.before && !o.after
  o.stale = f.live && T > f.t1 ? T - f.t1 : 0
  if (i < 0) { i = 0; j = 0 } else if (i >= n - 1) { i = n - 1; j = i } else { j = i + 1; const dt = f.t[j]! - f.t[i]!; a = dt > 0 && dt < 12000 ? (T - f.t[i]!) / dt : 0 }
  o.i = i
  o.x = lerp(f.x[i]!, f.x[j]!, a); o.y = lerp(f.y[i]!, f.y[j]!, a); o.z = lerp(f.z[i]!, f.z[j]!, a)
  o.rel = lerp(f.rel[i]!, f.rel[j]!, a); o.hs = lerp(f.hs[i]!, f.hs[j]!, a)
  o.head = lerpAng(f.head[i] || 0, f.head[j] || 0, a); o.gp = lerp(f.gp[i] || 0, f.gp[j] || 0, a); o.gy = lerpAng(f.gy[i] || 0, f.gy[j] || 0, a)
  o.vs = f.vs[i]!; o.bat = f.bat[i]!; o.mode = f.mode[i]!; o.gps = f.gps[i]!; o.wind = f.wind[i]!
  o.cum = lerp(f.cum[i]!, f.cum[j]!, a)
  o.home = Math.hypot(o.x - f.tx, o.y - f.ty)
  return o as FlightState
}

export function lastBefore<T extends { t: number }>(arr: T[], T: number): T | null {
  let r: T | null = null
  for (const e of arr) { if (e.t <= T) r = e; else break }
  return r
}

/**
 * The rest of a dog's track (D-40): distance walked (only while it reports moving, so GNSS jitter does not add up),
 * still / walking as its phases, its commands, and its own events in both feeds.
 */
function dogFlight(f: WatchFlight, input: FlightInput, sc: Scene, shift: number): WatchFlight {
  const n = f.n
  for (let i = 1; i < n; i++) f.cum[i] = f.cum[i - 1]! + (f.hs[i]! >= DOG_WALK_MPS ? Math.hypot(f.x[i]! - f.x[i - 1]!, f.y[i]! - f.y[i - 1]!) : 0)
  f.t0 = f.t[0]!; f.t1 = f.t[n - 1]!
  f.liftT = f.t0
  f.landT = input.live ? Infinity : f.t1
  f.route = []
  f.routeName = ''
  f.batLow = 30; f.batCrit = 15
  let cur: Phase = f.hs[0]! >= DOG_WALK_MPS ? 'walk' : 'still', s0 = f.t0
  for (let i = 1; i < n; i++) {
    const ph: Phase = f.hs[i]! >= DOG_WALK_MPS ? 'walk' : 'still'
    // a gap without data or a short pause does not split a walk
    if (ph !== cur && !(ph === 'still' && i + 2 < n && f.hs[i + 2]! >= DOG_WALK_MPS)) { f.phaseSegs.push({ ph: cur, t0: s0, t1: f.t[i]! }); cur = ph; s0 = f.t[i]! }
  }
  f.phaseSegs.push({ ph: cur, t0: s0, t1: f.t1 })
  const ev = input.events.filter((e) => e && isNum(e.ts)).map((e) => ({ ...e, t: e.ts + shift })).sort((a, b) => a.t - b.t)
  const openAlerts: Record<string, { t0: number; t1: number; msg: string }> = {}
  for (const e of ev) {
    const p = (e.payload ?? {}) as Record<string, unknown>
    if (e.eventType === 'ALERT_RAISED') { const a = { t0: e.t, t1: e.t + 1500, msg: String(p.message ?? e.title) }; f.alerts.push(a); openAlerts[String(p.code)] = a }
    const lvl = e.eventLevel === 'WARNING' ? 'warn' : e.eventLevel === 'CRITICAL' ? 'crit' : ''
    f.log.push({ t: e.t, f, kind: 'ev', lvl, title: e.title || e.eventType, detail: '' })
    if (['SESSION_START', 'SESSION_END', 'ALERT_RAISED', 'MODE', 'LINK_RESTORED'].includes(e.eventType)) {
      const title = e.eventType === 'SESSION_START' ? t('开始活动') : e.eventType === 'SESSION_END' ? t('结束活动') : e.title || e.eventType
      f.plog.push({ t: e.t, f, kind: 'ph', lvl: lvl as LogRow['lvl'], title, detail: '' })
    }
  }
  void sc
  f.cmds = input.commands.filter((c) => c && (isNum(c.sentAt) || isNum(c.createdAt))).map((c) => ({
    t: (isNum(c.sentAt) ? c.sentAt : c.createdAt) + shift, label: c.label || c.commandType || t('指令'),
    msg: c.message || CMD_STATUS[c.status] || c.status || '',
    lat: isNum(c.completedAt) && isNum(c.sentAt) ? c.completedAt - c.sentAt : null,
    bad: !!c.status && !['ACKED', 'SENT', 'PENDING'].includes(c.status),
  })).sort((a, b) => a.t - b.t)
  for (const c of f.cmds) f.log.push({ t: c.t, f, kind: 'cmd', lvl: c.bad ? 'crit' : '', title: c.label, detail: c.msg + (c.lat != null ? ' · ' + t('回执 {ms} ms', { ms: c.lat }) : '') })
  f.log.sort((a, b) => a.t - b.t)
  f.plog.sort((a, b) => a.t - b.t)
  return f
}

/** A dog's own reading at sample i (absent for a drone). */
export function dogField(f: WatchFlight, i: number, key: 'fix' | 'sats' | 'basicStateName' | 'mode' | 'controlHeld' | 'controlLabel'): unknown {
  return (f.src[i] as unknown as Record<string, unknown> | undefined)?.[key] ?? null
}

// ------------------------------------------------------------------ two-drone separation

export interface Pair { a: WatchFlight; b: WatchFlight; T: Float64Array; D: Float64Array; DH: Float64Array; DV: Float64Array; pmin: Int32Array; step: number; label: string }

/** Separation on a 0.5 s grid; pmin[k] = closest moment with both airborne up to grid k (what has happened so far). */
export function buildPairs(all: WatchFlight[]): Pair[] {
  const out: Pair[] = []
  const fl = all.filter((f) => f.kind !== 'dog')     // separation is about drones (S-05)
  for (let i = 0; i < fl.length; i++) for (let j = i + 1; j < fl.length; j++) {
    const a = fl[i]!, b = fl[j]!, t0 = Math.max(a.t0, b.t0), t1 = Math.min(a.t1, b.t1)
    if (t1 - t0 < 2000) continue
    const step = 500, N = Math.floor((t1 - t0) / step) + 1
    const T = new Float64Array(N), D = new Float64Array(N), DH = new Float64Array(N), DV = new Float64Array(N), pmin = new Int32Array(N)
    const sa: Partial<FlightState> = {}, sb: Partial<FlightState> = {}
    let best = -1
    for (let k = 0; k < N; k++) {
      const tt = t0 + k * step
      stateAt(a, tt, sa); stateAt(b, tt, sb)
      const dh = Math.hypot(sb.x! - sa.x!, sb.y! - sa.y!), dv = sb.z! - sa.z!, d = Math.hypot(dh, dv)
      T[k] = tt; D[k] = d; DH[k] = dh; DV[k] = dv
      if (sa.rel! > 3 && sb.rel! > 3 && (best < 0 || d < D[best]!)) best = k
      pmin[k] = best
    }
    out.push({ a, b, T, D, DH, DV, pmin, step, label: `${a.label}–${b.label}` })
  }
  return out
}
export function pairMinAt(p: Pair, cut: number): { d: number; t: number; dh: number; dv: number } | null {
  const N = p.pmin.length
  const k = cut === Infinity ? N - 1 : Math.floor((cut - p.T[0]!) / p.step)
  if (k < 0) return null
  const idx = p.pmin[Math.min(k, N - 1)]!
  return idx >= 0 ? { d: p.D[idx]!, t: p.T[idx]!, dh: p.DH[idx]!, dv: p.DV[idx]! } : null
}
export function sepAt(p: Pair, T: number): { d: number; dh: number; dv: number } | null {
  if (T < p.T[0]! || T > p.T[p.T.length - 1]!) return null
  const k = clamp(Math.round((T - p.T[0]!) / p.step), 0, p.T.length - 1)
  return { d: p.D[k]!, dh: p.DH[k]!, dv: p.DV[k]! }
}

// ------------------------------------------------------------------ camera footprint

export type FootMode = 'gimbal' | 'nadir'
/**
 * Ground quadrilateral the camera sees. Wide lens estimated at about 70°×45° (16:9 frame). 'gimbal': follows the gimbal
 * pitch, so a forward-looking camera sees ground ahead of the aircraft; 'nadir': treated as looking straight down
 * (heading still follows the gimbal). Forward reach is capped at 4× the height (60–260 m): near the horizon the
 * camera sees to the skyline and one frame would mark everything as seen.
 */
export function footCorners(st: Pick<FlightState, 'x' | 'y' | 'z' | 'rel' | 'gp' | 'gy' | 'head'>, mode: FootMode): [number, number][] | null {
  if (st.rel < 2 || st.z < 1) return null
  const yaw = (isNum(st.gy) ? st.gy : st.head) * D2R, th = Math.tan(35 * D2R), tv = Math.tan(22.5 * D2R)
  const box = [[-1, 1], [1, 1], [1, -1], [-1, -1]] as const
  if (mode === 'nadir') {
    const fx = Math.sin(yaw), fy = Math.cos(yaw), rx = Math.cos(yaw), ry = -Math.sin(yaw), hw = st.z * th, hh = st.z * tv
    return box.map(([a, b]) => [st.x + rx * hw * a + fx * hh * b, st.y + ry * hw * a + fy * hh * b] as [number, number])
  }
  const p = st.gp * D2R, range = clamp(st.z * 4, 60, 260)
  const fx = Math.sin(yaw) * Math.cos(p), fy = Math.cos(yaw) * Math.cos(p), fz = Math.sin(p)
  const rx = Math.cos(yaw), ry = -Math.sin(yaw), rz = 0
  const ux = ry * fz - rz * fy, uy = rz * fx - rx * fz, uz = rx * fy - ry * fx
  return box.map(([a, b]) => {
    const dx = fx + rx * th * a + ux * tv * b, dy = fy + ry * th * a + uy * tv * b, dz = fz + rz * th * a + uz * tv * b
    const hd = Math.hypot(dx, dy) || 1e-6
    const t = Math.min(dz < -0.02 ? st.z / -dz : Infinity, range / hd)
    return [st.x + dx * t, st.y + dy * t] as [number, number]
  })
}

/**
 * Footprints sampled every second between lift-off and landing. Cached per flight id (not per flight object: live
 * flights are rebuilt twice a second) and extended only by the seconds added since; reset when the mode, the scene
 * or the alignment changes. At most a few flights are kept.
 */
const seenCache = new Map<string, { key: string; list: { t: number; cs: [number, number][] }[]; upto: number }>()
export function seenList(f: WatchFlight, mode: FootMode, datum: number): { t: number; cs: [number, number][] }[] {
  const key = `${mode}|${f.shift}|${datum}|${f.liftT}|${f.tx.toFixed(2)},${f.ty.toFixed(2)}`
  let c = seenCache.get(f.id)
  if (!c || c.key !== key) {
    c = { key, list: [], upto: f.liftT - 1000 }
    seenCache.delete(f.id)
    seenCache.set(f.id, c)
    while (seenCache.size > 12) seenCache.delete(seenCache.keys().next().value!)
  }
  const st: Partial<FlightState> = {}
  const end = Math.min(f.landT, f.t1)
  for (let t = c.upto + 1000; t <= end; t += 1000) {
    stateAt(f, t, st)
    const cs = footCorners(st as FlightState, mode)
    if (cs) c.list.push({ t, cs })
    c.upto = t
  }
  return c.list
}

// ------------------------------------------------------------------ cut-off rules

/**
 * What "has happened" for the map: live always up to the watched moment; a replay with the route hidden too (it must
 * look like live); a replay with the route shown draws the rest faintly (Infinity).
 */
export function mapCut(mode: 'live' | 'replay', hideRoute: boolean, t: number): number {
  return mode === 'live' || hideRoute ? t : Infinity
}
/** How far the timeline and the feed go: live (also while reviewing) up to now; replay as the map. */
export function timelineCut(mode: 'live' | 'replay', hideRoute: boolean, t: number, now: number): number {
  return mode === 'live' ? now : mapCut(mode, hideRoute, t)
}

// ------------------------------------------------------------------ WGS84 → GCJ-02 (same algorithm as utils/coord.ts)
export { wgs84ToGcj02 } from '@/utils/coord'
