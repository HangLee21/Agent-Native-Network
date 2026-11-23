<script setup lang="ts">
/**
 * Everything the demo draws on the map (docs/demo-design.md §6): planned routes of the current stage,
 * tracks, aircraft with heading and camera footprint, the A–B link (animated while they "talk"),
 * target, recommended path, dog, its track and its semantic map cells.
 * Imperative Leaflet layers fed from the demo store; all positions go through toLatLng (WGS84 → base map).
 */
import { computed, inject, onBeforeUnmount, onMounted, watch } from 'vue'
import L from 'leaflet'
import { t } from '@/i18n'
import { MAP_CONTEXT } from '@/components/map/mapContext'
import { useDemoStore } from './useDemoStore'
import { COLORS, cellColor, stageIndex, type DemoDrone, type Label, type LatLon } from './demoApi'
import { distanceM, offset, project } from './demoGeo'

const props = withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
const ctx = inject(MAP_CONTEXT)!
const demo = useDemoStore()

const canvas = L.canvas({ padding: 0.3 })
const groups = {
  cells: L.layerGroup(),
  routes: L.layerGroup(),
  tracks: L.layerGroup(),
  fov: L.layerGroup(),
  path: L.layerGroup(),
  link: L.layerGroup(),
  marks: L.layerGroup(),
  drones: L.layerGroup(),
}
const drawnCells = new Set<string>()
const droneMarkers: Partial<Record<Label, L.Marker>> = {}
const trackLines: Partial<Record<Label, L.Polyline>> = {}
let dogMarker: L.Marker | null = null
let dogLine: L.Polyline | null = null

const ll = (p: LatLon) => ctx.toLatLng(p)
const stage = computed(() => demo.state?.stage ?? 'READY')

onMounted(() => {
  const m = ctx.map.value!
  Object.values(groups).forEach((g) => g.addTo(m))
})
onBeforeUnmount(() => Object.values(groups).forEach((g) => g.remove()))

// ---------------------------------------------------------------- planned routes

interface Plan {
  id: string | null
  label: Label
  strong: boolean
  name: string
  /** 'leg1': a first leg (ends at the rendezvous point); 'follow': the low follow route. */
  kind: 'leg1' | 'follow' | 'other'
}

const plans = computed<Plan[]>(() => {
  const s = demo.state
  if (!s) return []
  const i = stageIndex(s.stage === 'ABORTED' ? lastStageBeforeAbort() : s.stage)
  const hi = s.highLabel
  const lo = s.lowLabel
  const p: Plan[] = []
  const add = (id: string | null, label: Label, strong: boolean, name: string, kind: Plan['kind'] = 'other') =>
    id && p.push({ id, label, strong, name, kind })
  if (props.compact) {
    // console: every route, the current ones emphasised
    add(s.routes.A1, 'A', i <= 1, t('A 第一段'), 'leg1')
    add(s.routes.B1, 'B', i <= 1, t('B 第一段'), 'leg1')
    add(s.routes.high2, hi, i === 2 || i === 3, t('高空第二段'))
    add(s.routes.low2, lo, i === 2 || i === 3, t('低空第二段'))
    add(s.routes.lowFollow, lo, i >= 5, t('低空跟随'), 'follow')
    return p
  }
  if (i <= 2) {
    add(s.routes.A1, 'A', i <= 1, t('A 第一段'), 'leg1')
    add(s.routes.B1, 'B', i <= 1, t('B 第一段'), 'leg1')
  }
  if (i >= 2 && i <= 4) {
    add(s.routes.high2, hi, i >= 3, t('高空复查'))
    add(s.routes.low2, lo, i >= 3, t('低空复查'))
  }
  if (i >= 5) add(s.routes.lowFollow, lo, true, t('低空跟随'), 'follow')
  return p
})

