<script setup lang="ts">
/**
 * Fixed safety area at the bottom of the monitor side panel (R-10 ~ R-12, R-28, S-05, ui-design.md §2.2 / §5): the
 * selected drone's one stop for the running task plus a menu with every stop and the locked landing menu; the
 * distance between the two drones; and one card per drone with its take-off / return home and press-and-hold
 * emergency stop — so the safety buttons of both drones sit in one place, where the emergency stop always was.
 * Every button calls the same API, with the same confirmation, as before.
 */
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import DangerZone from '@/components/control/DangerZone.vue'
import FleetCard from './FleetCard.vue'
import { useControlStore } from '@/stores/control'
import { useFleetStore } from '@/stores/fleet'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTasksStore, STOP_ITEMS, type StopKey } from '@/stores/tasks'
import { distance } from '@/utils/geo'
import DogSafety from '@/components/dog/DogSafety.vue'
import { useDogStore, DOG_NAME } from '@/stores/dog'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'

/** dogMode: a dog is operated, so the selected drone's stop / landing row is not shown (ui-design.md 5.5). */
const props = defineProps<{ dogMode?: boolean }>()

const control = useControlStore()
const tel = useTelemetryStore()
const tasks = useTasksStore()
const fleet = useFleetStore()
const stopMenu = ref(false)
const landOpen = ref(false)
const many = computed(() => fleet.drones.length > 1)
const name = computed(() => fleet.label(tel.sn))
/* robot dogs: online (or lost while busy) dogs get a block like the drones; offline ones collapse into one line */
const dogs = useDogStore()
const dogIds = computed(() => dogs.ids.filter((id) => dogs.important(id)))
const offDogs = computed(() => dogs.ids.filter((id) => !dogs.important(id)))
/** Devices shown with buttons; three or more get one row each so every button stays on screen (ui-design.md 16 ③). */
const total = computed(() => fleet.enabled.length + dogIds.value.length)
const rows = computed(() => dogs.present && total.value > 2)
function lastSeen(id: DogId): string {
  const okAt = dogs.dogs[id]?.link.lastOkAt
  if (!okAt) return t('从未连上')
  const min = Math.round((dogs.serverNow() - okAt) / 60000)   // lastOkAt is the server's clock
  return min < 1 ? t('刚刚') : min < 60 ? t('{n} 分钟前', { n: min }) : t('{n} 小时前', { n: Math.round(min / 60) })
}

/** Shown in the air, and on the ground while something stoppable runs (e.g. a route waiting for authorisation). */
const showStop = computed(() => !props.dogMode && (tel.airborne || !tasks.stopPlan.idle))
const stopTitle = computed(() => (tasks.stopPlan.idle ? t('没有检测到正在运行的任务：按下发送「结束 flyto」，飞机悬停（与原来的「结束 flyto」相同）') : t('调用「{stop}」原来的接口', { stop: tasks.stopPlan.label.replace(t(' · 悬停'), '') })))

/** Two drones: their distance, from the proximity monitor while it reports the pair, else from their positions. */
const pair = computed(() => {
  if (fleet.enabled.length !== 2) return null
  const [a, b] = fleet.enabled as [(typeof fleet.enabled)[number], (typeof fleet.enabled)[number]]
  const names = `${a.label} ↔ ${b.label}`
  const p = fleet.proximity.find((x) => x.active && [x.a, x.b].includes(a.droneSn) && [x.a, x.b].includes(b.droneSn))
  if (p) return { names, h: p.horizontalM, v: p.verticalM, cls: p.level === 'hold' ? 'danger' : 'warn', close: true }
  const ta = useTelemetryStore(a.gatewaySn)
  const tb = useTelemetryStore(b.gatewaySn)
  if (!ta.online || !tb.online || !ta.airborne || !tb.airborne || !ta.position || !tb.position) return { names, h: null, v: null, cls: '', close: false }
  const ha = ta.drone?.ellipsoidHeight
  const hb = tb.drone?.ellipsoidHeight
  return { names, h: distance(ta.position, tb.position), v: ha != null && hb != null ? Math.abs(ha - hb) : null, cls: '', close: false }
})

