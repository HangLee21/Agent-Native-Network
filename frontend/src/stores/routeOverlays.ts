import { defineStore } from 'pinia'
import { ref } from 'vue'
import { routesApi, type Route, type RouteSummary } from '@/api/routes'

/** Colours of saved routes shown on the planning map (not the editor's accent, the drones' or the target's colours). */
export const OVERLAY_COLORS = ['#a78bfa', '#34d399', '#22d3ee', '#f0abfc', '#a3e635', '#fdba74']

const KEY = 'uav.plan.overlayRoutes'

function load(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : []
  } catch {
    return []
  }
}

function persist(ids: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids))
  } catch {
    /* private mode: the choice lasts for this page only */
  }
}

/**
 * Saved routes shown on the planning map while another one is edited (dual-drone planning, 2026-11-04): toggled with the
 * eye in the route list, dashed in their own colours. The choice is remembered in this browser.
 */
export const useRouteOverlaysStore = defineStore('routeOverlays', () => {
  /** In the order they were turned on: the order picks the colour. */
  const shown = ref<string[]>(load())
  const details = ref<Record<string, Route>>({})

  function isShown(id: string): boolean {
    return shown.value.includes(id)
  }

  function colorOf(id: string): string | null {
    const i = shown.value.indexOf(id)
    return i < 0 ? null : OVERLAY_COLORS[i % OVERLAY_COLORS.length]!
  }

  async function fetchRoute(id: string): Promise<void> {
    try {
      details.value = { ...details.value, [id]: await routesApi.get(id) }
    } catch {
      /* deleted or unreachable: nothing is drawn for it */
    }
  }

  function toggle(id: string): void {
    shown.value = isShown(id) ? shown.value.filter((x) => x !== id) : [...shown.value, id]
    persist(shown.value)
    if (isShown(id) && !details.value[id]) void fetchRoute(id)
  }

  /** After the library list loads: drop routes that are gone, refetch the ones saved since. */
  function sync(list: RouteSummary[]): void {
    const byId = new Map(list.map((r) => [r.id, r]))
    const kept = shown.value.filter((id) => byId.has(id))
    if (kept.length !== shown.value.length) {
      shown.value = kept
      persist(kept)
    }
    for (const id of kept) {
      if (details.value[id]?.version !== byId.get(id)!.version) void fetchRoute(id)
    }
  }

  function forget(id: string): void {
    if (isShown(id)) toggle(id)
    const next = { ...details.value }
    delete next[id]
    details.value = next
  }

  return { shown, details, isShown, colorOf, toggle, sync, forget, fetchRoute }
})
