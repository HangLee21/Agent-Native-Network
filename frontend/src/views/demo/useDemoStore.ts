/**
 * Demo page state: one snapshot on load (and after reconnects / resets), then the demo-* pushes.
 * Only the demo service's own model is used here (docs/demo-design.md §2), never the platform's raw messages.
 */
import { defineStore } from 'pinia'
import { computed, ref, shallowRef, triggerRef } from 'vue'
import { t } from '@/i18n'
import { telemetrySocket, type WsMessage } from '@/services/ws'
import { routesApi, type Route } from '@/api/routes'
import { distanceM } from './demoGeo'
import {
  demoApi,
  type Check,
  type DemoDrone,
  type DemoEvent,
  type DemoState,
  type Dog,
  type DronesFrame,
  type GeoCell,
  type Label,
  type Link,
  type Proximity,
  type TrackPoint,
} from './demoApi'

const MAX_EVENTS = 300
const MAX_TRACK = 6000

export const useDemoStore = defineStore('demo', () => {
  const state = ref<DemoState | null>(null)
  const drones = ref<DemoDrone[]>([])
  const link = ref<Link | null>(null)
  const proximity = ref<Proximity | null>(null)
  const tracks = shallowRef<Record<Label, TrackPoint[]>>({ A: [], B: [] })
  const events = ref<DemoEvent[]>([])
  const dog = ref<Dog | null>(null)
  const dogTrack = shallowRef<TrackPoint[]>([])
  /** All semantic-map cells, keyed by position; `cellsVersion` bumps on every change (the map is not deep-reactive). */
  const cells = new Map<string, GeoCell>()
  const cellsVersion = ref(0)
  const checks = ref<Check[]>([])
  const routes = ref<Record<string, Route>>({})
  const loaded = ref(false)
  const error = ref<string | null>(null)
  /** Time of the latest scripted message between two parties (drives the link animation). */
  const lastComm = ref<{ from: string; to: string; at: number } | null>(null)
  let started = false
  const offs: (() => void)[] = []

  const byLabel = computed(() => {
    const m: Partial<Record<Label, DemoDrone>> = {}
    for (const d of drones.value) if (d.label) m[d.label] = d
    return m
  })

  function cellKey(c: GeoCell): string {
    return `${Math.round(c.lat * 1e6)}:${Math.round(c.lon * 1e6)}`
  }

  function addCells(list: GeoCell[]): void {
    if (!list.length) return
    for (const c of list) cells.set(cellKey(c), c)
    cellsVersion.value++
  }

  async function refresh(): Promise<void> {
    try {
      const s = await demoApi.snapshot()
      state.value = s.state
      applyFrame(s.drones, false)
      tracks.value = { A: [...(s.tracks.A ?? [])], B: [...(s.tracks.B ?? [])] }
      events.value = s.events
      dog.value = s.dog.dog
      dogTrack.value = [...s.dog.track]
      cells.clear()
      addCells(s.dog.cells)
      cellsVersion.value++
      checks.value = s.checks
      loaded.value = true
      error.value = null
      void loadRoutes()
    } catch (e) {
      error.value = e instanceof Error ? e.message : t('无法读取演示状态')
    }
  }

  async function refreshChecks(): Promise<void> {
    try {
      checks.value = await demoApi.checks()
    } catch {
      /* shown by the next refresh */
    }
  }

  async function loadRoutes(): Promise<void> {
    const ids = Object.values(state.value?.routes ?? {}).filter((x): x is string => !!x)
    for (const id of ids) {
      if (routes.value[id]) continue
      try {
        const r = await routesApi.get(id)
        routes.value = { ...routes.value, [id]: r }
      } catch {
        /* deleted route: the console's checks say so */
      }
    }
  }

  function running(): boolean {
    const s = state.value?.stage
    return !!s && s !== 'READY' && s !== 'DONE' && s !== 'ABORTED'
  }

  function applyFrame(f: DronesFrame, append: boolean): void {
    drones.value = f.drones
    link.value = f.link
    proximity.value = f.proximity ?? null
    if (!append || !running()) return
    let changed = false
    const next = { ...tracks.value }
    for (const d of f.drones) {
      if (!d.label || d.lat == null || d.lon == null || d.phase === 'GROUND') continue
      const tr = next[d.label]
      const last = tr[tr.length - 1]
      if (!last || distanceM(last, { lat: d.lat, lon: d.lon }) > 1) {
        next[d.label] = [...tr.slice(-MAX_TRACK + 1), { lat: d.lat, lon: d.lon, h: d.relativeHeight ?? 0, t: Date.now() }]
        changed = true
      }
    }
    if (changed) tracks.value = next
  }

  function on(type: string, fn: (msg: WsMessage) => void): void {
    offs.push(telemetrySocket.on(type, fn))
  }

  function start(): void {
    if (started) return
    started = true
    telemetrySocket.start()
    on('demo-state', (m) => {
      const prev = state.value?.stage
      state.value = m.data as DemoState
      void loadRoutes()
      if (state.value.stage === 'READY' && prev !== 'READY') void refreshChecks()
    })
    on('demo-drones', (m) => applyFrame(m.data as DronesFrame, true))
    on('demo-event', (m) => {
      const e = m.data as DemoEvent
      events.value = [...events.value.slice(-MAX_EVENTS + 1), e]
      if (e.kind === 'COMM' || e.kind === 'COMMAND') lastComm.value = { from: e.from ?? '', to: e.to ?? '', at: Date.now() }
    })
    on('demo-dog', (m) => {
      const d = m.data as { dog: Dog; cells: GeoCell[] }
      dog.value = d.dog
      addCells(d.cells)
      if (d.dog.lat != null && d.dog.lon != null) {
        const tr = dogTrack.value
        const last = tr[tr.length - 1]
        const p = { lat: d.dog.lat, lon: d.dog.lon }
        if (!last || distanceM(last, p) > 0.5) {
          tr.push({ ...p, h: 0, t: Date.now() })
          if (tr.length > MAX_TRACK) tr.shift()
          triggerRef(dogTrack)
        }
      }
    })
    on('demo-reset', () => {
      tracks.value = { A: [], B: [] }
      events.value = []
      dogTrack.value = []
      cells.clear()
      cellsVersion.value++
      lastComm.value = null
    })
    offs.push(telemetrySocket.onStatus((up) => up && void refresh()))
    void refresh()
  }

  function stop(): void {
    offs.splice(0).forEach((f) => f())
    started = false
  }

  return {
    state, drones, link, proximity, tracks, events, dog, dogTrack, cells, cellsVersion, checks, routes, loaded, error, lastComm,
    byLabel, start, stop, refresh, refreshChecks, loadRoutes,
  }
})
