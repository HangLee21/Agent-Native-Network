<script setup lang="ts">
/**
 * Top of the monitor side panel (R-10 ~ R-13, ui-design.md §2.2): which drone is operated, control / DRC state with
 * the same request, enter-DRC and release calls as before, the flight phase bar with a one-line "what next" hint,
 * the DJI "RC keys disabled" notice, and the second-level numbers (vertical speed, gimbal / aircraft pitch, obstacles).
 * The first-level numbers of every drone are on its fleet card at the bottom of the panel.
 */
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import HeightLimitControl from './HeightLimitControl.vue'
import PhaseBar from './PhaseBar.vue'
import { controlApi } from '@/api/control'
import { useControlStore } from '@/stores/control'
import { useTelemetryStore } from '@/stores/telemetry'
import { useDeviceMessagesStore } from '@/stores/deviceMessages'
import { useFleetStore } from '@/stores/fleet'
import { useDroneSn } from '@/composables/useDrone'
import { useFlightPhase } from '@/composables/useFlightPhase'
import { num } from '@/utils/format'
import { t, tc } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const emit = defineEmits<{ (e: 'collapse'): void }>()
const control = useControlStore()
const tel = useTelemetryStore()
const deviceMessages = useDeviceMessagesStore()
const fleet = useFleetStore()
const { hint } = useFlightPhase(sn)
const menuOpen = ref(false)
const limitOpen = ref(false)
const rcMore = ref(false)
const device = computed(() => (fleet.drones.length > 1 ? fleet.byGateway(sn) ?? null : null))
const dr = computed(() => (tel.online ? tel.drone : null))

