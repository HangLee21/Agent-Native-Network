import { config } from '@/config/runtime'
import { t } from '@/i18n'
import { api } from './http'
import type { EventLevel, FlightCommand, FlightEvent, Sample, VideoPart, VideoStatus } from './history'

/**
 * Dog records (D-40): what a dog of the new dog system did, from the first command, control or movement to 60 s after
 * the last. Same shapes as the flight records where the meaning is the same (takeoffAt = start, landedAt = end,
 * horizontalSpeed, attitudeHead = GNSS heading, commands and events), so the replay reads both alike.
 */
export type DogOutcome = 'ENDED' | 'SOFT_ESTOP' | 'LINK_LOST' | 'INTERRUPTED'

/** Another device's record overlapping this one in time. */
export interface RecordTogether {
  kind: 'drone' | 'dog'
  id: string
  /** RC serial number of a drone, id of a dog. */
  device: string
}

export interface DogRecordSummary {
  kind: 'dog'
  id: string
  status: 'OPEN' | 'CLOSED'
  dogId: string
  dogModel: string | null
  dogLabel: string | null
  startedAt: number
  takeoffAt: number
  landedAt: number | null
  endedAt: number | null
  outcome: DogOutcome | null
  startReason: string | null
  routeId: null
  routeName: null
  distanceMeters: number
  maxRelativeHeight: null
  maxHorizontalSpeed: number | null
  batteryStart: number | null
  batteryEnd: number | null
  alertCount: number
  maxAlertLevel: EventLevel | null
  commandCount: number
  simulated: boolean
  resumed: false
  protectedFlag: boolean
  videoStatus: VideoStatus | null
  videoBytes: number | null
  trackPreview: [number, number][] | null
  together: RecordTogether[]
}

export interface DogRecordDetail extends DogRecordSummary {
  sampleCount: number
  videoWanted: boolean
  videoMessage: string | null
  videoPath: string | null
  videoParts: VideoPart[] | null
  videoOffsetMs: number
  recording: boolean
  takeoffEllipsoidHeight: null
  homeLat: null
  homeLon: null
  routeSnapshot: null
}

/** A dog sample: the flight sample's fields it has, plus its own. */
export type DogSample = Pick<Sample, 'ts' | 'lat' | 'lon' | 'horizontalSpeed' | 'attitudeHead' | 'attitudePitch' | 'attitudeRoll' | 'battery'> & {
  sampleSource: 'DOG'
  altitude: number | null
  fix: string | null
  sats: number | null
  headingSource: string | null
  basicState: number | null
  basicStateName: string | null
  motionState: number | null
  gaitState: number | null
  mode: string | null
  controlHeld: boolean | null
  controlLabel: string | null
  yaw: number | null
}

export interface DogRecordFilter {
  from?: number
  to?: number
  dog?: string
  outcome?: string
  hasAlerts?: boolean
  includeSimulated?: boolean
}

export const DOG_OUTCOME_LABELS: Record<DogOutcome, string> = {
  ENDED: t('正常结束'),
  SOFT_ESTOP: t('软急停'),
  LINK_LOST: t('失联'),
  INTERRUPTED: t('记录中断'),
}

/** How a dog is named on the records page: its model in the platform's spelling, else its id. */
export function dogName(r: { dogModel: string | null; dogLabel: string | null; dogId: string }): string {
  const m = r.dogModel === 'lite3' ? 'Lite3' : r.dogModel === 's10' ? 'S10' : null
  const label = r.dogLabel && r.dogLabel !== r.dogId ? r.dogLabel : null
  return label ?? m ?? r.dogId
}

function query(f: DogRecordFilter): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== '' && v !== null) p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

const base = '/api/v1/dog-records'

export const dogRecordsApi = {
  list: (f: DogRecordFilter = {}) => api<DogRecordSummary[]>(`${base}${query(f)}`),
  get: (id: string) => api<DogRecordDetail>(`${base}/${id}`),
  samples: (id: string) => api<DogSample[]>(`${base}/${id}/samples`),
  events: (id: string) => api<FlightEvent[]>(`${base}/${id}/events`),
  commands: (id: string) => api<FlightCommand[]>(`${base}/${id}/commands`),
  patch: (id: string, body: { protectedFlag?: boolean; videoOffsetMs?: number }) =>
    api<{ ok: boolean }>(`${base}/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => api<{ deleted: number }>(`${base}/${id}`, { method: 'DELETE' }),
  removeMany: (ids: string[]) => api<{ deleted: number; skipped: string[] }>(`${base}/delete`, { method: 'POST', body: { ids } }),
  removeVideo: (id: string) => api<{ id: string; freedBytes: number }>(`${base}/${id}/video`, { method: 'DELETE' }),
  removeVideos: (ids: string[]) =>
    api<{ deleted: number; skipped: string[]; freedBytes: number }>(`${base}/delete-video`, { method: 'POST', body: { ids } }),
  archiveVideo: (id: string) => api<DogRecordDetail>(`${base}/${id}/video/archive`, { method: 'POST' }),
  videoUrl: (id: string, index: number) => `${config().apiBaseUrl}${base}/${id}/video/${index}`,
}
