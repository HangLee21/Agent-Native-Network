<script setup lang="ts">
/**
 * Target card (proposal "Target and target card"): where the target is, how sure we are, and what the
 * drone may do next. Movement actions are separate, explicit choices; the backend applies the distance
 * rules (never moves inside the minimum distance) and the safety layer before anything is sent.
 */
import { computed } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useTargetsStore } from '@/stores/targets'
import { useConfirmStore } from '@/stores/confirm'
import { useControlStore } from '@/stores/control'
import { useTasksStore } from '@/stores/tasks'
import { useDog2Store } from '@/stores/dogv2'
import { ACTION_LABELS, LASER_LABELS, STATE_LABELS, type TargetAction, type TargetView } from '@/api/targets'
import { coord, num } from '@/utils/format'
import { t } from '@/i18n'

const props = defineProps<{ target: TargetView }>()
const targets = useTargetsStore()
const confirm = useConfirmStore()
const control = useControlStore()
const tasks = useTasksStore()

const tg = computed(() => props.target)
const cfg = computed(() => targets.config)
const decision = computed(() => targets.decisions[tg.value.id] ?? null)
const ai = computed(() => tg.value.source.startsWith('AI:'))
const sourceLabel = computed(() => (ai.value ? `AI · ${tg.value.source.slice(3)}` : t('操作员')))
const inputLabel = computed(() => ({ TAP: t('视频点选'), CIRCLE: t('视频框选'), AI_BOX: t('AI 画框'), MAP: t('地图选点'), MODEL_3D: t('三维模型'), AI_GEO: t('AI 坐标') })[tg.value.input])
const stateClass = computed(() => {
  const s = tg.value.state
  if (s === 'FAILED' || s === 'ABORTED') return 'danger'
  if (s === 'ACTIVE' || s === 'MEASURING' || s === 'CONFIRMED') return 'busy'
  if (s === 'PROPOSED') return 'warn'
  return 'ok'
})
const hasPosition = computed(() => tg.value.lat != null && tg.value.lon != null)
const usable = computed(() => hasPosition.value && !['MEASURING', 'ACTIVE', 'CANCELLED', 'EXPIRED', 'PROPOSED'].includes(tg.value.state))

/** Why movement buttons are locked, in plain words (the backend checks the same and more). */
const moveLock = computed<string | null>(() => {
  if (!usable.value) return null
  if (tg.value.ellipsoidHeight == null) {
    return tg.value.method === 'LASER' ? t('设置页的激光高度参考系是“未确认”，只能看向和标记') : t('目标高度无法换算，只能看向和标记')
  }
  if (tg.value.method === 'LASER' && !cfg.value?.laserFlyToEnabled) return t('“飞往激光目标”未开启（设置 → 目标选择）')
  if (!control.granted) return t('需要先获取云端控制权')
  return null
})

const heightText = computed(() => {
  if (tg.value.relativeHeight != null) return t('{h} m（相对起飞点）', { h: num(tg.value.relativeHeight, 1) })
  if (tg.value.rawAltitude != null) return t('激光原始 {h} m（参考系未确认）', { h: num(tg.value.rawAltitude, 1) })
  return '—'
})

type MoveAction = 'APPROACH' | 'ABOVE' | 'ORBIT' | 'CLIMB' | 'BACK'
/** Confirmation title and the "stop the other task first" button, one whole phrase per action. */
const MOVE_TITLE: Record<MoveAction, string> = {
  APPROACH: t('接近目标'), ABOVE: t('飞到上方目标'), ORBIT: t('环绕目标'), CLIMB: t('原地爬升目标'), BACK: t('返回原位置目标'),
}
const STOP_AND: Record<MoveAction, string> = {
  APPROACH: t('停止并接近'), ABOVE: t('停止并飞到上方'), ORBIT: t('停止并环绕'), CLIMB: t('停止并原地爬升'), BACK: t('停止并返回原位置'),
}

