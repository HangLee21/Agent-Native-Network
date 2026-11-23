
<script setup lang="ts">
/**
 * Upper part of the side panel while a dog is operated (ui-design.md 5.4): who is operated and link, the stage bar,
 * the next-step line (fixed height), the function pages, the two latest commands. The safety area below stays the
 * monitor page's own.
 */
import { computed, ref } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import FlowBar from './FlowBar.vue'
import NextBar from './NextBar.vue'
import CommandRow from './CommandRow.vue'
import S10Body from './S10Body.vue'
import Lite3Body from './Lite3Body.vue'
import { useDogStore, lite3Pose, DOG_NAME } from '@/stores/dog'
import { useDogActions } from './useDogActions'
import { lite3Flow, lite3Next, s10Flow, s10Next, s10RunningJob } from './dogFlow'
import type { DogId } from '@/api/dog'
import { t } from '@/i18n'
import { lite3Online } from './lite3Info'

const props = defineProps<{ dog: DogId }>()
const emit = defineEmits<{ (e: 'help', id: string): void }>()
const store = useDogStore()
const act = useDogActions()

const card = ref('posture')
const online = computed(() => store.online(props.dog))
/** Failure of the platform's last command, shown until acknowledged or the next command. */
const ackedFail = ref<string | null>(null)
const lastFail = computed(() => {
  const c = store.commands.s10[0]
  return c && ['failed', 'notdone', 'lost', 'unknown', 'noreply'].includes(c.state) && c.id !== ackedFail.value ? c : null
})

const s10AgeState = computed(() => (store.s10 ? store.age('s10.work', 0, store.s10.workAt) : null))
const jobSecs = computed(() => {
  const j = s10RunningJob(store.s10)
  // the job's start time is the board's clock: compare with "now" on the board's clock too
  const now = store.serverNow() / 1000 + (store.s10?.link.boardOffsetSec ?? 0)
  return j?.started ? Math.max(0, Math.round(now - j.started)) : 0
})

const segs = computed(() =>
  props.dog === 's10'
    ? s10Flow(store.s10, online.value, !!store.s10Hold)
    : lite3Flow(store.lite3, online.value, !!store.l3.session, store.l3Moving),
)
const next = computed(() =>
  props.dog === 's10'
    ? s10Next({ s: store.s10, online: online.value, lost: store.lost('s10'), holding: !!store.s10Hold || !!store.armHold, card: card.value, lastFail: lastFail.value, stateAge: s10AgeState.value, jobSecs: jobSecs.value })
    : lite3Next({
      l: store.lite3, online: online.value, mine: !!store.l3.session, holding: store.l3Moving, pose: lite3Pose(store.lite3?.robot.robot_state),
      marks: store.l3Marks, endedReason: store.l3.endedReason, feedbackAge: store.lite3 ? store.age('l3.state', store.lite3.robot.feedback_age, store.lite3.statusAt) : null,
      nav: store.l3Nav, adoptable: !!store.l3v2?.control?.adoptable,
    }),
)

const s10Ref = ref<InstanceType<typeof S10Body> | null>(null)
function fix(key: string): void {
  if (key.startsWith('card:')) {
    card.value = key.slice(5)
    return
  }
  switch (key) {
    case 'stand':
      if (props.dog === 'lite3') void store.l3Mode('stand', '起立（起立 / 趴下切换）')   // i18n-ignore: sent to the backend, shown via tb()
      else void act.s10({ action: 'posture', posture: 'stand', label: '站立' })   // i18n-ignore: sent to the backend, shown via tb()
      break
    case 'sit': void act.s10({ action: 'posture', posture: 'sit', label: '趴下' }); break   // i18n-ignore: sent to the backend, shown via tb()
    case 'rl': void act.s10({ action: 'posture', posture: 'rl', label: 'RL 控制' }); break   // i18n-ignore: sent to the backend, shown via tb()
    case 'armhome': void s10Ref.value?.armHome(); break
    case 'navcancel': void act.s10({ action: 'nav_cancel', label: '取消导航' }); break   // i18n-ignore: sent to the backend, shown via tb()
    case 'armstop': void act.s10({ action: 'arm_stop', label: '停止机械臂动作' }); break   // i18n-ignore: sent to the backend, shown via tb()
    case 'clearfail': ackedFail.value = lastFail.value?.id ?? null; break
    case 'arm': void store.l3Arm(); break
    case 'moving': void store.l3Mode('moving', '移动模式'); break   // i18n-ignore: sent to the backend, shown via tb()
    case 'selfsitok': store.l3Marks.selfSit = false; break
    case 'l3navcancel': void store.l3NavCancel(); break
    case 'l3navresume': void store.l3NavResume(); break
  }
}

