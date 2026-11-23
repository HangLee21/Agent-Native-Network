import { api } from './http'
import { dronePath } from './drone'
import { config } from '@/config/runtime'
import { t } from '@/i18n'

export type ExecState = 'PREPARING' | 'ACQUIRING_CONTROL' | 'TAKING_OFF' | 'FLYING' | 'AT_WAYPOINT' | 'PAUSED' | 'FINISHING' | 'COMPLETED' | 'FAILED' | 'ABORTED'
export type ExecMode = 'STOP_AND_GO' | 'CONTINUOUS_UPDATE'

export interface ExecLog {
  ts: number
  level: 'INFO' | 'WARN'
  text: string
}

export interface ExecutionSnapshot {
  id: string
  routeId: string
  routeName: string
  routeVersion: number
  mode: ExecMode
  state: ExecState
  /**
   * PROXIMITY: paused because two drones came too close (S-05); WAYPOINT_CONFIRM: hovering at a waypoint set to wait for
   * the operator (2026-11-04). Both are resumed only by the operator.
   */
  pauseReason?: string | null
  currentIndex: number
  total: number
  waypoints: { lat: number; lon: number; relativeHeight: number }[]
  reachedCount: number
  message: string
  startedAt: number
  endedAt: number | null
  log: ExecLog[]
  /** Grows with every change of the execution: a reply with a lower one is older than the last push. */
  version?: number
  active: boolean
}

export interface SyncResult {
  routeId: string
  waylineName: string
  routeVersion: number
  syncedAt: number
  warnings: string[]
  sizeBytes: number
}

export const STATE_TEXT: Record<ExecState, string> = {
  PREPARING: t('准备中'),
  ACQUIRING_CONTROL: t('等待飞手授权'),
  TAKING_OFF: t('起飞中'),
  FLYING: t('飞行中'),
  AT_WAYPOINT: t('到达航点'),
  PAUSED: t('已暂停（悬停）'),
  FINISHING: t('执行结束动作'),
  COMPLETED: t('已完成'),
  FAILED: t('失败'),
  ABORTED: t('已中止'),
}

/** Per-drone endpoints (D-29): sn is the RC serial number. */
export const executionApi = (sn: string) => ({
  execute: (routeId: string, mode?: ExecMode, rthConfirmed?: boolean) =>
    api<ExecutionSnapshot>(dronePath(sn, `/routes/${routeId}/execute`), { method: 'POST', body: { ...(mode ? { mode } : {}), ...(rthConfirmed ? { rthConfirmed } : {}) } }),
  current: () => api<ExecutionSnapshot | null>(dronePath(sn, '/executions/current')),
  abort: () => api<ExecutionSnapshot>(dronePath(sn, '/executions/current/abort'), { method: 'POST' }),
  /** After a two-drone proximity pause (S-05): flies the paused leg again; refused (409) while still too close. */
  resume: () => api<ExecutionSnapshot>(dronePath(sn, '/executions/current/resume'), { method: 'POST' }),
})

/** Platform-level: the wayline library is shared by every RC (R-31). */
export const syncApi = {
  sync: (routeId: string) => api<SyncResult>(`/api/v1/routes/${routeId}/sync`, { method: 'POST' }),
  kmzUrl: (routeId: string) => `${config().apiBaseUrl}/api/v1/routes/${routeId}/kmz`,
}
