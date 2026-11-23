<script setup lang="ts">
/**
 * Outdoor navigation of the new dog system on the map (docs/dog/ui-design.md 19.5; layer "dogNav" in the layer panel):
 * for every dog that can navigate and has a task on — its points and the line through them (points already reached in
 * grey, the one being walked to ringed), the path the dog plans now (nav.path, dashed), the arrival radius around each
 * point, the fused position the navigation uses (nav.pose, with its uncertainty), and a tag next to the dog when it is
 * paused (the reason) or walks with avoidance off ("避障关"). The allowed area of the dog's last check is drawn while
 * a task is on or points are being picked. Everything arrives in WGS84 and is drawn in the base map's coordinates.
 * The dog list is polled by DogV2Layer (same map); this layer only draws.
 */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useDog2Store } from '@/stores/dogv2'
import { useLayersStore } from '@/stores/layers'
import { NAV_SETTINGS_DEFAULT, type Dog2 } from '@/api/dogv2'
import { navPoints, navReason, navTaskOn } from '@/components/dog/dogNav'
import { t } from '@/i18n'

const COLOR = '#a3e635'
const CASING = '#0d1117'
const ZONE = '#3fb950'
const ctx = inject(MAP_CONTEXT)!
const v2 = useDog2Store()
const layers = useLayersStore()
const group = L.layerGroup()

function esc(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

function pointIcon(i: number, state: 'done' | 'cur' | 'next'): L.DivIcon {
  const bg = state === 'done' ? 'var(--text-dim)' : COLOR
  const ring = state === 'cur' ? `box-shadow:0 0 0 3px ${COLOR},0 1px 4px rgba(0,0,0,.6);` : 'box-shadow:0 1px 4px rgba(0,0,0,.6);'
  return L.divIcon({
    className: `dog-nav-pt ${state}`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
    html: `<div style="width:20px;height:20px;border-radius:50%;background:${bg};color:#0d1117;display:flex;align-items:center;justify-content:center;font:700 11px var(--font-num);border:2px solid #0d1117;${ring}">${i + 1}</div>`,
  })
}

function tagIcon(parts: { text: string; fill: boolean }[]): L.DivIcon {
  const html = parts.map((p) => `<span style="display:inline-block;margin-right:4px;padding:0 5px;border-radius:4px;font:700 11px var(--font-ui);line-height:17px;white-space:nowrap;${p.fill ? 'background:#f5a524;color:#0d1117' : 'border:1.5px solid #f5a524;color:#f5a524;background:rgba(13,17,23,.85)'}">${esc(p.text)}</span>`).join('')
  // below the dog marker (DogV2Layer draws it 40 px tall, centred)
  return L.divIcon({ className: 'dog-nav-tag', iconSize: [1, 1], iconAnchor: [-14, -22], html: `<div style="white-space:nowrap">${html}</div>` })
}

function drawDog(d: Dog2, m: L.Map): void {
  const nav = d.nav ?? null
  const on = navTaskOn(nav)
  const editing = v2.navDraft?.dog === d.id
  const area = v2.navArea[d.id]
  if ((on || editing) && area && area.length >= 3) {
    L.polygon(area.map(([lat, lon]) => ctx.toLatLng({ lat, lon })), { color: ZONE, weight: 2, dashArray: '8 6', fill: false, interactive: false, className: 'dog-nav-area' }).addTo(group)
  }
  if (!nav || !on) return
  const pts = navPoints(nav)
  const idx = nav.index ?? 0
  const radius = nav.arriveRadiusM ?? v2.navSettingsOf(d.id)?.arriveRadiusM ?? NAV_SETTINGS_DEFAULT.arriveRadiusM
  // a dark casing under each line keeps it readable on the light street map as well as on satellite imagery
  if (pts.length > 1) {
    const lls = pts.map((p) => ctx.toLatLng(p))
    L.polyline(lls, { color: CASING, weight: 6, opacity: 0.55, interactive: false, className: 'dog-nav-line-casing' }).addTo(group)
    L.polyline(lls, { color: COLOR, weight: 3, opacity: 0.95, interactive: false, className: 'dog-nav-line' }).addTo(group)
  }
  pts.forEach((p, i) => {
    const ll = ctx.toLatLng(p)
    L.circle(ll, { radius, color: COLOR, weight: 1, dashArray: '3 4', fillOpacity: 0.05, interactive: false, className: 'dog-nav-radius' }).addTo(group)
    const state = i < idx ? 'done' : i === idx ? 'cur' : 'next'
    L.marker(ll, { icon: pointIcon(i, state), interactive: false, keyboard: false, zIndexOffset: 800 }).addTo(group)
  })
  const path = (nav.path ?? []).filter((q) => Array.isArray(q) && q.length >= 2)
  if (path.length > 1) {
    const lls = path.map(([lat, lon]) => ctx.toLatLng({ lat, lon }))
    L.polyline(lls, { color: CASING, weight: 6, opacity: 0.55, interactive: false, className: 'dog-nav-path-casing' }).addTo(group)
    L.polyline(lls, { color: '#f8fafc', weight: 2.5, dashArray: '6 6', opacity: 1, interactive: false, className: 'dog-nav-path' }).addTo(group)
  }
  const pose = nav.pose ?? null
  if (pose) {
    const ll = ctx.toLatLng(pose)
    if (pose.std_m != null && pose.std_m > 0) L.circle(ll, { radius: pose.std_m, color: COLOR, weight: 0, fillOpacity: 0.12, interactive: false, className: 'dog-nav-std' }).addTo(group)
    L.circleMarker(ll, { radius: 5, color: COLOR, weight: 2, fill: false, interactive: false, className: 'dog-nav-pose' }).addTo(group)
  }
  const at = pose ?? (d.position?.lat != null && d.position.lon != null ? { lat: d.position.lat, lon: d.position.lon } : null)
  const tags: { text: string; fill: boolean }[] = []
  if (nav.state === 'paused') tags.push({ text: t('暂停：{reason}', { reason: navReason(nav) || '—' }), fill: true })
  if (nav.avoidance === false) tags.push({ text: t('避障关'), fill: false })
  if (at && tags.length) L.marker(ctx.toLatLng(at), { icon: tagIcon(tags), interactive: false, keyboard: false, zIndexOffset: 1000 }).addTo(group)
}

function render(): void {
  const m = ctx.map.value
  if (!m) return
  group.addTo(m)
  group.clearLayers()
  if (!layers.isVisible('dogNav')) return
  for (const d of v2.dogs) if (d.navCapability) drawDog(d, m)
}

watch(() => [v2.dogs, v2.navArea, v2.navDraft?.dog, layers.isVisible('dogNav'), ctx.map.value] as const, render, { deep: true, immediate: true })
onBeforeUnmount(() => group.remove())
</script>

<template><span class="sr-only">{{ t('机器狗导航') }}</span></template>
