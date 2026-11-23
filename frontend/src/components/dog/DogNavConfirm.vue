<script setup lang="ts">
/**
 * Confirmation dialogs of the outdoor navigation (docs/dog/ui-design.md 19.3, 19.4): starting a task (points, length,
 * allowed area, avoidance, speed level, arrival radius, the required "狗已站好") and turning avoidance off. Opened
 * from the store (Lite3 card, target card "让狗过去", /dog2), bound to one dog when it opens. The start is sent only
 * when this page holds control, the box is ticked and the platform's check passed; the dog's answer is shown here.
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useDog2Store } from '@/stores/dogv2'
import { NAV_SETTINGS_DEFAULT, replyText, type Dog2NavCheck, type Dog2NavProblem, type Dog2NavStart } from '@/api/dogv2'
import { dualHeading, headingWait, metresText, readyLines, speedLabel, speedLevels } from './dogNav'
import { t, tc } from '@/i18n'

const v2 = useDog2Store()
const req = computed(() => v2.navDialog)
const start = computed(() => (req.value?.kind === 'start' ? req.value : null))
const dog = computed(() => (req.value ? v2.byId[req.value.dog] ?? null : null))
const cap = computed(() => dog.value?.navCapability ?? null)
const settings = computed(() => (req.value ? v2.navSettingsOf(req.value.dog) : null) ?? NAV_SETTINGS_DEFAULT)
const levels = computed(() => speedLevels(cap.value))
const range = computed<[number, number]>(() => {
  const r = cap.value?.arrive_radius_m
  return Array.isArray(r) && r.length === 2 ? [r[0], r[1]] : [0.5, 50]
})

const avoidance = ref(true)
const speed = ref<string | null>(null)
/** A typed-in speed, offered when the dog reports its limit; chosen with speed = 'custom'. */
const speedMax = computed(() => (typeof cap.value?.speed_max_mps === 'number' && cap.value.speed_max_mps > 0 ? cap.value.speed_max_mps : null))
const customMps = ref<number | null>(null)
const customOk = computed(() => speed.value !== 'custom' || (speedMax.value != null && customMps.value != null
  && Number.isFinite(customMps.value) && customMps.value >= 0.05 && customMps.value <= speedMax.value))
const radius = ref<number>(3)
const standing = ref(false)
const check = ref<Dog2NavCheck | null>(null)
const checkError = ref<string | null>(null)
const checking = ref(false)
const sending = ref(false)
const answer = ref<{ cls: 'bad' | 'warn'; text: string; problems: Dog2NavProblem[] } | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)

const mine = computed(() => !!req.value && v2.hold.dog === req.value.dog && !!v2.hold.session)
/** The same lines as the navigation group's readiness (ui-design.md 20.5). */
const ready = computed(() => readyLines(dog.value?.nav?.ready, dualHeading(dog.value)))

/** A fresh dialog: options from the card's choice for the next start, else the dog's settings; then the check. */
watch(start, async (s) => {
  answer.value = null
  standing.value = false
  check.value = null
  checkError.value = null
  if (!s) return
  if (!v2.navSettingsOf(s.dog)) await v2.navLoad(s.dog)
  if (v2.navDialog !== s) return
  const next = v2.navNext[s.dog]
  avoidance.value = cap.value?.avoidance !== false && (next?.avoidance ?? settings.value.avoidanceDefault)
  const lv = next?.speedLevel ?? settings.value.speedLevel ?? cap.value?.default_speed ?? null
  speed.value = levels.value.some((l) => l.id === lv) ? lv : (levels.value[0]?.id ?? null)
  customMps.value = next?.speedMps ?? null
  if (customMps.value != null && speedMax.value != null) speed.value = 'custom'
  radius.value = Math.min(range.value[1], Math.max(range.value[0], settings.value.arriveRadiusM))
  checking.value = true
  const r = await v2.navCheck(s.dog, s.points)
  if (v2.navDialog !== s) return
  checking.value = false
  if ('error' in r) checkError.value = r.error
  else check.value = r
}, { immediate: true })

watch(req, async (r) => {
  if (!r) return
  await nextTick()
  cancelBtn.value?.focus()
})