function stopOne(k: StopKey): void {
  stopMenu.value = false
  void tasks.stop(k)
}
function toggleStopMenu(): void {
  stopMenu.value = !stopMenu.value
  landOpen.value = false
}
function toggleLand(): void {
  landOpen.value = !landOpen.value
  stopMenu.value = false
}
</script>

<template>
  <div class="footer" data-test="safety-footer">
    <div v-if="showStop" class="stop-row">
      <button class="btn stop" :class="{ hot: !tasks.stopPlan.idle }" :title="stopTitle" data-test="stop-main" @click="stopOne(tasks.stopPlan.key)">
        <AppIcon name="stop" :size="15" /><span v-if="many" class="who" :style="{ '--c': fleet.color(tel.sn) }">{{ name }}</span><span class="lbl">{{ tasks.stopPlan.label }}</span>
      </button>
      <button class="btn btn-icon menu-btn" :aria-expanded="stopMenu" :aria-label="t('全部停止选项')" :title="t('全部停止选项')" data-test="stop-menu-toggle" @click="toggleStopMenu">
        <AppIcon :name="stopMenu ? 'down' : 'up'" :size="15" />
      </button>
      <button v-if="tel.airborne" class="btn land" :aria-expanded="landOpen" data-test="danger-toggle" @click="toggleLand">
        <AppIcon name="land" :size="16" />{{ t('降落') }}<AppIcon :name="landOpen ? 'down' : 'up'" :size="12" />
      </button>
    </div>
    <p v-if="showStop && tasks.othersRunning.length" class="others">{{ t('另有运行中：{list}，用 ▾ 分别停止。', { list: tasks.othersRunning.join(t('、')) }) }}</p>
    <div v-if="stopMenu" class="pop" role="menu" :aria-label="t('全部停止选项')" data-test="stop-menu">
      <span class="pop-title">{{ many ? t('全部停止 · {name} · 每一项都调用原来的接口', { name }) : t('全部停止 · 每一项都调用原来的接口') }}</span>
      <button v-for="s in STOP_ITEMS" :key="s.key" class="item" role="menuitem" :class="{ main: tasks.stopPlan.key === s.key }"
        :disabled="!tasks.stopEnabled(s.key)" :data-test="`stop-${s.key}`" @click="stopOne(s.key)">
        <span>{{ s.label }}</span><span class="api num">{{ s.api }}</span>
      </button>
    </div>
    <div v-if="landOpen" class="pop danger" data-test="landing-menu">
      <span class="pop-title"><AppIcon name="alert" :size="14" />{{ many ? t('危险操作 · 降落 · {name}', { name }) : t('危险操作 · 降落') }}</span>
      <DangerZone bare :enabled="control.drcReady && tel.airborne" />
    </div>

    <p v-if="pair" class="prox num" :class="pair.cls" data-test="pair-distance">
      <template v-if="pair.h != null">
        <AppIcon name="alert" :size="13" />{{ t('{names} 水平', { names: pair.names }) }} <b>{{ Math.round(pair.h) }} m</b> · {{ t('高度差') }}
        <b>{{ pair.v == null ? t('未知') : `${Math.round(pair.v)} m` }}</b>{{ pair.close ? t(' · 靠近！') : '' }}
      </template>
      <template v-else>{{ t('{names}：两架都在空中时显示距离', { names: pair.names }) }}</template>
    </p>
    <div class="cards" :class="{ one: total < 2, list: total > 2, grid4: rows }">
      <FleetCard v-for="d in fleet.enabled" :key="d.gatewaySn" :device="d" :selected="d.gatewaySn === fleet.selectedSn && !dogs.selected" :compact="rows" />
      <DogSafety v-for="id in dogIds" :key="id" :dog="id" :variant="rows ? 'row' : 'card'" :selected="dogs.selected === id" @select="dogs.select(id)" />
    </div>
    <p v-if="offDogs.length" class="offline" data-test="dogs-offline">{{ t('离线：') }}
      <button v-for="id in offDogs" :key="id" class="link" :title="t('看 {name} 最后的数据', { name: DOG_NAME[id] })" @click="dogs.select(id)">{{ DOG_NAME[id] }} {{ lastSeen(id) }}</button>
    </p>
    <RouterLink v-if="fleet.pending.length" class="pending" to="/settings?section=devices" data-test="fleet-pending">
      {{ t('{n} 台设备待启用（{names}）→ 设置', { n: fleet.pending.length, names: fleet.pending.map((d) => d.label).join(t('、')) }) }}
    </RouterLink>
    <p v-if="dogs.present" class="estop-note"><AppIcon name="info" :size="13" />{{ t('急停 / 软急停：长按 0.8 秒 · 不能代替实体遥控器') }}</p>
    <p v-else class="estop-note"><AppIcon name="info" :size="13" />{{ t('急停：长按 0.8 秒，飞机原地悬停') }}</p>
  </div>
