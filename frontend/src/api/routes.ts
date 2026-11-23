import { api } from './http'
import { t } from '@/i18n'

export type HeadingMode = 'FOLLOW_WAYLINE' | 'MANUAL' | 'FIXED'
export type TurnMode = 'STOP' | 'COORDINATED' | 'CURVED_PASS'
export type ActionType = 'TAKE_PHOTO' | 'START_RECORD' | 'STOP_RECORD' | 'ZOOM' | 'GIMBAL_PITCH'
export type FinishAction = 'RETURN_HOME' | 'HOVER' | 'LAND'
export type RcLostAction = 'RETURN_HOME' | 'HOVER' | 'LAND'
export type RouteSource = 'MANUAL' | 'API' | 'FILE' | 'HISTORY'

export interface WaypointAction {
  type: ActionType
  value: number | null
}

export interface Waypoint {
  lat: number
  lon: number
  relativeHeight: number
  speed: number | null
  hoverSeconds: number
  gimbalPitch: number | null
  headingMode: HeadingMode
  turnMode: TurnMode
  actions: WaypointAction[]
  /** Platform execution only: hover here until the operator resumes ("继续航线"). Routes saved before 2026-11-04 lack it. */
  waitForConfirm?: boolean
}

export interface Route {
  id: string
  name: string
  description: string | null
  source: RouteSource
  defaultSpeed: number
  defaultHeight: number
  takeoffSecurityHeight: number
  rthHeight: number
  /** true: the backend sets rthHeight to the last waypoint's height on every save. */
  rthHeightAuto: boolean
  finishAction: FinishAction
  rcLostAction: RcLostAction
  waypoints: Waypoint[]
  version: number
  createdAt: number
  updatedAt: number
}

export type RouteRequest = Omit<Route, 'id' | 'source' | 'version' | 'createdAt' | 'updatedAt'>

export interface SyncInfo {
  synced: boolean
  syncedVersion: number | null
  syncedAt: number | null
  waylineName: string | null
}

export interface RouteSummary {
  id: string
  name: string
  source: RouteSource
  waypointCount: number
  lengthMeters: number
  maxHeight: number
  minHeight: number
  version: number
  updatedAt: number
  sync: SyncInfo
}

export const SOURCE_LABELS: Record<RouteSource, string> = { MANUAL: t('手绘'), API: t('接口'), FILE: t('文件'), HISTORY: t('飞行记录') }
export const FINISH_LABELS: Record<FinishAction, string> = { RETURN_HOME: t('返航'), HOVER: t('悬停'), LAND: t('原地降落') }
export const RC_LOST_LABELS: Record<RcLostAction, string> = { RETURN_HOME: t('返航'), HOVER: t('悬停'), LAND: t('降落') }

export const routesApi = {
  list: () => api<RouteSummary[]>('/api/v1/routes'),
  get: (id: string) => api<Route>(`/api/v1/routes/${id}`),
  create: (r: RouteRequest) => api<Route>('/api/v1/routes', { method: 'POST', body: r }),
  update: (id: string, r: RouteRequest) => api<Route>(`/api/v1/routes/${id}`, { method: 'PUT', body: r }),
  duplicate: (id: string) => api<Route>(`/api/v1/routes/${id}/duplicate`, { method: 'POST' }),
  remove: (id: string) => api<void>(`/api/v1/routes/${id}`, { method: 'DELETE' }),
}
