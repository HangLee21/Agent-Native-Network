import { api } from './http'
import { t } from '@/i18n'

/** The new dog system (docs/dog/v2/design.md, /api/v2/dogs). Separate from the old dog API in dog.ts. */
export type Dog2Mode = 'old' | 'new' | 'switching_to_new' | 'switching_to_old' | 'unknown'

export interface Dog2Video {
  path: string
  whep: string | null
  state: 'off' | 'starting' | 'live' | 'error'
  /** MediaMTX publisher readiness. Null or omitted when the server cannot check it. */
  ready?: boolean | null
}

export interface Dog2Telemetry {
  basic_state: number
  basic_state_name?: string
  battery_pct: number | null
  rpy: number[]
  vel_body: number[]
  feedback_age_s: number
  /** The rest of the state packet as the board passes it on (protocol.md section 7); rpy units not measured yet. */
  rpy_rate?: number[]
  acc?: number[]
  vel_world?: number[]
  pos_world?: number[]
  gait_state?: number
  motion_state?: number
  firmware?: number
  /** Front depth distance (the old Lite3 console's centre depth, protocol.md section 7); absent when the dog has none. */
  depth_front?: { dist_m: number | null; valid_pct: number | null; age_s: number | null; state?: string }
}

export interface Dog2Status {
  mode?: Dog2Mode
  gateway?: string
  control?: { session: string; label?: string; held_s?: number } | null
  motion_host?: { feedback_age_s: number | null }
  old_console?: { reachable?: boolean; connected?: boolean | null; armed?: boolean | null; robot_state?: string | null; battery_pct?: number | null }
  last_error?: { code: string; text: string; age_s?: number } | null
  /** The GNSS reader (absent when the dog has none): off, starting, no_device, no_permission, busy, no_data, no_fix, fix, error. */
  gnss?: { state: string; text?: string }
}

/** GNSS position and heading (protocol.md section 8); WGS84, degrees from true north clockwise. */
export interface Dog2Position {
  fix: string
  lat: number | null
  lon: number | null
  alt_m?: number | null
  sats?: number | null
  hdop?: number | null
  fix_age_s?: number | null
  speed_mps?: number | null
  course_deg?: number | null
  heading_deg?: number | null
  /** receiver (dual antenna), imu_aligned (yaw aligned to the GNSS course), course (direction of travel), none */
  heading_source: string
  heading_age_s?: number | null
  antenna?: string | null
}

export interface Dog2 {
  id: string
  label: string
  model: string | null
  software: string | null
  online: boolean
  enabled: boolean
  mode: Dog2Mode | null
  gateway: string | null
  statusAgeMs: number | null
  telemetryAgeMs: number | null
  status: Dog2Status | null
  telemetry: Dog2Telemetry | null
  position?: Dog2Position | null
  positionAgeMs?: number | null
  capabilities?: { position?: { source: string; heading?: string[] } } & Record<string, unknown>
  control: { held: boolean; label?: string | null; mine: boolean; session: string | null; endedReason: string | null
    /** During navigation the page that held control went silent (e.g. reloaded): another page can take it back. */
    adoptable?: boolean }
  video: Record<string, Dog2Video>
  lastSeenAt: number | null
  /** hello.capabilities.nav (outdoor GPS navigation); null or absent: the dog cannot navigate and no navigation UI shows. */
  navCapability?: Dog2NavCapability | null
  /** The latest nav message plus what the platform keeps of the task; null or absent before the first one. */
  nav?: Dog2Nav | null
}

export interface Dog2List { mode: 'off' | 'mock' | 'on'; broker: boolean; dogs: Dog2[] }

export interface Dog2Reply {
  cmdId?: string
  result: 'done' | 'rejected' | 'failed' | 'accepted' | 'no_reply' | 'not_sent'
  code?: string | null
  text?: string | null
  ms?: number
  session?: string
}

// ---------------------------------------------------------------- outdoor navigation (户外GPS导航-架构.md 5, 6.2)

/** One speed level the dog offers, slowest first; `mps` is its upper limit. */
export interface Dog2SpeedLevel { id: string; mps: number }

/** hello.capabilities.nav, as the dog reports it (protocol.md 9.1). */
export interface Dog2NavCapability {
  kind: string
  avoidance?: boolean
  /** Empty: one fixed speed; the platform shows no selector and sends no level. */
  speed_levels: Dog2SpeedLevel[]
  default_speed?: string
  /** A typed-in speed is accepted up to this (m/s); absent: only the levels. */
  speed_max_mps?: number
  /** [min, max] metres */
  arrive_radius_m?: [number, number]
  max_points?: number
  dry_run?: boolean
}

