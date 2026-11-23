<script setup lang="ts">
/** Interactive route layer (R-06): numbered draggable waypoints, right-click to delete, click to select. */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useEditorStore } from '@/stores/editor'
import { useLayersStore } from '@/stores/layers'
import { t } from '@/i18n'

const props = defineProps<{ invalid?: Set<number> }>()
const ctx = inject(MAP_CONTEXT)!
const ed = useEditorStore()
const layers = useLayersStore()
const group = L.layerGroup().addTo(ctx.map.value!)

function icon(i: number, selected: boolean, invalid: boolean): L.DivIcon {
  const bg = invalid ? 'var(--danger)' : selected ? '#facc15' : 'var(--accent)'
  return L.divIcon({
    className: 'wp-icon',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div style="width:30px;height:30px;border-radius:50%;background:${bg};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 13px var(--font-num);border:2px solid #0d1117;box-shadow:0 1px 6px rgba(0,0,0,.6);cursor:grab">${i + 1}</div>`,
  })
}

function render(): void {
  group.clearLayers()
  const d = ed.draft
  if (!d || !layers.isVisible('route')) return
  const pts = d.waypoints.map((w) => ctx.toLatLng(w))
  if (pts.length > 1) L.polyline(pts, { color: 'var(--accent)', weight: 4, opacity: 0.9, interactive: false }).addTo(group)
  d.waypoints.forEach((w, i) => {
    const m = L.marker(ctx.toLatLng(w), {
      icon: icon(i, ed.selected === i, props.invalid?.has(i) ?? false),
      draggable: true,
      zIndexOffset: 500 + i,
      title: t('航点 {n} · {h} m', { n: i + 1, h: w.relativeHeight }),
    })
    m.on('click', (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e)
      ed.selected = i
    })
    m.on('dragend', () => ed.movePoint(i, ctx.fromLatLng(m.getLatLng())))
    m.on('contextmenu', (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e)
      ed.removePoint(i)
    })
    m.addTo(group)
  })
}

watch(() => [ed.draft, ed.selected, props.invalid, layers.isVisible('route')], render, { deep: true, immediate: true })

onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('航线编辑图层') }}</span></template>
