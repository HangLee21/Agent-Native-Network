import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { dronesApi, type DeviceUpdate, type DeviceView, type FleetSafetyConfig, type ProximityPair } from '@/api/drones'
import { telemetrySocket } from '@/services/ws'
import { startDroneStores } from './droneStores'

const SELECTED_KEY = 'uav.selectedDrone'

function stored(): string | null {
  try {
    return localStorage.getItem(SELECTED_KEY)
  } catch {
    return null
  }
}

/**
 * The drones known to the platform and the one the operator works on (D-28, D-31, R-28). Every known drone's
 * stores are started, so the fleet cards and the map follow all of them; the page panels follow the selected one.
 * Also holds the platform-level two-drone state: proximity pairs and the two-drone safety settings (D-30).
 */
export const useFleetStore = defineStore('fleet', () => {
  const drones = ref<DeviceView[]>([])
  const selectedSn = ref<string | null>(stored())
  const ready = ref(false)
  const proximity = ref<ProximityPair[]>([])
  const safety = ref<FleetSafetyConfig | null>(null)
  let started = false

  const enabled = computed(() => drones.value.filter((d) => d.enabled))
  const selected = computed(() => drones.value.find((d) => d.gatewaySn === selectedSn.value) ?? null)
  const pending = computed(() => drones.value.filter((d) => !d.enabled))

  function byGateway(sn: string | null | undefined): DeviceView | undefined {
    return sn ? drones.value.find((d) => d.gatewaySn === sn || d.droneSn === sn) : undefined
  }
  const label = (sn: string | null | undefined) => byGateway(sn)?.label ?? sn ?? '—'
  const color = (sn: string | null | undefined) => byGateway(sn)?.color ?? 'var(--accent)'

  function select(sn: string): void {
    selectedSn.value = sn
    try {
      localStorage.setItem(SELECTED_KEY, sn)
    } catch {
      /* storage unavailable */
    }
  }

  /** Keeps a valid selection: an enabled drone, online ones first. */
  function ensureSelection(): void {
    const cur = drones.value.find((d) => d.gatewaySn === selectedSn.value)
    if (cur && cur.enabled) return
    const pick = enabled.value.find((d) => d.online) ?? enabled.value[0] ?? drones.value[0]
    if (pick) select(pick.gatewaySn)
    else selectedSn.value = null
  }

  function apply(list: DeviceView[]): void {
    drones.value = list
    ensureSelection()
    for (const d of list) startDroneStores(d.gatewaySn)
  }

  async function load(): Promise<void> {
    try {
      apply(await dronesApi.list())
      safety.value = await dronesApi.fleetSafety()
      proximity.value = await dronesApi.proximity()
    } catch {
      /* backend unreachable: the status bar shows it */
    } finally {
      ready.value = true
    }
  }

  async function update(sn: string, u: DeviceUpdate): Promise<DeviceView> {
    const v = await dronesApi.update(sn, u)
    drones.value = drones.value.map((d) => (d.gatewaySn === v.gatewaySn ? v : d))
    ensureSelection()
    return v
  }

  async function updateSafety(u: Partial<FleetSafetyConfig>): Promise<FleetSafetyConfig> {
    safety.value = await dronesApi.updateFleetSafety(u)
    return safety.value
  }

  function onProximity(p: ProximityPair): void {
    const key = `${p.a}|${p.b}`
    const rest = proximity.value.filter((x) => `${x.a}|${x.b}` !== key)
    proximity.value = p.active ? [...rest, p] : rest
  }

  /** The pair (if any) involving this drone (aircraft or RC SN). */
  function proximityOf(sn: string | null | undefined): ProximityPair | undefined {
    const d = byGateway(sn)
    return d ? proximity.value.find((p) => p.a === d.droneSn || p.b === d.droneSn) : undefined
  }

  function start(): Promise<void> {
    if (started) return Promise.resolve()
    started = true
    telemetrySocket.on('drones', (m) => apply(m.data as DeviceView[]))
    telemetrySocket.on('proximity', (m) => onProximity(m.data as ProximityPair))
    telemetrySocket.on('fleet-safety-config', (m) => (safety.value = m.data as FleetSafetyConfig))
    telemetrySocket.onStatus((c) => c && void load())
    telemetrySocket.start()
    return load()
  }

  return { drones, selectedSn, ready, proximity, safety, enabled, selected, pending, byGateway, label, color, select, apply,
    load, update, updateSafety, onProximity, proximityOf, start }
})
