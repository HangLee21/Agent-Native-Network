import { api } from './http'
import { dronePath } from './drone'
import { t } from '@/i18n'
import type { RcLostAction } from './routes'

export type CommandStatus = 'PENDING' | 'REJECTED' | 'SENT' | 'ACKED' | 'FAILED' | 'TIMEOUT'
export type CommandChannel = 'SERVICES' | 'DRC' | 'PROPERTY'

/** S-03 command receipt. The UI shows results from these records only. */
export interface CommandRecord {
  id: string
  type: string
  label: string
  channel: CommandChannel | null
  status: CommandStatus
  createdAt: number
  sentAt: number | null
  completedAt: number | null
  resultCode: number | null
  message: string | null
}

export type ControlState = 'NONE' | 'REQUESTING' | 'GRANTED' | 'DENIED' | 'LOST'

export interface ControlSnapshot {
  control: ControlState
  message: string
  drcState: number
  drcReady: boolean
  drcRequested: boolean
  heartbeatRttMs: number
  lastHeartbeatAckAt: number
  rcButtonsDisabled: boolean
}

export type AlertLevel = 'CRITICAL' | 'WARNING'

export interface Alert {
  code: string
  level: AlertLevel
  title: string
  message: string
  suggestion: string | null
  since: number
}

export interface TakeoffRequest {
  relativeHeight: number
  securityTakeoffHeight: number
  rthAltitude: number
  rcLostAction: RcLostAction
  maxSpeed: number
  /** The operator confirmed the return heights differ from another drone the platform did not launch (S-06). */
  rthConfirmed?: boolean
}

const post = <T>(path: string, body?: unknown) => api<T>(path, { method: 'POST', body })

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const controlApi = (sn: string) => ({
  state: () => api<ControlSnapshot>(dronePath(sn, '/control')),
  request: () => post<ControlSnapshot>(dronePath(sn, '/control/request')),
  release: () => post<CommandRecord>(dronePath(sn, '/control/release')),
  enterDrc: () => post<CommandRecord>(dronePath(sn, '/control/drc/enter')),
  commands: (limit = 50) => api<CommandRecord[]>(dronePath(sn, `/commands?limit=${limit}`)),
  alerts: () => api<Alert[]>(dronePath(sn, '/alerts')),
  takeoff: (r: TakeoffRequest) => post<CommandRecord>(dronePath(sn, '/flight/takeoff'), r),
  returnHome: () => post<CommandRecord>(dronePath(sn, '/flight/return-home')),
  cancelReturnHome: () => post<CommandRecord>(dronePath(sn, '/flight/return-home/cancel')),
  emergencyStop: () => post<CommandRecord>(dronePath(sn, '/flight/emergency-stop')),
  emergencyLanding: () => post<CommandRecord>(dronePath(sn, '/flight/emergency-landing')),
  forceLanding: () => post<CommandRecord>(dronePath(sn, '/flight/force-landing')),
  flyTo: (lat: number, lon: number, relativeHeight: number, maxSpeed: number) =>
    post<CommandRecord>(dronePath(sn, '/flight/fly-to'), { lat, lon, relativeHeight, maxSpeed }),
  stopFlyTo: () => post<CommandRecord>(dronePath(sn, '/flight/fly-to/stop')),
  poiEnter: (lat: number, lon: number, relativeHeight: number) => post<CommandRecord>(dronePath(sn, '/flight/poi/enter'), { lat, lon, relativeHeight }),
  poiExit: () => post<CommandRecord>(dronePath(sn, '/flight/poi/exit')),
  poiSpeed: (speed: number) => post<CommandRecord>(dronePath(sn, '/flight/poi/speed'), { speed }),
  photo: () => post<CommandRecord>(dronePath(sn, '/payload/photo')),
  recordStart: () => post<CommandRecord>(dronePath(sn, '/payload/recording/start')),
  recordStop: () => post<CommandRecord>(dronePath(sn, '/payload/recording/stop')),
  gimbalReset: (mode: number) => post<CommandRecord>(dronePath(sn, '/payload/gimbal/reset'), { mode }),
  zoom: (factor: number) => post<CommandRecord>(dronePath(sn, '/payload/zoom'), { factor, cameraType: 'zoom' }),
  heightLimit: (value: number) => api<CommandRecord>(dronePath(sn, '/height-limit'), { method: 'PUT', body: { value } }),
})

export const STATUS_TEXT: Record<CommandStatus, string> = {
  PENDING: t('等待飞手授权'),
  REJECTED: t('已拒绝（未发送）'),
  SENT: t('已发送，等待设备确认'),
  ACKED: t('设备已确认'),
  FAILED: t('失败'),
  TIMEOUT: t('超时：设备未确认'),
}
