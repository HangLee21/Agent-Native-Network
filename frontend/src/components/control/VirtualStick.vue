<script setup lang="ts">
/** One on-screen stick: drag the knob (pointer), release to centre. Emits x, y in -1..1 (y up = +1). */
import { ref } from 'vue'

const props = defineProps<{ label: string; xLabel: string; yLabel: string; x: number; y: number }>()
const emit = defineEmits<{ (e: 'move', x: number, y: number): void }>()

const pad = ref<HTMLDivElement | null>(null)
let pointerId: number | null = null

function update(ev: PointerEvent): void {
  const el = pad.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const nx = ((ev.clientX - r.left) / r.width) * 2 - 1
  const ny = 1 - ((ev.clientY - r.top) / r.height) * 2
  const len = Math.hypot(nx, ny)
  const k = len > 1 ? 1 / len : 1
  emit('move', Math.round(nx * k * 100) / 100, Math.round(ny * k * 100) / 100)
}

function down(ev: PointerEvent): void {
  pointerId = ev.pointerId
  pad.value?.setPointerCapture(ev.pointerId)
  update(ev)
}

function move(ev: PointerEvent): void {
  if (pointerId === ev.pointerId) update(ev)
}

function up(ev: PointerEvent): void {
  if (pointerId !== ev.pointerId) return
  pointerId = null
  emit('move', 0, 0)
}
</script>

<template>
  <div class="vstick">
    <div
      ref="pad"
      class="pad"
      :data-test="`vstick-${label}`"
      @pointerdown.prevent="down"
      @pointermove="move"
      @pointerup="up"
      @pointercancel="up"
    >
      <span class="axis-y">{{ yLabel }}</span>
      <span class="axis-x">{{ xLabel }}</span>
      <span class="knob" :style="{ left: `${50 + props.x * 40}%`, top: `${50 - props.y * 40}%` }" />
    </div>
    <span class="name">{{ label }}</span>
  </div>
</template>

<style scoped>
.vstick {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.pad {
  position: relative;
  width: 132px;
  height: 132px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--accent) 55%, transparent);
  background: radial-gradient(circle, color-mix(in srgb, var(--accent) 14%, transparent) 0 30%, transparent 31%), var(--overlay);
  touch-action: none;
  cursor: grab;
}
.knob {
  position: absolute;
  width: 34px;
  height: 34px;
  margin: -17px 0 0 -17px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 30%, transparent);
  pointer-events: none;
}
.axis-y,
.axis-x {
  position: absolute;
  font-size: 10px;
  color: var(--text-dim);
  pointer-events: none;
}
.axis-y {
  top: 4px;
  left: 50%;
  transform: translateX(-50%);
}
.axis-x {
  right: 6px;
  top: 50%;
  transform: translateY(-50%);
}
.name {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
</style>
