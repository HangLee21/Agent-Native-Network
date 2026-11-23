/**
 * 监视台 engine: page state, live / replay data, the watched time and the shared setting. Per-frame values live in the
 * plain object `S` (canvas code reads it every frame); Vue renders from `ui`, bumped about 8× a second.
 */
import { reactive } from 'vue'
import { t } from '@/i18n'
import { historyApi, type FlightCommand, type FlightEvent, type Sample, type SessionDetail, type SessionSummary } from '@/api/history'
import { dogRecordsApi, dogName, type DogRecordSummary } from '@/api/dogRecords'
import { dog2Api, type Dog2 } from '@/api/dogv2'
import { DOG_TRACK_COLORS, dogSample } from '@/utils/jointReplay'
import { watchApi, type WatchSettings } from '@/api/watch'
import type { DroneTelemetry } from '@/api/types'
import type { DeviceView } from '@/api/drones'
import { telemetrySocket } from '@/services/ws'
import {
  buildFlight, buildPairs, clamp, isNum, makeScene, mapCut, timelineCut,
  type FlightInput, type FootMode, type Pair, type Scene, type WatchFlight,
} from './model'
import { setDisplayOffset } from './clock'

export type Mode = 'live' | 'replay'
export type CamMode = 'all' | 'free' | string
export interface Layers { route: boolean; plan: boolean; track: boolean; curtain: boolean; seen: boolean; foot: boolean; los: boolean; sep: boolean; rc: boolean; labels: boolean; roads: boolean }

export interface WatchState {
  mode: Mode
  /** 「假装实时」: live mode on screen, driven by recorded flights instead of the drones. */
  fake: boolean
  hideRoute: boolean
  flights: WatchFlight[]
  scene: Scene
  pairs: Pair[]
  t: number
  now: number
  reviewing: boolean
  revPlaying: boolean
  revSpeed: number
  playing: boolean
  speed: number
  full: [number, number]
  domain: [number, number]
  view: [number, number]
  refLift: number
  lastLand: number
  align: 'abs' | 'takeoff'
  alignTouched: boolean
  sel: string | null
  cam: CamMode
  drag: 'pan' | 'rotate'
  /** 0 = off; 1–3 = slow / medium / fast (degrees per second in AUTO_ROTATE_SPEEDS). */
  autoRotate: number
  footMode: FootMode
  showCharts: boolean
  layers: Layers
  /** Bumped whenever flights are rebuilt (map / timeline caches). */
  version: number
}

export const AUTO_ROTATE_SPEEDS = [0, 2, 5, 10]

const S_INIT = (): WatchState => ({
  mode: 'live', fake: false, hideRoute: true, flights: [], scene: { origin: { lat: 0, lon: 0, cos: 1 }, datum: 0, clock: 'device' }, pairs: [],
  t: Date.now(), now: Date.now(), reviewing: false, revPlaying: true, revSpeed: 1, playing: false, speed: 4,
  full: [0, 1], domain: [0, 1], view: [0, 1], refLift: 0, lastLand: 0, align: 'abs', alignTouched: false,
  sel: null, cam: 'all', drag: 'pan', autoRotate: 0, footMode: 'gimbal', showCharts: true,
  layers: { route: true, plan: true, track: true, curtain: true, seen: true, foot: true, los: true, sep: true, rc: false, labels: true, roads: false },
  version: 0,
})

/** A drone's data in live mode: its open flight record (if any) plus telemetry pushed since. */
interface LiveEntry {
  device: DeviceView
  sessionId: string | null
  /** The record that just closed (landed): its flight stays on screen whole until the next take-off. */
  closedId: string | null
  detail: SessionDetail | null
  samples: Sample[]
  events: FlightEvent[]
  commands: FlightCommand[]
  loading: boolean
}

/** A record in the picker: a flight, or a dog record shown as one (id "dog:<record id>", D-40). */
export interface RecordOption { s: SessionSummary; label: string; color: string; devName: string; kind?: 'drone' | 'dog' }

