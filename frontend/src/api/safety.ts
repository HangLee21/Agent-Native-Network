import { api } from './http'
import type { RouteRequest } from './routes'

export interface Violation {
  code: string
  message: string
  waypointIndex: number | null
}

export interface SafetyCheckResult {
  passed: boolean
  violations: Violation[]
}

export type HeightPolicy = 'DUAL_CHECK' | 'ASSUME_INFERRED'

export interface SafetyConfig {
  maxHeight: number
  minHeight: number
  maxSpeed: number
  minTakeoffBattery: number
  safeZoneEnabled: boolean
  /** [[lat, lon], ...] WGS84 */
  safeZone: [number, number][]
  unknownHeightPolicy: HeightPolicy
  updatedAt: number
}

export const safetyApi = {
  config: () => api<SafetyConfig>('/api/v1/safety/config'),
  update: (c: Partial<SafetyConfig>) => api<SafetyConfig>('/api/v1/safety/config', { method: 'PUT', body: c }),
  checkRoute: (r: RouteRequest) => api<SafetyCheckResult>('/api/v1/safety/check-route', { method: 'POST', body: r }),
}

/**
 * Extracts safety violations from a 422 error: accepts the SafetyCheckResult itself or the whole response
 * body ({message, details: SafetyCheckResult}), which is what ApiError.details carries.
 */
export function violationsOf(details: unknown): Violation[] {
  const d = details as (SafetyCheckResult & { details?: SafetyCheckResult | null }) | null
  if (d && Array.isArray(d.violations)) return d.violations
  if (d?.details && Array.isArray(d.details.violations)) return d.details.violations
  return []
}