function lastStageBeforeAbort() {
  const at = demo.state?.stageAt ?? {}
  const order = ['S4_GUIDE', 'S3_TARGET', 'S2_RESCAN', 'S1_RENDEZVOUS', 'S1_EXPLORE'] as const
  return order.find((s) => at[s] != null) ?? 'READY'
}

function drawRoutes(): void {
  groups.routes.clearLayers()
  for (const p of plans.value) {
    const r = p.id ? demo.routes[p.id] : undefined
    if (!r || r.waypoints.length === 0) continue
    const pts = r.waypoints.map((w) => ll(w))
    const color = COLORS[p.label]
    L.polyline(pts, { color, weight: p.strong ? 3 : 2, opacity: p.strong ? 0.85 : 0.35, dashArray: '6 8', interactive: false }).addTo(groups.routes)
    if (p.strong) {
      for (const w of r.waypoints.slice(0, -1)) {
        L.circleMarker(ll(w), { radius: 2.5, color, weight: 1, fillColor: color, fillOpacity: 0.8, interactive: false }).addTo(groups.routes)
      }
    }
    const end = r.waypoints[r.waypoints.length - 1]!
    const endLabel = p.kind === 'leg1' ? t('汇合点 {label}', { label: p.label }) : p.kind === 'follow' ? t('跟随终点') : t('{name}终点', { name: p.name })
    const otherPlan = plans.value.find((o) => o.label !== p.label && o.strong === p.strong)
    const otherRoute = otherPlan?.id ? demo.routes[otherPlan.id] : undefined
    const labelSide = side(p.label, end.lon, otherRoute?.waypoints[otherRoute.waypoints.length - 1]?.lon)
    // the aircraft parked on its end point already carries a label there: showing both makes neither readable
    const showLabel = p.strong && !props.compact && !parkedLabels.value.includes(`${p.id}:${p.label}`)
    L.marker(ll(end), {
      interactive: false,
      icon: L.divIcon({
        className: 'demo-endpoint',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
        html: `<div class="ep" style="border-color:${color};opacity:${p.strong ? 1 : 0.5}"></div>${showLabel ? `<span class="ep-label ${labelSide}" style="color:${color}">${endLabel}</span>` : ''}`,
      }),
    }).addTo(groups.routes)
  }
}

/** "routeId:label" of each shown route whose aircraft is within PARKED_M of the route's end point. */
const PARKED_M = 15
const parkedLabels = computed(() => {
  const out: string[] = []
  for (const p of plans.value) {
    const r = p.id ? demo.routes[p.id] : undefined
    const d = demo.byLabel[p.label]
    const end = r?.waypoints[r.waypoints.length - 1]
    if (end && d?.lat != null && d.lon != null && distanceM({ lat: d.lat, lon: d.lon }, end) <= PARKED_M) out.push(`${p.id}:${p.label}`)
  }
  return out
})

// parkedLabels changes only when an aircraft arrives at or leaves an end point, not on every position update
watch([plans, () => demo.routes, () => parkedLabels.value.join(',')], drawRoutes, { deep: false })

// ---------------------------------------------------------------- tracks

watch(
  () => demo.tracks,
  (tr) => {
    for (const label of ['A', 'B'] as Label[]) {
      const pts = tr[label].map((p) => ll(p))
      let line = trackLines[label]
      if (!line) {
        line = L.polyline([], { color: COLORS[label], weight: 3, opacity: 0.9, interactive: false }).addTo(groups.tracks)
        trackLines[label] = line
      }
      line.setLatLngs(pts)
    }
  },
  { immediate: true },
)

// ---------------------------------------------------------------- aircraft, camera footprint, link

/**
 * Which side a label goes on: away from the other aircraft (west one left, east one right), so A, B and the dog
 * standing close together at the base — or the two rendezvous points — do not cover each other's labels.
 */
function side(label: Label, lon: number, otherLon: number | null | undefined): 'left' | 'right' {
  if (otherLon == null || Math.abs(otherLon - lon) < 1e-9) return label === 'A' ? 'left' : 'right'
  return lon < otherLon ? 'left' : 'right'
}

