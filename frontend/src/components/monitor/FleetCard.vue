<script setup lang="ts">
/**
 * One drone at the bottom of the flight-monitor side panel (R-28, ui-design.md §2.2 / §2.7): name and colour, link /
 * control, recording, its own small phase bar, height / speed / battery / distance to Home, what it is doing, and its
 * safety buttons — 起飞 (on the ground) / 返航 / 取消返航 in one place, press-and-hold 急停, and 继续航线 after a pause.
 * They are always available, also while another drone is selected; each one calls that drone's API with the same
 * confirmation as before. Clicking the card body selects the drone.
 */
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import HoldButton from '@/components/control/HoldButton.vue'
import PhaseBar from './PhaseBar.vue'
import { controlApi } from '@/api/control'
import type { DeviceView } from '@/api/drones'
import { STATE_TEXT } from '@/api/execution'
import { useFlightActions } from '@/composables/useFlightActions'
import { useControlStore } from '@/stores/control'
import { useExecutionStore } from '@/stores/execution'
import { useFleetStore } from '@/stores/fleet'
import { useHistoryStore } from '@/stores/history'
import { useTelemetryStore } from '@/stores/telemetry'
import { meters, modeLabel, num } from '@/utils/format'
import { useDogStore } from '@/stores/dog'
import { t, tc } from '@/i18n'

/** compact: one row (three or more devices with robot dogs in the safety area, ui-design.md 5.5). */
const props = defineProps<{ device: DeviceView; selected: boolean; compact?: boolean }>()
const dogs = useDogStore()
const sn = props.device.gatewaySn
const fleet = useFleetStore()
const tel = useTelemetryStore(sn)
const control = useControlStore(sn)
const execution = useExecutionStore(sn)
const history = useHistoryStore(sn)
const { returnHome, slot, cancelReturn, takeoffOpen } = useFlightActions(sn)
const many = computed(() => fleet.drones.length > 1)
const name = computed(() => props.device.label)
/** The selected drone's buttons keep the names they had in the former footer. */
const tid = (own: string, other: string) => (props.selected ? own : other)
const dr = computed(() => (tel.online ? tel.drone : null))

const link = computed(() => {
  if (!tel.online) {
    // in the air and out of contact: the map shows its last known position, not where it is
    const lost = tel.lastUpdateAt > 0 && tel.airborne ? Math.floor((tel.now - tel.lastUpdateAt) / 1000) : null
    return { text: lost != null ? t('失联 {n} 秒', { n: lost }) : t('离线'), cls: 'danger' }
  }
  if (control.granted) return { text: control.drcReady ? t('控制权 · DRC') : t('DRC 未连接'), cls: control.drcReady ? 'ok' : 'warn' }
  const s = control.snapshot?.control
  if (s === 'REQUESTING') return { text: t('等待同意'), cls: 'warn' }
  if (s === 'LOST') return { text: t('失去控制权'), cls: 'danger' }
  return { text: t('无控制权'), cls: '' }
})

const battery = computed(() => {
  const b = dr.value?.batteryPercent ?? null
  const rth = dr.value?.returnHomePower ?? 20
  return { v: b, cls: b == null ? '' : b <= rth ? 'danger' : b <= rth + 10 ? 'warn' : '', min: dr.value?.remainFlightTime ? Math.round(dr.value.remainFlightTime / 60) : null }
})

const paused = computed(() => (execution.current?.active && execution.current.state === 'PAUSED' ? execution.current : null))
const doing = computed(() => {
  const e = execution.current
  if (e?.active) {
    if (e.state === 'PAUSED') {
      const text = e.pauseReason === 'PROXIMITY' ? t('航线暂停（两机靠近）') : e.pauseReason === 'WAYPOINT_CONFIRM' ? t('到达航点 {n}，等待确认', { n: e.reachedCount }) : t('航线暂停')
      return { text, warn: true, pct: null }
    }
    return { text: t('航线 {n}/{total} · {state}', { n: e.reachedCount, total: e.total, state: STATE_TEXT[e.state] }), warn: false, pct: e.total ? Math.max(4, (100 * e.reachedCount) / e.total) : null }
  }
  return { text: tel.online ? modeLabel(tel.drone?.modeCode) : '—', warn: tel.drone?.modeCode === 9, pct: null }
})

