import { api } from './http'
import { dronePath } from './drone'

/** Device message feed (D-18): what the aircraft / RC report beyond plain telemetry. */
export interface DeviceMessage {
  id: string
  ts: number
  level: 'INFO' | 'WARNING' | 'CRITICAL'
  source: string
  title: string
  text: string
  raw: Record<string, unknown>
}

/** Obstacle distances in metres from hsi_info_push (null = not reported). */
export interface Obstacles {
  horizontal: number | null
  up: number | null
  down: number | null
  around: number[]
  working: Record<string, boolean>
  near: boolean
  ts: number
}

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const deviceMessagesApi = (sn: string) => ({
  list: (limit = 100) => api<{ list: DeviceMessage[]; obstacles: Obstacles | null }>(dronePath(sn, `/device-messages?limit=${limit}`)),
})
