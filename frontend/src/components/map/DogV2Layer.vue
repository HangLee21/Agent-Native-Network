<script setup lang="ts">
/**
 * Dogs of the new dog system on the same map as the drones (R-34, R-02, R-03; docs/dog/v2/protocol.md section 8):
 * the GNSS position (WGS84, shown in the base map's coordinates like the drones) with the heading as an arrow, and
 * the track walked since the page opened. Solid arrow: the dog's own heading (dual-antenna receiver, or the motion
 * host's yaw aligned to the GNSS course); hollow arrow: the direction of travel (only while walking); no arrow: no
 * heading. Grey at the last fix while the receiver has no fix ("定位中") or the dog stopped reporting.
 * Polls the new dog system only while it is on (DOG2_MODE not off).
 * follow: the model of the dog being operated (e.g. 'lite3'); the map keeps that dog centred while it has a fix.
 */
import { inject, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useDog2Store } from '@/stores/dogv2'
import { useLayersStore } from '@/stores/layers'
import { dog2Api, type Dog2 } from '@/api/dogv2'
import { t } from '@/i18n'

const COLOR = '#a3e635'
const STALE_MS = 5000
const TRACK_MAX = 2000

const props = withDefaults(defineProps<{ follow?: string | null }>(), { follow: null })
const ctx = inject(MAP_CONTEXT)!
const store = useDog2Store()
const layers = useLayersStore()
const now = ref(Date.now())
let clock: number | null = null
let started = false

interface Seen { lat: number; lon: number; heading: number | null; solid: boolean; at: number }
const last: Record<string, Seen> = {}
const tracks: Record<string, [number, number][]> = {}
const markers: Record<string, L.Marker> = {}
const lines: Record<string, L.Polyline> = {}

function icon(label: string, heading: number | null, solid: boolean, grey: boolean, tag: string): L.DivIcon {
  const color = grey ? 'var(--text-dim)' : COLOR
  const arrow = heading == null ? ''
    : `<div style="position:absolute;inset:0;transform:rotate(${heading}deg)"><svg viewBox="0 0 40 40" width="40" height="40">
       <path d="M20 2 L27 15 L20 12 L13 15 Z" fill="${solid ? color : 'none'}" stroke="${solid ? '#0d1117' : color}" stroke-width="${solid ? 1.2 : 2}" stroke-linejoin="round"/></svg></div>`
  const text = [label, tag].filter(Boolean).join(' · ')
  return L.divIcon({
    className: 'dog2-icon',
    iconSize: [40, 40],
    iconAnchor: [20, 20],
    html: `<div style="position:relative;width:40px;height:40px">${arrow}
      <svg viewBox="0 0 40 40" width="40" height="40" style="position:absolute;inset:0"><rect x="12" y="12" width="16" height="16" rx="5" fill="${color}" fill-opacity="0.9" stroke="#0d1117" stroke-width="1.5"/>
      <circle cx="20" cy="20" r="3" fill="#0d1117"/></svg>
      <div style="position:absolute;left:34px;top:9px;padding:0 5px;border-radius:4px;background:${color};color:#0d1117;font:700 12px var(--font-ui);line-height:18px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.5)">${text}</div></div>`,
  })
}

function metres(a: [number, number], b: [number, number]): number {
  const dy = (b[0] - a[0]) * 111_320
  const dx = (b[1] - a[1]) * 111_320 * Math.cos((a[0] * Math.PI) / 180)
  return Math.hypot(dx, dy)
}

function draw(d: Dog2, m: L.Map): void {
  const p = d.position
  const ageMs = d.positionAgeMs ?? Infinity
  const fresh = d.online && p != null && ageMs <= STALE_MS
  if (fresh && p.lat != null && p.lon != null) {
    const solid = p.heading_source === 'receiver' || p.heading_source === 'imu_aligned'
    last[d.id] = { lat: p.lat, lon: p.lon, heading: p.heading_deg ?? null, solid, at: now.value }
    const tr = (tracks[d.id] ??= [])
    const pt: [number, number] = [p.lat, p.lon]
    if (!tr.length || metres(tr[tr.length - 1]!, pt) >= 0.5) tr.push(pt)
    if (tr.length > TRACK_MAX) tr.splice(0, tr.length - TRACK_MAX)
  } else if (fresh && last[d.id]) {
    last[d.id]!.heading = p?.heading_deg ?? null
  }
  const s = last[d.id]
  if (!s || !layers.isVisible('dogs')) {
    markers[d.id]?.remove()
    delete markers[d.id]
  } else {
    const locating = fresh && (p?.lat == null)
    const tag = !fresh
      ? t('失联 {n} 秒 · 最后位置', { n: Math.round(Math.min(ageMs, now.value - s.at) / 1000) })
      : locating ? t('定位中') : ''
    const ic = icon(d.label, fresh ? s.heading : null, s.solid, !fresh || locating, tag)
    const ll = ctx.toLatLng({ lat: s.lat, lon: s.lon })
    if (!markers[d.id]) markers[d.id] = L.marker(ll, { icon: ic, zIndexOffset: 900, keyboard: false, interactive: false }).addTo(m)
    else markers[d.id]!.setLatLng(ll).setIcon(ic)
    // no pan animation, like the drone marker (tile seams)
    if (props.follow && d.model === props.follow && fresh && !locating) m.panTo(ll, { animate: false })
  }
  const tr = tracks[d.id]
  if (!tr || tr.length < 2 || !layers.isVisible('dogTrack')) {
    lines[d.id]?.remove()
    delete lines[d.id]
  } else {
    const lls = tr.map(([lat, lon]) => ctx.toLatLng({ lat, lon }))
    if (!lines[d.id]) lines[d.id] = L.polyline(lls, { color: COLOR, weight: 3, opacity: 0.8, interactive: false }).addTo(m)
    else lines[d.id]!.setLatLngs(lls)
  }
}

watch(
  // follow is a source too: turning it back on re-centres at once
  () => [store.dogs, now.value, layers.isVisible('dogs'), layers.isVisible('dogTrack'), ctx.map.value, props.follow] as const,
  ([dogs, , , , m]) => {
    if (!m) return
    const ids = new Set(dogs.map((d) => d.id))
    for (const id of Object.keys(markers)) if (!ids.has(id)) { markers[id]!.remove(); delete markers[id] }
    for (const id of Object.keys(lines)) if (!ids.has(id)) { lines[id]!.remove(); delete lines[id] }
    for (const d of dogs) if (d.capabilities?.position || d.position) draw(d, m)
  },
)

let gone = false

// the new dog system is polled only when it is on (DOG2_MODE not off), like the status bar's "新狗系统" tab
onMounted(() => {
  dog2Api.list().then((r) => {
    if (r.mode === 'off' || gone) return
    store.start()
    started = true
    clock = window.setInterval(() => { now.value = Date.now() }, 1000)
  }).catch(() => undefined)
})

onBeforeUnmount(() => {
  gone = true
  if (started) store.stop()
  if (clock !== null) window.clearInterval(clock)
  Object.values(markers).forEach((x) => x.remove())
  Object.values(lines).forEach((x) => x.remove())
})
</script>

<template><span class="sr-only">{{ t('机器狗位置') }}</span></template>