async function act(a: TargetAction): Promise<void> {
  if (a === 'APPROACH' || a === 'ABOVE' || a === 'ORBIT' || a === 'CLIMB' || a === 'BACK') {
    const c = cfg.value
    const details = [
      t('目标距离 {d} m，估计误差 ±{acc} m', { d: num(tg.value.distance, 0), acc: num(tg.value.accuracyM, 1) }),
      a === 'APPROACH' ? t('停在距目标约 {stop} m 处，高度不低于目标 + {clr} m', { stop: c?.stopDistanceM ?? 30, clr: c?.clearanceM ?? 10 }) : '',
      a === 'ABOVE' ? t('飞到目标上方 {h} m', { h: c?.aboveHeightM ?? 30 }) : '',
      a === 'ORBIT' ? t('以当前水平距离为半径环绕；中心高度不低于平台最低高度') : '',
      a === 'CLIMB' ? t('只垂直爬升，不水平移动') : '',
      a === 'BACK' ? t('飞回接近之前的位置') : '',
      t('小于 {min} m（或 3 倍误差）时不移动；每段都经过平台安全层', { min: c?.minDistanceM ?? 10 }),
      t('到达后悬停，相机自动看向目标；遥控器随时可夺回控制'),
    ].filter(Boolean)
    // one moving task at a time (ui-design.md §4.7): another one is stopped first, in the same confirmation
    const pre = tasks.conflictFor('tgt')
    if (pre) details.unshift(tasks.switchDetails(pre))
    if (!(await confirm.ask({ title: MOVE_TITLE[a], message: t('飞机将移动，确认执行？'), confirmText: pre ? STOP_AND[a] : ACTION_LABELS[a], details, ...(pre ? { danger: true } : {}) }))) return
    if (pre && !(await tasks.stopAndWait(pre))) return
  }
  await targets.act(tg.value.id, a)
}

/**
 * "让狗过去" (R-34, docs/dog/ui-design.md 19.8): only while this page controls a dog that can navigate; opens the
 * dog's start dialog with this one point (the dialog checks it and asks for "狗已站好").
 */
const dog2 = useDog2Store()
const navDog = computed(() => dog2.dogs.find((d) => !!d.navCapability && d.online && dog2.hold.dog === d.id && !!dog2.hold.session) ?? null)
function sendDog(): void {
  const d = navDog.value
  if (!d || tg.value.lat == null || tg.value.lon == null) return
  const name = tg.value.label ?? t('目标')
  void dog2.askStart(d.id, [{ lat: tg.value.lat, lon: tg.value.lon, name }], { source: name })
}

const remainingS = computed(() => (tg.value.expiresAt ? Math.max(0, Math.round((tg.value.expiresAt - Date.now()) / 1000)) : null))
</script>

