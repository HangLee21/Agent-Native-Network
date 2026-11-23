<script setup lang="ts">
/** Draws the editable safe-zone polygon (S-02). */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = defineProps<{ points: LatLon[] }>()
const emit = defineEmits<{ (e: 'move', i: number, p: LatLon): void; (e: 'remove', i: number): void }>()
const ctx = inject(MAP_CONTEXT)!
const group = L.layerGroup().addTo(ctx.map.value!)

function render(): void {
  group.clearLayers()
  const color = getComputedStyle(document.documentElement).getPropertyValue('--zone').trim() || '#3fb950'
  const lls = props.points.map((p) => ctx.toLatLng(p))
  if (lls.length >= 3) L.polygon(lls, { color, weight: 2, fillColor: color, fillOpacity: 0.1, interactive: false }).addTo(group)
  else if (lls.length === 2) L.polyline(lls, { color, weight: 2, dashArray: '6 6' }).addTo(group)
  props.points.forEach((p, i) => {
    const m = L.marker(ctx.toLatLng(p), {
      draggable: true,
      icon: L.divIcon({ className: 'zone-v', iconSize: [16, 16], iconAnchor: [8, 8],
        html: `<div style="width:16px;height:16px;border-radius:3px;background:${color};border:2px solid #0d1117"></div>` }),
      title: t('顶点 {n}（右键删除）', { n: i + 1 }),
    })
    m.on('dragend', () => emit('move', i, ctx.fromLatLng(m.getLatLng())))
    m.on('contextmenu', (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e)
      emit('remove', i)
    })
    m.addTo(group)
  })
}

watch(() => props.points, render, { deep: true, immediate: true })
onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('安全区编辑') }}</span></template>
