<script setup lang="ts">
/**
 * One dog in the safety area (ui-design.md 5.5): name, state, age, and its two buttons — "stop" (single click; S10
 * with a menu of the three stops) and the press-and-hold soft e-stop (0.8 s, same component as the drone e-stop).
 * Clicking the blank part selects the dog; the buttons act on this dog without selecting it. For 6 s after a stop
 * (or any other note about this dog) the second line shows that note instead of the state, so its answer is seen
 * even when the pad is hidden or another device is being operated.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import HoldButton from '@/components/control/HoldButton.vue'
import { useDogStore, navActive, lite3Pose, S10_POSTURE, DOG_NAME } from '@/stores/dog'
import { useDogActions } from './useDogActions'
import { jobLabel, lite3Battery, s10RunningJob } from './dogFlow'
import { navShort, navTaskOn } from './dogNav'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'

const props = defineProps<{ dog: DogId; variant: 'row' | 'card'; selected: boolean }>()
const emit = defineEmits<{ (e: 'select'): void }>()
const store = useDogStore()
const act = useDogActions()
const menu = ref(false)

const online = computed(() => store.online(props.dog))
const lost = computed(() => store.lost(props.dog))
const stale = computed(() => store.pageStale(props.dog))
const off = computed(() => (online.value ? null : stale.value ? t('本页 {n} 秒没收到 {name} 的新状态', { n: store.staleSecs(props.dog), name: DOG_NAME[props.dog] }) : lost.value ? t('{name} 失联，指令发不出去，请用实体遥控器', { name: DOG_NAME[props.dog] }) : t('{name} 离线', { name: DOG_NAME[props.dog] })))

const line = computed(() => {
  if (!online.value) return stale.value ? t('本页 {n} 秒没收到新状态', { n: store.staleSecs(props.dog) }) : lost.value ? t('失联 · 失联前正在执行，现在状态未知') : t('离线')
  if (props.dog === 's10') {
    const s = store.s10!
    const job = s10RunningJob(s)
    const doing = store.s10Hold ? t('按住移动中') : job ? (job.origin === 'other' ? t('{job}（别处）', { job: jobLabel(job) }) : jobLabel(job)) : navActive(s.nav) ? t('导航中') : t('空闲')
    return `${S10_POSTURE[s.posture ?? ''] ?? s.posture ?? '—'} · ${doing}`
  }
  const l = store.lite3!
  const ctl = store.l3.session ? (store.l3Moving ? t('按住移动中') : t('由这个页面控制')) : l.robot.controller === 'other' ? t('别处控制 · 停止会解除对方控制') : l.robot.controller === 'platform' ? t('本平台另一页面控制') : t('未控制')
  const b = lite3Battery(l)
  // a navigation task of the new dog system (only dogs that can navigate have one)
  const nav = l3NavOn.value ? navShort(store.l3Nav!) : null
  return `${l.robot.robot_state ?? '—'} · ${nav ?? ctl}${b == null ? '' : ` · ${b}%`}`
})
/** Lite3 outdoor navigation on (starting, running, paused): the row gets "结束导航" (ui-design.md 19.6). */
const l3NavOn = computed(() => props.dog === 'lite3' && !!store.l3NavCap && navTaskOn(store.l3Nav))
const navEndWhy = computed(() => (off.value ?? (!store.l3.session ? t('由别处控制：按「停止」也会结束导航') : null)))
function endNav(): void {
  menu.value = false
  void store.l3NavCancel()
}
const age = computed(() => {
  if (props.dog === 's10') return store.s10 ? store.age('s10.work', 0, store.s10.workAt) : null
  return store.lite3 ? store.age('l3.state', store.lite3.robot.feedback_age, store.lite3.statusAt) : null
})
const ageText = computed(() => {
  const d = store.dogs[props.dog]
  if (!online.value) return d?.link.lastOkAt ? t('最后 {time}', { time: new Date(d.link.lastOkAt).toTimeString().slice(0, 5) }) : ''
  const a = age.value
  if (a == null) return ''
  const n = a < 10 ? a.toFixed(1) : Math.round(a)
  return props.dog === 's10' ? t('状态 {n} 秒前', { n }) : t('反馈 {n} 秒前', { n })
})
const recentNote = computed(() => {
  const n = store.notes[props.dog]
  return n && store.tick - n.at < 6000 ? n : null
})
const warnLine = computed(() => props.dog === 'lite3' && online.value && (store.lite3?.robot.controller === 'other' || lite3Pose(store.lite3?.robot.robot_state) === 'protect'))

function stopOne(k: 'hold' | 'nav' | 'arm'): void {
  menu.value = false
  store.stopSeq++
  if (k === 'hold') void store.s10HoldEnd('停止')   // i18n-ignore: sent to the backend, shown via tb()
  else if (k === 'nav') void store.s10Action({ action: 'nav_cancel', label: '取消导航' })   // i18n-ignore: sent to the backend, shown via tb()
  else void store.s10Action({ action: 'arm_stop', label: '停止机械臂动作' })   // i18n-ignore: sent to the backend, shown via tb()
}
</script>

