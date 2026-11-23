<script setup lang="ts">
/**
 * Joint replay map layers (D-33, D-40; ui-design.md 2.6.1, 2.7.1): each device's track, a drone's route snapshot
 * and a dog's recorded navigation plans (dashed, numbered), plus home, alert and photo pins; at the cursor each drone (arrow) or dog (square
 * with a heading arrow, as on the live map) with its name, and between two drones a dashed line labelled with the
 * separation (red while a proximity alarm was active). Positions are WGS84 through toLatLng.
 */
import { inject, onBeforeUnmount, watchEffect } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from '@/components/map/mapContext'
import { pinsOf, type Track } from '@/utils/jointReplay'
import type { FilledSample } from '@/utils/replay'
import type { LatLon } from '@/utils/coord'
import { t } from '@/i18n'

export interface JointLayers {
  track: boolean
  route: boolean
  dogRoute: boolean
  pins: boolean
  link: boolean
}

const props = defineProps<{
  tracks: Track[]
  /** Each track's state at the cursor, null outside its recording. */
  states: (FilledSample | null)[]
  link: { a: LatLon; b: LatLon; text: string; alarm: boolean } | null
  layers: JointLayers
  selectedDogRoute: string
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

function pin(fill: string, ring: string, glyph: string, title: string): L.DivIcon {
  return L.divIcon({
    className: 'pin-icon',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
    html: `<div title="${title.replace(/"/g, '&quot;')}" style="width:22px;height:22px;border-radius:50%;background:${fill};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 11px var(--font-ui);border:2px solid ${ring};box-shadow:0 1px 4px rgba(0,0,0,.5)">${glyph}</div>`,
  })
}

function aircraftIcon(color: string, label: string, heading: number): L.DivIcon {
  return L.divIcon({
    className: 'drone-icon',
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    html: `<div style="position:relative;width:40px;height:40px"><div style="width:40px;height:40px;transform:rotate(${heading}deg)"><svg viewBox="0 0 44 44" width="40" height="40"><circle cx="22" cy="22" r="20" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="2"/><path d="M22 7 L31 31 L22 26 L13 31 Z" fill="${color}" stroke="#0d1117" stroke-width="1.5" stroke-linejoin="round"/></svg></div><div style="position:absolute;left:34px;top:-2px;padding:0 5px;border-radius:4px;background:${color};color:#0d1117;font:700 12px var(--font-ui);line-height:18px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.5)">${label}</div></div>`,
  })
}

function dogIcon(color: string, label: string, heading: number | null): L.DivIcon {
  const arrow = heading == null ? ''
    : `<div style="position:absolute;inset:0;transform:rotate(${heading}deg)"><svg viewBox="0 0 40 40" width="40" height="40"><path d="M20 2 L27 15 L20 12 L13 15 Z" fill="${color}" stroke="#0d1117" stroke-width="1.2" stroke-linejoin="round"/></svg></div>`
  return L.divIcon({
    className: 'dog2-icon',
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    html: `<div style="position:relative;width:40px;height:40px">${arrow}<svg viewBox="0 0 40 40" width="40" height="40" style="position:absolute;inset:0"><rect x="12" y="12" width="16" height="16" rx="5" fill="${color}" fill-opacity="0.9" stroke="#0d1117" stroke-width="1.5"/><circle cx="20" cy="20" r="3" fill="#0d1117"/></svg><div style="position:absolute;left:34px;top:9px;padding:0 5px;border-radius:4px;background:${color};color:#0d1117;font:700 12px var(--font-ui);line-height:18px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.5)">${label}</div></div>`,
  })
}

watchEffect(() => {
  const g = group('track')
  g.clearLayers()
  if (!props.layers.track) return
  for (const t of props.tracks) {
    const pts = t.filled.filter((s) => s.lat !== null && s.lon !== null).map((s) => ll({ lat: s.lat!, lon: s.lon! }))
    if (pts.length > 1) L.polyline(pts, { color: t.color, weight: 3, opacity: 0.9, interactive: false }).addTo(g)
  }
})

watchEffect(() => {
  const g = group('route')
  g.clearLayers()
  if (!props.layers.route) return
  for (const tr of props.tracks) {
    const wps = tr.detail.routeSnapshot?.waypoints ?? []
    if (!wps.length) continue
    const pts = wps.map((w) => ({ lat: w.lat, lon: w.lon }))
    L.polyline(pts.map(ll), { color: tr.color, weight: 2, dashArray: '8 6', opacity: 0.8, interactive: false }).addTo(g)
    pts.forEach((p, i) => L.marker(ll(p), { icon: pin(tr.color, '#0d1117', String(i + 1), t('{name} 航点 {n}', { name: tr.label, n: i + 1 })), interactive: false }).addTo(g))
  }
})

watchEffect(() => {
  const { tracks, layers } = props
  if (!tracks.some((tr) => tr.dogRoutes.length) && !groups.dogRoute) return
  const g = group('dogRoute')
  g.clearLayers()
  if (!layers.dogRoute) return
  for (const tr of tracks) {
    for (const route of tr.dogRoutes) {
      if (props.selectedDogRoute && route.id !== props.selectedDogRoute) continue
      if (route.points.length > 1) {
        L.polyline(route.points.map(ll), { className: 'dog-replay-route', color: '#e2e8f0', weight: 2, dashArray: '6 5', interactive: false }).addTo(g)
      }
      route.points.forEach((p, j) => {
        const title = t('路线 {route} · 第 {point} 个点', { route: route.number, point: j + 1 })
        L.marker(ll(p), {
          icon: pin('#e2e8f0', tr.color, String(j + 1), title),
          title: `${tr.label} · ${title}`,
          keyboard: false,
        }).addTo(g)
      })
    }
  }
})

watchEffect(() => {
  const g = group('pins')
  g.clearLayers()
  for (const tr of props.tracks) {
    const d = tr.detail
    if (d.homeLat != null && d.homeLon != null) {
      L.marker(ll({ lat: d.homeLat, lon: d.homeLon }), { icon: pin(tr.color, '#0d1117', 'H', t('{name} Home 点', { name: tr.label })), interactive: false }).addTo(g)
    }
    if (!props.layers.pins) continue
    for (const m of pinsOf(tr)) {
      const photo = m.kind === 'TakePhoto' || m.kind === 'StartRecording' || m.kind === 'StopRecording'
      const fill = photo ? '#e2e8f0' : m.level === 'CRITICAL' ? css('--danger', '#f85149') : css('--warn', '#f5a524')
      L.marker(ll(m.pos), { icon: pin(fill, tr.color, photo ? '◉' : '!', `${tr.label} · ${m.label}`) })
        .bindTooltip(`${tr.label} · ${m.label}`, { direction: 'top' }).addTo(g)
    }
  }
})

// moved every frame while playing: updated in place rather than redrawn
let link: L.Polyline | null = null
watchEffect(() => {
  const m = ctx.map.value
  const l = props.link
  if (!m || !props.layers.link || !l) {
    link?.remove()
    link = null
    return
  }
  const color = l.alarm ? css('--danger', '#f85149') : '#e2e8f0'
  const pts = [ll(l.a), ll(l.b)]
  if (!link) {
    link = L.polyline(pts, { color, weight: l.alarm ? 3 : 2, dashArray: '6 6', interactive: false })
      .bindTooltip(l.text, { permanent: true, direction: 'center', className: 'joint-link-tip' })
      .addTo(m)
  } else {
    link.setLatLngs(pts)
    link.setStyle({ color, weight: l.alarm ? 3 : 2 })
    link.setTooltipContent(l.text)
  }
})

const aircraft: (L.Marker | null)[] = []
watchEffect(() => {
  const m = ctx.map.value
  if (!m) return
  // a record taken out of the replay leaves no marker behind
  for (let i = props.tracks.length; i < aircraft.length; i++) {
    aircraft[i]?.remove()
    aircraft[i] = null
  }
  props.tracks.forEach((t, i) => {
    const s = props.states[i]
    if (!s || s.lat === null || s.lon === null) {
      aircraft[i]?.remove()
      aircraft[i] = null
      return
    }
    const p = ll({ lat: s.lat, lon: s.lon })
    const icon = t.kind === 'dog' ? dogIcon(t.color, t.label, s.attitudeHead ?? null) : aircraftIcon(t.color, t.label, s.attitudeHead ?? 0)
    const a = aircraft[i]
    if (!a) aircraft[i] = L.marker(p, { icon, zIndexOffset: 1000 + i, interactive: false, keyboard: false }).addTo(m)
    else {
      a.setLatLng(p)
      a.setIcon(icon)
    }
  })
})

onBeforeUnmount(() => {
  Object.values(groups).forEach((g) => g.remove())
  link?.remove()
  aircraft.forEach((a) => a?.remove())
})
</script>

<template><span class="sr-only">{{ t('回放图层') }}</span></template>

<style>
.dog-replay-route {
  filter: drop-shadow(0 0 1px #0d1117) drop-shadow(0 0 1px #0d1117);
}
.joint-link-tip {
  background: rgba(13, 17, 23, 0.85);
  color: #fff;
  border: none;
  font: 700 12px var(--font-ui);
}
</style>