const radiusOk = computed(() => Number.isFinite(radius.value) && radius.value >= range.value[0] && radius.value <= range.value[1])
const why = computed(() => {
  if (!dog.value?.online) return t('狗不在线')
  if (!mine.value) return t('先「取得控制」')
  if (checking.value) return t('正在检查…')
  if (checkError.value) return t('检查没做成：{why}', { why: checkError.value })
  if (check.value && !check.value.ok) return check.value.problems[0]?.text ?? t('检查没通过')
  if (!radiusOk.value) return t('到达半径要在 {a}–{b} m 之间', { a: range.value[0], b: range.value[1] })
  if (!customOk.value) return t('速度要在 0.05 ~ {max} m/s 之间', { max: speedMax.value ?? 0 })
  const wait = headingWait(dog.value)
  if (wait) return wait
  if (!standing.value) return t('先勾「狗已站好」')
  if (sending.value) return t('正在发送…')
  return null
})

const pointsLine = computed(() => {
  const s = start.value
  if (!s) return ''
  const n = s.points.length
  const total = metresText(check.value?.totalM)
  const first = metresText(check.value?.firstM)
  if (n === 1) {
    const name = s.points[0]?.name ?? s.source
    return name ? t('1 个点（{name}）· 离狗 {d}', { name, d: first }) : t('1 个点 · 离狗 {d}', { d: first })
  }
  return t('{n} 个点 · 总长 {total} · 第一个点离狗 {d}', { n, total, d: first })
})
const areaLine = computed(() => {
  const src = check.value?.areaSource
  if (src === 'dog') return t('这只狗的允许区域')
  if (src === 'aircraft') return t('飞机安全区')
  if (src === 'none') return t('没设：只限第一个点离狗不超过 {n} m', { n: settings.value.maxFirstM })
  return '—'
})

async function send(): Promise<void> {
  const s = start.value
  if (!s || why.value) return
  sending.value = true
  answer.value = null
  const body: Dog2NavStart = { points: s.points, avoidance: avoidance.value, arriveRadiusM: radius.value, standingConfirmed: true }
  if (speed.value === 'custom' && customMps.value != null) body.speedMps = Math.round(customMps.value * 100) / 100
  else if (levels.value.length && speed.value) body.speedLevel = speed.value
  if (s.dryRun) body.dryRun = true
  if (s.routeId != null) body.routeId = s.routeId
  const r = await v2.navStart(s.dog, body)
  sending.value = false
  if (v2.navDialog !== s) return
  if (r?.result === 'done') {
    v2.dialogDone(true)
    return
  }
  answer.value = r
    ? { cls: r.result === 'no_reply' ? 'warn' : 'bad', text: replyText(r), problems: r.problems ?? [] }
    : { cls: 'bad', text: t('没发出去'), problems: [] }
}

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    v2.dialogDone(false)
  }
}
</script>

