<script setup lang="ts">
/**
 * One drone in the collapsed side panel (ui-design.md §2.2): select it, its small phase bar, control / DRC, height and
 * battery, and its safety buttons — 继续航线 after a pause, 起飞 / 返航 / 取消返航, and press-and-hold 急停. Every
 * drone keeps them while the panel is collapsed; each calls that drone's API with the same confirmation as before.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import HoldButton from '@/components/control/HoldButton.vue'
import PhaseBar from './PhaseBar.vue'
import { controlApi } from '@/api/control'
import type { DeviceView } from '@/api/drones'
import { useFlightActions } from '@/composables/useFlightActions'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { useFleetStore } from '@/stores/fleet'
import { useTasksStore } from '@/stores/tasks'
import { useTelemetryStore } from '@/stores/telemetry'
import { num } from '@/utils/format'
import { t, tc } from '@/i18n'

const props = defineProps<{ device: DeviceView; selected: boolean }>()
const sn = props.device.gatewaySn
const fleet = useFleetStore()
const tel = useTelemetryStore(sn)
const control = useControlStore(sn)
const execution = useExecutionStore(sn)
const tasks = useTasksStore(sn)
const { slot, takeoffOpen, returnHome, cancelReturn } = useFlightActions(sn)
const many = computed(() => fleet.drones.length > 1)
const name = computed(() => props.device.label)
const dr = computed(() => (tel.online ? tel.drone : null))
const paused = computed(() => execution.current?.active && execution.current.state === 'PAUSED')
const ctl = computed(() => {
  if (!tel.online) return { cls: 'danger', text: t('离线'), title: t('设备未连接') }
  if (control.granted) return control.drcReady ? { cls: 'ok', text: 'DRC', title: t('控制权 · DRC') } : { cls: 'warn', text: t('无 DRC'), title: t('控制权 · DRC 未连接') }
  return { cls: control.snapshot?.control === 'LOST' ? 'danger' : '', text: t('无控制'), title: t('未获得控制权') }
})

const estop = () => control.run('estop', tc('monitor', '急停'), () => controlApi(sn).emergencyStop())
const resume = () => execution.resume()
function takeoff(): void {
  if (!props.selected) fleet.select(sn)
  takeoffOpen.value = true
}
</script>

<template>
  <div class="rd" :class="{ on: selected, many }" :style="{ '--c': device.color }" data-test="rail-drone" :data-sn="sn">
    <button v-if="many" class="dsel" :class="{ on: selected }" :title="selected ? t('正在操作 {name}', { name }) : t('切换到 {name}', { name })"
            :aria-label="t('选中 {name}', { name })" :aria-pressed="selected" @click="fleet.select(sn)">{{ name }}</button>
    <PhaseBar :sn="sn" mini />
    <span class="ctl" :class="ctl.cls" :title="ctl.title"><span class="dot" />{{ ctl.text }}</span>
    <div v-if="many" class="rn num">{{ num(dr?.relativeHeight, 0) }} m<br />{{ dr?.batteryPercent ?? '—' }}%</div>
    <div v-else class="nums num">
      <b>{{ num(dr?.relativeHeight, 1) }}</b><span>{{ t('高 m') }}</span>
      <b>{{ num(dr?.horizontalSpeed, 1) }}</b><span>{{ t('速 m/s') }}</span>
      <b>{{ dr?.batteryPercent ?? '—' }}</b><span>{{ t('电 %') }}</span>
    </div>
    <span v-if="!many && tasks.motionName" class="task" :title="t('{task}进行中', { task: tasks.motionName })">{{ tasks.motionName }}</span>
    <button v-if="paused" class="act warn" :aria-label="t('继续 {name} 的航线', { name })" :title="t('继续 {name} 的航线', { name })" data-test="rail-resume" @click="resume">
      <AppIcon name="play" :size="15" />{{ t('继续') }}
    </button>
    <button v-if="slot === 'takeoff'" class="act primary" :aria-label="t('{name} 一键起飞', { name })" :disabled="!tel.online || tel.airborne" data-test="rail-takeoff" @click="takeoff">
      <AppIcon name="takeoff" :size="17" />{{ t('起飞') }}
    </button>
    <button v-else-if="slot === 'rth'" class="act warn" :aria-label="t('让 {name} 返航', { name })" :title="t('让 {name} 返航', { name })" :disabled="!tel.gateway?.gatewayOnline" data-test="rail-rth" @click="returnHome">
      <AppIcon name="home" :size="17" />{{ t('返航') }}
    </button>
    <button v-else class="act" :aria-label="t('{name} 取消返航', { name })" data-test="rail-cancel-rth" @click="cancelReturn"><AppIcon name="x" :size="17" />{{ t('取消') }}</button>
    <HoldButton class="estop" :disabled="!control.drcReady" :aria-label="t('{name} 急停，长按 0.8 秒', { name })" data-test="rail-estop"
                :title="control.drcReady ? t('长按 0.8 秒：{name} 急停', { name }) : t('{name} 急停不可用：DRC 未连接', { name })" @trigger="estop">
      <AppIcon name="estop" :size="18" /><span class="v">{{ tc('monitor', '急停') }}</span><span v-if="many">{{ name }}</span>
    </HoldButton>
  </div>
</template>

<style scoped>
.rd {
  width: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.rd.many {
  padding: 6px 4px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  border-top: 3px solid var(--c);
}
.rd.many.on {
  border-color: var(--c);
  background: color-mix(in srgb, var(--c) 14%, transparent);
}
.rd :deep(.steps) {
  width: 100%;
}
.dsel {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  border: 2px solid var(--c);
  background: transparent;
  color: var(--c);
  font-weight: 800;
  cursor: pointer;
}
.dsel.on {
  background: var(--c);
  color: #0d1117;
}
.ctl {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--text-dim);
  white-space: nowrap;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-dim);
}
.ok .dot { background: var(--ok); }
.warn .dot { background: var(--warn); }
.danger .dot { background: var(--danger); }
.rn {
  font-size: 11px;
  line-height: 1.25;
  text-align: center;
  color: var(--text-dim);
  white-space: nowrap;
}
.nums {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 15px;
}
.nums span {
  margin-bottom: 4px;
  font-family: var(--font-ui);
  font-size: 10px;
  color: var(--text-dim);
}
.task {
  padding: 0 4px;
  font-size: 11px;
  text-align: center;
  color: var(--accent);
}
.act {
  width: 100%;
  max-width: 56px;
  min-height: 46px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  font-size: 10.5px;
  font-weight: 700;
  cursor: pointer;
}
.act:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.act.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.act.warn {
  border: 2px solid var(--warn);
  background: color-mix(in srgb, var(--warn) 18%, var(--panel-2));
}
.estop {
  width: 100% !important;
  max-width: 56px;
  min-height: 64px !important;
  padding: 4px 0 !important;
  letter-spacing: 0 !important;
  font-size: 12px !important;
}
.estop :deep(.content) {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.rd:not(.many) .estop {
  min-height: 112px !important;
  font-size: 15px !important;
}
.rd:not(.many) .v {
  writing-mode: vertical-rl;
  letter-spacing: 0.3em;
}
</style>
