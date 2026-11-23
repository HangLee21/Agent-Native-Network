<script setup lang="ts">
/**
 * Replay map layers (ui-design.md §2.6): flown track coloured by height or speed, the route as it
 * was flown (snapshot, dashed), paths the aircraft planned, home, pilot, alert and photo pins, and
 * the aircraft with its camera cone at the cursor. Positions are WGS84 and go through toLatLng.
 */
import { inject, onBeforeUnmount, watch, watchEffect } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from '@/components/map/mapContext'
import type { FilledSample, Mark, PlannedPath, ReplayTarget } from '@/utils/replay'
import { rampColor } from '@/utils/replay'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

export interface ReplayLayers {
  track: boolean
  route: boolean
  planned: boolean
  pins: boolean
  rc: boolean
  targets: boolean
}

const props = defineProps<{
  filled: FilledSample[]
  state: FilledSample | null
  route: LatLon[]
  planned: PlannedPath[]
  pins: (Mark & { pos: LatLon })[]
  targets: ReplayTarget[]
  rc: LatLon | null
  home: LatLon | null
  colorBy: 'height' | 'speed'
  layers: ReplayLayers
}>()

const ctx = inject(MAP_CONTEXT)!
const ll = (p: LatLon) => ctx.toLatLng(p)
const groups: Record<string, L.LayerGroup> = {}
function group(id: string): L.LayerGroup {
  if (!groups[id]) groups[id] = L.layerGroup().addTo(ctx.map.value!)
  return groups[id]
}

function css(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function pin(color: string, glyph: string, title: string): L.DivIcon {
  return L.divIcon({
    className: 'pin-icon',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<div title="${title.replace(/"/g, '&quot;')}" style="width:22px;height:22px;border-radius:50%;background:${color};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 11px var(--font-ui);border:2px solid #0d1117;box-shadow:0 1px 4px rgba(0,0,0,.5)">${glyph}</div>`,
  })
}

// track: consecutive samples with the same colour bucket drawn as one polyline
watchEffect(() => {
  const g = group('track')
  g.clearLayers()
  const pts = props.filled.filter((s) => s.lat !== null && s.lon !== null)
  if (!props.layers.track || pts.length < 2) return
  const val = (s: FilledSample) => (props.colorBy === 'height' ? s.height : s.horizontalSpeed)
  const vals = pts.map(val).filter((v): v is number => v !== null)
  const min = vals.length ? Math.min(...vals) : 0
  const max = vals.length ? Math.max(...vals) : 1
  const bucket = (v: number | null) => (v === null || max <= min ? 0 : Math.round(((v - min) / (max - min)) * 9))
  let run: L.LatLngExpression[] = [ll(pts[0] as LatLon)]
  let b = bucket(val(pts[0]!))
  for (let i = 1; i < pts.length; i++) {
    const nb = bucket(val(pts[i]!))
    run.push(ll(pts[i] as LatLon))
    if (nb !== b || i === pts.length - 1) {
      L.polyline(run, { color: rampColor(min + ((max - min) * b) / 9, min, max), weight: 4, opacity: 0.95, interactive: false }).addTo(g)
      run = [ll(pts[i] as LatLon)]
      b = nb
    }
  }
})

watchEffect(() => {
  const g = group('route')
  g.clearLayers()
  if (!props.layers.route || props.route.length === 0) return
  const color = css('--accent', '#38bdf8')
  L.polyline(props.route.map(ll), { color, weight: 2, dashArray: '8 6', opacity: 0.9, interactive: false }).addTo(g)
  props.route.forEach((p, i) => L.marker(ll(p), { icon: pin(color, String(i + 1), t('航点 {n}', { n: i + 1 })), interactive: false }).addTo(g))
})

watchEffect(() => {
  const g = group('planned')
  g.clearLayers()
  if (!props.layers.planned) return
  const colors: Record<string, string> = { flyto: '#e2e8f0', takeoff: '#93c5fd', returnHome: css('--warn', '#f5a524') }
  for (const p of props.planned) {
    if (p.points.length > 1) {
      L.polyline(p.points.map(ll), { color: colors[p.kind] ?? '#e2e8f0', weight: 2, dashArray: '3 6', opacity: 0.8, interactive: false }).addTo(g)
    }
  }
})