/** The latest of this drone's safety commands (take-off / return home / emergency stop), with its device receipt. */
const receipt = computed(() => {
  const list = ['takeoff', 'rth', 'estop'].map((k) => control.byAction(k)).filter((r) => !!r)
  return list.sort((a, b) => b.createdAt - a.createdAt)[0] ?? null
})

/**
 * One-row cards have no room for the receipt line: for 10 s after a safety command's answer changes, the answer takes
 * the place of the task text (so a refused return home is seen at once), then the task text comes back.
 */
const receiptSeenAt = ref(0)
watch(() => (receipt.value ? `${receipt.value.id}:${receipt.value.status}` : ''), (k) => {
  if (k) receiptSeenAt.value = Date.now()
})
const compactReceipt = computed(() => (props.compact && receipt.value && tel.now - receiptSeenAt.value < 10000 ? receipt.value : null))

const estop = () => control.run('estop', tc('monitor', '急停'), () => controlApi(sn).emergencyStop())
const resume = () => execution.resume()
/** Take-off opens this drone's take-off confirmation; the panel switches to it so its pre-flight checks are in view. */
function takeoff(): void {
  dogs.select(null)
  if (!props.selected) fleet.select(sn)
  takeoffOpen.value = true
}
const select = () => {
  dogs.select(null)
  if (!props.selected) fleet.select(sn)
}
</script>

