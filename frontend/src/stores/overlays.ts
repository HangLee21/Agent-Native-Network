import { defineStore } from 'pinia'
import { perDrone } from './perDrone'
import { ref } from 'vue'
import { api } from '@/api/http'
import { dronePath } from '@/api/drone'
import { telemetrySocket } from '@/services/ws'
import type { LatLon } from '@/utils/coord'

export interface PathPoint {
  lat: number
  lon: number
  ellipsoidHeight: number
}

export interface Overlay {
  kind: string
  data: unknown
  updatedAt: number
}

export interface TargetOverlay {
  lat: number
  lon: number
  relativeHeight: number
  label: string
}

export interface PoiOverlay extends TargetOverlay {
  radius: number | null
  status: string
}

/** One drone's map overlays that are not plain telemetry (R-03): device paths, target, POI and its executing route. */
export const useOverlaysStore = perDrone('overlays', (sn) => {
  const items = ref<Record<string, Overlay>>({})
  /** This drone's executing route, shown read-only on maps (editor has its own interactive layer). */
  const route = ref<LatLon[] | null>(null)
  let started = false

  function apply(o: Overlay): void {
    const next = { ...items.value }
    if (o.data === null || o.data === undefined) delete next[o.kind]
    else next[o.kind] = o
    items.value = next
  }

  async function load(): Promise<void> {
    try {
      items.value = await api<Record<string, Overlay>>(dronePath(sn, '/map/overlays'))
    } catch {
      /* keep previous */
    }
  }

  function start(): void {
    if (started || !sn) return
    started = true
    telemetrySocket.onDrone('overlay', sn, (m) => apply(m.data as Overlay))
    telemetrySocket.onStatus((c) => c && void load())
    void load()
  }

  function path(kind: string): PathPoint[] {
    const d = items.value[kind]?.data
    return Array.isArray(d) ? (d as PathPoint[]) : []
  }

  function target(): TargetOverlay | null {
    return (items.value.target?.data as TargetOverlay | undefined) ?? null
  }

  function poi(): PoiOverlay | null {
    return (items.value.poi?.data as PoiOverlay | undefined) ?? null
  }

  return { sn, items, route, apply, load, start, path, target, poi }
})

/** Platform-level map overlays (not tied to a drone): the safe zone and a route previewed from the library. */
export const useMapOverlaysStore = defineStore('mapOverlays', () => {
  const safeZone = ref<LatLon[] | null>(null)
  const preview = ref<LatLon[] | null>(null)
  return { safeZone, preview }
})
