<script setup lang="ts">
/**
 * Joint replay timeline (D-33, D-40; ui-design.md 2.6.1, 2.7.1): per drone a phase lane, per device an event lane
 * (commands as ticks, alerts as diamonds, photos as dots) in its colour; with two drones a lane with the
 * proximity-alarm periods. Then charts with one line per device: height (drones), horizontal speed (all), and with
 * two drones their horizontal separation with the base distance dashed. One cursor line crosses all of them; click
 * or drag to move it, click a marker to jump to it.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { time } from '@/utils/format'
import type { FilledSample } from '@/utils/replay'
import { PHASE_LABELS } from '@/utils/replay'
import type { Separation, Track } from '@/utils/jointReplay'
import { t } from '@/i18n'

const props = defineProps<{
  start: number
  end: number
  cursor: number
  tracks: Track[]
  proximity: [number, number][]
  separation: { t: number; s: Separation | null }[]
  /** Base horizontal distance of the proximity rule, drawn on the separation chart. */
  baseM: number | null
  selectedDogRoute: string
}>()
const emit = defineEmits<{ (e: 'seek', t: number): void; (e: 'select-dog-route', id: string): void }>()

const wrap = ref<HTMLDivElement | null>(null)
const width = ref(800)
let ro: ResizeObserver | null = null
onMounted(() => {
  if (!wrap.value) return
  width.value = wrap.value.clientWidth || 800
  ro = new ResizeObserver(() => (width.value = wrap.value?.clientWidth || width.value))
  ro.observe(wrap.value)
})
onBeforeUnmount(() => ro?.disconnect())

const LABEL_W = 92
const RIGHT = 12
const LANE_H = 20
const CHART_H = 44
const CHART_GAP = 8
const lanesTop = 6

const drones = computed(() => props.tracks.filter((tr) => tr.kind === 'drone').length)
const lanes = computed(() => [
  ...props.tracks.flatMap((tr, i) => [
    ...(tr.kind === 'drone' ? [{ key: `p${i}`, label: t('{name} 阶段', { name: tr.label }), track: i, kind: 'phase' as const }] : []),
    ...(tr.dogRoutes.length ? [{ key: `n${i}`, label: t('{name} 导航', { name: tr.label }), track: i, kind: 'dog-nav' as const }] : []),
    { key: `e${i}`, label: t('{name} 事件', { name: tr.label }), track: i, kind: 'events' as const },
  ]),
  ...(drones.value >= 2 ? [{ key: 'prox', label: t('两机靠近'), track: -1, kind: 'proximity' as const }] : []),
])
const chartsTop = computed(() => lanesTop + lanes.value.length * LANE_H + 10)
const height = computed(() => chartsTop.value + charts.value.length * (CHART_H + CHART_GAP))

const span = computed(() => Math.max(1, props.end - props.start))
const x = (t: number) => LABEL_W + ((Math.min(props.end, Math.max(props.start, t)) - props.start) / span.value) * (width.value - LABEL_W - RIGHT)
const laneY = (i: number) => lanesTop + i * LANE_H + LANE_H / 2

const PHASE_OPACITY: Record<string, number> = { takeoff: 0.2, route: 0.45, flight: 0.3, rth: 0.15, landing: 0.2 }

interface Chart {
  key: string
  label: string
  top: number
  lines: { color: string; d: string }[]
  min: number
  max: number
  refY: number | null
}

function path(pts: [number, number][], y: (v: number) => number): string {
  const step = Math.max(1, Math.floor(pts.length / (width.value * 1.5)))
  let d = ''
  let prevT = -Infinity
  for (let i = 0; i < pts.length; i += step) {
    const [t, v] = pts[i]!
    // a gap of more than 10 s (not recorded, or no position) breaks the line
    d += `${d && t - prevT < 10_000 ? 'L' : 'M'}${x(t).toFixed(1)} ${y(v).toFixed(1)}`
    prevT = t
  }
  return d
}

