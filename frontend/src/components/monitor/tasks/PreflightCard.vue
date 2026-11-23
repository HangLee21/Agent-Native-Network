<script setup lang="ts">
/** On the ground (ui-design.md §2.2): what is ready before take-off, and the aircraft height limit. */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import HeightLimitControl from '../HeightLimitControl.vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useLiveStore } from '@/stores/live'
import { t } from '@/i18n'

const tel = useTelemetryStore()
const control = useControlStore()
const live = useLiveStore()
const editLimit = ref(false)

type Row = { ok: boolean; warn?: boolean; title: string; sub: string }
const rows = computed<Row[]>(() => {
  const state = control.snapshot?.control ?? 'NONE'
  const ctl: Row = state === 'GRANTED'
    ? (control.drcReady ? { ok: true, title: t('控制权 · DRC 已连接'), sub: t('急停、相机可用') } : { ok: false, warn: true, title: t('控制权已获得 · DRC 未连接'), sub: t('点顶部「进入 DRC」') })
    : state === 'REQUESTING' ? { ok: false, warn: true, title: t('等待飞手同意…'), sub: t('遥控器上已弹出授权请求') }
    : { ok: false, title: t('云端控制权'), sub: t('点顶部「申请控制权」；也可以直接一键起飞，平台会先申请') }
  return [
    { ok: tel.online, title: tel.online ? t('设备已连接') : t('设备未连接'), sub: tel.gateway ? t('遥控器 {rc} · 飞行器 {drone}', { rc: tel.gateway.gatewaySn, drone: tel.gateway.droneSn }) : t('等待遥控器接入') },
    { ok: !!live.status?.streaming, title: live.status?.streaming ? t('视频已开启') : t('视频未开启'), sub: live.status?.streaming ? t('镜头、清晰度在画面右侧') : t('在画面中或右侧「视频」里开启') },
    ctl,
  ]
})
</script>

<template>
  <section class="pre" :aria-label="t('起飞前')" data-test="preflight">
    <h3 class="section-title">{{ t('起飞前') }}</h3>
    <ul class="rows">
      <li v-for="r in rows" :key="r.title" class="r" :class="{ warn: r.warn }">
        <AppIcon :name="r.ok ? 'check' : r.warn ? 'alert' : 'info'" :size="17" :class="r.ok ? 'ok' : r.warn ? 'w' : 'dim'" />
        <span class="t"><b>{{ r.title }}</b><span>{{ r.sub }}</span></span>
      </li>
      <li class="r">
        <AppIcon name="takeoff" :size="17" class="acc" />
        <span class="t"><b>{{ t('飞行器限高 {h} m', { h: tel.drone?.heightLimit ?? '—' }) }}</b><span>{{ t('首飞建议设低（如 40 m）') }}</span></span>
        <button class="btn btn-sm" :aria-expanded="editLimit" @click="editLimit = !editLimit">{{ editLimit ? t('收起') : t('修改') }}</button>
      </li>
      <li v-if="editLimit" class="edit"><HeightLimitControl /></li>
    </ul>
  </section>
</template>

<style scoped>
.pre {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.rows {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.r {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: 7px 10px;
  border-radius: var(--r-ctl);
  background: var(--panel-2);
}
.r.warn {
  border: 1px solid var(--warn);
}
.t {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  font-size: var(--fs-sm);
}
.t span {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.edit {
  padding: var(--sp-2) 10px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
}
.ok { color: var(--ok); }
.w { color: var(--warn); }
.acc { color: var(--accent); }
</style>
