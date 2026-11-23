<script setup lang="ts">
/** Small outline of a recorded track for the records list (lat/lon scaled with cos(lat)); a dog's is a 轨迹, not a 航迹. */
import { computed } from 'vue'
import { t } from '@/i18n'

const props = withDefaults(defineProps<{ points: [number, number][] | null; width?: number; height?: number; dog?: boolean }>(), { width: 72, height: 44, dog: false })

const path = computed(() => {
  const pts = props.points ?? []
  if (pts.length < 2) return ''
  const k = Math.cos((pts[0]![0] * Math.PI) / 180)
  const xs = pts.map((p) => p[1] * k)
  const ys = pts.map((p) => p[0])
  const minX = Math.min(...xs)
  const maxX = Math.max(...xs)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)
  const span = Math.max(maxX - minX, maxY - minY) || 1e-9
  const pad = 4
  const s = Math.min(props.width - 2 * pad, props.height - 2 * pad) / span
  const ox = (props.width - (maxX - minX) * s) / 2
  const oy = (props.height - (maxY - minY) * s) / 2
  return xs.map((x, i) => `${i ? 'L' : 'M'}${(ox + (x - minX) * s).toFixed(1)} ${(oy + (maxY - ys[i]!) * s).toFixed(1)}`).join('')
})
const start = computed(() => path.value.match(/^M([\d.]+) ([\d.]+)/))
</script>

<template>
  <svg class="thumb" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <path v-if="path" :d="path" fill="none" stroke="var(--track)" stroke-width="1.6" stroke-linejoin="round" />
    <circle v-if="start" :cx="start[1]" :cy="start[2]" r="2.5" fill="var(--ok)" />
    <text v-if="!path" :x="width / 2" :y="height / 2 + 4" text-anchor="middle" font-size="11" fill="var(--text-dim)">{{ dog ? t('无轨迹') : t('无航迹') }}</text>
  </svg>
</template>

<style scoped>
.thumb {
  display: block;
  border-radius: 4px;
  background: var(--panel-2);
}
</style>
