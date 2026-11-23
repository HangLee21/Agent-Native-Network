<script setup lang="ts">
/** Flight data over the video (R-15): height, speeds, aircraft pitch, gimbal pitch, heading, battery, mode, laser range. */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTargetsStore } from '@/stores/targets'
import { LASER_LABELS } from '@/api/targets'
import { modeLabel, num } from '@/utils/format'
import { t } from '@/i18n'

const tel = useTelemetryStore()
const d = computed(() => (tel.online ? tel.drone : null))
const targets = useTargetsStore()
const now = ref(Date.now())
let timer = 0
onMounted(() => (timer = window.setInterval(() => (now.value = Date.now()), 1000)))
onBeforeUnmount(() => window.clearInterval(timer))
/** Laser range at the image centre (drc_camera_osd_info_push.measure_target); hidden when stale. */
const laser = computed(() => {
  const l = targets.laser
  const at = l?.at ?? l?.receivedAt
  if (!l || !at || now.value - at > 3000) return null
  const ok = l.state === 'NORMAL' || l.state === 'UNREPORTED'
  return ok && l.distance ? t('激光 {d} m', { d: num(l.distance, 0) }) : t('激光 {state}', { state: LASER_LABELS[l.state] ?? l.state })
})
</script>

<template>
  <div class="hud num" data-test="hud">
    <div class="col left">
      <div><span>{{ t('相对高度') }}</span><b>{{ num(d?.relativeHeight, 1) }}</b><i>m</i></div>
      <div><span>{{ t('垂直速度') }}</span><b>{{ num(d?.verticalSpeed, 1) }}</b><i>m/s</i></div>
      <div><span>{{ t('水平速度') }}</span><b>{{ num(d?.horizontalSpeed, 1) }}</b><i>m/s</i></div>
    </div>
    <div class="center">
      <div class="heading">{{ t('航向 {deg}°', { deg: num(d?.attitudeHead, 0) }) }}</div>
      <div class="mode">{{ tel.online ? modeLabel(d?.modeCode) : t('设备未连接') }}</div>
      <div v-if="laser" class="laser" data-test="hud-laser">{{ laser }}</div>
    </div>
    <div class="col right">
      <div><span>{{ t('飞机俯仰') }}</span><b>{{ num(d?.attitudePitch, 1) }}</b><i>°</i></div>
      <div><span>{{ t('云台俯仰') }}</span><b>{{ num(d?.gimbalPitch, 1) }}</b><i>°</i></div>
      <div><span>{{ t('电量') }}</span><b>{{ d?.batteryPercent ?? '—' }}</b><i>%</i></div>
    </div>
  </div>
</template>

<style scoped>
.hud {
  position: absolute;
  inset: 0;
  pointer-events: none;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  /* --hud-right: room for the monitor's camera rail on the right edge */
  padding: 56px var(--hud-right, var(--sp-4)) var(--sp-4) var(--sp-4);
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.9), 0 0 2px rgba(0, 0, 0, 0.9);
}
.col {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: rgba(0, 0, 0, 0.32);
  border-radius: var(--r-ctl);
  padding: 6px 10px;
}
.col div {
  display: grid;
  grid-template-columns: 64px 64px 28px;
  align-items: baseline;
}
.col span {
  font-size: 11px;
  opacity: 0.85;
}
.col b {
  font-size: 20px;
  text-align: right;
}
.col i {
  font-style: normal;
  font-size: 11px;
  margin-left: 4px;
  opacity: 0.85;
}
.center {
  text-align: center;
  background: rgba(0, 0, 0, 0.32);
  border-radius: var(--r-ctl);
  padding: 4px 12px;
}
.heading {
  font-size: 16px;
  font-weight: 700;
}
.mode {
  font-size: 12px;
}
.laser {
  font-size: 12px;
  color: #fde68a;
}
</style>
