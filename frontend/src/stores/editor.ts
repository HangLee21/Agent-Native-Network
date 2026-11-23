import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { routesApi, type Route, type RouteRequest, type Waypoint } from '@/api/routes'
import type { LatLon } from '@/utils/coord'
import { distance, pathLength } from '@/utils/geo'

export interface Draft extends RouteRequest {
  id: string | null
  version: number | null
}

export function emptyDraft(): Draft {
  return {
    id: null,
    version: null,
    name: '',
    description: null,
    defaultSpeed: 8,
    defaultHeight: 60,
    takeoffSecurityHeight: 30,
    rthHeight: 80,
    // new routes return at the height they end at; the backend keeps rthHeight in step on every save
    rthHeightAuto: true,
    finishAction: 'RETURN_HOME',
    rcLostAction: 'RETURN_HOME',
    waypoints: [],
  }
}

/** 1e-7 degrees ≈ 1 cm: enough precision for waypoints, keeps forms readable. */
export function round7(v: number): number {
  return Math.round(v * 1e7) / 1e7
}

export function newWaypoint(p: LatLon, height: number): Waypoint {
  return { lat: round7(p.lat), lon: round7(p.lon), relativeHeight: height, speed: null, hoverSeconds: 0, gimbalPitch: null,
    headingMode: 'FOLLOW_WAYLINE', turnMode: 'STOP', actions: [], waitForConfirm: false }
}

function copyWaypoint(w: Waypoint): Waypoint {
  return { ...w, actions: w.actions.map((a) => ({ ...a })), waitForConfirm: w.waitForConfirm ?? false }
}

/** Options of "接上另一条航线" (copied in, not linked: later edits of that route do not follow). */
export interface ChainOptions {
  /** Hover at this route's last waypoint before leaving it (s). */
  leaveHover: number
  /** Hover at the other route's first waypoint on arrival (s). */
  arriveHover: number
  /** Wait for the operator at the other route's first waypoint (platform execution only). */
  arriveWait: boolean
  /** Heights differ: add a point so the leg between the routes is flown level at the higher height. */
  levelTransit: boolean
}

/** Below this height difference no transit point is added (the leg is nearly level anyway). */
export const TRANSIT_MIN_DIFF_M = 2

export interface ChainResult {
  /** Index of the first waypoint added (a transit point, if one was added). */
  from: number
  to: number
  transit: boolean
}

/**
 * Route editor state (R-06): select points on the map, edit waypoint properties, save (R-07). Waypoints can be
 * checked for batch edits: editing a field of a checked waypoint changes every checked one.
 */
