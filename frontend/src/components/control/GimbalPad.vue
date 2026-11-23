<script setup lang="ts">
/**
 * Gimbal hold buttons (R-13, D-16): while a direction is held, turn speeds are streamed to the
 * platform (5 Hz); release sends a stop. The platform also stops the gimbal if frames stop arriving.
 * Direction signs follow the doc (pitch_speed / yaw_speed in rad/s); confirm in the field (U-20).
 * Turn speed: 慢 / 中 / 快 chosen by the operator and remembered in this browser (user, 2026-11-01: the fixed
 * 17°/s felt slow); zoomed in, it slows down so the picture does not jump (the platform caps it at 1 rad/s).
 */
import { computed, onBeforeUnmount, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { manualSocketFor } from '@/services/manualSocket'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

/**
 * `pad`: direction keys as a cross with 回中 in the middle and the reset presets below (camera rail flyout).
 * `zoom`: zoom factor of the lens on screen (1 = wide angle).
 */
const props = withDefaults(defineProps<{ disabled?: boolean; pad?: boolean; zoom?: number }>(), { disabled: false, pad: false, zoom: 1 })
const emit = defineEmits<{ (e: 'reset', mode: number): void }>()

const SPEEDS = [
  { id: 'slow', label: t('慢'), deg: 10 },
  { id: 'mid', label: t('中'), deg: 25 },
  { id: 'fast', label: t('快'), deg: 50 },
] as const
type SpeedId = (typeof SPEEDS)[number]['id']
const SPEED_KEY = 'uav.gimbalSpeed'

function loadSpeed(): SpeedId {
  try {
    const v = window.localStorage.getItem(SPEED_KEY)
    return SPEEDS.some((o) => o.id === v) ? (v as SpeedId) : 'mid'
  } catch {
    return 'mid' // storage unavailable: the default works without it
  }
}
const speedId = ref<SpeedId>(loadSpeed())
function setSpeed(id: SpeedId): void {
  speedId.value = id
  try {
    window.localStorage.setItem(SPEED_KEY, id)
  } catch {
    /* not remembered */
  }
}

/** Above 2× the speed shrinks with the zoom (a 20× view would otherwise sweep past in a blink), down to 15 %. */
const zoomScale = computed(() => (props.zoom > 2 ? Math.max(0.15, 2 / props.zoom) : 1))
const degPerS = computed(() => SPEEDS.find((o) => o.id === speedId.value)!.deg * zoomScale.value)

const held = ref<null | 'left' | 'right' | 'up' | 'down'>(null)
let timer: ReturnType<typeof setInterval> | null = null

function vector(dir: NonNullable<typeof held.value>): [number, number] {
  const s = Math.round(((degPerS.value * Math.PI) / 180) * 1000) / 1000
  switch (dir) {
    case 'left': return [0, -s]
    case 'right': return [0, s]
    case 'up': return [s, 0]
    case 'down': return [-s, 0]
  }
}

function press(dir: NonNullable<typeof held.value>): void {
  if (props.disabled) return
  stop()
  held.value = dir
  manualSocketFor(sn).ensure()
  const [p, y] = vector(dir)
  manualSocketFor(sn).gimbal(p, y)
  timer = setInterval(() => manualSocketFor(sn).gimbal(p, y), 200)
}

function stop(): void {
  if (timer) clearInterval(timer)
  timer = null
  if (held.value) {
    manualSocketFor(sn).gimbal(0, 0)
    held.value = null
  }
}

onBeforeUnmount(stop)

const dirs = [
  { id: 'left', icon: 'left', label: t('向左'), title: t('按住云台向左，松开停止'), aria: t('云台向左') },
  { id: 'up', icon: 'up', label: t('向上'), title: t('按住云台向上，松开停止'), aria: t('云台向上') },
  { id: 'down', icon: 'down', label: t('向下转'), title: t('按住云台向下转，松开停止'), aria: t('云台向下转') },
  { id: 'right', icon: 'chevron', label: t('向右'), title: t('按住云台向右，松开停止'), aria: t('云台向右') },
] as const
</script>

<template>
  <div class="gimbal-pad" :class="{ pad }" data-test="gimbal-pad">
    <button
      v-for="d in dirs"
      :key="d.id"
      class="btn btn-sm"
      :class="[{ 'btn-primary': held === d.id }, `dir-${d.id}`]"
      :disabled="disabled"
      :data-test="`gimbal-${d.id}`"
      :title="d.title"
      :aria-label="d.aria"
      @pointerdown.prevent="press(d.id)"
      @pointerup="stop"
      @pointerleave="stop"
      @pointercancel="stop"
    >
      <AppIcon :name="d.icon" :size="15" /><span class="lbl">{{ d.label }}</span>
    </button>
    <template v-if="pad">
      <button class="btn btn-sm center" :disabled="disabled" data-test="gimbal-center" :title="t('镜头转回水平，并转回正对机头')"
        @click="emit('reset', 0)">{{ t('回中') }}</button>
      <button class="btn btn-sm preset p1" :disabled="disabled" data-test="gimbal-down-preset" :title="t('镜头转到正下方，并转回正对机头')"
        @click="emit('reset', 1)">{{ t('向下') }}</button>
    </template>
    <button class="btn btn-sm" :class="{ 'preset p2': pad }" :disabled="disabled" data-test="gimbal-yaw-center"
      :title="t('只把左右转回正对机头，上下角度不变')" @click="emit('reset', 2)">{{ t('偏航回中') }}</button>
    <button class="btn btn-sm" :class="{ 'preset p3': pad }" :disabled="disabled" data-test="gimbal-pitch-down"
      :title="t('只把镜头转到正下方，左右朝向不变')" @click="emit('reset', 3)">{{ t('俯仰向下') }}</button>
    <div class="speeds" role="radiogroup" :aria-label="t('云台转速')">
      <span class="speeds-label">{{ t('转速') }}</span>
      <button v-for="o in SPEEDS" :key="o.id" class="btn btn-sm" :class="{ 'btn-primary': speedId === o.id }" role="radio"
        :aria-checked="speedId === o.id" :data-test="`gimbal-speed-${o.id}`" @click="setSpeed(o.id)">{{ o.label }}</button>
    </div>
    <span class="rate num" data-test="gimbal-rate">{{ t('约 {deg}°/s', { deg: Math.round(degPerS) }) }}<template v-if="zoomScale < 1">{{ t('（{zoom}× 变焦，已放慢）', { zoom }) }}</template></span>
  </div>
</template>

<style scoped>
.gimbal-pad {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  touch-action: none;
}
.gimbal-pad.pad {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-areas: '. up .' 'left center right' '. down .' 'p1 p2 p3' 'sp sp sp' 'rt rt rt';
  gap: 4px;
}
.speeds {
  display: flex;
  align-items: center;
  gap: 4px;
}
.pad .speeds {
  grid-area: sp;
  margin-top: 4px;
}
.pad .speeds .btn {
  flex: 1;
  min-height: 30px;
}
.speeds-label,
.rate {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.speeds-label {
  white-space: nowrap;
}
.pad .rate {
  grid-area: rt;
}
.pad .btn {
  min-height: 38px;
  padding: 0 4px;
}
.pad .preset {
  min-height: 30px;
  font-size: var(--fs-xs);
}
.pad .lbl {
  display: none;
}
.pad .dir-up { grid-area: up; }
.pad .dir-down { grid-area: down; }
.pad .dir-left { grid-area: left; }
.pad .dir-right { grid-area: right; }
.pad .center { grid-area: center; font-size: var(--fs-xs); }
.pad .p1 { grid-area: p1; }
.pad .p2 { grid-area: p2; }
.pad .p3 { grid-area: p3; }
</style>
