import { api } from './http'

/** One drone known to the platform (GET /api/v1/drones, D-28 / D-29); gatewaySn is the stable key. */
export interface DeviceView {
  droneSn: string | null
  gatewaySn: string
  label: string
  color: string
  online: boolean
  droneOnline: boolean
  enabled: boolean
  model: string | null
  firstSeenAt: number
  lastSeenAt: number | null
  simulated: boolean
}

export interface DeviceUpdate {
  label?: string
  color?: string
  enabled?: boolean
}

export type ProximityMode = 'HOLD' | 'WARN_ONLY'

/** Two-drone safety settings (D-30, S-05, S-06). */
export interface FleetSafetyConfig {
  proximityMode: ProximityMode
  proximityBaseM: number
  proximityReactionS: number
  proximityLookaheadS: number
  proximityVerticalM: number
  rthSeparationM: number
  updatedAt: number
}

/** A pair of drones judged close (WS "proximity", GET /api/v1/proximity). */
export interface ProximityPair {
  a: string | null
  b: string | null
  aLabel: string
  bLabel: string
  horizontalM: number
  verticalM: number | null
  closingSpeedMps: number
  predictedMinM: number
  thresholdM: number
  level: 'warning' | 'hold' | 'clear'
  /** Stopped by the platform and measured hovering. */
  stopped: string[]
  /** Stopped by the platform but still measured moving (the stop is sent again). */
  stopping?: string[]
  /** Drones out of contact for staleSeconds: judged from where they were last seen. */
  stale?: string[]
  staleSeconds?: number
  active: boolean
  since: number
}

export const dronesApi = {
  list: () => api<DeviceView[]>('/api/v1/drones'),
  update: (sn: string, u: DeviceUpdate) => api<DeviceView>(`/api/v1/drones/${encodeURIComponent(sn)}`, { method: 'PATCH', body: u }),
  fleetSafety: () => api<FleetSafetyConfig>('/api/v1/safety/fleet'),
  updateFleetSafety: (u: Partial<FleetSafetyConfig>) => api<FleetSafetyConfig>('/api/v1/safety/fleet', { method: 'PUT', body: u }),
  proximity: () => api<ProximityPair[]>('/api/v1/proximity'),
}