<template>
  <div v-if="req" class="backdrop" data-test="dog-nav-dialog" @keydown="onKey">
    <div v-if="req.kind === 'avoidanceOff'" class="dialog panel" role="alertdialog" aria-modal="true" :aria-label="t('关掉自动避障')">
      <div class="panel-head">{{ t('关掉自动避障 · {name}', { name: dog?.label ?? req.dog }) }}</div>
      <div class="panel-body"><p class="msg">{{ t('关掉以后，狗不绕障碍，也不会因为障碍停下。') }}</p></div>
      <div class="actions">
        <button ref="cancelBtn" class="btn" data-test="nav-dlg-cancel" @click="v2.dialogDone(false)">{{ t('取消') }}</button>
        <button class="btn btn-warn" data-test="nav-dlg-avoid-off" @click="v2.dialogDone(true)">{{ t('关掉避障') }}</button>
      </div>
    </div>

    <div v-else-if="start" class="dialog panel" role="alertdialog" aria-modal="true" :aria-label="t('开始导航')">
      <div class="panel-head">{{ t('开始导航 · {name}', { name: dog?.label ?? start.dog }) }}</div>
      <div class="panel-body">
        <dl class="rows">
          <dt>{{ t('点') }}</dt><dd data-test="nav-dlg-points">{{ pointsLine }}<span v-if="start.routeName" class="dim"> · {{ start.routeName }}</span></dd>
          <dt>{{ t('允许区域') }}</dt><dd>{{ areaLine }}</dd>
          <dt>{{ tc('setting', '自动避障') }}</dt>
          <dd>
            <label class="chk"><input v-model="avoidance" type="checkbox" :disabled="cap?.avoidance === false" data-test="nav-dlg-avoid" />{{ avoidance ? t('开') : t('关') }}</label>
            <span v-if="!avoidance" class="warnc block" data-test="nav-dlg-avoid-fact">{{ t('关掉以后，狗不绕障碍，也不会因为障碍停下。') }}</span>
          </dd>
          <template v-if="levels.length || speedMax != null">
            <dt>{{ t('速度档位') }}</dt>
            <dd class="seg" data-test="nav-dlg-speed">
              <label v-for="l in levels" :key="l.id" class="chk"><input v-model="speed" type="radio" name="nav-speed" :value="l.id" />{{ speedLabel(l) }}</label>
              <label v-if="speedMax != null" class="chk" data-test="nav-dlg-custom">
                <input v-model="speed" type="radio" name="nav-speed" value="custom" />{{ t('自定') }}
                <input v-model.number="customMps" class="input num rad" type="number" step="0.05" min="0.05" :max="speedMax"
                       data-test="nav-dlg-custom-mps" @focus="speed = 'custom'" /> m/s
              </label>
            </dd>
          </template>
          <dt>{{ t('到达半径') }}</dt>
          <dd><input v-model.number="radius" class="input num rad" type="number" :min="range[0]" :max="range[1]" step="0.5" data-test="nav-dlg-radius" /> m</dd>
          <template v-if="start.dryRun">
            <dt>{{ t('只算不走') }}</dt><dd>{{ t('狗照常规划，不动') }}</dd>
          </template>
        </dl>
        <ul v-if="ready.length" class="warn-list" data-test="nav-dlg-ready">
          <li v-for="(line, i) in ready" :key="i">{{ line }}</li>
        </ul>
        <p v-if="checking" class="dim">{{ t('正在检查…') }}</p>
        <ul v-else-if="check && !check.ok" class="bad-list" data-test="nav-dlg-problems">
          <li v-for="(p, i) in check.problems" :key="i">{{ p.index != null ? t('第 {n} 个点：{text}', { n: p.index + 1, text: p.text }) : p.text }}</li>
        </ul>
        <p v-else-if="checkError" class="badc">{{ t('检查没做成：{why}', { why: checkError }) }}</p>
        <label class="chk stand"><input v-model="standing" type="checkbox" data-test="nav-dlg-standing" /><b>{{ t('狗已站好（看画面或现场确认）') }}</b></label>
        <div v-if="answer" class="answer" :class="answer.cls" data-test="nav-dlg-answer">
          <span>{{ answer.text }}</span>
          <ul v-if="answer.problems.length"><li v-for="(p, i) in answer.problems" :key="i">{{ p.index != null ? t('第 {n} 个点：{text}', { n: p.index + 1, text: p.text }) : p.text }}</li></ul>
        </div>
      </div>
      <div class="actions">
        <span v-if="why" class="dim small" data-test="nav-dlg-why">{{ why }}</span>
        <button ref="cancelBtn" class="btn" data-test="nav-dlg-cancel" @click="v2.dialogDone(false)">{{ answer ? tc('verb', '关闭') : t('取消') }}</button>
        <button class="btn btn-primary" :disabled="!!why" :title="why ?? ''" data-test="nav-dlg-start" @click="send">{{ t('开始导航') }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.backdrop { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.55); z-index: 2400; display: flex; align-items: center; justify-content: center; }
.dialog { width: 480px; max-width: calc(100vw - 32px); max-height: calc(100vh - 32px); overflow: auto; box-shadow: var(--shadow); }
.msg { margin: 0; }
.rows { display: grid; grid-template-columns: 88px 1fr; gap: 6px 12px; margin: 0; font-size: var(--fs-sm); align-items: baseline; }
.rows dt { color: var(--text-dim); }
.rows dd { margin: 0; }
.seg { display: flex; gap: 10px; flex-wrap: wrap; }
.chk { display: inline-flex; align-items: center; gap: 6px; cursor: pointer; }
.stand { margin-top: 12px; padding: 8px; border: 1px solid var(--warn); border-radius: var(--r-ctl); width: 100%; box-sizing: border-box; }
.rad { width: 80px; }
.block { display: block; margin-top: 4px; font-size: var(--fs-xs); }
.warnc { color: var(--warn); }
.badc { color: var(--danger); }
.dim { color: var(--text-dim); }
.small { font-size: var(--fs-xs); margin-right: auto; }
.warn-list, .bad-list { margin: 10px 0 0; padding-left: 18px; font-size: var(--fs-sm); }
.warn-list { color: var(--warn); }
.bad-list { color: var(--danger); }
.answer { margin-top: 10px; font-size: var(--fs-sm); }
.answer.bad { color: var(--danger); }
.answer.warn { color: var(--warn); }
.answer ul { margin: 4px 0 0; padding-left: 18px; }
.actions { display: flex; justify-content: flex-end; align-items: center; gap: var(--sp-2); padding: 0 var(--sp-4) var(--sp-4); }
</style>
