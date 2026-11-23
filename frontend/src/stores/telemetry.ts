import { perDrone } from './perDrone'
import { computed, ref, watch } from 'vue'
import { api } from '@/api/http'
import { dronePath } from '@/api/drone'
import type { DroneState, DroneTelemetry, GatewayInfo, RcTelemetry, TrackPoint } from '@/api/types'
import type { LatLon } from '@/utils/coord'
import { telemetrySocket } from '@/services/ws'

/** Link considered lost when no OSD for this long (normal OSD is 0.5 Hz per the docs). */
export const LINK_TIMEOUT_MS = 6000

export const useTelemetryStore = perDrone('telemetry', (sn) => {
  const drone = ref<DroneTelemetry | null>(null)
  const rc = ref<RcTelemetry | null>(null)
  const gateway = ref<GatewayInfo | null>(null)
  const track = ref<TrackPoint[]>([])
  const lastUpdateAt = ref(0)
  const wsConnected = ref(false)
  const now = ref(Date.now())
  let started = false
  let clock: number | undefined

  const linkFresh = computed(() => lastUpdateAt.value > 0 && now.value - lastUpdateAt.value < LINK_TIMEOUT_MS)
  const online = computed(() => !!gateway.value?.droneOnline && linkFresh.value)
  const airborne = computed(() => {
    const m = drone.value?.modeCode
    return m !== null && m !== undefined && m !== 0 && m !== 14
  })
  /** Telemetry without a position: no satellites yet (the backend drops the 0/0 the drone reports then). */
  const locating = computed(() => !!drone.value && (drone.value.lat == null || drone.value.lon == null))
  /** Last position the drone really had; the map keeps it while the drone is locating. */
  const lastFix = ref<LatLon | null>(null)
  watch(
    () => [drone.value?.lat, drone.value?.lon] as const,
    ([lat, lon]) => {
      if (lat != null && lon != null) lastFix.value = { lat, lon }
    },
    { flush: 'sync' },
  )
  const position = computed(() =>
    drone.value?.lat != null && drone.value?.lon != null ? { lat: drone.value.lat, lon: drone.value.lon } : lastFix.value,
  )
  const home = computed(() =>
    drone.value?.homeLat != null && drone.value?.homeLon != null ? { lat: drone.value.homeLat, lon: drone.value.homeLon } : null,
  )

  function applyTelemetry(t: DroneTelemetry): void {
    const prevMode = drone.value?.modeCode
    if (t.highFrequency && drone.value) {
      // DRC push only carries a subset; keep the last full snapshot for the other fields.
      drone.value = { ...drone.value, lat: t.lat, lon: t.lon, attitudeHead: t.attitudeHead, horizontalSpeed: t.horizontalSpeed,
        gimbalPitch: t.gimbalPitch, gimbalRoll: t.gimbalRoll, gimbalYaw: t.gimbalYaw, raw: { ...drone.value.raw, drc_height: t.raw.drc_height } }
    } else {
      drone.value = t
    }
    lastUpdateAt.value = Date.now()
    if (prevMode === 0 && t.modeCode !== 0) track.value = []
    if (airborne.value && t.lat != null && t.lon != null) {
      const last = track.value[track.value.length - 1]
      if (!last || last.lat !== t.lat || last.lon !== t.lon) {
        track.value.push({ lat: t.lat, lon: t.lon, relativeHeight: drone.value?.relativeHeight ?? 0, ts: t.timestamp })
        if (track.value.length > 20000) track.value.splice(0, track.value.length - 20000)
      }
    }
  }

  async function load(): Promise<void> {
    try {
      const s = await api<DroneState>(dronePath(sn, '/state'))
      gateway.value = s.gateway
      rc.value = s.rc
      if (s.telemetry) {
        drone.value = s.telemetry
        // Server-side freshness: convert the server's last OSD time into local time.
        if (s.lastTelemetryAt > 0) lastUpdateAt.value = Date.now() - (s.serverTime - s.lastTelemetryAt)
      }
      track.value = await api<TrackPoint[]>(dronePath(sn, '/track'))
    } catch {
      /* backend unreachable: status bar shows it */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('telemetry', sn, (m) => applyTelemetry(m.data as DroneTelemetry))
    telemetrySocket.onDrone('rc', sn, (m) => (rc.value = m.data as RcTelemetry))
    telemetrySocket.onDrone('topology', sn, (m) => (gateway.value = m.data as GatewayInfo))
    telemetrySocket.onStatus((c) => {
      wsConnected.value = c
      if (c) void load()
    })
    clock = window.setInterval(() => (now.value = Date.now()), 1000)
    void load()
  }

  function stop(): void {
    window.clearInterval(clock)
    started = false
  }

  return { sn, drone, rc, gateway, track, lastUpdateAt, wsConnected, now, linkFresh, online, airborne, locating, position, home,
    applyTelemetry, load, start, stop }
})