watchEffect(() => {
  const g = group('targets')
  g.clearLayers()
  if (!props.layers.targets) return
  const color = '#f43f5e'
  for (const tg of props.targets) {
    if (tg.accuracyM) L.circle(ll(tg.pos), { radius: Math.max(1, tg.accuracyM), color, weight: 1, fillOpacity: 0.12, interactive: false }).addTo(g)
    L.marker(ll(tg.pos), { icon: pin(color, 'T', tg.label) }).bindTooltip(`${tg.label} · ${tg.state}`, { direction: 'top' }).addTo(g)
    if (tg.stop) {
      L.polyline([ll(tg.stop), ll(tg.pos)], { color, weight: 2, dashArray: '3 5', interactive: false }).addTo(g)
      L.circleMarker(ll(tg.stop), { radius: 5, color, weight: 2, fillOpacity: 0.3 }).bindTooltip(t('停止点')).addTo(g)
    }
  }
})

watchEffect(() => {
  const g = group('pins')
  g.clearLayers()
  if (props.home) L.marker(ll(props.home), { icon: pin(css('--ok', '#3fb950'), 'H', t('Home 点')), interactive: false }).addTo(g)
  if (!props.layers.pins) return
  for (const m of props.pins) {
    const photo = m.kind === 'TakePhoto' || m.kind === 'StartRecording' || m.kind === 'StopRecording'
    const color = photo ? '#e2e8f0' : m.level === 'CRITICAL' ? css('--danger', '#f85149') : css('--warn', '#f5a524')
    L.marker(ll(m.pos), { icon: pin(color, photo ? '◉' : '!', m.label) }).bindTooltip(m.label, { direction: 'top' }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('rc')
  g.clearLayers()
  if (props.layers.rc && props.rc) L.marker(ll(props.rc), { icon: pin('#f472b6', 'RC', t('遥控器（飞手）位置')), interactive: false }).addTo(g)
})

// aircraft and camera cone at the cursor
let aircraft: L.Marker | null = null
let cone: L.Polygon | null = null

function aircraftIcon(heading: number): L.DivIcon {
  return L.divIcon({
    className: 'drone-icon',
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    html: `<div style="width:40px;height:40px;transform:rotate(${heading}deg)"><svg viewBox="0 0 44 44" width="40" height="40"><circle cx="22" cy="22" r="20" fill="var(--accent)" fill-opacity="0.18" stroke="var(--accent)" stroke-width="1.5"/><path d="M22 7 L31 31 L22 26 L13 31 Z" fill="var(--accent)" stroke="#0d1117" stroke-width="1.5" stroke-linejoin="round"/></svg></div>`,
  })
}

/** Point at distance d (m) and bearing b (deg) from p. */
function offset(p: LatLon, d: number, b: number): LatLon {
  const r = (b * Math.PI) / 180
  return { lat: p.lat + (d * Math.cos(r)) / 111_320, lon: p.lon + (d * Math.sin(r)) / (111_320 * Math.cos((p.lat * Math.PI) / 180)) }
}

watch(
  () => props.state,
  (s) => {
    const m = ctx.map.value
    if (!m) return
    if (!s || s.lat === null || s.lon === null) {
      aircraft?.remove()
      cone?.remove()
      aircraft = null
      cone = null
      return
    }
    const pos = { lat: s.lat, lon: s.lon }
    const head = s.attitudeHead ?? 0
    if (!aircraft) aircraft = L.marker(ll(pos), { icon: aircraftIcon(head), zIndexOffset: 1000, interactive: false, keyboard: false }).addTo(m)
    else {
      aircraft.setLatLng(ll(pos))
      aircraft.setIcon(aircraftIcon(head))
    }
    // gimbal yaw when reported (absolute bearing), otherwise the aircraft heading; narrower when zoomed in
    const bearing = s.gimbalYaw ?? head
    const half = 41 / Math.max(1, s.zoomFactor ?? 1)
    const len = 60
    const pts = [pos, offset(pos, len, bearing - half), offset(pos, len, bearing + half)].map(ll)
    const color = css('--accent', '#38bdf8')
    if (!cone) cone = L.polygon(pts, { color, weight: 1, fillColor: color, fillOpacity: 0.15, interactive: false }).addTo(m)
    else cone.setLatLngs(pts)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  Object.values(groups).forEach((g) => g.remove())
  aircraft?.remove()
  cone?.remove()
})
</script>

<template><span class="sr-only">{{ t('回放图层') }}</span></template>