<template>
  <div class="card" :class="{ selected, compact, answered: !!compactReceipt }" :style="{ '--c': device.color }" role="button" tabindex="0"
       :aria-label="selected ? t('正在操作 {name}', { name }) : t('切换到 {name}', { name })" :aria-pressed="selected" data-test="fleet-card" :data-sn="sn"
       :title="t('{name}：{sn}', { name, sn: device.droneSn ?? sn })" @click="select" @keydown.enter.self="select">
    <div class="head">
      <b class="name">{{ name }}</b>
      <span class="chip" :class="link.cls"><span class="dot" />{{ link.text }}</span>
      <span v-if="history.currentId" class="rec" :title="t('正在记录这次飞行')">● {{ t('记录') }}</span>
    </div>
    <PhaseBar v-if="!compact" :sn="sn" mini />
    <div class="g4 num">
      <span><small>{{ t('高') }}</small>{{ num(dr?.relativeHeight, 1) }}<em>m</em></span>
      <span><small>{{ t('速') }}</small>{{ num(dr?.horizontalSpeed, 1) }}<em>m/s</em></span>
      <span :class="battery.cls"><small>{{ t('电') }}</small>{{ battery.v ?? '—' }}<em>%<template v-if="battery.min != null">{{ t(' 剩{n}分', { n: battery.min }) }}</template></em></span>
      <span><small>{{ t('家') }}</small>{{ meters(dr?.homeDistance) }}</span>
    </div>
    <div class="tk">
      <CommandStatus v-if="compactReceipt" class="receipt" :record="compactReceipt" compact data-test="fleet-compact-receipt" />
      <button v-else-if="paused" class="btn btn-sm btn-warn wide" data-test="fleet-resume" @click.stop="resume">
        <AppIcon name="play" :size="14" />{{ many ? t('继续 {name} 的航线', { name }) : t('继续航线') }}
      </button>
      <template v-else>
        <span class="t" :class="{ warn: doing.warn }">{{ doing.text }}</span>
        <span v-if="doing.pct != null" class="prog"><i :style="{ width: `${doing.pct}%` }" /></span>
      </template>
    </div>
    <div class="acts" @click.stop>
      <button v-if="slot === 'takeoff'" class="btn btn-primary" :disabled="!tel.online || tel.airborne" :data-test="tid('takeoff', 'fleet-takeoff')"
              :title="t('{name} 一键起飞', { name })" @click="takeoff">
        <AppIcon name="takeoff" :size="16" />{{ selected && !many ? t('一键起飞') : t('起飞') }}
      </button>
      <button v-else-if="slot === 'rth'" class="btn btn-warn" :disabled="!tel.gateway?.gatewayOnline" :data-test="tid('return-home', 'fleet-rth')"
              :title="t('让 {name} 返航', { name })" @click="returnHome">
        <AppIcon name="home" :size="16" />{{ selected && !many ? t('一键返航') : t('返航') }}
      </button>
      <button v-else class="btn" :data-test="tid('cancel-return', 'fleet-cancel-rth')" @click="cancelReturn"><AppIcon name="x" :size="16" />{{ t('取消返航') }}</button>
      <HoldButton class="estop" :disabled="!control.drcReady" :data-test="tid('estop', 'fleet-estop')"
                  :title="control.drcReady ? t('长按 0.8 秒：{name} 急停', { name }) : t('{name} 急停不可用：DRC 未连接', { name })" @trigger="estop">
        <template v-if="control.drcReady"><AppIcon name="estop" :size="16" />{{ many ? t('急停 {name}', { name }) : tc('monitor', '急停') }}</template>
        <span v-else class="off">{{ many ? t('急停 {name}', { name }) : tc('monitor', '急停') }}<small>{{ t('DRC 未连接') }}</small></span>
      </HoldButton>
    </div>
    <CommandStatus v-if="receipt && !compact" class="receipt" :record="receipt" compact />
  </div>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
  padding: 6px 8px 8px;
  border: 1px solid var(--border);
  border-top: 4px solid var(--c);
  border-radius: var(--r-panel);
  background: var(--panel-2);
  cursor: pointer;
}
/* one row per device (three or more devices with robot dogs): name and link, task, height and battery, buttons */
.card.compact {
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 4px 8px;
  border-top-width: 1px;
  border-left: 4px solid var(--c);
}
.card.compact .head {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  /* the text side gives way (ellipsis) so the take-off / return and E-stop buttons always stay fully on screen */
  flex: 0 1 auto;
}
.card.compact .head .chip {
  max-width: 100%;
}
.card.compact .tk {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-xs);
}
.card.compact .g4 {
  display: flex;
  flex-direction: column;
  gap: 0;
  font-size: var(--fs-xs);
  flex: 0 1 auto;
  min-width: 0;
}
.card.compact .g4 > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card.compact .g4 span:nth-child(2),
.card.compact .g4 span:nth-child(4) {
  display: none;
}
.card.compact .acts {
  flex: none;
}
.card.compact .acts .btn,
.card.compact .acts .estop {
  min-height: 40px;
}
@media (max-height: 800px) {
  /* two columns on low screens: name and state on top, the two buttons below */
  .card.compact {
    flex-wrap: wrap;
    row-gap: 4px;
  }
  .card.compact .tk,
  .card.compact .g4 {
    display: none;
  }
  .card.compact.answered .tk {
    display: block;
  }
  .card.compact .acts {
    flex: 1 1 100%;
  }
}
.card.selected {
  border: 2px solid var(--c);
  border-top-width: 4px;
  padding: 6px 7px 7px;
  background: color-mix(in srgb, var(--c) 13%, var(--panel-2));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 22%, transparent);
}
.head {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.name {
  font-size: 20px;
  font-weight: 800;
  line-height: 1;
  color: var(--c);
}
.head .chip {
  height: 22px;
  padding: 0 7px;
  font-size: 11.5px;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.rec {
  margin-left: auto;
  color: var(--danger);
  font-size: 11px;
  white-space: nowrap;
}
.g4 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px 8px;
  font-size: 15px;
  font-weight: 700;
}
.g4 span {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.g4 small {
  margin-right: 3px;
  font-family: var(--font-ui);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
}
.g4 em {
  margin-left: 1px;
  font-style: normal;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
}
.g4 .warn {
  color: var(--warn);
}
.g4 .danger {
  color: var(--danger);
}
.tk {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 20px;
  min-width: 0;
  font-size: var(--fs-xs);
}
.tk .t {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-dim);
}
.tk .t.warn {
  color: var(--warn);
  font-weight: 700;
}
.prog {
  flex: 1;
  min-width: 24px;
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}
.prog i {
  display: block;
  height: 100%;
  background: var(--accent);
}
.wide {
  flex: 1;
  justify-content: center;
}
.acts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.acts .btn {
  justify-content: center;
  min-height: 46px;
  padding: 0 4px;
  gap: 4px;
  font-size: var(--fs-sm);
  white-space: nowrap;
}
.estop {
  min-height: 46px !important;
  border-radius: var(--r-ctl) !important;
  font-size: var(--fs-sm) !important;
  letter-spacing: 0.04em !important;
}
.estop :deep(.content) {
  gap: 4px;
}
.off {
  display: flex;
  flex-direction: column;
  line-height: 1.15;
  font-size: var(--fs-xs);
}
.off small {
  font-size: 10.5px;
  font-weight: 500;
}
.receipt {
  font-size: 11px;
}
</style>