<template>
  <div class="card" data-test="target-card">
    <div class="head">
      <span class="chip" :class="ai ? 'warn' : ''">{{ sourceLabel }}</span>
      <span class="dim">{{ inputLabel }}</span>
      <span class="state" :class="stateClass" data-test="target-state">
        <AppIcon v-if="stateClass === 'busy'" name="spinner" :size="13" />{{ STATE_LABELS[tg.state] }}
      </span>
    </div>

    <div v-if="tg.label || tg.confidence != null" class="label">
      <b>{{ tg.label ?? t('未命名') }}</b><span v-if="tg.confidence != null" class="dim">{{ t('置信度 {c}', { c: num(tg.confidence, 2) }) }}</span>
      <span v-if="tg.suggestedAction" class="dim">{{ t('建议：{action}', { action: ACTION_LABELS[tg.suggestedAction] }) }}</span>
    </div>

    <template v-if="tg.state === 'PROPOSED'">
      <p class="note">{{ t('AI 只能建议目标；采纳后才会转动云台测距。') }}<span v-if="remainingS != null">{{ t('{n} 秒后过期。', { n: remainingS }) }}</span></p>
      <div class="row">
        <button class="btn btn-primary btn-sm" :disabled="targets.busy" data-test="target-accept" @click="targets.accept(tg.id)"><AppIcon name="check" :size="14" />{{ t('采纳并测距') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy" @click="targets.cancel(tg.id)"><AppIcon name="x" :size="14" />{{ t('拒绝') }}</button>
      </div>
    </template>

    <p v-else-if="tg.state === 'MEASURING'" class="note"><AppIcon name="spinner" :size="13" />{{ t('正在转动云台并读取激光测距…') }}</p>

    <dl v-if="hasPosition" class="grid num">
      <dt>{{ t('距离') }}</dt><dd data-test="target-distance">{{ num(tg.distance, 0) }} m <span v-if="tg.accuracyM != null" class="dim">±{{ num(tg.accuracyM, 1) }}</span></dd>
      <dt>{{ t('高度') }}</dt><dd>{{ heightText }}</dd>
      <dt>{{ t('坐标') }}</dt><dd>{{ coord(tg.lat) }}, {{ coord(tg.lon) }}</dd>
      <dt>{{ t('方式') }}</dt><dd>{{ tg.method === 'LASER' ? t('激光 · {state}', { state: LASER_LABELS[tg.laserState ?? ''] ?? tg.laserState }) : tg.method === 'MAP' ? t('地图选点') : tg.method === 'MODEL_3D' ? t('三维模型') : t('AI 给定坐标') }}</dd>
    </dl>

    <ul v-if="tg.warnings.length" class="warnings">
      <li v-for="w in tg.warnings" :key="w"><AppIcon name="alert" :size="13" />{{ w }}</li>
    </ul>
    <p v-if="tg.message" class="msg" :class="{ bad: tg.state === 'FAILED' || tg.state === 'ABORTED' }" data-test="target-message">{{ tg.message }}</p>
    <p v-if="tg.check" class="msg" :class="{ bad: tg.check.inView === false }">
      {{ t('复测：预期 {expected} m · 实测 {measured}', { expected: num(tg.check.expectedDistance, 0), measured: tg.check.measuredDistance == null ? '—' : `${num(tg.check.measuredDistance, 0)} m` }) }}
      {{ tg.check.inView == null ? '' : tg.check.inView ? t('· 相符') : t('· 不符，请检查画面') }}
    </p>

    <template v-if="tg.state === 'ACTIVE'">
      <button class="btn btn-danger stop" data-test="target-stop" @click="targets.stop()"><AppIcon name="stop" />{{ t('停止（悬停）') }}</button>
    </template>
    <template v-else-if="usable">
      <div class="actions">
        <button class="btn btn-sm" :disabled="targets.busy || !!tasks.lookBlockedReason" :title="tasks.lookBlockedReason ?? t('相机看向目标（机身随云台转动）')" data-test="target-look" @click="act('LOOK')"><AppIcon name="eye" :size="14" />{{ t('看向') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy || !!moveLock" data-test="target-approach" @click="act('APPROACH')"><AppIcon name="target" :size="14" />{{ t('接近') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy || !!moveLock" @click="act('ABOVE')"><AppIcon name="down" :size="14" />{{ t('飞到上方') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy || !!moveLock" @click="act('ORBIT')"><AppIcon name="orbit" :size="14" />{{ t('环绕') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy" :title="t('保留为地图点，不发送指令')" @click="act('MARK')"><AppIcon name="plus" :size="14" />{{ t('标记') }}</button>
        <button v-if="navDog" class="btn btn-sm" :title="t('{name} 走到这个目标（先确认）', { name: navDog.label })" data-test="target-send-dog" @click="sendDog"><AppIcon name="route" :size="14" />{{ t('让狗过去') }}</button>
      </div>
      <p v-if="moveLock" class="lock"><AppIcon name="lock" :size="13" />{{ moveLock }}</p>
      <p v-if="tasks.lookBlockedReason" class="lock" data-test="look-blocked"><AppIcon name="lock" :size="13" />{{ t('看向 / 复测：{reason}', { reason: tasks.lookBlockedReason }) }}</p>
      <div v-if="decision?.decision === 'CLIMB_ONLY' && !moveLock" class="row">
        <button class="btn btn-sm btn-primary" :disabled="targets.busy" data-test="target-climb" @click="act('CLIMB')"><AppIcon name="up" :size="14" />{{ t('原地爬升到安全高度') }}</button>
      </div>
      <div class="row foot">
        <button v-if="tg.backPoint && !moveLock" class="btn btn-sm" :disabled="targets.busy" @click="act('BACK')"><AppIcon name="left" :size="14" />{{ t('返回原位置') }}</button>
        <button class="btn btn-sm" :disabled="targets.busy || !!tasks.lookBlockedReason" :title="t('相机重新看向目标并复测')" @click="targets.remeasure(tg.id)"><AppIcon name="sync" :size="14" />{{ t('复测') }}</button>
        <button class="btn btn-sm btn-ghost" :disabled="targets.busy" @click="targets.cancel(tg.id)"><AppIcon name="trash" :size="14" />{{ t('取消目标') }}</button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: var(--sp-2);
  padding: var(--sp-3);
  border: 1px solid var(--border);
  border-radius: var(--r-ctl);
  background: var(--panel-2, rgba(255, 255, 255, 0.02));
}
.head {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  font-size: var(--fs-sm);
}
.state {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 600;
}
.state.ok { color: var(--ok); }
.state.busy { color: var(--accent); }
.state.warn { color: var(--warn); }
.state.danger { color: var(--danger); }
.label {
  display: flex;
  gap: var(--sp-2);
  align-items: baseline;
  flex-wrap: wrap;
}
.grid {
  display: grid;
  grid-template-columns: 44px 1fr;
  gap: 2px var(--sp-2);
  margin: 0;
  font-size: var(--fs-sm);
}
.grid dt {
  color: var(--text-dim);
}
.grid dd {
  margin: 0;
}
.note, .msg, .lock {
  margin: 0;
  font-size: var(--fs-xs);
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}
.msg.bad { color: var(--danger); }
.lock { color: var(--warn); }
.warnings {
  margin: 0;
  padding: 0;
  list-style: none;
  font-size: var(--fs-xs);
  color: var(--warn);
}
.warnings li {
  display: flex;
  gap: 4px;
  align-items: center;
}
.actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}
.row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.foot {
  border-top: 1px solid var(--border);
  padding-top: var(--sp-2);
}
.stop {
  width: 100%;
  justify-content: center;
}
</style>