const charts = computed<Chart[]>(() => {
  const series: { key: string; label: string; get: (s: FilledSample) => number | null }[] = [
    ...(drones.value > 0 ? [{ key: 'height', label: t('高度 m'), get: (s: FilledSample) => s.height }] : []),
    { key: 'speed', label: t('水平速度 m/s'), get: (s) => s.horizontalSpeed },
  ]
  const out: Chart[] = series.map((c, ci) => {
    const top = chartsTop.value + ci * (CHART_H + CHART_GAP)
    const per = props.tracks.map((t) => t.filled.map((s) => [s.ts, c.get(s)] as const).filter((p): p is readonly [number, number] => p[1] != null))
    const vals = per.flat().map((p) => p[1])
    const min = Math.min(0, ...(vals.length ? vals : [0]))
    let max = vals.length ? Math.max(...vals) : 1
    if (max <= min) max = min + 1
    const y = (v: number) => top + CHART_H - ((v - min) / (max - min)) * CHART_H
    return { key: c.key, label: c.label, top, min, max, refY: null,
      lines: per.map((pts, i) => ({ color: props.tracks[i]!.color, d: path(pts.map((p) => [p[0], p[1]]), y) })) }
  })
  if (drones.value < 2) return out
  const top = chartsTop.value + out.length * (CHART_H + CHART_GAP)
  const pts = props.separation.filter((p) => p.s !== null).map((p) => [p.t, p.s!.horizontalM] as [number, number])
  const vals = pts.map((p) => p[1])
  let max = Math.max(vals.length ? Math.max(...vals) : 1, (props.baseM ?? 0) * 1.5)
  if (max <= 0) max = 1
  const y = (v: number) => top + CHART_H - (v / max) * CHART_H
  out.push({ key: 'separation', label: t('两机水平间距 m'), top, min: 0, max, refY: props.baseM !== null ? y(props.baseM) : null,
    lines: [{ color: 'var(--text)', d: path(pts, y) }] })
  return out
})

const cursorX = computed(() => x(props.cursor))

let dragging = false
function seekAt(ev: PointerEvent): void {
  const rect = (ev.currentTarget as SVGElement).getBoundingClientRect()
  const t = props.start + ((ev.clientX - rect.left - LABEL_W) / (width.value - LABEL_W - RIGHT)) * span.value
  emit('seek', Math.min(props.end, Math.max(props.start, t)))
}
function down(ev: PointerEvent): void {
  dragging = true
  ;(ev.currentTarget as SVGElement).setPointerCapture?.(ev.pointerId)
  seekAt(ev)
}
function move(ev: PointerEvent): void {
  if (dragging) seekAt(ev)
}
function up(): void {
  dragging = false
}

const fmt = (v: number) => (Math.abs(v) >= 100 ? Math.round(v).toString() : v.toFixed(1))
const isPhoto = (kind: string) => kind === 'TakePhoto' || kind === 'StartRecording' || kind === 'StopRecording'
</script>

