<script setup lang="ts">
/**
 * Every drone on one map (R-28, ui-design.md 2.7): platform layers once (safe zone, library preview), then each
 * known drone's layers and marker in its colour with its name; only the selected one follows. Two drones the
 * proximity monitor judges close are joined by a dashed line with their distance (S-05).
 */
import { computed, inject, onBeforeUnmount, watchEffect } from 'vue'
import L from 'leaflet'
import DroneScope from '@/components/common/DroneScope.vue'
import DroneMarker from './DroneMarker.vue'
import DogV2Layer from './DogV2Layer.vue'
import DogNavLayer from './DogNavLayer.vue'
import MapOverlays from './MapOverlays.vue'
import { MAP_CONTEXT } from './mapContext'
import { useFleetStore } from '@/stores/fleet'
import { useTelemetryStore } from '@/stores/telemetry'
import { t } from '@/i18n'

/** markersOnly: just the drones (settings maps with their own editors). followDog: model of the dog to keep centred instead. */
const props = withDefaults(defineProps<{ showRoute?: boolean; follow?: boolean; markersOnly?: boolean; followDog?: string | null }>(),
  { showRoute: true, follow: false, markersOnly: false, followDog: null })
const ctx = inject(MAP_CONTEXT)!
const fleet = useFleetStore()
const many = computed(() => fleet.drones.length > 1)

const lines = L.layerGroup()
watchEffect(() => {
  const m = ctx.map.value
  if (!m) return
  lines.addTo(m)
  lines.clearLayers()
  for (const p of fleet.proximity) {
    const a = fleet.byGateway(p.a)
    const b = fleet.byGateway(p.b)
    const pa = a ? useTelemetryStore(a.gatewaySn).position : null
    const pb = b ? useTelemetryStore(b.gatewaySn).position : null
    if (!pa || !pb) continue
    const color = p.level === 'hold' ? '#ef4444' : '#f59e0b'
    const h = Math.round(p.horizontalM)
    const tip = p.verticalM == null ? `${h} m` : t('{h} m · 高度差 {v} m', { h, v: Math.round(p.verticalM) })
    L.polyline([ctx.toLatLng(pa), ctx.toLatLng(pb)], { color, weight: 3, dashArray: '6 6', interactive: false })
      .bindTooltip(tip, { permanent: true, direction: 'center', className: 'prox-tip' })
      .addTo(lines)
  }
})
onBeforeUnmount(() => lines.remove())
</script>

<template>
  <MapOverlays v-if="!props.markersOnly" :drone="false" :show-route="props.showRoute" />
  <DroneScope v-for="d in fleet.drones" :key="d.gatewaySn" :sn="d.gatewaySn">
    <MapOverlays v-if="!props.markersOnly" :platform="false" :show-route="props.showRoute" :color="many ? d.color : ''" :label="many ? d.label : ''" />
    <DroneMarker :follow="props.follow && d.gatewaySn === fleet.selectedSn" :color="many ? d.color : undefined"
      :label="many ? d.label : ''" :selected="d.gatewaySn === fleet.selectedSn" />
  </DroneScope>
  <DogV2Layer v-if="!props.markersOnly" :follow="props.followDog" />
  <!-- outdoor navigation of dogs that can navigate (draws nothing for any other dog) -->
  <DogNavLayer v-if="!props.markersOnly" />
</template>

<style>
.prox-tip {
  background: rgba(13, 17, 23, 0.85);
  color: #fff;
  border: none;
  font: 700 12px var(--font-ui);
}
</style>