const recent = computed(() => store.commands[props.dog].slice(0, 2))
const linkTag = computed(() => {
  const d = store.dogs[props.dog]
  if (!d) return { cls: '', text: t('没有数据') }
  if (store.lost(props.dog)) return { cls: 'bad', text: t('失联') }
  if (store.pageStale(props.dog)) return { cls: '', text: t('本页 {n} 秒没收到新状态', { n: store.staleSecs(props.dog) }) }
  if (d.link.state === 'reconnecting') return { cls: '', text: t('正在重新连接') }
  if (!online.value) return { cls: '', text: t('离线') }
  if (props.dog === 'lite3') return lite3Online(store.l3v2)
  const a = s10AgeState.value
  return { cls: 'ok', text: t('在线 · 状态 {age}', { age: a == null ? '—' : t('{n} 秒前', { n: a.toFixed(1) }) }) }
})
</script>

<template>
  <div class="dogpanel" :style="{ '--c': `var(--dog-${dog})` }" data-test="dog-panel">
    <div class="head">
      <span class="bar" /><span class="lbl">{{ t('正在操作') }}</span><b class="nm">{{ DOG_NAME[dog] }}</b>
      <span class="tag" :class="linkTag.cls"><span class="sd" />{{ linkTag.text }}</span>
      <span class="grow" />
      <button class="qm" :title="t('怎么用 {name}', { name: DOG_NAME[dog] })" @click="emit('help', dog === 's10' ? 'm-s10-walk' : 'm-lite3')">?</button>
    </div>
    <FlowBar :segs="segs" />
    <NextBar :step="next" @fix="fix" />
    <S10Body v-if="dog === 's10' && store.s10" ref="s10Ref" :card="card" @card="card = $event" @help="emit('help', $event)" />
    <Lite3Body v-else-if="dog === 'lite3' && store.lite3" @help="emit('help', $event)" />
    <div class="recent">
      <div class="rh"><span>{{ t('最近指令 · {name}', { name: DOG_NAME[dog] }) }}</span></div>
      <CommandRow v-for="c in recent" :key="c.id" :cmd="c" />
      <div v-if="!recent.length" class="dim none">{{ t('暂无指令') }}</div>
    </div>
  </div>
</template>

<style scoped>
.dogpanel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 0;
  flex: 1;
  padding: 8px var(--sp-3) 6px;
}
.head { display: flex; align-items: center; gap: 8px; height: 30px; flex: none; }
.bar { width: 4px; height: 22px; border-radius: 2px; background: var(--c); }
.lbl { color: var(--text-dim); font-size: var(--fs-sm); }
.nm { font-size: 20px; color: var(--c); }
.tag { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); font-size: var(--fs-xs); }
.tag.ok { border-color: color-mix(in srgb, var(--ok) 55%, transparent); }
.tag.bad { border-color: var(--danger); color: var(--danger); }
.sd { width: 7px; height: 7px; border-radius: 50%; background: var(--text-dim); }
.tag.ok .sd { background: var(--ok); }
.tag.bad .sd { background: var(--danger); }
.grow { flex: 1; }
.qm { width: 20px; height: 20px; border-radius: 50%; border: 1px solid var(--border); background: transparent; color: var(--text-dim); cursor: pointer; padding: 0; }
.recent { flex: none; border-top: 1px solid var(--border); padding-top: 4px; height: 76px; overflow: hidden; }
/* short screens: one command (ui-design.md 5.8) */
@media (max-height: 800px) {
  .recent { height: 50px; }
  .recent > :nth-child(3) { display: none; }
}
.rh { font-size: var(--fs-xs); color: var(--text-dim); margin-bottom: 2px; }
.none { font-size: var(--fs-xs); }
</style>
