
<script setup lang="ts">
/**
 * The Lite3 area under the next-step line (ui-design.md 20): eight always-visible numbers, then the groups in a fixed
 * order — preparation (take control → stand → walk; moving mode and low-speed gait when needed), outdoor navigation,
 * motion and attitude, position and heading, board and video. Groups fold only when the operator clicks their title.
 *
 * Preparation (ui-design.md 5.4, 9.0): the 2026-11-10 MQTT log shows lite3-01 walking and turning right after standing
 * with no moving mode sent (four sessions, also after a soft e-stop), so moving mode is no longer a required step; it
 * is kept for a dog that only tilts its body (pose mode in the official manual). Gait only switches in moving mode
 * (official manual). The stand button is a toggle on the dog's side, so it says what this press will do — and when the
 * dog's state name is not one the platform knows, it says both and shows the dog's own word.
 */
import { computed, nextTick, ref, watch } from 'vue'
import Step from './Step.vue'
import Btn2 from './Btn2.vue'
import Lite3Nav from './Lite3Nav.vue'
import DogSection from './DogSection.vue'
import { navSummary, navTaskOn } from './dogNav'
import { useDogStore, lite3Pose } from '@/stores/dog'
import { lite3Battery } from './dogFlow'
import { boardRows, boardSummary, lite3Chips, motionRows, motionSummary, positionRows, positionSummary } from './lite3Info'
import { t } from '@/i18n'

const emit = defineEmits<{ (e: 'help', id: string): void }>()
/** Command labels: sent to the backend in Chinese (shared data stays in one language), shown translated via tb(). */
const CMD = {
  release: '手动释放',   // i18n-ignore: sent to the backend, shown via tb()
  lie: '趴下（起立 / 趴下切换）',   // i18n-ignore: sent to the backend, shown via tb()
  stand: '起立（起立 / 趴下切换）',   // i18n-ignore: sent to the backend, shown via tb()
  moving: '移动模式',   // i18n-ignore: sent to the backend, shown via tb()
  low: '低速步态',   // i18n-ignore: sent to the backend, shown via tb()
}
const store = useDogStore()
const l = computed(() => store.lite3!)
const online = computed(() => store.online('lite3'))
const mine = computed(() => !!store.l3.session)
const pose = computed(() => lite3Pose(l.value.robot.robot_state))
const up = computed(() => pose.value === 'standing')
const fbAge = computed(() => store.age('l3.state', l.value.robot.feedback_age, l.value.statusAt))
const otherCtl = computed(() => l.value.robot.controller === 'other' || (l.value.robot.controller === 'platform' && !mine.value))
const ctlText = computed(() => (mine.value ? t('由这个页面控制') : !otherCtl.value ? t('还没有取得控制') : l.value.robot.controller === 'platform' ? t('由本平台另一个页面控制') : t('由别处控制')))

/** Navigating while the page that held control went silent (reloaded, crashed): this page can take it back. */
const adoptable = computed(() => !mine.value && !!store.l3v2?.control?.adoptable)
const ctlReason = computed(() => {
  if (!online.value) return t('Lite3 离线')
  if (l.value.robot.connected === false) return l.value.robot.error || t('收不到运动主机的状态包：这时取得控制会被拒绝')
  if (otherCtl.value && !adoptable.value) return t('被别处控制')
  return null
})
const modeReason = computed(() => (!online.value ? t('Lite3 离线') : !mine.value ? (otherCtl.value ? t('被别处控制') : t('先「取得控制」')) : store.l3Moving ? t('先松开方向键') : null))
const standReason = computed(() => {
  if (modeReason.value) return modeReason.value
  if (pose.value === 'transition') return t('{state}，等它完成再按', { state: l.value.robot.robot_state })
  if (fbAge.value != null && fbAge.value > 1) return t('状态 {n} 秒没更新：这是切换按钮，状态不准时按下去可能起相反的作用', { n: fbAge.value.toFixed(1) })
  return null
})
/** 3 s after a stand / lie toggle from this page or any other (browser clock for ours, server clock for theirs). */
const standCooling = computed(() => store.l3StandCooling())
const standLabel = computed(() => {
  if (pose.value === 'transition') return `${l.value.robot.robot_state}…`
  if (pose.value === 'unknown') return t('起立 / 趴下')   // the platform does not know which way it will go
  return up.value ? t('趴下') : t('起立')
})
const battery = computed(() => lite3Battery(l.value))
/** Outdoor navigation, only for a dog that reports it (ui-design.md 19). */
const navOn = computed(() => !!store.l3NavCap)
const navTask = computed(() => navOn.value && navTaskOn(store.l3Nav))
const bodyEl = ref<HTMLElement | null>(null)
const navSec = ref<InstanceType<typeof DogSection> | null>(null)
// a task starting scrolls the groups to the navigation group; the order of the groups never changes (ui-design.md 20.3)
watch(navTask, async (on) => {
  if (!on) return
  await nextTick()
  const box = bodyEl.value
  const sec = navSec.value?.el
  if (box && sec) box.scrollTop = sec.offsetTop
})
/** Everything the platform has from the new dog system (ui-design.md 20): the chips and the three data groups. */
const v2dog = computed(() => store.l3v2)
const chips = computed(() => lite3Chips(v2dog.value, { battery: battery.value, state: l.value.robot.robot_state, feedbackAge: fbAge.value }))
const motion = computed(() => motionRows(v2dog.value))
const position = computed(() => positionRows(v2dog.value))
const board = computed(() => boardRows(v2dog.value, mine.value))
const prepSum = computed(() => ({ text: `${ctlText.value} · ${l.value.robot.robot_state ?? '—'}`, cls: otherCtl.value ? 'warnc' : '' }))
const navSum = computed(() => navSummary(store.l3Nav))
const motionSum = computed(() => motionSummary(v2dog.value))
const positionSum = computed(() => positionSummary(v2dog.value))
const boardSum = computed(() => boardSummary(v2dog.value))
const lowCooling = computed(() => {
  const c = store.commands.lite3.find((x) => x.action === 'low' || x.action === 'moving')
  return !!c && store.tick - c.createdAt < 1000
})
</script>

