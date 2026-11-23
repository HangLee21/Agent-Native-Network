<script setup lang="ts">
/**
 * Stick control overlay (R-13, D-16). Shown while the platform is in stick mode. Inputs from the
 * keyboard and two on-screen sticks are combined and sent at 10 Hz; the platform clamps them,
 * applies the height / safe-zone guards and the dead-man, and owns the stream to the aircraft.
 * Mode 2 layout: left stick = throttle (up/down) + yaw (turn), right stick = pitch (fwd/back) + roll.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import VirtualStick from './VirtualStick.vue'
import { manualSocketFor } from '@/services/manualSocket'
import { useManualStore } from '@/stores/manual'
import { useTelemetryStore } from '@/stores/telemetry'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const manual = useManualStore()
const tel = useTelemetryStore()
const snap = computed(() => manual.snapshot)

const left = reactive({ x: 0, y: 0 })
const right = reactive({ x: 0, y: 0 })
const keys = reactive(new Set<string>())
const scalePct = ref(Math.round((snap.value?.scale ?? 0.3) * 100))
watch(() => snap.value?.scale, (s) => s != null && (scalePct.value = Math.round(s * 100)))

const KEYMAP: Record<string, true> = { w: true, s: true, a: true, d: true, ArrowUp: true, ArrowDown: true, ArrowLeft: true, ArrowRight: true }
const axis = (pos: string, neg: string, stick: number) => {
  const k = (keys.has(pos) ? 1 : 0) - (keys.has(neg) ? 1 : 0)
  return Math.abs(k) > Math.abs(stick) ? k : stick
}
/** Combined inputs, each -1..1. */
const input = computed(() => ({
  roll: axis('d', 'a', right.x),
  pitch: axis('w', 's', right.y),
  throttle: axis('ArrowUp', 'ArrowDown', left.y),
  yaw: axis('ArrowRight', 'ArrowLeft', left.x),
}))

function neutral(): void {
  keys.clear()
  left.x = left.y = right.x = right.y = 0
}

function onKey(ev: KeyboardEvent, isDown: boolean): void {
  const el = ev.target as HTMLElement | null
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT')) return
  const k = ev.key.length === 1 ? ev.key.toLowerCase() : ev.key
  if (k === ' ') {
    ev.preventDefault()
    neutral()
    return
  }
  if (!KEYMAP[k]) return
  ev.preventDefault()
  if (isDown) keys.add(k)
  else keys.delete(k)
}
const keydown = (e: KeyboardEvent) => onKey(e, true)
const keyup = (e: KeyboardEvent) => onKey(e, false)
const onVisibility = () => document.hidden && neutral()

let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  manualSocketFor(sn).ensure()
  window.addEventListener('keydown', keydown)
  window.addEventListener('keyup', keyup)
  window.addEventListener('blur', neutral)
  document.addEventListener('visibilitychange', onVisibility)
  timer = setInterval(() => {
    const i = input.value
    manualSocketFor(sn).stick(i.roll, i.pitch, i.throttle, i.yaw)
  }, 100)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  manualSocketFor(sn).stick(0, 0, 0, 0)
  window.removeEventListener('keydown', keydown)
  window.removeEventListener('keyup', keyup)
  window.removeEventListener('blur', neutral)
  document.removeEventListener('visibilitychange', onVisibility)
})

const fmt = (v: number | null | undefined, d = 1) => (v == null ? '—' : v.toFixed(d))
const applyScale = () => void manual.setScale(scalePct.value / 100)
const exit = () => {
  neutral()
  void manual.exit()
}

defineExpose({ input, neutral, keys, left, right })
</script>

<template>
  <div class="stick-overlay" data-test="stick-overlay">
    <header class="head">
      <AppIcon name="joystick" :size="18" />
      <strong>{{ t('杆量控制中') }}</strong>
      <span class="dim">{{ snap?.exiting ? t('正在退出（发送回中）…') : snap?.message }}</span>
      <button class="btn btn-sm btn-warn exit" data-test="stick-exit" @click="exit"><AppIcon name="x" :size="15" />{{ t('退出杆量控制') }}</button>
    </header>

    <div class="body">
      <VirtualStick :label="t('左摇杆')" :x-label="t('转向')" :y-label="t('升降')" :x="input.yaw" :y="input.throttle" @move="(x, y) => ((left.x = x), (left.y = y))" />

      <div class="center">
        <div class="readouts">
          <div><span class="dim">{{ t('相对高度') }}</span><b>{{ fmt(tel.drone?.relativeHeight) }}</b> m</div>
          <div><span class="dim">{{ t('水平速度') }}</span><b>{{ fmt(tel.drone?.horizontalSpeed) }}</b> m/s</div>
          <div><span class="dim">{{ t('垂直速度') }}</span><b>{{ fmt(tel.drone?.verticalSpeed) }}</b> m/s</div>
        </div>
        <label class="scale">
          <span>{{ t('最大杆量 {pct}%', { pct: scalePct }) }}</span>
          <input v-model.number="scalePct" type="range" min="5" :max="Math.round((snap?.maxScale ?? 0.5) * 100)" step="5" data-test="stick-scale" @change="applyScale" />
        </label>
        <p v-if="snap?.heightClamped" class="guard" data-test="guard-height">{{ t('已接近平台限高：上升被阻止') }}</p>
        <p v-if="snap?.zoneBlocked" class="guard" data-test="guard-zone">{{ t('已在安全区外：前后左右被阻止，请返航或飞到地图点') }}</p>
        <p class="keys dim">{{ t('键盘：W/S 前后 · A/D 左右 · ↑/↓ 升降 · ←/→ 转向 · 空格 全部回中') }}</p>
        <p class="note">{{ t('杆量指令没有设备回执，以遥测数据为准；松开或切走页面即回中。急停仍在右下角。') }}</p>
      </div>

      <VirtualStick :label="t('右摇杆')" :x-label="t('左右')" :y-label="t('前后')" :x="input.roll" :y="input.pitch" @move="(x, y) => ((right.x = x), (right.y = y))" />
    </div>
  </div>
</template>

<style scoped>
.stick-overlay {
  /* right of the 360 px picture-in-picture window (bottom-left), left of the camera rail (--hud-right) */
  position: absolute;
  left: 392px;
  right: var(--hud-right, 16px);
  bottom: 70px;
  z-index: 1200;
  max-width: 760px;
  padding: var(--sp-3);
  border-radius: var(--r-panel, 10px);
  border: 2px solid var(--accent);
  background: color-mix(in srgb, var(--panel) 92%, transparent);
  backdrop-filter: blur(4px);
  color: var(--text);
}
.head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
.head .exit {
  margin-left: auto;
}
.body {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--sp-3);
}
.center {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.readouts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px var(--sp-3);
  justify-content: center;
  font-size: var(--fs-sm);
}
.readouts > div {
  white-space: nowrap;
}
.readouts b {
  font-family: var(--font-num);
  font-size: 1.15em;
  margin: 0 2px 0 6px;
}
.scale {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}
.scale input {
  flex: 1;
}
.guard {
  margin: 0;
  padding: 2px 8px;
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--warn) 18%, transparent);
  color: var(--warn);
  font-size: var(--fs-xs);
}
.keys,
.note {
  margin: 0;
  font-size: var(--fs-xs);
}
.note {
  color: var(--text-dim);
}
.dim {
  color: var(--text-dim);
}
</style>
