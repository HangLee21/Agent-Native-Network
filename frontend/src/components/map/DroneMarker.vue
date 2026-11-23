<script setup lang="ts">
/**
 * Live aircraft position and heading (R-02). Grey when the link is stale (last known position), grey and "定位中" at
 * the last fix while the drone reports no position (no satellites yet). With several drones
 * (D-31, ui-design.md 2.7) each marker has its drone's colour and name; only the selected one follows.
 */
import { inject, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import { MAP_CONTEXT } from './mapContext'
import { useTelemetryStore } from '@/stores/telemetry'
import { useLayersStore } from '@/stores/layers'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ follow?: boolean; color?: string; label?: string; selected?: boolean }>(),
  { follow: false, color: 'var(--accent)', label: '', selected: true })
const ctx = inject(MAP_CONTEXT)!
const tel = useTelemetryStore()
const layers = useLayersStore()

/** Stale: seconds since the last telemetry, shown on the tag (the position is the last known one, not where it is). */
function icon(heading: number, live: boolean, locating: boolean, lostS: number): L.DivIcon {
  const color = live && !locating ? props.color : 'var(--text-dim)'
  const ring = props.selected ? 2.5 : 1.5
  const text = live
    ? [props.label, locating ? t('定位中') : ''].filter(Boolean).join(' · ')
    : props.label ? t('{name} 失联 {n} 秒 · 最后位置', { name: props.label, n: lostS }) : t('失联 {n} 秒 · 最后位置', { n: lostS })
  const tag = text
    ? `<div style="position:absolute;left:36px;top:-2px;padding:0 5px;border-radius:4px;background:${color};color:#0d1117;font:700 12px var(--font-ui);line-height:18px;white-space:nowrap;box-shadow:0 1px 3px rgba(0,0,0,.5)">${text}</div>`
    : ''
  return L.divIcon({
    className: 'drone-icon',
    iconSize: [44, 44],
    iconAnchor: [22, 22],
    html: `<div style="position:relative;width:44px;height:44px"><div style="width:44px;height:44px;transform:rotate(${heading}deg)">
      <svg viewBox="0 0 44 44" width="44" height="44"><circle cx="22" cy="22" r="20" fill="${color}" fill-opacity="0.16" stroke="${color}" stroke-width="${ring}"/>
      <path d="M22 7 L31 31 L22 26 L13 31 Z" fill="${color}" stroke="#0d1117" stroke-width="1.5" stroke-linejoin="round"/></svg></div>${tag}</div>`,
  })
}

let marker: L.Marker | null = null
// a map re-created for a base-map switch keeps the user's view instead of jumping to the drone
let firstFix = !ctx.recreated()

watch(
  // follow is a source too: turning it back on re-centres at once, not at the next position
  () => [tel.position, tel.drone?.attitudeHead, tel.linkFresh, layers.isVisible('drone'), props.follow, tel.locating,
    tel.linkFresh ? 0 : Math.floor((tel.now - tel.lastUpdateAt) / 1000)] as const,
  ([pos, head, live, shown, , locating, lostS]) => {
    const m = ctx.map.value
    if (!m) return
    if (!pos || !shown) {
      marker?.remove()
      marker = null
      return
    }
    const ll = ctx.toLatLng(pos)
    // "定位中" only while telemetry is live; a stale link already shows grey at the last known position
    const ic = icon(head ?? 0, live, live && locating, lostS)
    if (!marker) {
      marker = L.marker(ll, { icon: ic, zIndexOffset: 1000, keyboard: false, interactive: false }).addTo(m)
    } else {
      marker.setLatLng(ll)
      marker.setIcon(ic)
    }
    if ((firstFix && props.selected) || props.follow) {
      // no pan animation: telemetry arrives faster than the animation finishes, which kept the map
      // pane at fractional pixel offsets and showed hairline seams between base-map tiles
      m.panTo(ll, { animate: false })
      firstFix = false
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => marker?.remove())
</script>

<template><span class="sr-only">{{ t('无人机位置') }}</span></template>