export const useEditorStore = defineStore('editor', () => {
  const draft = ref<Draft | null>(null)
  const selected = ref<number | null>(null)
  /** Checked waypoints (sorted indices) for batch edits. */
  const checked = ref<number[]>([])
  /** Anchor of a shift-click range. */
  let anchor: number | null = null
  const dirty = ref(false)
  const saving = ref(false)

  const editing = computed(() => draft.value !== null)
  const points = computed<LatLon[]>(() => draft.value?.waypoints.map((w) => ({ lat: w.lat, lon: w.lon })) ?? [])
  const length = computed(() => pathLength(points.value))
  const maxHeight = computed(() => Math.max(0, ...(draft.value?.waypoints.map((w) => w.relativeHeight) ?? [0])))
  /** The return height that will be saved: the last waypoint's when automatic. */
  const rthEffective = computed<number | null>(() => {
    const d = draft.value
    if (!d) return null
    if (!d.rthHeightAuto) return d.rthHeight
    const last = d.waypoints[d.waypoints.length - 1]
    return last ? last.relativeHeight : null
  })

  function touch(): void {
    dirty.value = true
  }

  function resetSelection(): void {
    selected.value = null
    checked.value = []
    anchor = null
  }

  function startNew(): void {
    draft.value = emptyDraft()
    resetSelection()
    dirty.value = false
  }

  function loadRoute(r: Route): void {
    draft.value = {
      id: r.id, version: r.version, name: r.name, description: r.description, defaultSpeed: r.defaultSpeed,
      defaultHeight: r.defaultHeight, takeoffSecurityHeight: r.takeoffSecurityHeight, rthHeight: r.rthHeight,
      rthHeightAuto: r.rthHeightAuto ?? false, finishAction: r.finishAction, rcLostAction: r.rcLostAction,
      waypoints: r.waypoints.map(copyWaypoint),
    }
    resetSelection()
    dirty.value = false
  }

  async function open(id: string): Promise<void> {
    loadRoute(await routesApi.get(id))
  }

  function close(): void {
    draft.value = null
    resetSelection()
    dirty.value = false
  }

  function addPoint(p: LatLon): void {
    if (!draft.value) return
    draft.value.waypoints.push(newWaypoint(p, draft.value.defaultHeight))
    selected.value = draft.value.waypoints.length - 1
    touch()
  }

  function movePoint(i: number, p: LatLon): void {
    const w = draft.value?.waypoints[i]
    if (!w) return
    w.lat = round7(p.lat)
    w.lon = round7(p.lon)
    touch()
  }

  function removePoint(i: number): void {
    if (!draft.value || !draft.value.waypoints[i]) return
    draft.value.waypoints.splice(i, 1)
    if (selected.value !== null) {
      if (selected.value === i) selected.value = draft.value.waypoints.length ? Math.min(i, draft.value.waypoints.length - 1) : null
      else if (selected.value > i) selected.value--
    }
    checked.value = checked.value.filter((k) => k !== i).map((k) => (k > i ? k - 1 : k))
    anchor = null
    touch()
  }

  /** Removes every checked waypoint. */
  function removeChecked(): number {
    const ks = [...checked.value].sort((a, b) => b - a)
    for (const k of ks) removePoint(k)
    checked.value = []
    return ks.length
  }

  function reorder(i: number, delta: -1 | 1): void {
    const wps = draft.value?.waypoints
    const j = i + delta
    if (!wps || j < 0 || j >= wps.length) return
    const tmp = wps[i]!
    wps[i] = wps[j]!
    wps[j] = tmp
    selected.value = j
    // a checked waypoint stays checked where it moved to
    const ci = checked.value.includes(i)
    const cj = checked.value.includes(j)
    if (ci !== cj) checked.value = checked.value.map((k) => (k === i ? j : k === j ? i : k)).sort((a, b) => a - b)
    touch()
  }

  function updateWaypoint(i: number, patch: Partial<Waypoint>): void {
    const w = draft.value?.waypoints[i]
    if (!w) return
    Object.assign(w, patch)
    touch()
  }

  // ------------------------------------------------------------------ batch edits

  function isChecked(i: number): boolean {
    return checked.value.includes(i)
  }

  /** Checks / unchecks one waypoint; `range` (shift-click) sets every waypoint from the last one clicked to this one. */
  function toggleCheck(i: number, range = false): void {
    const n = draft.value?.waypoints.length ?? 0
    if (i < 0 || i >= n) return
    const on = !isChecked(i)
    const set = new Set(checked.value)
    if (range && anchor !== null && anchor < n) {
      const [a, b] = anchor < i ? [anchor, i] : [i, anchor]
      for (let k = a; k <= b; k++) {
        if (on) set.add(k)
        else set.delete(k)
      }
    } else if (on) set.add(i)
    else set.delete(i)
    checked.value = [...set].sort((a, b) => a - b)
    anchor = i
  }

  function setAllChecked(on: boolean): void {
    checked.value = on ? (draft.value?.waypoints.map((_, k) => k) ?? []) : []
    anchor = null
  }

  /** The waypoints an edit of waypoint i applies to: every checked one when i is checked among others. */
  function targetsOf(i: number): number[] {
    return isChecked(i) && checked.value.length > 1 ? [...checked.value] : [i]
  }

  /** Edits waypoint i, or every checked waypoint when i is one of several checked. Returns how many changed. */
  function setField(i: number, patch: Partial<Waypoint>): number {
    const ks = targetsOf(i)
    for (const k of ks) {
      const w = draft.value?.waypoints[k]
      if (w) Object.assign(w, patch)
    }
    touch()
    return ks.length
  }

  /** Sets a field on every waypoint (used when the defaults change and the operator wants existing points to follow). */
  function applyToAll(patch: Partial<Waypoint>): void {
    for (const w of draft.value?.waypoints ?? []) Object.assign(w, patch)
    touch()
  }

  // ------------------------------------------------------------------ chaining

  /**
   * Appends a copy of another route's waypoints ("接上另一条航线"). The leg from this route's end to its start is an
   * ordinary leg; with `levelTransit` and a height difference, one point is added so that leg is flown at the higher of
   * the two heights (climb above this route's end, or fly level and descend above the other route's start). Waypoints
   * that followed the other route's default speed keep that speed.
   */
  function appendRoute(r: Route, o: ChainOptions): ChainResult | null {
    const d = draft.value
    if (!d || r.waypoints.length === 0) return null
    const copies = r.waypoints.map(copyWaypoint)
    if (r.defaultSpeed !== d.defaultSpeed) for (const w of copies) w.speed = w.speed ?? r.defaultSpeed
    const first = copies[0]!
    first.hoverSeconds = Math.max(0, o.arriveHover || 0)
    first.waitForConfirm = o.arriveWait
    const from = d.waypoints.length
    let transit = false
    const last = d.waypoints[d.waypoints.length - 1]
    if (last) {
      last.hoverSeconds = Math.max(0, o.leaveHover || 0)
      const diff = first.relativeHeight - last.relativeHeight
      const apart = distance(last, first) > 1
      if (o.levelTransit && apart && Math.abs(diff) >= TRANSIT_MIN_DIFF_M) {
        const at = diff > 0 ? last : first
        const t = newWaypoint(at, Math.max(last.relativeHeight, first.relativeHeight))
        t.speed = first.speed
        d.waypoints.push(t)
        transit = true
      }
    }
    d.waypoints.push(...copies)
    selected.value = from
    touch()
    return { from, to: d.waypoints.length - 1, transit }
  }

  function request(): RouteRequest {
    const d = draft.value!
    return {
      name: d.name.trim(), description: d.description, defaultSpeed: d.defaultSpeed, defaultHeight: d.defaultHeight,
      takeoffSecurityHeight: d.takeoffSecurityHeight, rthHeight: rthEffective.value ?? d.rthHeight, rthHeightAuto: d.rthHeightAuto,
      finishAction: d.finishAction, rcLostAction: d.rcLostAction, waypoints: d.waypoints,
    }
  }

  async function save(): Promise<Route> {
    if (!draft.value) throw new Error('no draft')
    saving.value = true
    try {
      const r = draft.value.id ? await routesApi.update(draft.value.id, request()) : await routesApi.create(request())
      draft.value.id = r.id
      draft.value.version = r.version
      if (typeof r.rthHeight === 'number') draft.value.rthHeight = r.rthHeight
      dirty.value = false
      return r
    } finally {
      saving.value = false
    }
  }

  return { draft, selected, checked, dirty, saving, editing, points, length, maxHeight, rthEffective, touch, startNew, loadRoute,
    open, close, addPoint, movePoint, removePoint, removeChecked, reorder, updateWaypoint, isChecked, toggleCheck, setAllChecked,
    targetsOf, setField, applyToAll, appendRoute, request, save }
})
