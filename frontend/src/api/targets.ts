/** Target selection and fly-to (R-24 ~ R-27 draft, D-21 ~ D-24). */
import { api } from './http'
import { dronePath } from './drone'
import { t } from '@/i18n'

export type TargetInput = 'TAP' | 'CIRCLE' | 'AI_BOX' | 'MAP' | 'MODEL_3D' | 'AI_GEO'
export type TargetState = 'PROPOSED' | 'MEASURING' | 'MEASURED' | 'FAILED' | 'CONFIRMED' | 'ACTIVE' | 'DONE' | 'ABORTED' | 'CANCELLED' | 'EXPIRED'
export type TargetAction = 'LOOK' | 'APPROACH' | 'ABOVE' | 'ORBIT' | 'MARK' | 'CLIMB' | 'BACK'
export type LaserReference = 'UNKNOWN' | 'ELLIPSOID' | 'MSL'

export interface TargetPoint {
  lat: number
  lon: number
  ellipsoidHeight: number | null
  relativeHeight: number | null
}

export interface TargetView {
  id: string
  createdAt: number
  updatedAt: number
  source: string
  label: string | null
  confidence: number | null
  input: TargetInput
  image: { lens: string; x: number; y: number; w: number; h: number; frameTimestamp: number | null } | null
  state: TargetState
  method: 'LASER' | 'MAP' | 'MODEL_3D' | 'GIVEN' | null
  lat: number | null
  lon: number | null
  ellipsoidHeight: number | null
  relativeHeight: number | null
  distance: number | null
  accuracyM: number | null
  laserState: string | null
  rawAltitude: number | null
  altitudeReference: string | null
  geoidOffsetM: number | null
  lowConfidence: boolean
  zoomAtSelect: number | null
  message: string | null
  warnings: string[]
  action: TargetAction | null
  suggestedAction: TargetAction | null
  stopPoint: TargetPoint | null
  backPoint: TargetPoint | null
  commandId: string | null
  check: { expectedDistance: number; measuredDistance: number | null; inView: boolean | null; at: number } | null
  expiresAt: number | null
}

export interface TargetConfig {
  laserFlyToEnabled: boolean
  laserAltitudeReference: LaserReference
  geoidOffsetM: number
  minDistanceM: number
  stopDistanceM: number
  clearanceM: number
  maxLaserRangeM: number
  maxAccuracyM: number
  approachSpeed: number
  aboveHeightM: number
  aiLookLevel: number
  aiApproachLevel: number
  aiAboveLevel: number
  aiOrbitLevel: number
  aiMinConfidence: number
  aiMaxMoveM: number
  aiStopDistanceM: number
  aiExtraHeightM: number
  aiMaxAccuracyM: number
  aiCooldownS: number
  aiMaxPerMinute: number
  aiCountdownS: number
  aiForbiddenMoveLabels: string[]
  aiAllowedMoveLabels: string[]
  aiWorkArea: [number, number][]
  updatedAt: number
}

export type TargetConfigUpdate = Partial<Omit<TargetConfig, 'aiForbiddenMoveLabels' | 'aiAllowedMoveLabels' | 'updatedAt'>> & {
  aiForbiddenMoveLabels?: string
  aiAllowedMoveLabels?: string
}

export interface AiCountdown {
  targetId: string
  action: TargetAction
  deadline: number
  label: string
}

export interface AiStatus {
  on: boolean
  since: number | null
  by: string | null
  offReason: string | null
  lookLevel: number
  approachLevel: number
  aboveLevel: number
  orbitLevel: number
  countdown: AiCountdown | null
  actionsLastMinute: number
  lastActionAt: number | null
}

export interface LaserReading {
  distance: number | null
  state: string
  lat: number | null
  lon: number | null
  altitude: number | null
  at?: number
  receivedAt?: number
}