const obstacles = computed(() => {
  const o = deviceMessages.obstacles
  if (!o) return null
  const m = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)} m`)
  return { text: t('避障 水平 {h} · 上方 {up} · 下方 {down}', { h: m(o.horizontal), up: m(o.up), down: m(o.down) }), near: o.near, stale: Date.now() - o.ts > 10_000 }
})

const state = computed(() => control.snapshot?.control ?? 'NONE')
const chip = computed(() => {
  switch (state.value) {
    case 'GRANTED':
      if (control.drcReady) return { cls: 'ok', text: control.snapshot && control.snapshot.heartbeatRttMs >= 0 ? t('控制权 · DRC {ms} ms', { ms: control.snapshot.heartbeatRttMs }) : t('控制权 · DRC') }
      return { cls: 'warn', text: control.snapshot?.drcState === 1 ? t('控制权 · DRC 连接中') : t('控制权 · DRC 未连接') }
    case 'REQUESTING': return { cls: 'warn', text: t('等待飞手同意…') }
    case 'DENIED': return { cls: 'danger', text: t('授权被拒绝') }
    case 'LOST': return { cls: 'danger', text: t('已失去控制权') }
    default: return { cls: '', text: t('未获得控制权') }
  }
})

const enterDrc = () => control.run('drc', t('进入 DRC'), () => controlApi(sn).enterDrc())
function release(): void {
  menuOpen.value = false
  void control.run('control', t('释放控制权'), () => controlApi(sn).release())
}
</script>

<template>
  <div class="head" data-test="panel-header">
    <div class="line">
      <span v-if="device" class="op" :style="{ '--c': device.color }" :title="t('{name}：{sn}', { name: device.label, sn: device.droneSn ?? device.gatewaySn })" data-test="operating">
        <span class="bar" />{{ t('正在操作') }} <b>{{ device.label }}</b>
      </span>
      <span class="chip" :class="chip.cls" data-test="control-chip"><span class="dot" />{{ chip.text }}</span>
      <button v-if="state !== 'GRANTED'" class="btn btn-sm btn-primary" :disabled="state === 'REQUESTING' || !tel.gateway?.gatewayOnline" data-test="request-control" @click="control.requestControl()">
        {{ state === 'REQUESTING' ? t('等待同意…') : tc('monitor', '申请控制权') }}
      </button>
      <button v-else-if="!control.drcReady" class="btn btn-sm btn-primary" data-test="enter-drc" @click="enterDrc">{{ t('进入 DRC') }}</button>
      <span class="grow" />
      <button class="btn btn-sm btn-icon sq" :aria-expanded="menuOpen" :aria-label="t('更多设置')" :title="t('更多设置')" data-test="panel-menu" @click="menuOpen = !menuOpen">
        <AppIcon name="more" :size="18" />
      </button>
      <button class="btn btn-sm btn-icon sq" :aria-label="t('收起侧栏')" :title="t('收起侧栏')" data-test="panel-collapse" @click="emit('collapse')">
        <AppIcon name="panel-close" :size="16" />
      </button>
    </div>
    <p v-if="control.snapshot?.message && state !== 'NONE' && state !== 'GRANTED'" class="msg">{{ control.snapshot.message }}</p>
    <CommandStatus class="ctl-status" :record="control.byAction('control') ?? control.byAction('drc')" />
    <PhaseBar :sn="sn" />
    <p v-if="hint" class="next" :class="{ warn: hint.warn }" data-test="next-hint">
      <AppIcon :name="hint.warn ? 'alert' : 'info'" :size="14" /><span>{{ hint.text }}</span>
    </p>
    <div v-if="state === 'GRANTED'" class="hint" data-test="rc-disabled-hint">
      <AppIcon name="alert" :size="15" />
      <span class="hint-text">{{ t('云端控制中：遥控器摇杆、拨轮、返航、急停按键') }}<b>{{ t('已失效') }}</b><template v-if="rcMore">{{ t('。飞手可在 Pilot 2 点击“抢夺控制权”收回控制。') }}</template></span>
      <button class="more" :aria-expanded="rcMore" :title="rcMore ? t('收起') : t('飞手怎样收回控制')" @click="rcMore = !rcMore">{{ rcMore ? t('收起') : 'ⓘ' }}</button>
    </div>
    <p class="sec num" :class="{ calm: !obstacles?.near }" data-test="secondary-line">
      {{ t('垂直 {v} m/s · 云台 {g}° · 机身俯仰 {p}°', { v: num(dr?.verticalSpeed, 1), g: num(dr?.gimbalPitch, 1), p: num(dr?.attitudePitch, 1) }) }}<br />
      <span class="obstacles" :class="{ near: obstacles?.near }" data-test="obstacles">
        {{ obstacles ? obstacles.text + (obstacles.stale ? t('（数据已过时）') : '') : t('避障：需 DRC 连接后才有数据') }}
      </span>
    </p>

    <div v-if="menuOpen" class="menu" role="menu" :aria-label="t('更多设置')">
      <button class="item" role="menuitem" :aria-expanded="limitOpen" @click="limitOpen = !limitOpen">
        <span>{{ t('飞行器限高（height_limit）') }}</span><span class="dim num">{{ tel.drone?.heightLimit ?? '—' }} m</span>
      </button>
      <div v-if="limitOpen" class="sub"><HeightLimitControl /></div>
      <RouterLink class="item" role="menuitem" to="/settings" @click="menuOpen = false">{{ t('平台安全设置、目标与 AI 设置 →') }}</RouterLink>
      <hr />
      <button class="item danger" role="menuitem" :disabled="state !== 'GRANTED'" data-test="release-control" @click="release">{{ t('释放控制权') }}</button>
    </div>
  </div>
</template>

<style scoped>
.head {
  position: relative;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px var(--sp-3) 8px;
  border-bottom: 1px solid var(--border);
}
.line {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.line .chip {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sq {
  width: 32px;
  min-height: 32px;
  flex: none;
}
.msg {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.op {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  font-size: var(--fs-sm);
  white-space: nowrap;
}
.op .bar {
  width: 4px;
  height: 18px;
  background: var(--c);
}
.op b {
  color: var(--c);
  font-size: var(--fs-md, 15px);
}
.next {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: var(--fs-xs);
  line-height: 1.35;
  color: var(--accent);
}
.next :deep(svg) {
  flex: none;
}
.next.warn {
  color: var(--warn);
  font-weight: 600;
}
.sec {
  margin: 0;
  font-size: var(--fs-xs);
  line-height: 1.5;
  color: var(--text-dim);
}
.obstacles.near {
  color: var(--warn);
  font-weight: 600;
}
/* small screens: the second-level line gives its room to the task area unless an obstacle is near */
@media (max-height: 800px) {
  .sec.calm {
    display: none;
  }
}
/* a confirmed control / DRC request is already shown by the chip; pending and failed ones stay visible */
.ctl-status[data-status='ACKED'] {
  display: none;
}
.hint {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 4px var(--sp-2);
  border-radius: var(--r-ctl);
  font-size: var(--fs-xs);
  line-height: 1.4;
  background: color-mix(in srgb, var(--warn) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--warn) 50%, transparent);
}
.hint :deep(svg) {
  color: var(--warn);
  flex: none;
  margin-top: 1px;
}
.hint-text {
  flex: 1;
  min-width: 0;
}
.hint .more {
  flex: none;
  padding: 0 4px;
  border: 0;
  background: none;
  color: var(--text-dim);
  font: inherit;
  cursor: pointer;
}
.menu {
  position: absolute;
  top: 50px;
  right: var(--sp-3);
  z-index: 50;
  width: 280px;
  padding: 6px;
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow);
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--sp-2);
  min-height: 36px;
  padding: 0 10px;
  border-radius: var(--r-ctl);
  border: 0;
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: var(--fs-sm);
  text-align: left;
  text-decoration: none;
  cursor: pointer;
}
.item:hover:not(:disabled) {
  background: var(--panel-2);
}
.item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.item.danger {
  color: var(--danger);
}
.sub {
  padding: 4px 10px 8px;
}
hr {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}
</style>
