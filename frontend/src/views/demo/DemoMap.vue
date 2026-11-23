<script setup lang="ts">
/** The demo map: base map from the platform settings, demo layers on top, framed on the demo's routes. */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '@/i18n'
import MapCanvas from '@/components/map/MapCanvas.vue'
import { useLayersStore } from '@/stores/layers'
import DemoMapLayers from './DemoMapLayers.vue'
import { useDemoStore } from './useDemoStore'
import type { LatLon } from './demoApi'

const props = withDefaults(defineProps<{ compact?: boolean; baseMapSwitch?: boolean }>(), { compact: false, baseMapSwitch: false })
const emit = defineEmits<{ (e: 'pick', p: LatLon): void }>()
const demo = useDemoStore()
const layers = useLayersStore()

/** Every point the demo will use: routes, take-off points, target, dog start. Framed once they are known. */
const framePoints = computed<LatLon[]>(() => {
  const pts: LatLon[] = []
  for (const id of Object.values(demo.state?.routes ?? {})) {
    const r = id ? demo.routes[id] : undefined
    r?.waypoints.forEach((w) => pts.push({ lat: w.lat, lon: w.lon }))
  }
  for (const d of demo.drones) if (d.label && d.homeLat != null && d.homeLon != null) pts.push({ lat: d.homeLat, lon: d.homeLon })
  if (demo.state?.target) pts.push(demo.state.target)
  if (demo.state?.dogStart) pts.push(demo.state.dogStart)
  return pts
})
const fit = ref<LatLon[] | null>(null)
const framedKey = ref('')
watch(
  framePoints,
  (pts) => {
    // re-frame only when the set of routes changes, not on every frame
    const key = Object.values(demo.state?.routes ?? {}).join(',') + ':' + Object.keys(demo.routes).length
    if (pts.length === 0 || key === framedKey.value) return
    framedKey.value = key
    fit.value = [...pts]
  },
  { immediate: true },
)
const center = computed(() => framePoints.value[0] ?? null)

function reframe(): void {
  userMoved = false
  fit.value = [...framePoints.value]
}

// The show page is often resized after it opens (full screen, projector): keep the demo area framed until someone
// drags or zooms the map by hand.
const box = ref<HTMLDivElement | null>(null)
let userMoved = false
let resizeTimer = 0
let observer: ResizeObserver | null = null
let lastSize = ''
onMounted(() => {
  observer = new ResizeObserver(() => {
    const el = box.value
    if (!el) return
    const size = `${el.clientWidth}x${el.clientHeight}`
    if (size === lastSize) return
    lastSize = size
    window.clearTimeout(resizeTimer)
    resizeTimer = window.setTimeout(() => {
      if (!userMoved && framePoints.value.length) fit.value = [...framePoints.value]
    }, 300)
  })
  if (box.value) observer.observe(box.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  window.clearTimeout(resizeTimer)
})
const markMoved = () => (userMoved = true)

function nextBaseMap(): void {
  const list = layers.baseMaps
  const i = list.findIndex((b) => b.id === layers.baseMap.id)
  layers.setBaseMap(list[(i + 1) % list.length]!.id)
}

defineExpose({ reframe })
</script>

<template>
  <div ref="box" class="demo-map" @wheel.passive="markMoved" @mousedown="markMoved" @touchstart.passive="markMoved">
    <MapCanvas :center="center" :fit="fit" :zoom="17" @map-click="(p) => emit('pick', p)">
      <DemoMapLayers :compact="props.compact" />
    </MapCanvas>
    <div class="map-tools">
      <button class="tool" type="button" :title="t('回到全景')" @click="reframe">{{ t('全景') }}</button>
      <button v-if="props.baseMapSwitch" class="tool" type="button" :title="t('底图：{name}', { name: layers.baseMap.label })" @click="nextBaseMap">{{ t('底图') }}</button>
    </div>
  </div>
</template>

<style scoped>
.demo-map {
  position: relative;
  width: 100%;
  height: 100%;
}
.map-tools {
  position: absolute;
  left: 12px;
  top: 12px;
  z-index: 600;
  display: flex;
  gap: 6px;
  opacity: 0.35;
  transition: opacity 0.2s;
}
.demo-map:hover .map-tools {
  opacity: 1;
}
.tool {
  padding: 4px 10px;
  border: 1px solid rgba(226, 232, 240, 0.35);
  border-radius: 6px;
  background: rgba(11, 18, 32, 0.75);
  color: #e2e8f0;
  font: 600 12px var(--font-ui);
  cursor: pointer;
}
</style>