/** A point of a navigation task or a dog route (WGS84). */
export interface Dog2NavPoint { lat: number; lon: number; name?: string | null }

/** What the next start needs (nav.ready). */
export interface Dog2NavReady {
  loc?: boolean
  nav2?: boolean
  lidar?: boolean | null
  gnss?: string
  heading?: string
  heading_start_ok?: boolean
  text?: string | null
}

/** Navigation state: the dog's nav message (nav.schema.json, snake_case) plus the platform's task fields (camelCase). */
export interface Dog2Nav {
  v?: number
  ts?: number
  task_id?: string | null
  /** idle, starting, running, paused, arrived, ended; a string, more may come */
  state: string
  reason?: string | null
  reason_text?: string | null
  index?: number | null
  count?: number
  to_point_m?: number | null
  to_end_m?: number | null
  eta_s?: number | null
  speed_mps?: number | null
  speed_level?: string | null
  /** The speed chosen for the task (a level's or a typed-in one); speed_level is "custom" for a typed-in one. */
  speed_target_mps?: number | null
  avoidance?: boolean | null
  dry_run?: boolean
  front_m?: number | null
  pose?: { lat: number; lon: number; heading_deg?: number | null; std_m?: number | null } | null
  path?: [number, number][]
  /** The dog sends [[lat, lon]…]; the platform may put its own task points ({lat, lon, name}) here instead. */
  points?: ([number, number] | Dog2NavPoint)[]
  ready?: Dog2NavReady
  // platform
  taskId?: string | null
  startedAt?: number | null
  /** How long ago the platform received this nav message (platform clock). */
  ageMs?: number | null
  routeName?: string | null
  /** Arrival radius of this task, when the platform reports it (else the dog's setting is used). */
  arriveRadiusM?: number | null
}

/** Per-dog navigation defaults (PUT /nav/settings). */
export interface Dog2NavSettings {
  avoidanceDefault: boolean
  arriveRadiusM: number
  /** null: the dog's default level */
  speedLevel: string | null
  area: [number, number][] | null
  useAircraftZone: boolean
  maxFirstM: number
}

export const NAV_SETTINGS_DEFAULT: Dog2NavSettings = {
  avoidanceDefault: true, arriveRadiusM: 3, speedLevel: null, area: null, useAircraftZone: true, maxFirstM: 300,
}

/** GET /nav */
export interface Dog2NavView {
  capability: Dog2NavCapability | null
  settings: Dog2NavSettings | null
  nav: Dog2Nav | null
  task: Record<string, unknown> | null
}

export interface Dog2NavProblem { code: string; text: string; index?: number | null }

/** POST /nav/check */
export interface Dog2NavCheck {
  ok: boolean
  problems: Dog2NavProblem[]
  area: [number, number][] | null
  areaSource: 'dog' | 'aircraft' | 'none'
  totalM: number
  firstM: number | null
}

/** POST /nav/start; fields left out take the dog's settings. */
export interface Dog2NavStart {
  points: Dog2NavPoint[]
  avoidance?: boolean
  speedLevel?: string
  /** A typed-in speed (m/s) instead of a level. */
  speedMps?: number
  arriveRadiusM?: number
  standingConfirmed: true
  dryRun?: boolean
  routeId?: number
}

/** Replies of the nav endpoints: as POST /commands, plus the task id. */
export interface Dog2NavReply extends Dog2Reply { taskId?: string | null }

/** A route of the dog route library (/api/v2/dog-routes). */
export interface Dog2Route {
  id: number
  name: string
  points: Dog2NavPoint[]
  note?: string | null
  createdAt?: number
  updatedAt?: number
}

export interface Dog2LogEntry { at: number; kind: string; action?: string; result?: string; code?: string; text?: string; ended?: string; stopped?: string }

const base = (id: string) => `/api/v2/dogs/${encodeURIComponent(id)}`

