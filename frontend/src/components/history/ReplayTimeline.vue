<script setup lang="ts">
/**
 * Replay timeline (ui-design.md §2.6): lanes for phases, commands, alerts, photos and link gaps,
 * then height, speed and battery charts on the same time axis; one cursor line crosses all of them.
 * Click or drag anywhere to move the cursor; click a marker to jump to it.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { FilledSample, Mark, Phase } from '@/utils/replay'
import { PHASE_LABELS } from '@/utils/replay'
import { t } from '@/i18n'

const props = defineProps<{
  start: number
  end: number
  cursor: number
  filled: FilledSample[]
  phases: Phase[]
  commands: Mark[]
  alerts: Mark[]
  photos: Mark[]
  targets: Mark[]
  gaps: [number, number][]
}>()
const emit = defineEmits<{ (e: 'seek', t: number): void }>()

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

const LABEL_W = 76
const RIGHT = 12
const LANE_H = 22
const LANES = [t('阶段'), t('指令'), t('告警'), t('拍照'), t('目标'), t('断链')] as const
const CHART_H = 52
const CHART_GAP = 8
const lanesTop = 6
const chartsTop = lanesTop + LANES.length * LANE_H + 10
const charts = [
  { key: 'height', label: t('高度 m'), get: (s: FilledSample) => s.height },
  { key: 'speed', label: t('水平速度 m/s'), get: (s: FilledSample) => s.horizontalSpeed },
  { key: 'battery', label: t('电量 %'), get: (s: FilledSample) => s.battery },
] as const
const height = chartsTop + charts.length * (CHART_H + CHART_GAP)

const span = computed(() => Math.max(1, props.end - props.start))
const x = (t: number) => LABEL_W + ((t - props.start) / span.value) * (width.value - LABEL_W - RIGHT)
const laneY = (i: number) => lanesTop + i * LANE_H + LANE_H / 2

const PHASE_COLORS: Record<string, string> = {
  takeoff: 'var(--ok)', route: 'var(--accent)', flight: 'var(--track)', rth: 'var(--warn)', landing: 'var(--ok)',
}

interface ChartPath {
  key: string
  label: string
  top: number
  d: string
  min: number
  max: number
  limitY: number | null
}

const chartPaths = computed<ChartPath[]>(() =>
  charts.map((c, ci) => {
    const top = chartsTop + ci * (CHART_H + CHART_GAP)
    const pts = props.filled.map((s) => [s.ts, c.get(s)] as const).filter((p): p is readonly [number, number] => p[1] !== null)
    const vals = pts.map((p) => p[1])
    const limit = c.key === 'height' ? (props.filled.find((s) => s.heightLimit !== null)?.heightLimit ?? null) : null
    let min = vals.length ? Math.min(...vals) : 0
    let max = vals.length ? Math.max(...vals) : 1
    if (c.key === 'battery') {
      min = 0
      max = 100
    }
    if (c.key !== 'battery') min = Math.min(0, min)
    if (max <= min) max = min + 1
    const y = (v: number) => top + CHART_H - ((v - min) / (max - min)) * CHART_H
    const step = Math.max(1, Math.floor(pts.length / (width.value * 1.5)))
    let d = ''
    for (let i = 0; i < pts.length; i += step) d += `${d ? 'L' : 'M'}${x(pts[i]![0]).toFixed(1)} ${y(pts[i]![1]).toFixed(1)}`
    return { key: c.key, label: c.label, top, d, min, max, limitY: limit !== null && limit <= max * 1.5 && limit >= min ? y(Math.min(limit, max)) : null }
  }),
)

const cursorX = computed(() => x(props.cursor))

let dragging = false
function seekAt(ev: PointerEvent): void {
  const rect = (ev.currentTarget as SVGElement).getBoundingClientRect()
  const px = ev.clientX - rect.left
  const t = props.start + ((px - LABEL_W) / (width.value - LABEL_W - RIGHT)) * span.value
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
</script>

<template>
  <div ref="wrap" class="timeline">
    <svg :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="t('回放时间轴')" data-test="replay-timeline"
      @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
      <g class="lanes">
        <g v-for="(name, i) in LANES" :key="name">
          <text :x="8" :y="laneY(i) + 4" class="lane-label">{{ name }}</text>
          <line :x1="LABEL_W" :x2="width - RIGHT" :y1="laneY(i)" :y2="laneY(i)" class="grid" />
        </g>
        <g v-for="p in phases" :key="`${p.kind}-${p.start}`">
          <rect :x="x(p.start)" :y="laneY(0) - 7" :width="Math.max(2, x(p.end) - x(p.start))" height="14" rx="4"
            :fill="PHASE_COLORS[p.kind]" fill-opacity="0.25" :stroke="PHASE_COLORS[p.kind]" />
          <text v-if="x(p.end) - x(p.start) > 40" :x="(x(p.start) + x(p.end)) / 2" :y="laneY(0) + 4" class="phase-label">{{ PHASE_LABELS[p.kind] }}</text>
        </g>
        <line v-for="m in commands" :key="`c${m.ts}${m.kind}`" :x1="x(m.ts)" :x2="x(m.ts)" :y1="laneY(1) - 7" :y2="laneY(1) + 7"
          :class="['tick', m.level === 'CRITICAL' ? 'bad' : '']" @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></line>
        <path v-for="m in alerts" :key="`a${m.ts}${m.label}`" :d="`M${x(m.ts)} ${laneY(2) - 7}l7 7l-7 7l-7 -7z`"
          :class="['diamond', m.level === 'CRITICAL' ? 'bad' : 'warn']" @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></path>
        <circle v-for="m in photos" :key="`p${m.ts}`" :cx="x(m.ts)" :cy="laneY(3)" r="4.5" class="photo" @pointerdown.stop="emit('seek', m.ts)">
          <title>{{ m.label }}</title>
        </circle>
        <rect v-for="m in targets" :key="`t${m.ts}${m.kind}`" :x="x(m.ts) - 3" :y="laneY(4) - 6" width="6" height="12" rx="2"
          :class="['target', m.level === 'INFO' ? '' : 'warn']" @pointerdown.stop="emit('seek', m.ts)"><title>{{ m.label }}</title></rect>
        <rect v-for="g in gaps" :key="`g${g[0]}`" :x="x(g[0])" :y="laneY(5) - 6" :width="Math.max(3, x(g[1]) - x(g[0]))" height="12" rx="3" class="gap">
          <title>{{ t('无遥测') }}</title>
        </rect>
      </g>
      <g v-for="c in chartPaths" :key="c.key" class="chart">
        <text :x="8" :y="c.top + CHART_H / 2 + 4" class="lane-label">{{ c.label }}</text>
        <text :x="LABEL_W - 4" :y="c.top + 9" class="axis" text-anchor="end">{{ fmt(c.max) }}</text>
        <text :x="LABEL_W - 4" :y="c.top + CHART_H" class="axis" text-anchor="end">{{ fmt(c.min) }}</text>
        <line :x1="LABEL_W" :x2="width - RIGHT" :y1="c.top + CHART_H" :y2="c.top + CHART_H" class="grid" />
        <line v-if="c.limitY !== null" :x1="LABEL_W" :x2="width - RIGHT" :y1="c.limitY" :y2="c.limitY" class="limit"><title>{{ t('飞行器限高') }}</title></line>
        <path :d="c.d" class="series" />
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
  stroke: var(--text-dim);
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
.target {
  fill: #f43f5e;
  cursor: pointer;
}
.target.warn {
  fill: var(--warn);
}
.gap {
  fill: var(--panel-3);
  stroke: var(--text-dim);
}
.limit {
  stroke: var(--warn);
  stroke-dasharray: 4 4;
}
.series {
  fill: none;
  stroke: var(--accent);
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