export interface ActionResult {
  target: TargetView
  decision: 'MOVE' | 'STAY' | 'CLIMB_ONLY' | 'LOOK' | 'MARKED' | 'STOPPED'
  message: string
  commandId: string | null
}

export interface TargetsSnapshot {
  targets: TargetView[]
  active: TargetView | null
  laser: LaserReading | null
  config: TargetConfig
  ai: AiStatus
}

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const targetsApi = (sn: string) => ({
  list: () => api<TargetsSnapshot>(dronePath(sn, '/targets')),
  select: (input: 'TAP' | 'CIRCLE', lens: string, x: number, y: number, width = 0, height = 0) =>
    api<TargetView>(dronePath(sn, '/targets/select'), { method: 'POST', body: { input, lens, x, y, width, height, frameTimestamp: Date.now() } }),
  geo: (lat: number, lon: number, height: number, heightRef: 'RELATIVE' | 'ELLIPSOID' | 'MSL', input: 'MAP' | 'MODEL_3D' = 'MAP', look = true) =>
    api<TargetView>(dronePath(sn, '/targets/geo'), { method: 'POST', body: { input, lat, lon, height, heightRef, look } }),
  act: (id: string, action: TargetAction, extra: { photo?: boolean } = {}) =>
    api<ActionResult>(dronePath(sn, `/targets/${id}/actions`), { method: 'POST', body: { action, ...extra } }),
  stop: () => api<ActionResult>(dronePath(sn, '/targets/active/stop'), { method: 'POST' }),
  remeasure: (id: string) => api<TargetView>(dronePath(sn, `/targets/${id}/remeasure`), { method: 'POST' }),
  accept: (id: string) => api<TargetView>(dronePath(sn, `/targets/${id}/accept`), { method: 'POST' }),
  cancel: (id: string) => api<TargetView>(dronePath(sn, `/targets/${id}`), { method: 'DELETE' }),
  clearFinished: () => api<{ removed: number }>(dronePath(sn, '/targets/clear-finished'), { method: 'POST' }),
  aiOn: () => api<AiStatus>(dronePath(sn, '/targets/ai/on'), { method: 'POST' }),
  aiOff: () => api<AiStatus>(dronePath(sn, '/targets/ai/off'), { method: 'POST' }),
  aiStop: () => api<AiStatus>(dronePath(sn, '/targets/ai/stop'), { method: 'POST' }),
  cancelCountdown: () => api<AiStatus>(dronePath(sn, '/targets/ai/countdown/cancel'), { method: 'POST' }),
})

/** Platform-level target settings (shared by every drone). */
export const targetConfigApi = {
  config: () => api<TargetConfig>('/api/v1/targets/config'),
  updateConfig: (u: TargetConfigUpdate) => api<TargetConfig>('/api/v1/targets/config', { method: 'PUT', body: u }),
}

export const ACTION_LABELS: Record<TargetAction, string> = {
  LOOK: t('看向'),
  APPROACH: t('接近'),
  ABOVE: t('飞到上方'),
  ORBIT: t('环绕'),
  MARK: t('标记'),
  CLIMB: t('原地爬升'),
  BACK: t('返回原位置'),
}

export const STATE_LABELS: Record<TargetState, string> = {
  PROPOSED: t('AI 建议'),
  MEASURING: t('测距中'),
  MEASURED: t('已测得'),
  FAILED: t('失败'),
  CONFIRMED: t('执行中'),
  ACTIVE: t('飞行中'),
  DONE: t('完成'),
  ABORTED: t('已中止'),
  CANCELLED: t('已取消'),
  EXPIRED: t('已过期'),
}

export const LASER_LABELS: Record<string, string> = {
  NORMAL: t('正常'),
  UNREPORTED: t('正常（未报告状态）'),
  TOO_CLOSE: t('太近'),
  TOO_FAR: t('太远'),
  NO_SIGNAL: t('无回波'),
  NO_DATA: t('无数据'),
}