<template>
  <div class="dsafe" :class="[variant, { on: selected, lost, offl: !online, tight: dog === 'lite3' && l3NavOn }]" :style="{ '--c': `var(--dog-${dog})` }" data-test="dog-safety"
       @click.self="emit('select')">
    <span class="bar" @click="emit('select')" />
    <div class="info" @click="emit('select')">
      <div class="nm"><b>{{ DOG_NAME[dog] }}</b><span class="dim num">{{ ageText }}</span></div>
      <div v-if="recentNote" class="ln" :class="{ warnc: recentNote.cls === 'warn', badc: recentNote.cls === 'bad', okc: recentNote.cls === 'ok' }"
           :title="recentNote.text" data-test="dog-safety-note">{{ recentNote.text }}</div>
      <div v-else class="ln" :class="{ warnc: warnLine, badc: lost }" :title="line">{{ line }}</div>
    </div>
    <div class="acts">
      <button class="btn stopb" :disabled="!!off" :title="off ?? (dog === 's10' ? t('停止正在进行的那件事（单击）') : t('停止运动并解除控制，也会解除别人的控制（单击）'))"
              data-test="dog-stop" @click="act.stop(dog)">
        <AppIcon name="stop" :size="15" />{{ t('停止') }}
      </button>
      <button v-if="dog === 's10' || l3NavOn" class="btn caret" :disabled="!!off" :title="t('分别停止')" :aria-expanded="menu" @click="menu = !menu">
        <AppIcon :name="menu ? 'down' : 'up'" :size="14" />
      </button>
      <HoldButton class="estopb" :disabled="!!off" :title="off ?? (dog === 's10' ? t('长按 0.8 秒：{name} 软急停（阻尼：关节不出力，之后要重新站立）', { name: DOG_NAME[dog] }) : t('长按 0.8 秒：{name} 软急停（进入保护状态并自动趴下）', { name: DOG_NAME[dog] }))"
                  data-test="dog-estop" @trigger="act.softEstop(dog)">
        <AppIcon name="estop" :size="15" />{{ t('软急停') }}
      </HoldButton>
    </div>
    <div v-if="menu && dog === 'lite3' && l3NavOn" class="pop" role="menu" data-test="dog-nav-menu">
      <span class="pt">{{ t('分别停止 · Lite3') }}</span>
      <button class="item" :disabled="!!navEndWhy" :title="navEndWhy ?? t('结束这次导航，狗原地停下（单击）')" data-test="dog-nav-end" @click="endNav">{{ t('结束导航') }}</button>
    </div>
    <div v-else-if="menu && dog === 's10'" class="pop" role="menu">
      <span class="pt">{{ t('分别停止 · S10') }}</span>
      <button class="item" :disabled="!store.s10Hold" @click="stopOne('hold')">{{ t('结束按住移动') }}</button>
      <button class="item" @click="stopOne('nav')">{{ t('取消导航') }}</button>
      <button class="item" @click="stopOne('arm')">{{ t('停止机械臂动作') }}</button>
    </div>
  </div>
</template>

<style scoped>
.dsafe {
  position: relative;
  display: grid;
  grid-template-columns: 4px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  background: var(--panel);
  cursor: pointer;
}
.dsafe.row { min-height: 48px; padding: 4px 6px 4px 0; }
@media (max-height: 800px) {
  /* two columns on low screens: name and state on top, buttons below */
  .dsafe.row { grid-template-columns: 4px minmax(0, 1fr); row-gap: 4px; }
  .dsafe.row .acts { grid-column: 1 / span 2; padding-left: 10px; }
  .dsafe.row .estopb { min-width: 0; flex: 1; }
  .dsafe.row .stopb { padding: 0 6px; }
  .dsafe.row .caret { width: 22px; }
}
.dsafe.card { grid-template-columns: 4px minmax(0, 1fr); padding: 8px 8px 8px 0; align-items: start; }
/* Lite3 navigating: the ▾ joins stop and soft stop; all three stay inside the half-width card */
.dsafe.card.tight .stopb { padding: 0 6px; }
.dsafe.card.tight .caret { width: 22px; }
.dsafe.card.tight .estopb { min-width: 78px; }
.dsafe.card .acts { grid-column: 1 / span 2; padding-left: 12px; }
.dsafe.on { border-color: var(--c); box-shadow: inset 0 0 0 1px var(--c); }
.dsafe.lost { border-color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, var(--panel)); }
.dsafe.offl .info { opacity: 0.6; }
.bar { align-self: stretch; border-radius: 0 2px 2px 0; background: var(--c); }
.info { min-width: 0; }
.nm { display: flex; gap: 8px; align-items: baseline; }
.nm b { color: var(--c); font-size: var(--fs-md); }
.nm .dim { font-size: 11px; }
.ln { font-size: var(--fs-xs); overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.warnc { color: var(--warn); }
.badc { color: var(--danger); }
.okc { color: var(--ok); }
.acts { display: flex; gap: 6px; align-items: center; }
.stopb { min-height: 40px; padding: 0 10px; white-space: nowrap; color: var(--danger); border-color: color-mix(in srgb, var(--danger) 55%, transparent); background: transparent; }
.caret { min-height: 40px; width: 28px; padding: 0; }
.estopb { min-height: 40px; min-width: 88px; white-space: nowrap; }
.estopb { font-size: 15px; letter-spacing: 0.04em; }
.estopb :deep(.content) { gap: 4px; }
.pop {
  position: absolute;
  right: 0;
  bottom: calc(100% + 4px);
  z-index: 50;
  display: flex;
  flex-direction: column;
  min-width: 200px;
  padding: 6px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel);
  box-shadow: var(--shadow);
}
.pt { font-size: var(--fs-xs); color: var(--text-dim); padding: 2px 6px 6px; }
.item { text-align: left; padding: 8px; border: none; background: transparent; color: var(--text); cursor: pointer; border-radius: var(--r-ctl); font: inherit; }
.item:hover:not(:disabled) { background: color-mix(in srgb, var(--accent) 15%, transparent); }
.item:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
