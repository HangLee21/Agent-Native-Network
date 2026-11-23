<script setup lang="ts">
/**
 * "Select target" mode over the live video (R-24 draft, D-21): tap → drc_camera_aim, drag → box →
 * drc_camera_frame_zoom. Coordinates are mapped to the visible video frame (object-fit: contain);
 * clicks on the black bars are ignored. Selecting only points the camera and measures.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTargetsStore } from '@/stores/targets'
import { t } from '@/i18n'
import { frameRect, toFrame, toFrameBox, TAP_SLOP_PX, type FrameRect } from '@/utils/videoCoords'

const props = defineProps<{ video: HTMLVideoElement | null; lens: string; frame?: { w: number; h: number } | null }>()
const targets = useTargetsStore()
const root = ref<HTMLDivElement | null>(null)
const start = ref<{ x: number; y: number } | null>(null)
const cur = ref<{ x: number; y: number } | null>(null)

function rect(): FrameRect {
  const el = root.value!
  const w = props.frame?.w ?? props.video?.videoWidth ?? 0
  const h = props.frame?.h ?? props.video?.videoHeight ?? 0
  return frameRect(el.clientWidth, el.clientHeight, w, h)
}

function local(e: PointerEvent): { x: number; y: number } {
  const b = root.value!.getBoundingClientRect()
  return { x: e.clientX - b.left, y: e.clientY - b.top }
}

function down(e: PointerEvent): void {
  if (e.button !== 0) return
  root.value?.setPointerCapture(e.pointerId)
  start.value = local(e)
  cur.value = start.value
}

function move(e: PointerEvent): void {
  if (start.value) cur.value = local(e)
}

function up(e: PointerEvent): void {
  const s = start.value
  start.value = null
  if (!s) return
  const p = local(e)
  cur.value = null
  const r = rect()
  if (Math.hypot(p.x - s.x, p.y - s.y) < TAP_SLOP_PX) {
    const f = toFrame(p.x, p.y, r)
    if (f) void targets.select('TAP', props.lens, round(f.x), round(f.y))
  } else {
    const b = toFrameBox(s.x, s.y, p.x, p.y, r)
    if (b) void targets.select('CIRCLE', props.lens, round(b.x), round(b.y), round(b.w), round(b.h))
  }
}

const round = (v: number) => Math.round(v * 10000) / 10000

const box = computed(() => {
  if (!start.value || !cur.value) return null
  const x = Math.min(start.value.x, cur.value.x)
  const y = Math.min(start.value.y, cur.value.y)
  const w = Math.abs(cur.value.x - start.value.x)
  const h = Math.abs(cur.value.y - start.value.y)
  return w < TAP_SLOP_PX && h < TAP_SLOP_PX ? null : { x, y, w, h }
})

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') targets.selecting = false
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div ref="root" class="select-layer" data-test="target-select-layer" @pointerdown="down" @pointermove="move" @pointerup="up"
    @pointercancel="start = null">
    <div class="hint"><AppIcon name="crosshair" :size="15" />{{ t('点选或框选目标 · 只转动云台并测距，不会移动飞机 · Esc 退出') }}</div>
    <div v-if="box" class="box" :style="{ left: `${box.x}px`, top: `${box.y}px`, width: `${box.w}px`, height: `${box.h}px` }" />
    <div class="reticle" aria-hidden="true" />
  </div>
</template>

<style scoped>
.select-layer {
  position: absolute;
  inset: 0;
  z-index: 5;
  cursor: crosshair;
  touch-action: none;
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.hint {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-ctl);
  background: var(--accent);
  color: var(--accent-ink);
  font-size: var(--fs-sm);
  font-weight: 600;
  white-space: nowrap;
  pointer-events: none;
}
.box {
  position: absolute;
  border: 2px dashed #facc15;
  background: rgba(250, 204, 21, 0.12);
  pointer-events: none;
}
.reticle {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 36px;
  height: 36px;
  margin: -18px 0 0 -18px;
  border: 2px solid rgba(255, 255, 255, 0.8);
  border-radius: 50%;
  pointer-events: none;
}
.reticle::before,
.reticle::after {
  content: '';
  position: absolute;
  background: rgba(255, 255, 255, 0.8);
}
.reticle::before {
  left: 50%;
  top: -10px;
  bottom: -10px;
  width: 2px;
  margin-left: -1px;
}
.reticle::after {
  top: 50%;
  left: -10px;
  right: -10px;
  height: 2px;
  margin-top: -1px;
}
</style>
