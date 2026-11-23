import { config } from '@/config/runtime'
import { api } from './http'

/** 监视台 settings, shared by every screen (stored on the backend, pushed as `monitor-settings`). */
export interface WatchSettings {
  /** Show only the track already flown: no planned route, waypoints, route names or route progress. Default true. */
  hideRoute: boolean
  /** Device keys (drone RC serial, later `dog:<id>`) in the order their videos are shown; others follow by name. */
  videoOrder: string[]
}

export interface RecordingSpan {
  startAt: number
  durationMs: number
}

export const watchApi = {
  settings: () => api<WatchSettings>('/api/v1/monitor/settings'),
  /** Partial update: fields left out keep their value. */
  updateSettings: (s: Partial<WatchSettings>) => api<WatchSettings>('/api/v1/monitor/settings', { method: 'PUT', body: s }),
  /** Recorded spans of a flight's video, also while it is still being recorded (ends ~2 s before now). */
  spans: (sessionId: string, start?: number, end?: number) => {
    const q = new URLSearchParams()
    if (start !== undefined) q.set('start', String(Math.round(start)))
    if (end !== undefined) q.set('end', String(Math.round(end)))
    const s = q.toString()
    return api<RecordingSpan[]>(`/api/v1/history/sessions/${sessionId}/recording/spans${s ? `?${s}` : ''}`)
  },
  /** URL of an mp4 clip of the recording (max 60 s); usable directly as a <video> src. */
  clipUrl: (sessionId: string, start: number, durationS: number) =>
    `${config().apiBaseUrl}/api/v1/history/sessions/${sessionId}/recording?start=${Math.round(start)}&duration=${durationS.toFixed(1)}`,
}
