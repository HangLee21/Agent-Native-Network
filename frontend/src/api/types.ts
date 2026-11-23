/** DTOs mirroring the backend (com.uavplatform.*). */
export interface DroneTelemetry {
  sn: string
  timestamp: number
  lat: number | null
  lon: number | null
  ellipsoidHeight: number | null
  relativeHeight: number | null
  horizontalSpeed: number | null
  verticalSpeed: number | null
  attitudePitch: number | null
  attitudeRoll: number | null
  attitudeHead: number | null
  gimbalPitch: number | null
  gimbalRoll: number | null
  gimbalYaw: number | null
  zoomFactor: number | null
  batteryPercent: number | null
  remainFlightTime: number | null
  returnHomePower: number | null
  landingPower: number | null
  modeCode: number | null
  gear: number | null
  homeLat: number | null
  homeLon: number | null
  homeDistance: number | null
  heightLimit: number | null
  nearHeightLimit: boolean | null
  nearAreaLimit: boolean | null
  gpsNumber: number | null
  rtkNumber: number | null
  windSpeed: number | null
  windDirection: number | null
  controlSource: string | null
  trackId: string | null
  highFrequency: boolean
  raw: Record<string, unknown>
}

export interface RcTelemetry {
  sn: string
  timestamp: number
  lat: number | null
  lon: number | null
  ellipsoidHeight: number | null
  batteryPercent: number | null
  drcState: number | null
  raw: Record<string, unknown>
}

export interface GatewayInfo {
  mode: string
  gatewaySn: string
  droneSn: string
  gatewayOnline: boolean
  droneOnline: boolean
  droneModel: string | null
  rcModel: string | null
}

export interface DroneState {
  gateway: GatewayInfo
  telemetry: DroneTelemetry | null
  rc: RcTelemetry | null
  lastTelemetryAt: number
  serverTime: number
}

export interface TrackPoint {
  lat: number
  lon: number
  relativeHeight: number
  ts: number
}