/** A dog in live mode (D-40): its open record (if any) plus the positions polled from the new dog system since. */
interface LiveDog {
  id: string
  recordId: string | null
  samples: Sample[]
  events: FlightEvent[]
  commands: FlightCommand[]
  view: Dog2 | null
}

/** "dog:<id>" refers to a dog record in the picker and in loadReplay. */
export const DOG_REF = 'dog:'
const dogDevName = (model: string | null | undefined) => (model === 's10' ? 'S10' : model === 'lite3' ? 'Lite3' : t('机器狗'))

export function createWatchEngine(fleet: { drones: DeviceView[]; byGateway: (sn: string | null | undefined) => DeviceView | undefined }, currentSession: (sn: string) => string | null) {
  const S = S_INIT()
  const ui = reactive({
    tick: 0, mode: 'live' as Mode, fake: false, hideRoute: true, reviewing: false, playing: false, loading: false, error: null as string | null,
    settingsLoaded: false, records: [] as RecordOption[], selectedIds: [] as string[], flightsKey: '',
    /** Device keys in video order (from the shared setting). */
    videoOrder: [] as string[],
    /** Bumped on every rebuild (lists that show flight data recompute on it). */
    version: 0,
    /** What fills the large area: 'map' or a device key whose video was swapped in (this screen only). */
    mainKey: 'map' as string,
    /** The new dog system's dogs as last polled (live video of a dog's tile). */
    dogs: {} as Record<string, Dog2>,
  })

  // ---------------------------------------------------------------- rebuild
  const live = new Map<string, LiveEntry>()
  let replayInputs: FlightInput[] = []
  let sceneKey = ''
  let liveLag: number | null = null
  const lagWindow: number[] = []

  function deviceOf(gatewaySn: string | null | undefined, droneSn: string | null | undefined): { label: string; color: string; name: string } {
    const d = fleet.byGateway(gatewaySn) ?? fleet.byGateway(droneSn)
    return { label: d?.label ?? (droneSn ? `…${droneSn.slice(-5)}` : '?'), color: d?.color ?? '#4a90e8', name: d?.model ?? 'Matrice 4E' }
  }

  // ---------------------------------------------------------------- dogs (D-40)
  const liveDogs = new Map<string, LiveDog>()
  const dogColors = new Map<string, string>()
  function dogColor(id: string): string {
    if (!dogColors.has(id)) dogColors.set(id, DOG_TRACK_COLORS[dogColors.size % DOG_TRACK_COLORS.length]!)
    return dogColors.get(id)!
  }
  function dogLabel(id: string): { label: string; name: string } {
    const v = ui.dogs[id]
    return { label: v ? dogName({ dogModel: v.model, dogLabel: v.label, dogId: v.id }) : id, name: dogDevName(v?.model) }
  }
  const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
  /** A polled dog as one sample (the platform's receive time minus the position's age). */
  function dogLiveSample(d: Dog2): Sample | null {
    const p = d.position
    if (!d.online || !p || num(p.lat) === null || num(p.lon) === null) return null
    const tel = (d.telemetry ?? {}) as Record<string, unknown>
    const st = (d.status ?? {}) as Record<string, unknown>
    const vel = Array.isArray(tel.vel_body) ? tel.vel_body as number[] : null
    const fresh = d.telemetryAgeMs != null && d.telemetryAgeMs < 2000
    const speed = fresh && vel && num(vel[0]) !== null && num(vel[1]) !== null ? Math.hypot(vel[0]!, vel[1]!) : num(p.speed_mps)
    const old = (st.old_console ?? {}) as Record<string, unknown>
    const ob = num(old.battery_pct)
    const battery = fresh && num(tel.battery_pct) !== null ? num(tel.battery_pct) : ob === null ? null : ob <= 1 ? ob * 100 : ob
    const ctl = (st.control ?? null) as Record<string, unknown> | null
    return dogSample({
      ts: Date.now() - (d.positionAgeMs ?? 0), sampleSource: 'DOG', lat: p.lat!, lon: p.lon!, horizontalSpeed: speed,
      attitudeHead: num(p.heading_deg), attitudePitch: null, attitudeRoll: null, battery: battery === null ? null : Math.round(battery),
      altitude: num(p.alt_m), fix: p.fix ?? null, sats: num(p.sats), headingSource: p.heading_source ?? null,
      basicState: fresh ? num(tel.basic_state) : null, basicStateName: fresh ? (tel.basic_state_name as string | undefined) ?? null : (old.robot_state as string | undefined) ?? null,
      motionState: fresh ? num(tel.motion_state) : null, gaitState: fresh ? num(tel.gait_state) : null, mode: d.mode ?? null,
      controlHeld: !!ctl, controlLabel: (ctl?.label as string | undefined) ?? null, yaw: null,
    })
  }
  let dogsOn = true
  async function pollDogs(): Promise<void> {
    if (!dogsOn) return
    try {
      const r = await dog2Api.list()
      if (r.mode === 'off') { dogsOn = false; return }
      for (const d of r.dogs) {
        ui.dogs[d.id] = d
        let e = liveDogs.get(d.id)
        const s = dogLiveSample(d)
        if (!e) {
          if (!s) continue
          e = { id: d.id, recordId: null, samples: [], events: [], commands: [], view: d }
          liveDogs.set(d.id, e)
        }
        e.view = d
        const last = e.samples[e.samples.length - 1]
        if (s && (!last || s.ts > last.ts + 200)) {
          e.samples.push(s)
          if (e.samples.length > 20000) e.samples.splice(0, e.samples.length - 20000)
          if (S.mode === 'live' && !S.fake) rebuildPending = true
        }
      }
    } catch { /* next round */ }
  }
  /** Dog records being written: the dog's track since the record started, its commands and events. */
  async function loadOpenDogRecords(): Promise<void> {
    if (!dogsOn) return
    try {
      const open = (await dogRecordsApi.list({ includeSimulated: true })).filter((r) => r.status === 'OPEN')
      for (const r of open) {
        const [samples, events, commands] = await Promise.all([dogRecordsApi.samples(r.id), dogRecordsApi.events(r.id), dogRecordsApi.commands(r.id)])
        let e = liveDogs.get(r.dogId)
        if (!e) { e = { id: r.dogId, recordId: null, samples: [], events: [], commands: [], view: null }; liveDogs.set(r.dogId, e) }
        const firstPolled = e.samples[0]?.ts ?? Infinity
        if (e.recordId !== r.id) e.samples = [...samples.map(dogSample).filter((x) => x.ts < firstPolled), ...e.samples]
        e.recordId = r.id; e.events = events; e.commands = commands
      }
      rebuildPending = true
    } catch { /* the polled positions still show */ }
  }
  function dogInputs(): FlightInput[] {
    const out: FlightInput[] = []
    for (const e of liveDogs.values()) {
      if (!e.samples.some((x) => isNum(x.lat))) continue
      const { label, name } = dogLabel(e.id)
      out.push({ kind: 'dog', id: `${DOG_REF}${e.recordId ?? 'live:' + e.id}`, gatewaySn: e.id, label, color: dogColor(e.id), devName: name, droneSn: e.id,
        detail: null, samples: e.samples, events: e.events, commands: e.commands, live: true, sessionId: e.recordId })
    }
    return out
  }

  function liveInputs(): FlightInput[] {
    const out: FlightInput[] = []
    for (const e of live.values()) {
      if (!e.samples.length) continue
      const dev = deviceOf(e.device.gatewaySn, e.device.droneSn)
      out.push({
        id: e.sessionId ?? e.closedId ?? `live:${e.device.gatewaySn}`, gatewaySn: e.device.gatewaySn, label: dev.label, color: dev.color, devName: dev.name,
        droneSn: e.device.droneSn ?? '', detail: e.detail, samples: e.samples, events: e.events, commands: e.commands, live: true, sessionId: e.sessionId ?? e.closedId,
      })
    }
    return [...out.sort((a, b) => a.label.localeCompare(b.label)), ...dogInputs()]
  }

  function rebuild(): void {
    const inputs = S.mode === 'live' && !S.fake ? liveInputs() : replayInputs
    // keep the scene origin while the same drones are shown, so the map does not jump on every new sample
    const key = `${S.mode}|${inputs.map((i) => i.gatewaySn + ':' + (i.sessionId ?? '')).join(',')}|${S.scene.clock}`
    if (key !== sceneKey) { S.scene = makeScene(inputs, S.scene.clock); sceneKey = key }
    let fl = inputs.map((i) => buildFlight(S.scene, i)).filter((f): f is WatchFlight => !!f)
    if (S.mode === 'live') S.align = 'abs'
    else if (!S.alignTouched) S.align = fl.every((f) => fl.every((g) => f.t0 < g.t1 && g.t0 < f.t1)) ? 'abs' : 'takeoff'
    if (S.align === 'takeoff' && fl.length > 1) {
      const ref = fl[0]!.liftT
      fl = fl.map((f, k) => (k === 0 || !isFinite(f.liftT) ? f : buildFlight(S.scene, inputs[k]!, ref - f.liftT) ?? f))
    }
    S.flights = fl
    S.pairs = S.align === 'abs' ? buildPairs(fl) : []
    if (fl.length) {
      S.full = [Math.min(...fl.map((f) => f.t0)), Math.max(...fl.map((f) => f.t1))]
      const lifts = fl.map((f) => f.liftT).filter((t) => t <= f_max(fl))
      S.refLift = lifts.length ? Math.min(...lifts) : S.full[0]
      S.lastLand = Math.max(...fl.map((f) => (isFinite(f.landT) ? f.landT : f.t1)))
    } else {
      S.full = [S.now - 60000, S.now]; S.refLift = S.full[0]; S.lastLand = S.full[1]
    }
    if (!fl.find((f) => f.id === S.sel)) S.sel = fl[0]?.id ?? null
    setDomain()
    if (S.mode === 'replay') {
      S.t = clamp(S.t, S.domain[0], S.domain[1])
      if (S.view[0] < S.domain[0] - 1 || S.view[1] > S.domain[1] + 1 || S.view[1] - S.view[0] < 1000) S.view = [...S.domain]
    }
    S.version++
    ui.version = S.version
    ui.flightsKey = fl.map((f) => f.id).join(',')
    bump()
  }
  const f_max = (fl: WatchFlight[]) => Math.max(...fl.map((f) => f.t1))

  function setDomain(): void {
    if (S.mode === 'live') {
      const start = S.flights.length ? S.full[0] : S.now - 60000
      const now = Math.max(start + 1000, S.now)
      S.domain = [start, now]
      S.view = [start, now + Math.max(15000, (now - start) * 0.04)]
    } else S.domain = [...S.full]
  }

  // ---------------------------------------------------------------- live source
  const unsubs: (() => void)[] = []
  let pollTimer: number | undefined
  let rebuildPending = false
  /** Live data is merged into the flights at most this often (every telemetry message used to rebuild everything). */
  const LIVE_REBUILD_MS = 500
  /**
   * How far the watched "now" stays behind the newest telemetry. Real flights send a sample about every 0.65 s (one in ten
   * gaps 0.8–0.9 s) and a sample waits up to LIVE_REBUILD_MS before it is merged; with less delay the aircraft reached
   * its last known point before the next one arrived, stopped, then jumped (0.9 s before 11-09).
   */
  const LIVE_DELAY_MS = 1800
  let lastRebuild = 0

  function toSample(t: DroneTelemetry): Sample | null {
    if (!isNum(t.lat) || !isNum(t.lon)) return null
    return {
      ts: Date.now(), deviceTs: isNum(t.timestamp) ? t.timestamp : null, sampleSource: t.highFrequency ? 'DRC' : 'OSD',
      lat: t.lat, lon: t.lon, ellipsoidHeight: t.highFrequency ? null : t.ellipsoidHeight, relativeHeight: t.highFrequency ? null : t.relativeHeight,
      drcHeight: null, horizontalSpeed: t.horizontalSpeed, verticalSpeed: t.highFrequency ? null : t.verticalSpeed, attitudeHead: t.attitudeHead,
      attitudePitch: null, attitudeRoll: null, gimbalPitch: t.gimbalPitch, gimbalYaw: t.gimbalYaw, gimbalRoll: null, zoomFactor: null,
      battery: t.highFrequency ? null : t.batteryPercent, remainFlightTime: null, returnHomePower: null, modeCode: t.highFrequency ? null : t.modeCode,
      gpsNumber: t.highFrequency ? null : t.gpsNumber, rtkNumber: null, windSpeed: t.highFrequency ? null : t.windSpeed, windDirection: null,
      homeDistance: null, heightLimit: null,
    }
  }

  function onTelemetry(gatewaySn: string, t: DroneTelemetry): void {
    const e = live.get(gatewaySn)
    if (!e) return
    const s = toSample(t)
    if (!s) return
    const last = e.samples[e.samples.length - 1]
    if (last && isNum(last.deviceTs) && isNum(s.deviceTs) && s.deviceTs <= last.deviceTs) return
    e.samples.push(s)
    // with a flight record the whole flight is kept; a drone without one (on the ground) only needs its recent position
    const cap = e.sessionId || e.closedId ? 40000 : 300
    if (e.samples.length > cap) e.samples.splice(0, e.samples.length - cap)
    if (isNum(s.deviceTs)) {
      lagWindow.push(s.ts - s.deviceTs)
      if (lagWindow.length > 40) lagWindow.shift()
      liveLag = Math.min(...lagWindow)
    }
    if (S.mode === 'live' && !S.fake) rebuildPending = true
  }

  async function loadSession(e: LiveEntry, id: string | null): Promise<void> {
    if (!id) {
      // landed: keep the finished flight (track, take-off point, events) until a new record starts
      if (e.sessionId) e.closedId = e.sessionId
      e.sessionId = null
      rebuildPending = true
      return
    }
    e.sessionId = id
    e.closedId = null
    e.loading = true
    try {
      const [detail, samples, events, commands] = await Promise.all([historyApi.get(id), historyApi.samples(id), historyApi.events(id), historyApi.commands(id)])
      if (e.sessionId !== id) return
      // keep telemetry that arrived after the record's last sample
      const lastTs = samples.length ? (samples[samples.length - 1]!.deviceTs ?? samples[samples.length - 1]!.ts) : -Infinity
      const tail = e.samples.filter((s) => (s.deviceTs ?? s.ts) > lastTs && (s.deviceTs ?? s.ts) >= (detail.startedAt - (detail.clockOffsetMs ?? 0)))
      e.detail = detail; e.samples = [...samples, ...tail]; e.events = events; e.commands = commands
    } catch {
      /* keep what we have; the next poll or reconnect tries again */
    } finally {
      e.loading = false
      rebuildPending = true
    }
  }

  async function pollOpen(): Promise<void> {
    for (const e of live.values()) {
      if (!e.sessionId || e.loading) continue
      try {
        const [events, commands] = await Promise.all([historyApi.events(e.sessionId), historyApi.commands(e.sessionId)])
        e.events = events; e.commands = commands; rebuildPending = true
      } catch { /* next round */ }
    }
    void loadOpenDogRecords()
  }

  /** Called by the view whenever the fleet or a drone's open record changes. */
  function syncLive(devices: DeviceView[]): void {
    const keep = new Set(devices.map((d) => d.gatewaySn))
    for (const sn of [...live.keys()]) if (!keep.has(sn)) live.delete(sn)
    for (const d of devices) {
      let e = live.get(d.gatewaySn)
      if (!e) {
        e = { device: d, sessionId: null, closedId: null, detail: null, samples: [], events: [], commands: [], loading: false }
        live.set(d.gatewaySn, e)
      }
      e.device = d
      const id = currentSession(d.gatewaySn)
      if (id !== e.sessionId) {
        // a new take-off starts a new record: the live screen follows the new flight
        if (id && e.sessionId && id !== e.sessionId) e.samples = []
        void loadSession(e, id)
      }
    }
    rebuildPending = true
  }

  /** Seeds a drone that has no record yet (on the ground) with its current telemetry. */
  function seedTelemetry(gatewaySn: string, t: DroneTelemetry | null): void {
    if (t) onTelemetry(gatewaySn, t)
  }

  function startLive(): void {
    unsubs.push(telemetrySocket.on('telemetry', (m) => {
      const sn = (m as { gatewaySn?: string }).gatewaySn
      if (sn) onTelemetry(sn, m.data as DroneTelemetry)
    }))
    unsubs.push(telemetrySocket.on('monitor-settings', (m) => applySettings(m.data as Partial<WatchSettings>)))
    unsubs.push(telemetrySocket.onStatus((c) => {
      if (!c) return
      void loadSettings()
      for (const e of live.values()) if (e.sessionId) void loadSession(e, e.sessionId)
    }))
    pollTimer = window.setInterval(() => void pollOpen(), 5000)
    dogTimer = window.setInterval(() => void pollDogs(), 1000)
    void pollDogs().then(() => loadOpenDogRecords())
  }
  let dogTimer: number | undefined

  function stop(): void {
    unsubs.splice(0).forEach((u) => u())
    window.clearInterval(pollTimer)
    window.clearInterval(dogTimer)
  }

  // ---------------------------------------------------------------- settings
  function applySettings(s: Partial<WatchSettings> | null): void {
    if (!s) return
    if (Array.isArray(s.videoOrder)) ui.videoOrder = s.videoOrder.filter((k) => typeof k === 'string')
    if (typeof s.hideRoute === 'boolean' && (S.hideRoute !== s.hideRoute || !ui.settingsLoaded)) {
      S.hideRoute = s.hideRoute; ui.hideRoute = s.hideRoute
      S.version++
    }
    ui.settingsLoaded = true
    bump()
  }
  async function loadSettings(): Promise<void> {
    try { applySettings(await watchApi.settings()) } catch { ui.settingsLoaded = true /* default: hidden */ }
  }

  // ---------------------------------------------------------------- replay source
  async function loadRecords(): Promise<void> {
    try {
      const [list, dogs] = await Promise.all([historyApi.list({ includeSimulated: true }), dogRecordsApi.list({ includeSimulated: true }).catch(() => [] as DogRecordSummary[])])
      const flights = list.slice(0, 80)
      // the 监视台 is map-first: a dog record without a track (imported from its video) is replayed on the 记录 page
      const dogRecs = dogs.filter((r) => (r.trackPreview?.length ?? 0) > 0).slice(0, 80)
      const end = (s: { landedAt: number | null; endedAt: number | null }) => s.landedAt ?? s.endedAt ?? Date.now()
      // a flight's row also takes the dog records that overlap it; a dog record's row takes every record it overlaps
      const drones: RecordOption[] = flights.map((s) => {
        const d = deviceOf(s.gatewaySn, s.droneSn)
        const from = s.takeoffAt ?? s.startedAt
        const withDogs = dogRecs.filter((r) => r.startedAt < end(s) && from < end(r)).map((r) => ({ id: DOG_REF + r.id, gatewaySn: r.dogId, droneSn: null }))
        return { s: { ...s, together: [...(s.together ?? []), ...withDogs] }, label: d.label, color: d.color, devName: d.name, kind: 'drone' }
      })
      const dogOpts: RecordOption[] = dogRecs.map((r) => ({
        s: { ...r, id: DOG_REF + r.id, outcome: null, gatewaySn: r.dogId, droneSn: null,
          together: r.together.map((x) => ({ id: x.kind === 'dog' ? DOG_REF + x.id : x.id, gatewaySn: x.device, droneSn: null })) } as unknown as SessionSummary,
        label: dogName(r), color: dogColor(r.dogId), devName: dogDevName(r.dogModel), kind: 'dog',
      }))
      ui.records = [...drones, ...dogOpts].sort((a, b) => (b.s.takeoffAt ?? b.s.startedAt) - (a.s.takeoffAt ?? a.s.startedAt))
    } catch { /* the picker shows nothing */ }
  }

  /** A dog record as a replay input (D-40). */
  async function dogReplayInput(ref: string): Promise<FlightInput> {
    const id = ref.slice(DOG_REF.length)
    const [d, samples, events, commands] = await Promise.all([dogRecordsApi.get(id), dogRecordsApi.samples(id), dogRecordsApi.events(id), dogRecordsApi.commands(id)])
    const first = samples.find((x) => isNum(x.lat) && isNum(x.lon))
    return {
      kind: 'dog', id: ref, gatewaySn: d.dogId, label: dogName(d), color: dogColor(d.dogId), devName: dogDevName(d.dogModel), droneSn: d.dogId,
      detail: { takeoffLat: first?.lat ?? null, takeoffLon: first?.lon ?? null, takeoffEllipsoidHeight: null, homeLat: null, homeLon: null,
        takeoffAt: d.startedAt, clockOffsetMs: 0, routeName: null, routeSnapshot: null, outcome: null, rawAtTakeoff: null,
        videoParts: d.videoParts, videoOffsetMs: d.videoOffsetMs, videoStatus: d.videoStatus, status: d.status },
      samples: samples.map(dogSample), events, commands, live: false, sessionId: id,
    }
  }

  async function loadReplay(ids: string[]): Promise<void> {
    if (!ids.length) { replayInputs = []; ui.selectedIds = []; rebuild(); return }
    ui.loading = true; ui.error = null
    try {
      const got = await Promise.all(ids.map(async (id) => {
        if (id.startsWith(DOG_REF)) return dogReplayInput(id)
        const [detail, samples, events, commands] = await Promise.all([historyApi.get(id), historyApi.samples(id), historyApi.events(id), historyApi.commands(id)])
        const dev = deviceOf(detail.gatewaySn, detail.droneSn)
        return { id, gatewaySn: detail.gatewaySn ?? detail.droneSn ?? id, label: dev.label, color: dev.color, devName: dev.name, droneSn: detail.droneSn ?? '',
          detail, samples, events, commands, live: false, sessionId: id } satisfies FlightInput
      }))
      // drones first, then dogs
      replayInputs = got.sort((a, b) => (a.kind === 'dog' ? 1 : 0) - (b.kind === 'dog' ? 1 : 0) || a.label.localeCompare(b.label))
      ui.selectedIds = replayInputs.map((i) => i.id)
      S.alignTouched = false
      rebuild()
      S.t = clamp(S.refLift - 2000, S.domain[0], S.domain[1])
      S.view = [...S.domain]
    } catch (e) {
      ui.error = e instanceof Error ? e.message : t('飞行记录加载失败')
    } finally {
      ui.loading = false
      bump()
    }
  }

  /** Default replay: the latest flight and the flights that overlap it. */
  async function loadLatest(): Promise<void> {
    if (!ui.records.length) await loadRecords()
    const first = ui.records[0]?.s
    if (!first) { await loadReplay([]); return }
    await loadReplay([first.id, ...(first.together ?? []).map((t) => t.id)])
  }

  // ---------------------------------------------------------------- 假装实时
  /** Recorded flights shown as live: the clock starts 8 s before the first take-off and runs at real speed; every time on
   * the page is shifted to today's clock; review (drag back) works as in live. Real drones are ignored meanwhile. */
  let fakeStart = 0
  let wallStart = 0
  async function startFakeLive(ids: string[]): Promise<void> {
    await loadReplay(ids)
    if (!S.flights.length) return
    S.fake = true; ui.fake = true
    S.mode = 'live'; ui.mode = 'live'
    S.playing = false; ui.playing = false
    S.reviewing = false; ui.reviewing = false
    S.cam = 'all'
    fakeStart = S.refLift - 8000
    wallStart = Date.now()
    setDisplayOffset(wallStart - fakeStart)
    S.now = fakeStart; S.t = fakeStart
    rebuild()
    bump()
  }

  // ---------------------------------------------------------------- time
  function setMode(m: Mode): void {
    if (S.fake) { S.fake = false; ui.fake = false; setDisplayOffset(0) }
    S.mode = m; ui.mode = m
    S.playing = false; ui.playing = false
    S.reviewing = false; ui.reviewing = false
    S.cam = S.cam === 'free' ? 'all' : S.cam
    if (m === 'live') { S.t = S.now; rebuild() }
    else if (replayInputs.length) rebuild()
    else void loadLatest()
    bump()
  }

  function seek(t: number): void {
    if (S.mode === 'live') {
      S.t = clamp(t, S.domain[0], S.now)
      S.reviewing = S.t < S.now - 800
      if (!S.reviewing) S.t = S.now
      ui.reviewing = S.reviewing
    } else {
      S.t = clamp(t, S.domain[0], S.domain[1])
      keepInView(true)
    }
    bump()
  }
  function goLive(): void { S.reviewing = false; ui.reviewing = false; S.t = S.now; bump() }
  function togglePlay(): void {
    if (S.mode === 'live') { if (S.reviewing) S.revPlaying = !S.revPlaying; bump(); return }
    if (!S.playing && S.t >= S.domain[1] - 50) S.t = S.domain[0]
    S.playing = !S.playing; ui.playing = S.playing
    bump()
  }
  function keepInView(jump: boolean): void {
    if (S.mode === 'live') return
    const span = S.view[1] - S.view[0]
    if (S.t > S.view[1] - span * 0.04 || S.t < S.view[0]) {
      if (span < S.domain[1] - S.domain[0] - 1) setView(S.t - span * (jump ? 0.5 : 0.25), S.t + span * (jump ? 0.5 : 0.75))
    }
  }
  function setView(a: number, b: number): void {
    const span = b - a, full = S.domain[1] - S.domain[0]
    if (span >= full) { a = S.domain[0]; b = S.domain[1] } else {
      if (a < S.domain[0]) { b += S.domain[0] - a; a = S.domain[0] }
      if (b > S.domain[1]) { a -= b - S.domain[1]; b = S.domain[1] }
    }
    S.view = [a, b]
  }

  let lastBump = 0
  function bump(): void { ui.tick++; lastBump = performance.now() }

  /** One animation frame. Returns true when time moved (map / timeline must redraw). */
  function step(now: number, dt: number): boolean {
    let moved = false
    if (rebuildPending && S.mode === 'live' && !S.fake && now - lastRebuild >= LIVE_REBUILD_MS) {
      rebuildPending = false
      lastRebuild = now
      rebuild()
      moved = true
    }
    if (S.mode === 'live') {
      // the watched "now" runs on the aircraft clock, kept a little behind the newest data so motion stays smooth
      if (S.fake) S.now = Math.min(fakeStart + (Date.now() - wallStart), S.full[1] + 15000)
      else {
        const lag = liveLag ?? (S.flights.length ? Math.max(0, Date.now() - Math.max(...S.flights.map((f) => f.t1))) : 0)
        S.now = Date.now() - lag - LIVE_DELAY_MS
      }
      if (S.reviewing) {
        if (S.revPlaying) S.t += dt * S.revSpeed
        if (S.t >= S.now - 50) { S.reviewing = false; ui.reviewing = false }
      }
      if (!S.reviewing) S.t = S.now
      setDomain()
      moved = true
    } else if (S.playing) {
      S.t += dt * S.speed
      if (S.t >= S.domain[1]) { S.t = S.domain[1]; S.playing = false; ui.playing = false }
      keepInView(false)
      moved = true
    }
    if (now - lastBump > 120) bump()
    return moved
  }

  const mapCutoff = () => mapCut(S.mode, S.hideRoute, S.t)
  const tlCutoff = () => timelineCut(S.mode, S.hideRoute, S.t, S.now)

  return {
    S, ui, rebuild, syncLive, seedTelemetry, startLive, stop, loadSettings, loadRecords, loadReplay, loadLatest,
    setMode, startFakeLive, seek, goLive, togglePlay, setView, keepInView, step, bump, mapCutoff, tlCutoff,
    setAlign(v: 'abs' | 'takeoff') { S.align = v; S.alignTouched = true; rebuild(); S.view = [...S.domain]; seek(S.refLift - 2000) },
    setClock(v: Scene['clock']) { S.scene = { ...S.scene, clock: v }; sceneKey = ''; rebuild() },
    select(id: string) { S.sel = id; bump() },
  }
}

export type WatchEngine = ReturnType<typeof createWatchEngine>
