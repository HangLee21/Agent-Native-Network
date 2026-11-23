import { config } from '@/config/runtime'
import { t } from '@/i18n'
import { api } from './http'
import type { Route } from './routes'

/** Flight history API (D-19, D-20). */
export type Outcome = 'LANDED' | 'COMPLETED' | 'STOPPED' | 'RETURNED_HOME' | 'EMERGENCY_STOP' | 'LINK_LOST' | 'INTERRUPTED'
export type VideoStatus = 'UNAVAILABLE' | 'OFF' | 'PENDING' | 'ARCHIVING' | 'READY' | 'NONE' | 'FAILED' | 'DELETED'
export type EventLevel = 'INFO' | 'WARNING' | 'CRITICAL'

export interface SessionSummary {
  id: string
  status: 'OPEN' | 'CLOSED'
  startedAt: number
  takeoffAt: number | null
  landedAt: number | null
  endedAt: number | null
  outcome: Outcome | null
  routeId: string | null
  routeName: string | null
  distanceMeters: number
  maxRelativeHeight: number | null
  maxHomeDistance: number | null
  maxHorizontalSpeed: number | null
  batteryStart: number | null
  batteryEnd: number | null
  alertCount: number
  maxAlertLevel: EventLevel | null
  commandCount: number
  simulated: boolean
  resumed: boolean
  protectedFlag: boolean
  videoStatus: VideoStatus | null
  /** Total size of the archived video files; null when the flight has none. */
  videoBytes?: number | null
  trackPreview: [number, number][] | null
  droneSn?: string | null
  gatewaySn?: string | null
  /** Other drones' flights overlapping this one in time (D-33): they can be replayed together. */
  together?: Together[]
}

export interface Together {
  id: string
  gatewaySn: string
  droneSn: string | null
}

export interface VideoPart {
  index: number
  file: string
  startAt: number
  durationMs: number
  bytes: number
  transcoded: boolean
}

export interface SessionDetail extends SessionSummary {
  droneSn: string | null
  gatewaySn: string | null
  takeoffLat: number | null
  takeoffLon: number | null
  takeoffEllipsoidHeight: number | null
  homeLat: number | null
  homeLon: number | null
  sampleCount: number
  droppedItems: number
  delayMinMs: number | null
  delayAvgMs: number | null
  delayMaxMs: number | null
  clockOffsetMs: number | null
  routeSnapshot: Route | null
  rawAtTakeoff: Record<string, unknown> | null
  rawAtLanding: Record<string, unknown> | null
  videoWanted: boolean
  videoMessage: string | null
  videoPath: string | null
  videoParts: VideoPart[] | null
  videoQuality: number | null
  videoOffsetMs: number
  recording: boolean
}

/** One telemetry sample. OSD rows carry every field; DRC rows only position, heading, speed, gimbal and drcHeight. */
export interface Sample {
  ts: number
  deviceTs: number | null
  sampleSource: 'OSD' | 'DRC'
  lat: number | null
  lon: number | null
  ellipsoidHeight: number | null
  relativeHeight: number | null
  drcHeight: number | null
  horizontalSpeed: number | null
  verticalSpeed: number | null
  attitudeHead: number | null
  attitudePitch: number | null
  attitudeRoll: number | null
  gimbalPitch: number | null
  gimbalYaw: number | null
  gimbalRoll: number | null
  zoomFactor: number | null
  battery: number | null
  remainFlightTime: number | null
  returnHomePower: number | null
  modeCode: number | null
  gpsNumber: number | null
  rtkNumber: number | null
  windSpeed: number | null
  windDirection: number | null
  homeDistance: number | null
  heightLimit: number | null
}

export interface FlightEvent {
  id: number
  ts: number
  eventType: string
  eventLevel: EventLevel
  title: string
  payload: Record<string, unknown> | null
}

export interface FlightCommand {
  id: string
  commandType: string
  label: string
  channel: string | null
  status: 'PENDING' | 'REJECTED' | 'SENT' | 'ACKED' | 'FAILED' | 'TIMEOUT'
  createdAt: number
  sentAt: number | null
  completedAt: number | null
  resultCode: number | null
  message: string | null
  params: { command?: string; params?: Record<string, unknown> } | null
}

