<script setup lang="ts">
/**
 * Leaflet map (R-01). Base maps (tile URLs / coordinate system / key) come from runtime config and
 * the selection in the layers store (D-04, D-17). Overlays always receive WGS84 and go through
 * toLatLng/fromLatLng, so switching between WGS84 and GCJ-02 base maps re-creates the map and
 * remounts the slot content to redraw everything in the new coordinate system.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, shallowRef, watch } from 'vue'
import L from 'leaflet'
import { config, type BaseMapConfig } from '@/config/runtime'
import { useLayersStore } from '@/stores/layers'
import { fromDisplay, toDisplay, type LatLon } from '@/utils/coord'
import { MAP_CONTEXT } from './mapContext'
import { t } from '@/i18n'

/** zoomAt: corner of the +/- buttons; the monitor moves them up while a dog's hold-to-move pad owns the bottom right. */
const props = withDefaults(defineProps<{ center?: LatLon | null; zoom?: number; interactive?: boolean; fit?: LatLon[] | null; zoomAt?: 'bottomright' | 'topright' }>(), {
  center: null,
  fit: null,
  zoom: 17,
  interactive: true,
  zoomAt: 'bottomright',
})
const emit = defineEmits<{ (e: 'map-click', p: LatLon): void; (e: 'ready', map: L.Map): void }>()

const el = ref<HTMLDivElement | null>(null)
const map = shallowRef<L.Map | null>(null)
const mapCfg = config().map
const layers = useLayersStore()
const baseMap = computed(() => layers.baseMap)
/** Coordinate system of the map instance currently on screen. */
let coordSys = baseMap.value.coordSys
const tileError = ref(false)

const toLatLng = (p: LatLon): L.LatLngExpression => {
  const d = toDisplay(p, coordSys)
  return [d.lat, d.lon]
}
const fromLatLng = (ll: L.LatLng): LatLon => fromDisplay({ lat: ll.lat, lon: ll.lng }, coordSys)

let recreated = false
provide(MAP_CONTEXT, { map, toLatLng, fromLatLng, recreated: () => recreated })

let resizeObserver: ResizeObserver | null = null
let tileLayers: L.TileLayer[] = []
let zoomControl: L.Control.Zoom | null = null
/** Closest zoom (about 5 m on the scale bar); tiles past the provider's native level are enlarged. */
const MAP_MAX_ZOOM = 21

function setTiles(m: L.Map, bm: BaseMapConfig): void {
  for (const tl of tileLayers) tl.remove()
  tileError.value = false
  tileLayers = bm.tiles.map((tile) => {
    const layer = L.tileLayer(tile.url.replace('{key}', encodeURIComponent(mapCfg.apiKey)), {
      // the provider's last level is the native one; beyond it tiles are enlarged so short routes stay readable
      maxNativeZoom: tile.maxZoom ?? mapCfg.maxZoom,
      maxZoom: MAP_MAX_ZOOM,
      attribution: tile.attribution ?? '',
      subdomains: tile.subdomains || 'abc',
    })
    layer.on('tileerror', () => (tileError.value = true))
    layer.on('tileload', () => (tileError.value = false))
    return layer.addTo(m)
  })
}

function createMap(center: LatLon, zoom: number): void {
  if (!el.value) return
  coordSys = baseMap.value.coordSys
  const m = L.map(el.value, {
    zoomControl: false,
    attributionControl: true,
    dragging: props.interactive,
    scrollWheelZoom: props.interactive,
    doubleClickZoom: false,
    maxZoom: MAP_MAX_ZOOM,
  })
  setTiles(m, baseMap.value)
  zoomControl = L.control.zoom({ position: props.zoomAt })
  if (props.interactive) zoomControl.addTo(m)
  L.control.scale({ position: 'bottomleft', imperial: false }).addTo(m)
  m.setView(toLatLng(center), zoom)
  m.on('click', (ev: L.LeafletMouseEvent) => emit('map-click', fromLatLng(ev.latlng)))
  map.value = m
  emit('ready', m)
}

onMounted(() => {
  if (!el.value) return
  createMap(props.center ?? { lat: 22.58, lon: 113.94 }, props.zoom)
  resizeObserver = new ResizeObserver(() => map.value?.invalidateSize())
  resizeObserver.observe(el.value)
  fitTo(props.fit)
})

watch(baseMap, async (bm) => {
  const m = map.value
  if (!m) return
  if (bm.coordSys === coordSys) {
    setTiles(m, bm)
    return
  }
  // Different coordinate system: keep the same WGS84 view, unmount the overlays (slot v-if) so
  // they clean up on the old map, then build a new map and let them redraw through toLatLng.
  const c = m.getCenter()
  const center = fromDisplay({ lat: c.lat, lon: c.lng }, coordSys)
  const zoom = m.getZoom()
  map.value = null
  await nextTick()
  tileLayers = []
  m.remove()
  recreated = true
  createMap(center, zoom)
})

/** Shows the given points (e.g. a loaded route) in full. */
function fitTo(points: LatLon[] | null): void {
  const m = map.value
  if (!m || !points || points.length === 0) return
  if (points.length === 1) m.setView(toLatLng(points[0]!), Math.max(m.getZoom(), 17))
  else m.fitBounds(L.latLngBounds(points.map((p) => toLatLng(p) as L.LatLngTuple)), { padding: [60, 60], maxZoom: 18 })
}

watch(() => props.fit, (p) => fitTo(p))

// a map created as a small picture-in-picture becomes the main view later (monitor swap): follow the prop
watch(() => props.interactive, (on) => {
  const m = map.value
  if (!m) return
  if (on) {
    m.dragging.enable()
    m.scrollWheelZoom.enable()
    zoomControl?.addTo(m)
  } else {
    m.dragging.disable()
    m.scrollWheelZoom.disable()
    zoomControl?.remove()
  }
})

watch(() => props.zoomAt, (at) => zoomControl?.setPosition(at))

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  map.value?.remove()
  map.value = null
})

defineExpose({ map, toLatLng, fromLatLng })
</script>

<template>
  <div class="map-wrap">
    <div ref="el" class="map" />
    <div v-if="tileError" class="tile-warn">{{ t('底图瓦片加载失败（离线或底图服务不可用），坐标与图层仍正常显示') }}</div>
    <slot v-if="map" />
  </div>
</template>

<style scoped>
.map-wrap {
  position: absolute;
  inset: 0;
}
.map {
  position: absolute;
  inset: 0;
  background: var(--panel-2);
}
.tile-warn {
  position: absolute;
  left: 50%;
  bottom: 12px;
  transform: translateX(-50%);
  z-index: 500;
  padding: 4px 12px;
  border-radius: 14px;
  background: var(--overlay);
  color: var(--text-dim);
  font-size: var(--fs-xs);
  pointer-events: none;
}
:deep(.leaflet-container) {
  font-family: var(--font-ui);
  background: var(--panel-2);
}
:deep(.leaflet-control-attribution) {
  background: var(--overlay);
  color: var(--text-dim);
}
:deep(.leaflet-control-attribution a) {
  color: var(--accent);
}
:deep(.leaflet-bar a) {
  background: var(--panel);
  color: var(--text);
  border-color: var(--border);
}
:deep(.leaflet-control-scale-line) {
  background: var(--overlay);
  color: var(--text);
  border-color: var(--text-dim);
}
</style>
