<script setup lang="ts">
/**
 * The points of a dog's navigation being picked or edited on the map (docs/dog/ui-design.md 19.5): numbered points in
 * the dog's colour, draggable, right-click deletes; points the platform's check refused are red. A separate copy of the
 * aircraft route editor's numbered points (RouteEditLayer.vue), which stays as it is. Points are WGS84; the map shows
 * them in the base map's coordinates (toLatLng / fromLatLng).
 */
import { computed, inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useDog2Store } from '@/stores/dogv2'
import { t } from '@/i18n'

const COLOR = '#a3e635'
const ctx = inject(MAP_CONTEXT)!
const v2 = useDog2Store()
const group = L.layerGroup().addTo(ctx.map.value!)

/** Indexes of points the check named in its problems. */
const invalid = computed(() => new Set((v2.navDraft?.check?.problems ?? []).map((p) => p.index).filter((i): i is number => typeof i === 'number')))

function icon(i: number, bad: boolean): L.DivIcon {
  const bg = bad ? 'var(--danger)' : COLOR
  return L.divIcon({
    className: 'dog-route-pt',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<div data-i="${i}" style="width:26px;height:26px;border-radius:50%;background:${bg};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 12px var(--font-num);border:2px solid #0d1117;box-shadow:0 1px 6px rgba(0,0,0,.6);cursor:grab">${i + 1}</div>`,
  })
}

function render(): void {
  group.clearLayers()
  const d = v2.navDraft
  if (!d) return
  const lls = d.points.map((p) => ctx.toLatLng(p))
  if (lls.length > 1) L.polyline(lls, { color: COLOR, weight: 3, opacity: 0.9, interactive: false, className: 'dog-route-line' }).addTo(group)
  d.points.forEach((p, i) => {
    const m = L.marker(ctx.toLatLng(p), {
      icon: icon(i, invalid.value.has(i)),
      draggable: true,
      zIndexOffset: 950 + i,
      title: t('点 {n}（拖动调整，右键删除）', { n: i + 1 }),
    })
    m.on('click', (e: L.LeafletMouseEvent) => L.DomEvent.stopPropagation(e))
    m.on('dragend', () => v2.draftMove(i, ctx.fromLatLng(m.getLatLng())))
    m.on('contextmenu', (e: L.LeafletMouseEvent) => {
      L.DomEvent.stopPropagation(e)
      v2.draftRemove(i)
    })
    m.addTo(group)
  })
}

watch(() => [v2.navDraft?.points, invalid.value], render, { deep: true, immediate: true })
onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('狗的路线编辑') }}</span></template>