export interface HistoryFilter {
  from?: number
  to?: number
  outcome?: string
  routeId?: string
  hasAlerts?: boolean
  includeSimulated?: boolean
  /** Aircraft or RC serial number (D-27). */
  drone?: string
}

export interface RecorderStatus { enabled: boolean; paused: boolean; pausedMessage: string | null; queueSize: number; droppedTotal: number; pendingRows: number; currentSessionId: string | null }

export interface HistoryStatus {
  /** The drone recording right now (or the first one); `recorders` has every drone's (D-27). */
  recorder: RecorderStatus
  recorders?: { gatewaySn: string; droneSn: string | null; label: string; status: RecorderStatus }[]
  video: { configured: boolean; recordingEnabled: boolean; diskLow: boolean; freeBytes: number | null; minFreeBytes: number; transcode: boolean; autoStartStream: boolean; recordQuality: number }
  sessions: number
  samples: number
  /** Total size of all flights' archived video files. */
  videoBytes?: number
}

export const OUTCOME_LABELS: Record<Outcome, string> = {
  LANDED: t('已降落'),
  COMPLETED: t('航线完成'),
  STOPPED: t('航线中止'),
  RETURNED_HOME: t('已返航'),
  EMERGENCY_STOP: t('急停'),
  LINK_LOST: t('失联'),
  INTERRUPTED: t('记录中断'),
}

export const VIDEO_LABELS: Record<VideoStatus, string> = {
  UNAVAILABLE: t('未配置录像'),
  OFF: t('未录像'),
  PENDING: t('待归档'),
  ARCHIVING: t('归档中'),
  READY: t('有视频'),
  NONE: t('无视频'),
  FAILED: t('归档失败'),
  DELETED: t('录像已删除'),
}

function query(f: HistoryFilter): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(f)) if (v !== undefined && v !== '' && v !== null) p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

const base = '/api/v1/history'

export const historyApi = {
  list: (f: HistoryFilter = {}) => api<SessionSummary[]>(`${base}/sessions${query(f)}`),
  get: (id: string) => api<SessionDetail>(`${base}/sessions/${id}`),
  samples: (id: string) => api<Sample[]>(`${base}/sessions/${id}/samples`),
  events: (id: string) => api<FlightEvent[]>(`${base}/sessions/${id}/events`),
  commands: (id: string) => api<FlightCommand[]>(`${base}/sessions/${id}/commands`),
  patch: (id: string, body: { protectedFlag?: boolean; videoOffsetMs?: number; videoWanted?: boolean }) =>
    api<{ ok: boolean }>(`${base}/sessions/${id}`, { method: 'PATCH', body }),
  remove: (id: string) => api<{ deleted: number }>(`${base}/sessions/${id}`, { method: 'DELETE' }),
  removeMany: (ids: string[]) => api<{ deleted: number; skipped: string[] }>(`${base}/sessions/delete`, { method: 'POST', body: { ids } }),
  /** Deletes only the video files; the flight record stays. */
  removeVideo: (id: string) => api<{ id: string; freedBytes: number }>(`${base}/sessions/${id}/video`, { method: 'DELETE' }),
  /** Archives a closed flight's video again in the background (after a failed or empty archive); returns the flight. */
  archiveVideo: (id: string) => api<SessionDetail>(`${base}/sessions/${id}/video/archive`, { method: 'POST' }),
  removeVideos: (ids: string[]) =>
    api<{ deleted: number; skipped: string[]; freedBytes: number }>(`${base}/sessions/delete-video`, { method: 'POST', body: { ids } }),
  saveRoute: (id: string, body: { name?: string; spacingMeters?: number; speed?: number }) =>
    api<Route>(`${base}/sessions/${id}/route`, { method: 'POST', body }),
  status: () => api<HistoryStatus>(`${base}/status`),
  settings: () => api<{ videoRecording: boolean; videoConfigured: boolean }>(`${base}/settings`),
  updateSettings: (videoRecording: boolean) =>
    api<{ videoRecording: boolean; videoConfigured: boolean }>(`${base}/settings`, { method: 'PUT', body: { videoRecording } }),
  exportUrl: (id: string, format: 'geojson' | 'kml' | 'csv' | 'json') => `${config().apiBaseUrl}${base}/sessions/${id}/export?format=${format}`,
  videoUrl: (id: string, index: number) => `${config().apiBaseUrl}${base}/sessions/${id}/video/${index}`,
}
