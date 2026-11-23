/** Demo service API and types (backend com.uavplatform.demo, docs/demo-design.md). */
import { api } from '@/api/http'
import { t, tb, tc } from '@/i18n'

export type Stage = 'READY' | 'S1_EXPLORE' | 'S1_RENDEZVOUS' | 'S2_RESCAN' | 'S3_TARGET' | 'S4_GUIDE' | 'DONE' | 'ABORTED'
export type ExecState =
  | 'NONE' | 'PREPARING' | 'ACQUIRING_CONTROL' | 'TAKING_OFF' | 'FLYING' | 'AT_WAYPOINT' | 'FINISHING'
  | 'COMPLETED' | 'FAILED' | 'ABORTED' | 'PAUSED'
export type FlightPhase = 'GROUND' | 'TAKING_OFF' | 'FLYING' | 'HOVERING' | 'LANDING' | 'UNKNOWN'
export type EventKind = 'STAGE' | 'COMM' | 'TARGET' | 'COMMAND' | 'INFO' | 'WARN'
export type Label = 'A' | 'B'

export interface LatLon {
  lat: number
  lon: number
}

export interface Execution {
  routeId: string | null
  state: ExecState
  currentIndex: number
  total: number
  pauseReason: string | null
  message: string | null
}

export interface Video {
  protocol: 'SIM' | 'WHEP' | 'HLS' | 'NONE'
  url: string | null
  fallbackUrl: string | null
}

export interface DemoDrone {
  id: string
  label: Label | null
  online: boolean
  lat: number | null
  lon: number | null
  relativeHeight: number | null
  ellipsoidHeight: number | null
  heading: number | null
  horizontalSpeed: number | null
  verticalSpeed: number | null
  battery: number | null
  gimbalPitch: number | null
  gimbalYaw: number | null
  phase: FlightPhase
  execution: Execution
  video: Video | null
  homeLat: number | null
  homeLon: number | null
}

export interface Link {
  a: string
  b: string
  horizontalM: number
  verticalM: number
}

/** The platform's proximity judgement while the two are close (console only). */
export interface Proximity {
  level: 'warning' | 'hold' | 'clear'
  horizontalM: number
  verticalM: number | null
  predictedMinM: number
  thresholdM: number
  stopped: Label[]
  since: number
}

export interface DronesFrame {
  drones: DemoDrone[]
  link: Link | null
  proximity: Proximity | null
}

export interface FleetSafety {
  proximityMode: 'HOLD' | 'WARN_ONLY'
  rthSeparationM: number
}

export interface RthConfirm {
  label: Label
  message: string
}

export interface TrackPoint {
  lat: number
  lon: number
  h: number
  t: number
}

export interface ImageBox {
  x: number
  y: number
  w: number
  h: number
}

export interface DemoTarget {
  lat: number
  lon: number
  relativeHeight: number | null
  source: 'LASER' | 'MAP' | 'PRESET'
  droneId: string | null
  box: ImageBox | null
  at: number
}

export interface DemoEvent {
  id: number
  ts: number
  kind: EventKind
  from: string | null
  to: string | null
  text: string
}

export interface GeoCell {
  lat: number
  lon: number
  sizeM: number
  label: string
}

export interface Dog {
  mode: 'SIM' | 'EXTERNAL' | 'SKIP'
  online: boolean
  lat: number | null
  lon: number | null
  heading: number | null
  speed: number | null
  arrived: boolean
  lastCommand: { text: string; at: number } | null
  updatedAt: number
}

export interface DogSnapshot {
  dog: Dog
  track: TrackPoint[]
  cells: GeoCell[]
  path: LatLon[]
  target: DemoTarget | null
}

export interface DemoState {
  stage: Stage
  stageAt: Partial<Record<Stage, number>>
  startedAt: number
  waiting: string
  nextHint: string
  canNext: boolean
  autoContinue: boolean
  source: 'SIM' | 'PLATFORM'
  sourceAvailable: boolean
  sourceReason: string | null
  dogMode: 'SIM' | 'EXTERNAL' | 'SKIP'
  drones: Record<Label, string>
  highLabel: Label
  lowLabel: Label
  routes: { A1: string | null; B1: string | null; high2: string | null; low2: string | null; lowFollow: string | null }
  target: DemoTarget | null
  dogPath: LatLon[]
  dogStart: LatLon | null
  paused: Label[]
  simSpeedFactor: number
  /** The aircraft are simulated (the demo's own pair, or the platform's mock gateway). */
  simulated: boolean
  fleetSafety: FleetSafety
  /** A take-off waiting for the operator to confirm the return heights. */
  rthConfirm: RthConfirm | null
}

export interface Check {
  level: 'OK' | 'WARN' | 'FAIL'
  text: string
}

export interface Snapshot {
  state: DemoState
  drones: DronesFrame
  tracks: Partial<Record<Label, TrackPoint[]>>
  events: DemoEvent[]
  dog: DogSnapshot
  checks: Check[]
}

export interface DogMapping {
  coordSys: 'WGS84' | 'GCJ02' | 'LOCAL'
  origin: LatLon | null
  latPath: string
  lonPath: string
  xPath: string
  yPath: string
  headingPath: string
  headingUnit: 'DEG' | 'RAD'
  headingZeroEast: boolean
  speedPath: string
  cellsPath: string
  cellLatPath: string
  cellLonPath: string
  cellXPath: string
  cellYPath: string
  cellLabelPath: string
  cellSizeM: number
}

