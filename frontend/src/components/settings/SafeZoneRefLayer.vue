<script setup lang="ts">
/** Read-only dashed outline of the saved safe zone (S-02), drawn under the AI work-area editor for reference. */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from '@/components/map/mapContext'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = defineProps<{ points: LatLon[] | null }>()
const ctx = inject(MAP_CONTEXT)!
const group = L.layerGroup().addTo(ctx.map.value!)

function render(): void {
  group.clearLayers()
  const pts = props.points
  if (!pts || pts.length < 3) return
  const color = getComputedStyle(document.documentElement).getPropertyValue('--zone').trim() || '#3fb950'
  L.polygon(pts.map((p) => ctx.toLatLng(p)), { color, weight: 2.5, dashArray: '10 7', fill: false, interactive: false }).addTo(group)
}

watch(() => props.points, render, { deep: true, immediate: true })
onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('安全区（只读）') }}</span></template>