function droneIcon(d: DemoDrone): L.DivIcon {
  const color = COLORS[d.label!]
  const head = d.heading ?? 0
  const h = d.relativeHeight == null ? '' : `${Math.round(d.relativeHeight)} m`
  const dim = d.online ? '' : 'opacity:.45;'
  // smaller on the ground: at the base both aircraft and the dog stand within a few metres
  const size = props.compact ? 34 : d.phase === 'GROUND' ? 30 : 46
  const other = demo.byLabel[d.label === 'A' ? 'B' : 'A']
  const tagSide = side(d.label!, d.lon!, other?.lon)
  return L.divIcon({
    className: 'demo-drone',
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div class="dr" style="${dim}width:${size}px;height:${size}px">
      <div class="dr-rot" style="transform:rotate(${head}deg)">
        <svg viewBox="0 0 44 44" width="${size}" height="${size}"><circle cx="22" cy="22" r="19" fill="${color}" fill-opacity="0.18" stroke="${color}" stroke-width="1.5"/>
        <path d="M22 6 L31 31 L22 26 L13 31 Z" fill="${color}" stroke="#0b1220" stroke-width="1.6" stroke-linejoin="round"/></svg>
      </div>
      <span class="dr-tag ${tagSide}" style="background:${color}">${d.label}<b>${h}</b></span>
    </div>`,
  })
}

function footprint(d: DemoDrone): LatLon[] | null {
  if (d.lat == null || d.lon == null || d.relativeHeight == null || d.relativeHeight < 2) return null
  const pitch = d.gimbalPitch ?? -30
  if (pitch > -5) return null
  const yaw = (d.heading ?? 0) + (d.gimbalYaw ?? 0)
  const centre = Math.min(150, Math.max(5, d.relativeHeight / Math.tan((-pitch * Math.PI) / 180)))
  const p = { lat: d.lat, lon: d.lon }
  const pts: LatLon[] = [p]
  for (let a = -34; a <= 34; a += 8.5) pts.push(project(p, yaw + a, centre * 1.25))
  return pts
}

watch(
  () => demo.drones,
  (ds) => {
    groups.fov.clearLayers()
    for (const d of ds) {
      if (!d.label || d.lat == null || d.lon == null) continue
      const pos = ll({ lat: d.lat, lon: d.lon })
      let mk = droneMarkers[d.label]
      if (!mk) {
        mk = L.marker(pos, { icon: droneIcon(d), zIndexOffset: 1000, interactive: false, keyboard: false }).addTo(groups.drones)
        droneMarkers[d.label] = mk
      } else {
        mk.setLatLng(pos)
        mk.setIcon(droneIcon(d))
      }
      const fp = footprint(d)
      if (fp && d.phase !== 'GROUND') {
        L.polygon(fp.map(ll), { color: COLORS[d.label], weight: 1, opacity: 0.5, fillOpacity: 0.12, interactive: false }).addTo(groups.fov)
      }
    }
    drawLinks()
    drawDog()
  },
  { immediate: true },
)

/** A function, not a computed: it depends on the clock, and the drones watcher above calls it during setup. */
function isTalking(): boolean {
  const c = demo.lastComm
  return stage.value === 'S1_RENDEZVOUS' || (!!c && Date.now() - c.at < 6000 && ['A', 'B'].includes(c.from) && ['A', 'B'].includes(c.to))
}

function drawLinks(): void {
  groups.link.clearLayers()
  const a = demo.byLabel.A
  const b = demo.byLabel.B
  const s = stage.value
  if (a?.lat != null && b?.lat != null && s !== 'READY' && a.phase !== 'GROUND' && b.phase !== 'GROUND') {
    const on = isTalking()
    const line = L.polyline([ll({ lat: a.lat, lon: a.lon! }), ll({ lat: b.lat, lon: b.lon! })], {
      color: COLORS.link,
      weight: on ? 3 : 1.5,
      opacity: on ? 0.95 : 0.35,
      dashArray: on ? '4 10' : '2 8',
      className: on ? 'demo-flow' : '',
      interactive: false,
    }).addTo(groups.link)
    if (!props.compact && demo.link) {
      line.bindTooltip(on ? t('通信中 · {d} m', { d: Math.round(demo.link.horizontalM) }) : t('链路 · {d} m', { d: Math.round(demo.link.horizontalM) }), {
        permanent: true,
        direction: 'center',
        className: on ? 'demo-link-tip on' : 'demo-link-tip',
      })
    }
  }
  const low = demo.state ? demo.byLabel[demo.state.lowLabel] : undefined
  const dg = demo.dog
  if (s === 'S4_GUIDE' && low?.lat != null && dg?.lat != null && dg.lon != null && demo.state?.dogMode !== 'SKIP') {
    L.polyline([ll({ lat: low.lat, lon: low.lon! }), ll({ lat: dg.lat, lon: dg.lon })], {
      color: COLORS.dog,
      weight: 2.5,
      opacity: 0.9,
      dashArray: '4 10',
      className: 'demo-flow',
      interactive: false,
    }).addTo(groups.link)
  }
}

let linkTimer = 0
onMounted(() => (linkTimer = window.setInterval(drawLinks, 1000))) // the "talking" window ends without a new frame
onBeforeUnmount(() => window.clearInterval(linkTimer))

// ---------------------------------------------------------------- target, recommended path

watch(
  () => [demo.state?.target, demo.state?.dogPath, demo.state?.dogMode] as const,
  ([tg, path, mode]) => {
    groups.marks.clearLayers()
    groups.path.clearLayers()
    if (path && path.length >= 2 && mode !== 'SKIP') {
      L.polyline(path.map(ll), { color: COLORS.dog, weight: 3, opacity: 0.85, dashArray: '10 8', interactive: false }).addTo(groups.path)
    }
    if (tg) {
      L.marker(ll(tg), {
        interactive: false,
        zIndexOffset: 900,
        icon: L.divIcon({
          className: 'demo-target',
          iconSize: [28, 28],
          iconAnchor: [14, 14],
          html: `<div class="tg-pulse"></div><div class="tg-dot"></div>${props.compact ? '' : `<span class="tg-label">${t('采样目标')}</span>`}`,
        }),
      }).addTo(groups.marks)
    }
  },
  { immediate: true },
)

// ---------------------------------------------------------------- dog

function drawDog(): void {
  const dg = demo.dog
  const s = demo.state
  const show = !!dg && s?.dogMode !== 'SKIP' && dg.lat != null && dg.lon != null && stageIndex(s?.stage ?? 'READY') >= 0
  if (!show) {
    dogMarker?.remove()
    dogMarker = null
    return
  }
  const pos = ll({ lat: dg!.lat!, lon: dg!.lon! })
  const icon = L.divIcon({
    className: 'demo-dog',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    html: `<div class="dg" style="opacity:${dg!.online ? 1 : 0.45}"><div class="dg-rot" style="transform:rotate(${dg!.heading ?? 0}deg)">
      <svg viewBox="0 0 30 30" width="30" height="30"><rect x="7" y="7" width="16" height="16" rx="4" transform="rotate(45 15 15)" fill="${COLORS.dog}" stroke="#0b1220" stroke-width="1.5"/>
      <path d="M15 3 L19 9 L11 9 Z" fill="#0b1220"/></svg></div>${props.compact ? '' : `<span class="dg-label">${t('机器狗')}</span>`}</div>`,
  })
  if (!dogMarker) dogMarker = L.marker(pos, { icon, zIndexOffset: 950, interactive: false }).addTo(groups.drones)
  else {
    dogMarker.setLatLng(pos)
    dogMarker.setIcon(icon)
  }
}

watch(() => demo.dog, drawDog)

watch(
  () => demo.dogTrack,
  (tr) => {
    if (!dogLine) dogLine = L.polyline([], { color: COLORS.dog, weight: 3, opacity: 0.95, interactive: false }).addTo(groups.tracks)
    dogLine.setLatLngs(tr.map((p) => ll(p)))
  },
  { immediate: true },
)

// ---------------------------------------------------------------- semantic map cells

watch(
  () => demo.cellsVersion,
  () => {
    if (demo.cells.size === 0) {
      groups.cells.clearLayers()
      drawnCells.clear()
      return
    }
    for (const [key, c] of demo.cells) {
      const id = key + c.label
      if (drawnCells.has(id)) continue
      drawnCells.add(id)
      const h = c.sizeM / 2
      const sw = offset(c, -h, -h)
      const ne = offset(c, h, h)
      L.rectangle([ll(sw) as L.LatLngTuple, ll(ne) as L.LatLngTuple], {
        renderer: canvas,
        stroke: false,
        fillColor: cellColor(c.label),
        fillOpacity: 0.55,
        interactive: false,
      }).addTo(groups.cells)
    }
  },
  { immediate: true },
)
</script>

<template><span class="sr-only">{{ t('演示地图图层') }}</span></template>

<style>
.demo-drone .dr {
  position: relative;
}
.demo-drone .dr-rot {
  position: absolute;
  inset: 0;
}
.demo-drone .dr-tag {
  position: absolute;
  left: 70%;
  top: -6px;
  padding: 1px 6px;
  border-radius: 9px;
  color: #0b1220;
  font: 700 12px/16px var(--font-ui);
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
}
.demo-drone .dr-tag.left {
  left: auto;
  right: 70%;
}
.demo-drone .dr-tag b {
  margin-left: 4px;
  font-weight: 600;
  font-family: var(--font-num);
}
.demo-endpoint .ep {
  width: 14px;
  height: 14px;
  border: 2.5px solid;
  border-radius: 50%;
  background: rgba(11, 18, 32, 0.6);
}
.demo-endpoint .ep-label {
  position: absolute;
  left: 18px;
  top: -2px;
  font: 600 12px var(--font-ui);
  white-space: nowrap;
  text-shadow: 0 0 3px #000, 0 0 3px #000;
}
.demo-endpoint .ep-label.left {
  left: auto;
  right: 18px;
}
.demo-target .tg-dot {
  position: absolute;
  left: 8px;
  top: 8px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #f43f5e;
  border: 2px solid #fff;
}
.demo-target .tg-pulse {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 3px solid #f43f5e;
  animation: demo-pulse 1.6s ease-out infinite;
}
.demo-target .tg-label,
.demo-dog .dg-label {
  position: absolute;
  left: 30px;
  top: 4px;
  font: 700 13px var(--font-ui);
  color: #fff;
  white-space: nowrap;
  text-shadow: 0 0 3px #000, 0 0 4px #000;
}
.demo-dog .dg-label {
  left: 50%;
  top: 30px;
  transform: translateX(-50%);
}
.demo-dog .dg {
  position: relative;
  width: 30px;
  height: 30px;
}
.demo-dog .dg-rot {
  position: absolute;
  inset: 0;
}
@keyframes demo-pulse {
  0% {
    transform: scale(0.5);
    opacity: 1;
  }
  100% {
    transform: scale(2.4);
    opacity: 0;
  }
}
.leaflet-overlay-pane path.demo-flow {
  animation: demo-flow 0.8s linear infinite;
}
@keyframes demo-flow {
  to {
    stroke-dashoffset: -28;
  }
}
.demo-link-tip {
  background: rgba(11, 18, 32, 0.75);
  border: 1px solid rgba(226, 232, 240, 0.4);
  color: #e2e8f0;
  font: 600 12px var(--font-ui);
  box-shadow: none;
  padding: 2px 8px;
}
.demo-link-tip.on {
  border-color: #e2e8f0;
  color: #fff;
}
.demo-link-tip::before {
  display: none;
}
</style>