<template>
  <div ref="wrap" class="timeline">
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="t('回放时间轴')" data-test="joint-timeline"
      @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
      <g v-for="(lane, li) in lanes" :key="lane.key">
        <rect v-if="lane.track >= 0" x="2" :y="laneY(li) - 6" width="4" height="12" rx="2" :fill="tracks[lane.track]!.color" />
        <text :x="10" :y="laneY(li) + 4" class="lane-label">{{ lane.label }}</text>
        <line :x1="LABEL_W" :x2="width - RIGHT" :y1="laneY(li)" :y2="laneY(li)" class="grid" />
        <template v-if="lane.kind === 'phase'">
          <g v-for="p in tracks[lane.track]!.phases" :key="`${p.kind}-${p.start}`">
            <rect :x="x(p.start)" :y="laneY(li) - 7" :width="Math.max(2, x(p.end) - x(p.start))" height="14" rx="4"
              :fill="tracks[lane.track]!.color" :fill-opacity="PHASE_OPACITY[p.kind]" :stroke="tracks[lane.track]!.color" />
            <text v-if="x(p.end) - x(p.start) > 40" :x="(x(p.start) + x(p.end)) / 2" :y="laneY(li) + 4" class="phase-label">{{ PHASE_LABELS[p.kind] }}</text>
          </g>
        </template>
        <template v-else-if="lane.kind === 'dog-nav'">
          <g v-for="plan in tracks[lane.track]!.dogRoutes" :key="plan.id" class="dog-nav-span"
            :class="{ selected: plan.id === selectedDogRoute }" :style="{ '--route-color': tracks[lane.track]!.color }"
            :data-test="`dog-nav-span-${plan.number}`" @pointerdown.stop="emit('select-dog-route', plan.id)">
            <title>{{ t('{name} · 第 {n} 次 · {time} · {count} 个点', {
              name: tracks[lane.track]!.label, n: plan.number, time: time(plan.start), count: plan.points.length,
            }) }}</title>
            <rect :x="x(plan.start)" :y="laneY(li) - 7" :width="Math.max(4, x(plan.end ?? plan.start) - x(plan.start))" height="14" rx="3" />
            <text v-if="plan.end !== null && x(plan.end) - x(plan.start) > 18"
              :x="(x(plan.end) + x(plan.start)) / 2" :y="laneY(li) + 4" class="phase-label">{{ plan.number }}</text>
          </g>
        </template>
        <template v-else-if="lane.kind === 'events'">
          <template v-for="m in tracks[lane.track]!.marks" :key="`m${m.ts}${m.kind}${m.label}`">
            <line v-if="m.kind !== 'ALERT_RAISED' && m.kind !== 'OBSTACLE' && m.kind !== 'DEVICE_MESSAGE'" :x1="x(m.ts)" :x2="x(m.ts)"
              :y1="laneY(li) - 7" :y2="laneY(li) + 7" :class="['tick', m.level === 'CRITICAL' ? 'bad' : '']" :stroke="tracks[lane.track]!.color"
              @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></line>
            <path v-else :d="`M${x(m.ts)} ${laneY(li) - 7}l7 7l-7 7l-7 -7z`" :class="['diamond', m.level === 'CRITICAL' ? 'bad' : 'warn']"
              @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></path>
          </template>
          <circle v-for="m in tracks[lane.track]!.photos.filter((p) => isPhoto(p.kind))" :key="`p${m.ts}`" :cx="x(m.ts)" :cy="laneY(li)" r="4"
            class="photo" @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></circle>
        </template>
        <template v-else>
          <rect v-for="s in proximity" :key="`x${s[0]}`" :x="x(s[0])" :y="laneY(li) - 6" :width="Math.max(3, x(s[1]) - x(s[0]))" height="12" rx="3"
            class="prox" @pointerdown.stop="emit('seek', s[0])"><title>{{ t('两机靠近告警') }}</title></rect>
        </template>
      </g>
      <g v-for="c in charts" :key="c.key" class="chart">
        <text :x="10" :y="c.top + CHART_H / 2 + 4" class="lane-label">{{ c.label }}</text>
        <text :x="LABEL_W - 4" :y="c.top + 9" class="axis" text-anchor="end">{{ fmt(c.max) }}</text>
        <text :x="LABEL_W - 4" :y="c.top + CHART_H" class="axis" text-anchor="end">{{ fmt(c.min) }}</text>
        <line :x1="LABEL_W" :x2="width - RIGHT" :y1="c.top + CHART_H" :y2="c.top + CHART_H" class="grid" />
        <line v-if="c.refY !== null" :x1="LABEL_W" :x2="width - RIGHT" :y1="c.refY" :y2="c.refY" class="limit"><title>{{ t('靠近判断的水平基础距离') }}</title></line>
        <path v-for="(l, i) in c.lines" :key="i" :d="l.d" class="series" :stroke="l.color" />
      </g>
      <g class="cursor" pointer-events="none">
        <line :x1="cursorX" :x2="cursorX" :y1="0" :y2="height" />
        <path :d="`M${cursorX - 6} 0L${cursorX + 6} 0L${cursorX} 8Z`" />
      </g>
    </svg>
  </div>
</template>

<style scoped>
.timeline {
  width: 100%;
  user-select: none;
}
svg {
  display: block;
  cursor: crosshair;
  touch-action: none;
}
.lane-label {
  font-size: 12px;
  fill: var(--text-dim);
}
.phase-label {
  font-size: 11px;
  fill: var(--text);
  text-anchor: middle;
  pointer-events: none;
}
.axis {
  font-size: 10.5px;
  fill: var(--text-dim);
  font-family: var(--font-num);
}
.grid {
  stroke: var(--border);
  stroke-width: 1;
}
.tick {
  stroke-width: 2;
  cursor: pointer;
}
.tick.bad {
  stroke: var(--danger);
  stroke-width: 3;
}
.diamond {
  cursor: pointer;
}
.diamond.warn { fill: var(--warn); }
.diamond.bad { fill: var(--danger); }
.photo {
  fill: var(--text-dim);
  cursor: pointer;
}
.prox {
  fill: color-mix(in srgb, var(--danger) 35%, transparent);
  stroke: var(--danger);
  cursor: pointer;
}
.dog-nav-span rect {
  fill: color-mix(in srgb, var(--route-color) 38%, transparent);
  stroke: var(--route-color);
  cursor: pointer;
}
.dog-nav-span.selected rect {
  fill: color-mix(in srgb, var(--route-color) 68%, transparent);
  stroke-width: 2px;
}
.limit {
  stroke: var(--danger);
  stroke-dasharray: 4 4;
}
.series {
  fill: none;
  stroke-width: 1.5;
}
.cursor line {
  stroke: var(--accent);
  stroke-width: 1.5;
}
.cursor path {
  fill: var(--accent);
}
</style>
