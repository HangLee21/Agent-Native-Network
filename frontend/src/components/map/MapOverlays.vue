<script setup lang="ts">
/**
 * Renders every map layer except the live drone marker and the route editor (R-03, R-04). With several drones
 * (D-31) one instance per drone draws that drone's layers in its colour (`platform: false`), and one instance
 * draws the platform layers once (`drone: false`): safe zone and a route previewed from the library.
 */
import { inject, onBeforeUnmount, watchEffect } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useTelemetryStore } from '@/stores/telemetry'
import { useLayersStore } from '@/stores/layers'
import { useMapOverlaysStore, useOverlaysStore } from '@/stores/overlays'
import { useTargetsStore } from '@/stores/targets'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ showRoute?: boolean; color?: string; label?: string; drone?: boolean; platform?: boolean }>(),
  { showRoute: true, color: '', label: '', drone: true, platform: true })
const ctx = inject(MAP_CONTEXT)!
const tel = useTelemetryStore()
const layers = useLayersStore()
const ov = useOverlaysStore()
const mapOv = useMapOverlaysStore()
const targets = useTargetsStore()

const groups: Record<string, L.LayerGroup> = {}
function group(id: string): L.LayerGroup {
  if (!groups[id]) groups[id] = L.layerGroup().addTo(ctx.map.value!)
  return groups[id]
}

function css(name: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || '#38bdf8'
}

function pinIcon(color: string, glyph: string, title: string): L.DivIcon {
  return L.divIcon({
    className: 'pin-icon',
    iconSize: [26, 26],
    iconAnchor: [13, 13],
    html: `<div title="${title}" style="width:26px;height:26px;border-radius:50%;background:${color};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 12px var(--font-ui);border:2px solid #0d1117;box-shadow:0 1px 4px rgba(0,0,0,.5)">${glyph}</div>`,
  })
}

const ll = (p: LatLon) => ctx.toLatLng(p)

