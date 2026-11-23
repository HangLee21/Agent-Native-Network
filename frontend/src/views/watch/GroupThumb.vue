<script setup lang="ts">
/** Outline of the flown tracks of flights picked together, each in its drone's colour, in one frame (like TrackThumb). */
import { computed } from 'vue'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ tracks: { points: [number, number][] | null; color: string }[]; width?: number; height?: number }>(), { width: 72, height: 44 })

const paths = computed(() => {
  const all = props.tracks.flatMap((t) => t.points ?? [])
  if (all.length < 2) return []
  const k = Math.cos((all[0]![0] * Math.PI) / 180)
  const xs = all.map((p) => p[1] * k), ys = all.map((p) => p[0])
  const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys)
  const span = Math.max(maxX - minX, maxY - minY) || 1e-9
  const pad = 4
  const s = Math.min(props.width - 2 * pad, props.height - 2 * pad) / span
  const ox = (props.width - (maxX - minX) * s) / 2, oy = (props.height - (maxY - minY) * s) / 2
  const X = (lon: number) => (ox + (lon * k - minX) * s).toFixed(1)
  const Y = (lat: number) => (oy + (maxY - lat) * s).toFixed(1)
  return props.tracks.filter((t) => (t.points?.length ?? 0) >= 2).map((t) => ({
    color: t.color,
    d: t.points!.map((p, i) => `${i ? 'L' : 'M'}${X(p[1])} ${Y(p[0])}`).join(''),
    start: [X(t.points![0]![1]), Y(t.points![0]![0])] as const,
  }))
})
</script>

<template>
  <svg class="thumb" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <template v-for="(p, i) in paths" :key="i">
      <path :d="p.d" fill="none" :stroke="p.color" stroke-width="1.6" stroke-linejoin="round" />
      <circle :cx="p.start[0]" :cy="p.start[1]" r="2.2" :fill="p.color" />
    </template>
    <text v-if="!paths.length" :x="width / 2" :y="height / 2 + 4" text-anchor="middle" font-size="11" fill="var(--text-dim)">{{ t('无航迹') }}</text>
  </svg>
</template>

<style scoped>
.thumb { display: block; border-radius: 4px; background: var(--panel-2); flex: none; }
</style>