<template>
  <div class="l3body">
    <!-- always visible: the numbers needed while walking or navigating (ui-design.md 20.3) -->
    <div class="chips" data-test="l3-chips">
      <div v-for="c in chips" :key="c.key" class="l3c" :title="t('{label}：{message}', { label: c.label, message: c.title ?? c.value })" :data-test="`l3-chip-${c.key}`">
        <em>{{ c.label }}</em><b :class="[c.cls, c.key === 'state' ? '' : 'num']">{{ c.value }}</b>
      </div>
    </div>
    <div ref="bodyEl" class="secs scroll">
      <DogSection id="lite3-prep" :title="t('准备 · 走动')" :summary="prepSum.text" :summary-cls="prepSum.cls">
        <Step :n="1" :state="mine ? 'done' : 'cur'" :title="t('取得控制')" help="g-ctl" @help="emit('help', $event)">
          <span class="ctlchip" :class="mine ? 'ok' : otherCtl ? 'warn' : ''" :title="ctlText">{{ ctlText }}</span>
          <Btn2 v-if="mine" :main="t('释放')" @click="store.l3Release(CMD.release)" />
          <Btn2 v-else :main="adoptable ? t('接回控制') : t('取得控制')" kind="primary" :reason="ctlReason ?? (store.l3.arming ? t('正在取得…') : null)" @click="store.l3Arm()" />
          <template #expl>{{ t('同一时间只能有一处控制 Lite3。在这里取得控制后，别的浏览器页面、别的电脑都动不了它，直到你点「释放」。网络卡 0.5 秒狗先停下、控制权还在，3 秒没联系才交出；离开这个页面时会自动释放。') }}</template>
        </Step>
        <Step :n="2" :state="mine && up ? 'done' : mine ? 'cur' : ''" :title="t('站起来')" help="g-toggle" @help="emit('help', $event)">
          <Btn2 :main="standLabel" :sub="t('起立 / 趴下切换')" kind="warn" :reason="standReason ?? (standCooling ? t('刚按过，3 秒内不能再按') : null)"
                @click="store.l3Mode('stand', up ? CMD.lie : CMD.stand)" />
          <template #expl>{{ t('厂家的起立 / 趴下是同一个切换指令，按钮上写的是这次按下去会做什么。开机后第一次起立会先初始化关节，约 10 秒。') }}</template>
        </Step>
        <Step :n="3" :state="mine && up ? 'cur' : ''" :title="t('走')">
          <template #expl>{{ t('用主画面右下角「按住移动」：只有一档速度，按住才动，松手即停。可以同时按几个键（W+A 斜走、W+Q 边走边转）。') }}</template>
        </Step>
        <div class="gl need">{{ t('需要时') }}</div>
        <Step :state="store.l3Marks.moving ? 'done' : ''" :title="t('移动模式（方向键不走时）')" help="g-moving" @help="emit('help', $event)">
          <Btn2 :main="t('移动模式')" :reason="modeReason ?? (lowCooling ? t('刚按过，1 秒内不能再按') : null)" @click="store.l3Mode('moving', CMD.moving)" />
          <span v-if="store.l3Marks.moving" class="sent">{{ t('已发送') }}</span>
          <template #expl>{{ t('起立后按方向键就能走（11-10 实测，没按这一步）。如果按方向键狗只歪身体、原地扭，不往前走，按一次「移动模式」再走；重复按没有坏处。') }}</template>
        </Step>
        <Step :state="store.l3Marks.low ? 'done' : ''" :title="t('低速步态（想走慢些时）')" help="g-low" @help="emit('help', $event)">
          <Btn2 :main="t('低速步态')" :sub="t('平地低速')" :reason="modeReason ?? (lowCooling ? t('刚按过，1 秒内不能再按') : null)" @click="store.l3Mode('low', CMD.low)" />
          <span v-if="store.l3Marks.low" class="sent">{{ t('已发送') }}</span>
          <template #expl>{{ t('平地上慢速走的步态，不是趴下。官方说明步态只能在移动模式下切换：按了没变慢，先按「移动模式」再按这里。') }}</template>
        </Step>
      </DogSection>
      <DogSection v-if="navOn" id="lite3-nav" ref="navSec" :title="t('导航（户外 GPS）')" :summary="navSum.text" :summary-cls="navSum.cls">
        <Lite3Nav />
      </DogSection>
      <DogSection id="lite3-motion" :title="t('运动与姿态')" :summary="motionSum.text" :summary-cls="motionSum.cls" :default-open="false">
        <div class="srows" data-test="l3-motion">
          <div v-for="r in motion" :key="r.label"><em>{{ r.label }}</em><b class="num" :class="r.cls" :title="r.title ?? r.value">{{ r.value }}</b></div>
        </div>
      </DogSection>
      <DogSection id="lite3-position" :title="t('位置与朝向')" :summary="positionSum.text" :summary-cls="positionSum.cls" :default-open="false">
        <div class="srows" data-test="l3-position">
          <div v-for="r in position" :key="r.label"><em>{{ r.label }}</em><b class="num" :class="r.cls" :title="r.title ?? r.value">{{ r.value }}</b></div>
        </div>
      </DogSection>
      <DogSection id="lite3-board" :title="t('板卡与视频')" :summary="boardSum.text" :summary-cls="boardSum.cls" :default-open="false">
        <div class="srows" data-test="l3-info">
          <div v-for="r in board" :key="r.label"><em>{{ r.label }}</em><b :class="r.cls" :title="r.title ?? r.value">{{ r.value }}</b></div>
        </div>
      </DogSection>
    </div>
  </div>