watchEffect(() => {
  const g = group('track')
  g.clearLayers()
  if (props.drone && layers.isVisible('track') && tel.track.length > 1) {
    L.polyline(tel.track.map(ll), { color: props.color || css('--track'), weight: 3, opacity: 0.85 }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('home')
  g.clearLayers()
  if (props.drone && layers.isVisible('home') && tel.home) {
    L.marker(ll(tel.home), { icon: pinIcon(props.color || css('--ok'), 'H', props.label ? t('{name} Home 点', { name: props.label }) : t('Home 点')), interactive: false }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('rc')
  g.clearLayers()
  const rc = tel.rc
  if (props.drone && layers.isVisible('rc') && rc?.lat != null && rc.lon != null) {
    L.marker(ll({ lat: rc.lat, lon: rc.lon }), { icon: pinIcon('#f472b6', 'RC', props.label ? t('{name} 遥控器（飞手）位置', { name: props.label }) : t('遥控器（飞手）位置')), interactive: false }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('alertRing')
  g.clearLayers()
  const t = tel.drone
  if (!props.drone || !layers.isVisible('alertRing') || !tel.position || !t) return
  if (t.nearHeightLimit || t.nearAreaLimit) {
    L.circle(ll(tel.position), { radius: 25, color: css('--warn'), weight: 3, dashArray: '6 6', fill: false, interactive: false }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('route')
  g.clearLayers()
  // the platform instance draws a route previewed from the library, a drone instance that drone's executing route
  const route = props.drone && props.platform ? (mapOv.preview ?? ov.route) : props.platform ? mapOv.preview : ov.route
  if (!props.showRoute || !layers.isVisible('route') || !route || route.length === 0) return
  const color = props.color || css('--accent')
  L.polyline(route.map(ll), { color, weight: 4, opacity: 0.9 }).addTo(g)
  route.forEach((p, i) => {
    L.marker(ll(p), { icon: pinIcon(color, String(i + 1), t('航点 {n}', { n: i + 1 })), interactive: false }).addTo(g)
  })
})

watchEffect(() => {
  const g = group('target')
  g.clearLayers()
  const t = ov.target()
  if (!props.drone || !layers.isVisible('target') || !t) return
  L.circleMarker(ll(t), { radius: 9, color: '#facc15', weight: 3, fillOpacity: 0.15 })
    .bindTooltip(`${t.label} · ${t.relativeHeight.toFixed(0)} m`, { direction: 'top' })
    .addTo(g)
  if (tel.position) L.polyline([ll(tel.position), ll(t)], { color: '#facc15', weight: 2, dashArray: '4 6' }).addTo(g)
})

watchEffect(() => {
  const g = group('devicePaths')
  g.clearLayers()
  if (!props.drone || !layers.isVisible('devicePaths')) return
  const styles: Record<string, string> = { flytoPath: '#e2e8f0', takeoffPath: '#93c5fd', returnHomePath: css('--warn') }
  for (const kind of Object.keys(styles)) {
    const pts = ov.path(kind)
    if (pts.length > 1) L.polyline(pts.map(ll), { color: styles[kind], weight: 2, dashArray: '8 6', opacity: 0.9 }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('poi')
  g.clearLayers()
  const p = ov.poi()
  if (!props.drone || !layers.isVisible('poi') || !p) return
  L.marker(ll(p), { icon: pinIcon('#fb923c', 'P', t('兴趣点')), interactive: false }).addTo(g)
  if (p.radius) L.circle(ll(p), { radius: p.radius, color: '#fb923c', weight: 2, dashArray: '6 6', fill: false }).addTo(g)
})

watchEffect(() => {
  const g = group('safeZone')
  g.clearLayers()
  if (!props.platform || !layers.isVisible('safeZone') || !mapOv.safeZone || mapOv.safeZone.length < 3) return
  const c = css('--zone')
  L.polygon(mapOv.safeZone.map(ll), { color: c, weight: 3, dashArray: '10 6', fillColor: c, fillOpacity: 0.1, interactive: false }).addTo(g)
})

watchEffect(() => {
  const g = group('targets')
  g.clearLayers()
  if (!props.drone || !layers.isVisible('targets')) return
  const color = '#f43f5e'
  const sel = targets.selected?.id
  for (const tg of targets.visibleOnMap) {
    const p = { lat: tg.lat!, lon: tg.lon! }
    const isSel = tg.id === sel
    if (tg.accuracyM) L.circle(ll(p), { radius: Math.max(1, tg.accuracyM), color, weight: 1, fillOpacity: 0.12, interactive: false }).addTo(g)
    const glyph = tg.source.startsWith('AI:') ? 'AI' : 'T'
    const m = L.marker(ll(p), { icon: pinIcon(isSel ? color : '#fda4af', glyph, tg.label ?? t('目标')), zIndexOffset: isSel ? 500 : 0 })
    m.on('click', () => (targets.selectedId = tg.id))
    m.bindTooltip(`${tg.label ?? t('目标')}${tg.distance != null ? ` · ${tg.distance.toFixed(0)} m` : ''}`, { direction: 'top' }).addTo(g)
    if (isSel && tg.stopPoint) {
      const s = { lat: tg.stopPoint.lat, lon: tg.stopPoint.lon }
      L.polyline([ll(s), ll(p)], { color, weight: 2, dashArray: '3 5', interactive: false }).addTo(g)
      L.circleMarker(ll(s), { radius: 6, color, weight: 2, fillOpacity: 0.3 }).bindTooltip(t('停止点')).addTo(g)
    }
    if (isSel && tg.backPoint) {
      L.circleMarker(ll({ lat: tg.backPoint.lat, lon: tg.backPoint.lon }), { radius: 5, color: '#94a3b8', weight: 2, fillOpacity: 0.2 })
        .bindTooltip(t('返回点')).addTo(g)
    }
  }
})

onBeforeUnmount(() => Object.values(groups).forEach((g) => g.remove()))
</script>

<template><span class="sr-only">{{ t('地图图层') }}</span></template>