export const dog2Api = {
  list: (signal?: AbortSignal) => api<Dog2List>('/api/v2/dogs', { signal }),
  command: (id: string, action: string, args: Record<string, unknown> = {}) =>
    api<Dog2Reply>(`${base(id)}/commands`, { method: 'POST', body: { action, args } }),
  take: (id: string, page: string) => api<Dog2Reply>(`${base(id)}/control`, { method: 'POST', body: { op: 'take', page } }),
  release: (id: string, session: string, reason: string) =>
    api<Dog2Reply>(`${base(id)}/control`, { method: 'POST', body: { op: 'release', session, reason } }),
  /** `n` numbers the beats: separate requests can overtake each other, the backend drops an older one. */
  teleop: (id: string, session: string, axes: [number, number, number], n: number) =>
    api<{ ok: boolean; seq?: number; dropped?: boolean }>(`${base(id)}/teleop`, { method: 'POST', body: { session, axes, n } }),
  video: (id: string, stream: string) => api<{ path: string; state: string }>(`${base(id)}/video`, { method: 'POST', body: { stream } }),
  enable: (id: string, enabled: boolean) => api<Dog2>(`${base(id)}/enabled`, { method: 'PUT', body: { enabled } }),
  log: (id: string) => api<Dog2LogEntry[]>(`${base(id)}/commands`),
  // outdoor navigation (contract 户外GPS导航-架构.md 6.2); nav_* never go through POST /commands
  nav: (id: string) => api<Dog2NavView>(`${base(id)}/nav`),
  /** nav_prepare: the dog starts its navigation parts ahead of a start (no control needed; added by the backend beyond 6.2). */
  navPrepare: (id: string) => api<Dog2Reply>(`${base(id)}/nav/prepare`, { method: 'POST', body: {} }),
  navCheck: (id: string, points: Dog2NavPoint[]) => api<Dog2NavCheck>(`${base(id)}/nav/check`, { method: 'POST', body: { points } }),
  navStart: (id: string, req: Dog2NavStart) => api<Dog2NavReply>(`${base(id)}/nav/start`, { method: 'POST', body: req }),
  navPause: (id: string) => api<Dog2NavReply>(`${base(id)}/nav/pause`, { method: 'POST', body: {} }),
  navResume: (id: string) => api<Dog2NavReply>(`${base(id)}/nav/resume`, { method: 'POST', body: {} }),
  navCancel: (id: string) => api<Dog2NavReply>(`${base(id)}/nav/cancel`, { method: 'POST', body: {} }),
  navOptions: (id: string, opts: { avoidance?: boolean; speedLevel?: string; speedMps?: number }) =>
    api<Dog2NavReply>(`${base(id)}/nav/options`, { method: 'PUT', body: opts }),
  navSettings: (id: string, s: Dog2NavSettings) => api<Dog2NavSettings>(`${base(id)}/nav/settings`, { method: 'PUT', body: s }),
}

/** The dog route library (/api/v2/dog-routes): points are WGS84 latitude, longitude and an optional name. */
export const dogRoutesApi = {
  list: () => api<Dog2Route[]>('/api/v2/dog-routes'),
  get: (id: number) => api<Dog2Route>(`/api/v2/dog-routes/${id}`),
  create: (r: { name: string; points: Dog2NavPoint[]; note?: string | null }) => api<Dog2Route>('/api/v2/dog-routes', { method: 'POST', body: r }),
  update: (id: number, r: { name: string; points: Dog2NavPoint[]; note?: string | null }) => api<Dog2Route>(`/api/v2/dog-routes/${id}`, { method: 'PUT', body: r }),
  remove: (id: number) => api<void>(`/api/v2/dog-routes/${id}`, { method: 'DELETE' }),
  /** Imports an aircraft route (only latitude and longitude are taken). */
  fromRoute: (routeId: string) => api<Dog2Route>(`/api/v2/dog-routes/from-route/${encodeURIComponent(routeId)}`, { method: 'POST', body: {} }),
}

/** What each reply means for the operator (results come from the dog, as for the aircraft). */
export function replyText(r: Dog2Reply): string {
  switch (r.result) {
    case 'done': return t('狗已执行')
    case 'rejected': return t('狗没执行：{reason}', { reason: r.text ?? r.code ?? '' })
    case 'failed': return t('狗执行失败：{reason}', { reason: r.text ?? r.code ?? '' })
    case 'no_reply': return r.text ?? t('没收到回复：狗可能已经收到，先看狗的状态')
    case 'not_sent': return r.text ?? t('没发出去')
    default: return r.result
  }
}

export const MODE_TEXT: Record<Dog2Mode, string> = {
  old: t('老系统在控'),
  new: t('新系统在控'),
  switching_to_new: t('正在切到新系统'),
  switching_to_old: t('正在切回老系统'),
  unknown: t('模式未知'),
}

/** Lite3 directions, the same axes as the old Lite3 page (components/dog/HoldPad.vue L3_AXES). */
export type Dog2Dir = 'fwd' | 'back' | 'left' | 'right' | 'tl' | 'tr'
export const DOG2_AXES: Record<Dog2Dir, [number, number, number]> = {
  fwd: [1, 0, 0], back: [-1, 0, 0], left: [0, -1, 0], right: [0, 1, 0], tl: [0, 0, -1], tr: [0, 0, 1],
}