</template>

<style scoped>
.footer {
  position: relative;
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px var(--sp-3) 8px;
  border-top: 1px solid var(--border);
  background: color-mix(in srgb, var(--panel-2) 45%, var(--panel));
}
.stop-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 44px 96px;
  gap: 6px;
}
.stop {
  justify-content: flex-start;
  min-width: 0;
  min-height: 46px;
  border-color: color-mix(in srgb, var(--danger) 55%, transparent);
  background: transparent;
  color: var(--danger);
}
.stop.hot {
  border-width: 2px;
  border-color: var(--danger);
  background: color-mix(in srgb, var(--danger) 18%, transparent);
  color: var(--text);
}
.stop .lbl {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.who {
  flex: none;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--c);
  color: #fff;
  font-weight: 800;
}
.menu-btn {
  min-height: 46px;
  border-color: color-mix(in srgb, var(--danger) 55%, transparent);
  background: transparent;
  color: var(--danger);
}
.others {
  margin: -2px 0 0;
  font-size: var(--fs-xs);
  color: var(--danger);
}
.land {
  min-height: 46px;
  padding: 0 6px;
  gap: 4px;
  border-color: color-mix(in srgb, var(--danger) 55%, transparent);
  background: transparent;
  color: var(--danger);
  font-size: var(--fs-md);
}
.pop {
  position: absolute;
  left: var(--sp-3);
  right: var(--sp-3);
  bottom: calc(100% + 6px);
  z-index: 45;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: var(--sp-2);
  border-radius: var(--r-panel);
  border: 1px solid var(--danger);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.pop-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 4px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.pop.danger .pop-title {
  color: var(--danger);
  font-weight: 700;
  font-size: var(--fs-sm);
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
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}
.item.main {
  background: color-mix(in srgb, var(--danger) 16%, transparent);
}
.item:hover:not(:disabled) {
  background: var(--panel-2);
}
.item:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.prox {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  margin: 0;
  min-height: 18px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.prox.warn {
  color: var(--warn);
}
.prox.danger {
  color: var(--danger);
  font-weight: 700;
}
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.cards.one,
.cards.list {
  grid-template-columns: 1fr;
}
.offline {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.offline .link {
  border: none;
  background: none;
  color: var(--text-dim);
  text-decoration: underline dotted;
  cursor: pointer;
  font: inherit;
  padding: 0 6px 0 0;
}
.pending {
  font-size: var(--fs-xs);
  color: var(--warn);
}
.estop-note {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: 11px;
  color: var(--text-dim);
}
.api {
  font-size: 11px;
  font-weight: 400;
  color: var(--text-dim);
}
/* small screens: the note stays in the emergency stop buttons' tooltip */
@media (max-height: 800px) {
  .estop-note {
    display: none;
  }
  /* three or more devices with robot dogs on a low screen: two columns, two rows (ui-design.md 5.5) */
  .cards.list.grid4 {
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
}
</style>
