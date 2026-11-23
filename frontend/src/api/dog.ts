/**
 * Robot-dog API (/api/v1/dogs, docs/dog/ui-design.md). The browser never talks to a dog board directly; tokens and
 * control owners stay in the backend, the browser only holds opaque session ids.
 */
import { api } from './http'
import { config } from '@/config/runtime'

export type DogId = 's10' | 'lite3'
export type LinkState = 'online' | 'reconnecting' | 'offline' | 'never'

export interface DogLink {
  state: LinkState
  lastOkAt: number | null
  rttMs: number | null
  clockOk?: boolean
  /** S10: board clock minus server clock, seconds (null until the first good ping). */
  boardOffsetSec?: number | null
  error?: string | null
  tokenError?: string | null
}

export interface S10Job {
  id: string
  action: string
  state: 'running' | 'done' | 'failed'
  started?: number
  finished?: number
  detail?: string | null
  error?: string | null
  origin: 'platform' | 'other'
  commandId?: string | null
  label?: string | null
  stoppable: boolean
}

export interface ImageRow {
  image?: string
  last?: number
  render?: number
  age?: number | null
  error?: string | null
  resolution?: [number, number]
}

export interface CloudRow {
  count?: number
  points?: number
  frame?: string
  age?: number | null
  error?: string | null
}

export interface S10State {
  dogId: 's10'
  kind: 's10'
  name: string
  link: DogLink
  serverTime: number
  chassis: Record<string, unknown>
  posture: string | null
  available: boolean | null
  nav: Record<string, unknown> | null
  map: Record<string, unknown> | null
  maps: string[]
  mapsError?: string | null
  ik: { ready?: boolean; limits?: [number, number][]; error?: string } | null
  vision: { ready?: boolean; detail?: string } | null
  boardTime: number | null
  workAt: number | null
  workError: string | null
  jobs: S10Job[]
  topics: {
    boardNow?: number | null
    rgb?: ImageRow
    depth?: ImageRow
    joints?: { deg?: (number | null)[]; age?: number | null }
    motion?: { state?: number; age?: number | null }
    cloudMap?: CloudRow
    cloudRaw?: CloudRow
  }
  stateAt: number | null
  stateError: string | null
  holdActive: boolean
  armHoldActive: boolean
}

export interface Lite3State {
  dogId: 'lite3'
  kind: 'lite3'
  name: string
  link: DogLink
  serverTime: number
  statusAt: number | null
  /** Server time of the last stand / lie toggle sent by anyone on this platform (a second one is refused for 3 s). */
  standAt?: number | null
  robot: {
    connected?: boolean
    armed?: boolean
    controller?: 'platform' | 'other' | null
    controlSession?: string | null
    control_mode?: string
    feedback_age?: number | null
    stop_serial?: number
    error?: string
    feedback_available?: boolean
    battery?: number | null
    robot_state?: string
  }
  camera?: {
    topics?: string[]
    selected?: { rgb: string; depth: string }
    ages?: { rgb?: number; depth?: number }
    error?: string
    depth_guard?: { age?: number | null; valid_ratio?: number; distance_m?: number | null }
  }
}

export type DogState = S10State | Lite3State

export type CommandState =
  | 'sent' | 'running' | 'replied' | 'done' | 'notdone' | 'noflag' | 'failed' | 'timeout' | 'lost' | 'unknown'
  | 'received' | 'navstart' | 'gripped' | 'stopped' | 'unconfirmed' | 'noreply'

export interface DogCommand {
  id: string
  dogId: DogId
  action: string
  label: string
  params: Record<string, unknown>
  state: CommandState
  detail: string | null
  error: string | null
  result: unknown
  jobId: string | null
  createdAt: number
  finishedAt: number | null
}

export interface HoldReply {
  ok?: boolean
  closed?: boolean
  skipped?: boolean
  /** Lite3 idle keep-alive did not get through; control is kept and the browser sends it again. */
  retry?: boolean
  ignored?: boolean
  confirmed?: boolean
  detail?: string
  session?: string
  leaseMs?: number
}

export const dogApi = {
  list: () => api<DogState[]>('/api/v1/dogs'),
  time: () => api<{ serverMs: number; mode: string }>('/api/v1/dogs/time'),
  commands: (id: DogId) => api<DogCommand[]>(`/api/v1/dogs/${id}/commands`),
  s10Action: (body: Record<string, unknown>) => api<DogCommand>('/api/v1/dogs/s10/actions', { method: 'POST', body }),
  s10Hold: (body: Record<string, unknown>) => api<HoldReply>('/api/v1/dogs/s10/hold', { method: 'POST', body }),
  s10ArmHold: (body: Record<string, unknown>) => api<HoldReply>('/api/v1/dogs/s10/arm-hold', { method: 'POST', body }),
  s10Clouds: () => api<Record<'map' | 'raw', CloudRow & { pointsXYZ: [number, number, number][] }>>('/api/v1/dogs/s10/clouds'),
  lite3: (body: Record<string, unknown>) => api<HoldReply & Partial<DogCommand>>('/api/v1/dogs/lite3/control', { method: 'POST', body }),
  lite3Camera: (rgb: string, depth: string) => api<DogCommand>('/api/v1/dogs/lite3/camera', { method: 'POST', body: { rgb, depth } }),
}

/**
 * Image URLs go through the backend; the query string only defeats caching. The board gives image names either bare or
 * as "/media/<name>" (snapshot, recognition, state rows): the prefix is dropped here once for all of them.
 */
export function s10MediaUrl(name: string, stamp: number | string): string {
  const bare = name.replace(/^\/?media\//, '')
  return `${config().apiBaseUrl}/api/v1/dogs/s10/media/${encodeURIComponent(bare)}?t=${stamp}`
}
export function s10MapUrl(stamp: number): string {
  return `${config().apiBaseUrl}/api/v1/dogs/s10/map.png?t=${stamp}`
}
export function lite3FrameUrl(kind: 'rgb' | 'depth', stamp: number): string {
  return `${config().apiBaseUrl}/api/v1/dogs/lite3/frame/${kind}?t=${stamp}`
}

/** Best-effort end of a hold or control when the page is going away (keepalive request). */
export function beacon(path: string, body: Record<string, unknown>): void {
  try {
    void fetch(config().apiBaseUrl + path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), keepalive: true })
  } catch {
    /* page is closing */
  }
}
