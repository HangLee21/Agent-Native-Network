import { api } from './http'
import { dronePath } from './drone'

/** Stick control mode state pushed by the backend (D-16). */
export interface ManualSnapshot {
  active: boolean
  exiting: boolean
  scale: number
  maxScale: number
  message: string
  heightClamped: boolean
  zoneBlocked: boolean
  gimbalMoving: boolean
  log: string[]
}

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const manualApi = (sn: string) => ({
  state: () => api<ManualSnapshot>(dronePath(sn, '/manual')),
  enter: (scale: number) => api<ManualSnapshot>(dronePath(sn, '/manual/stick/enter'), { method: 'POST', body: { scale } }),
  exit: () => api<ManualSnapshot>(dronePath(sn, '/manual/stick/exit'), { method: 'POST' }),
  scale: (scale: number) => api<ManualSnapshot>(dronePath(sn, '/manual/stick/scale'), { method: 'PUT', body: { scale } }),
})
