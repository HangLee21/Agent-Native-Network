<script setup lang="ts">
/**
 * Saved routes shown next to the one being edited (dual-drone planning, 2026-11-04): dashed, each in its own colour,
 * small numbered points and the route name at its first point. Read-only and not clickable, so a click on the map
 * still adds a waypoint to the edited route. The route open in the editor is drawn by RouteEditLayer instead.
 */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { t } from '@/i18n'
import { useEditorStore } from '@/stores/editor'
import { useRouteOverlaysStore } from '@/stores/routeOverlays'

const ctx = inject(MAP_CONTEXT)!
const ed = useEditorStore()
const ov = useRouteOverlaysStore()
const group = L.layerGroup().addTo(ctx.map.value!)

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

function render(): void {
  group.clearLayers()
  for (const id of ov.shown) {
    const r = ov.details[id]
    if (!r || id === ed.draft?.id || r.waypoints.length === 0) continue
    const color = ov.colorOf(id)!
    const pts = r.waypoints.map((w) => ctx.toLatLng(w))
    if (pts.length > 1) L.polyline(pts, { color, weight: 3, opacity: 0.9, dashArray: '8 6', interactive: false }).addTo(group)
    r.waypoints.forEach((w, i) => {
      L.marker(ctx.toLatLng(w), {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: 'overlay-wp',
          iconSize: [20, 20],
          iconAnchor: [10, 10],
          html: `<div style="width:20px;height:20px;border-radius:50%;background:#0d1117;color:${color};border:2px solid ${color};display:flex;align-items:center;justify-content:center;font:700 10px var(--font-num)">${i + 1}</div>`,
        }),
      }).addTo(group)
    })
    L.marker(pts[0]!, {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({
        className: 'overlay-name',
        iconSize: [0, 0],
        iconAnchor: [-14, 26],
        html: `<div style="white-space:nowrap;padding:1px 6px;border-radius:4px;background:#0d1117cc;color:${color};border:1px solid ${color};font:600 12px var(--font-ui, sans-serif)">${esc(r.name)}</div>`,
      }),
    }).addTo(group)
  }
}

watch(() => [ov.shown, ov.details, ed.draft?.id], render, { deep: true, immediate: true })

onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('叠加显示的已保存航线') }}</span></template>