export interface DemoConfig {
  source: 'SIM' | 'PLATFORM'
  dogMode: 'SIM' | 'EXTERNAL' | 'SKIP'
  droneA: string
  droneB: string
  highLabel: Label
  routeA1: string | null
  routeB1: string | null
  routeHigh2: string | null
  routeLow2: string | null
  routeLowFollow: string | null
  autoContinue: boolean
  staggerDistanceM: number
  staggerMaxWaitS: number
  exchangeHoldS: number
  targetWaitS: number
  targetHoldS: number
  presetTarget: LatLon | null
  dogStart: LatLon | null
  simHomeA: LatLon | null
  simHomeB: LatLon | null
  simGroundEllipsoidM: number
  simSpeedFactor: number
  simDogSpeed: number
  messages: Record<string, string>
  dogMapping: DogMapping
}

/** One device of the platform's dual-drone backend (GET /api/v1/drones), for choosing A / B on the console. */
export interface PlatformDevice {
  droneSn: string | null
  gatewaySn: string
  label: string
  online: boolean
  droneOnline: boolean
  enabled: boolean
}

export const platformDevices = () => api<PlatformDevice[]>('/api/v1/drones')

/** Setting A / B to this follows the platform's own A / B labels (backend DemoScriptService.idFor). */
export const AUTO_DRONE = 'AUTO'

const base = '/api/v1/demo'
const post = <T>(path: string, body?: unknown) => api<T>(base + path, { method: 'POST', body })

export const demoApi = {
  snapshot: () => api<Snapshot>(`${base}/snapshot`),
  config: () => api<DemoConfig>(`${base}/config`),
  saveConfig: (c: DemoConfig) => api<DemoConfig>(`${base}/config`, { method: 'PUT', body: c }),
  autoContinue: (on: boolean) => api<DemoConfig>(`${base}/auto-continue`, { method: 'PUT', body: { on } }),
  checks: () => api<Check[]>(`${base}/checks`),
  start: () => post<DemoState>('/start'),
  next: () => post<DemoState>('/next'),
  presetTarget: () => post<DemoState>('/preset-target'),
  resume: (label: Label) => post<DemoState>(`/resume/${label}`),
  abort: () => post<DemoState>('/abort'),
  reset: () => post<DemoState>('/reset'),
  simPause: (label: Label) => post<DemoState>(`/sim/pause/${label}`),
  confirmRth: () => post<DemoState>('/confirm-rth'),
  sampleRoutes: (lat: number, lon: number, headingDeg: number) => post<DemoConfig>('/sample-routes', { lat, lon, headingDeg }),
}

/** Stage steps as the audience sees them (rendezvous is its own step: the "communication" moment). */
export const STEPS: { stage: Stage; title: string; short: string }[] = [
  { stage: 'S1_EXPLORE', title: t('分头探索'), short: t('一') },
  { stage: 'S1_RENDEZVOUS', title: t('汇合通信'), short: t('汇') },
  { stage: 'S2_RESCAN', title: t('高低复查'), short: t('二') },
  { stage: 'S3_TARGET', title: t('识别目标'), short: t('三') },
  { stage: 'S4_GUIDE', title: t('引导机器狗'), short: t('四') },
]

const ORDER: Stage[] = ['READY', 'S1_EXPLORE', 'S1_RENDEZVOUS', 'S2_RESCAN', 'S3_TARGET', 'S4_GUIDE', 'DONE']

/** Position of a stage in the run (ABORTED keeps the position where it stopped, see stageIndexOf). */
export function stageIndex(s: Stage): number {
  return ORDER.indexOf(s)
}

export const STAGE_TEXT: Record<Stage, string> = {
  READY: t('未开始'),
  S1_EXPLORE: t('第一阶段 · 分头探索'),
  S1_RENDEZVOUS: t('汇合 · 交换信息'),
  S2_RESCAN: t('第二阶段 · 高低协同复查'),
  S3_TARGET: t('第三阶段 · 低空识别目标'),
  S4_GUIDE: t('第四阶段 · 引导机器狗'),
  DONE: t('演示完成'),
  ABORTED: t('已中止'),
}

export const EXEC_TEXT: Record<ExecState, string> = {
  NONE: t('待命'),
  PREPARING: t('准备中'),
  ACQUIRING_CONTROL: tc('state', '申请控制权'),
  TAKING_OFF: t('起飞中'),
  FLYING: t('飞行中'),
  AT_WAYPOINT: t('到达航点'),
  FINISHING: tc('state', '结束动作'),
  COMPLETED: t('已到达，悬停'),
  FAILED: t('失败'),
  ABORTED: t('已中止'),
  PAUSED: t('靠近暂停'),
}

export const PHASE_TEXT: Record<FlightPhase, string> = {
  GROUND: t('地面'),
  TAKING_OFF: tc('state', '起飞'),
  FLYING: tc('state', '飞行'),
  HOVERING: tc('state', '悬停'),
  LANDING: tc('state', '降落'),
  UNKNOWN: t('未知'),
}

/** Colours of the two aircraft, the dog and the target on the demo pages (readable on satellite and dark maps). */
export const COLORS = { A: '#22d3ee', B: '#fb923c', dog: '#4ade80', target: '#f43f5e', link: '#e2e8f0' } as const

/** Keyed by the label as it arrives from the backend (translated in English mode, hence tb()). */
export const CELL_COLORS: Record<string, string> = {
  [tb('可通行')]: '#4ade80',
  [tb('草地')]: '#65a30d',
  [tb('碎石')]: '#a8a29e',
  [tb('灌木')]: '#15803d',
  [tb('障碍')]: '#ef4444',
  [tb('未知')]: '#64748b',
}

export function cellColor(label: string): string {
  return CELL_COLORS[label] ?? '#94a3b8'
}