</template>

<style scoped>
.l3body { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 6px; }
/* the state name is the longest value (FORCE_CONTROL): its column is wider */
.chips { flex: none; display: grid; grid-template-columns: minmax(0, 0.75fr) minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1fr); gap: 4px; }
.l3c { display: flex; flex-direction: column; justify-content: center; gap: 1px; height: 38px; padding: 0 7px; border: 1px solid var(--border); border-radius: var(--r-ctl); min-width: 0; }
.l3c em { font-style: normal; color: var(--text-dim); font-size: 11px; line-height: 14px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.l3c b { font-size: 13px; line-height: 17px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.secs { position: relative; flex: 1; min-height: 0; padding: 0 2px; }
.secs > :first-child { border-top: none; }
.ctlchip { display: inline-flex; align-items: center; padding: 0 10px; height: 40px; white-space: nowrap; border-radius: var(--r-ctl); border: 1px solid var(--border); font-size: var(--fs-xs); }
.ctlchip.ok { border-color: var(--ok); color: var(--ok); }
.ctlchip.warn { border-color: var(--warn); color: var(--warn); }
.sent { align-self: center; font-size: 12px; color: var(--warn); }
.gl { font-weight: 600; font-size: var(--fs-sm); margin-bottom: 6px; }
.gl.need { margin: 8px 0 0; padding-top: 6px; border-top: 1px dashed var(--border); color: var(--text-dim); }
.srows { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 12px; font-size: var(--fs-xs); }
.srows div { display: flex; flex-direction: column; min-width: 0; }
.srows em { font-style: normal; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.srows b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.num { font-variant-numeric: tabular-nums; }
.okc { color: var(--ok); }
.warnc { color: var(--warn); }
.badc { color: var(--danger); }
.dim { color: var(--text-dim); }
</style>
