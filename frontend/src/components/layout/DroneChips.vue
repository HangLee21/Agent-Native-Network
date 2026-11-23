<script setup lang="ts">
/** First-level status of one drone in the top bar: link, battery, satellites (ui-design.md §3); see LinkChips. */
import { computed } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useHistoryStore } from '@/stores/history'
import { t } from '@/i18n'

const tel = useTelemetryStore()
const control = useControlStore()
const history = useHistoryStore()
const ctl = computed(() => {
  switch (control.snapshot?.control) {
    case 'GRANTED': return { cls: 'ok', text: control.drcReady ? t('控制权 · DRC') : t('控制权 · DRC 未连接') }
    case 'REQUESTING': return { cls: 'warn', text: t('等待授权') }
    case 'LOST': return { cls: 'danger', text: t('失去控制权') }
    case 'DENIED': return { cls: 'danger', text: t('授权被拒') }
    default: return { cls: '', text: t('无控制权') }
  }
})
const dr = computed(() => (tel.online ? tel.drone : null))
const linkLabel = computed(() => {
  if (!tel.gateway?.gatewayOnline) return t('遥控器未连接')
  if (!tel.gateway?.droneOnline) return t('飞行器未连接')
  return tel.linkFresh ? t('已连接') : t('链路中断')
})
const batteryCls = computed(() => {
  const b = dr.value?.batteryPercent
  if (b == null) return ''
  const rth = dr.value?.returnHomePower ?? 20
  return b <= rth ? 'danger' : b <= rth + 10 ? 'warn' : 'ok'
})
</script>

<template>
  <span class="chip" :class="tel.online ? 'ok' : 'danger'" data-test="link-chip" :title="tel.gateway ? t('遥控器 {rc} · 飞行器 {drone}', { rc: tel.gateway.gatewaySn, drone: tel.gateway.droneSn }) : ''">
    <span class="dot" />{{ linkLabel }}
  </span>
  <span class="chip" :class="ctl.cls" data-test="top-control-chip" :title="t('云端控制权 / DRC 状态')"><AppIcon name="antenna" :size="15" />{{ ctl.text }}</span>
  <span class="chip" :class="batteryCls" :title="t('飞行器电量')">
    <AppIcon name="battery" :size="15" /><span class="num">{{ dr?.batteryPercent != null ? dr.batteryPercent + '%' : '—' }}</span>
  </span>
  <span class="chip" :title="t('GPS 卫星数')">
    <AppIcon name="satellite" :size="15" /><span class="num">{{ dr?.gpsNumber ?? '—' }}</span>
  </span>
  <RouterLink v-if="history.currentId" class="chip rec" :to="`/history/${history.currentId}`" :title="t('正在记录本次飞行，点击查看')" data-test="recording-chip">
    <span class="dot" />{{ t('记录中') }}
  </RouterLink>
  <span class="chip" :class="control.criticalCount ? 'danger' : control.alerts.length ? 'warn' : ''" :title="t('告警数量')" data-test="alert-count">
    <AppIcon name="alert" :size="15" /><span class="num">{{ control.alerts.length }}</span>
  </span>
</template>

<style scoped>
.rec {
  text-decoration: none;
  color: var(--text);
}
.rec .dot {
  background: var(--danger);
  animation: blink 1.6s ease-in-out infinite;
}
@keyframes blink {
  50% { opacity: 0.25; }
}
</style>
