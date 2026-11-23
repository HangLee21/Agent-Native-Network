<script setup lang="ts">
/**
 * Lite3 outdoor navigation group (docs/dog/ui-design.md 19.2, 20): readiness, the goal or route being picked, the
 * platform's check, the running task (point i/n, distances, ETA), pause reasons and what to do about them, avoidance
 * and speed level, and the dog route library. Shown only for a dog that reports a navigation capability (Lite3Body
 * checks); the group's title is Lite3Body's. While a task is on, its buttons are the first row under the state, so
 * pausing (which adds the reason box) does not move "resume" away from where "pause" was (ui-design.md 20.6).
 * The task state comes from the 700 ms poll; every action's answer is the dog's.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useDogStore } from '@/stores/dog'
import { useDog2Store } from '@/stores/dogv2'
import { useControlStore } from '@/stores/control'
import { useConfirmStore } from '@/stores/confirm'
import { NAV_SETTINGS_DEFAULT, type Dog2Route } from '@/api/dogv2'
import { routesApi, type RouteSummary } from '@/api/routes'
import { pathLength, distance } from '@/utils/geo'
import {
  AVOIDANCE_REASONS, dualHeading, headingWait, etaText, metresText, navAdvice, navPoints, navReason, navReasonDetail, navStateText, navTaskOn, progressText,
  readyItems, readyLines, speedLabel, speedLevels,
} from './dogNav'
import { t, tc } from '@/i18n'

const store = useDogStore()
const v2 = useDog2Store()
const control = useControlStore()
const confirm = useConfirmStore()

const d = computed(() => store.l3NavDog!)
const id = computed(() => d.value.id)
const cap = computed(() => d.value.navCapability!)
const nav = computed(() => d.value.nav ?? null)
const online = computed(() => store.online('lite3'))
const mine = computed(() => !!store.l3.session)
const taskOn = computed(() => navTaskOn(nav.value))
const busy = computed(() => v2.busy[id.value] ?? null)
const settings = computed(() => v2.navSettingsOf(id.value) ?? NAV_SETTINGS_DEFAULT)
const levels = computed(() => speedLevels(cap.value))
const canAvoid = computed(() => cap.value.avoidance !== false)

const next = computed(() => v2.navNext[id.value] ?? null)
const avoidanceNext = computed(() => canAvoid.value && (next.value?.avoidance ?? settings.value.avoidanceDefault))
const customNext = computed(() => next.value?.speedMps ?? null)
const speedNext = computed(() => (customNext.value != null ? 'custom' : next.value?.speedLevel ?? settings.value.speedLevel ?? cap.value.default_speed ?? null))
/** A typed-in speed is offered when the dog reports its limit (2026-11-11, user: the levels are too slow). */
const speedMax = computed(() => (typeof cap.value.speed_max_mps === 'number' && cap.value.speed_max_mps > 0 ? cap.value.speed_max_mps : null))
/** What is in force: the dog's word while a task is on, the choice for the next start otherwise. */
const avoidance = computed(() => (taskOn.value ? (nav.value?.avoidance ?? avoidanceNext.value) : avoidanceNext.value))
const speed = computed(() => (taskOn.value ? (nav.value?.speed_level ?? speedNext.value) : speedNext.value))
const customOn = computed(() => speed.value === 'custom')
/** What the box shows: the typed-in speed in force (the dog's word while walking), else the last one typed. */
const customShown = computed(() => (taskOn.value && customOn.value ? nav.value?.speed_target_mps ?? null : customNext.value))
const customDraft = ref<string | number>('')   // a number input: Vue hands back a number once typed
const customBad = ref(false)
watch(customShown, (v) => { customDraft.value = v == null ? '' : String(v) }, { immediate: true })
function commitCustom(): void {
  const raw = String(customDraft.value ?? '').trim()
  if (!raw || speedMax.value == null) return
  const v = Number(raw)
  customBad.value = !Number.isFinite(v) || v < 0.05 || v > speedMax.value
  if (customBad.value) return
  const mps = Math.round(v * 100) / 100
  if (customOn.value && customShown.value === mps) return
  void store.l3NavSpeedMps(mps, taskOn.value)
}

const draft = computed(() => (v2.navDraft?.dog === id.value ? v2.navDraft : null))
const picking = computed(() => control.pickingTarget === 'dogGoal' || control.pickingTarget === 'dogRoute')
const taskPoints = computed(() => navPoints(nav.value))
const ready = computed(() => readyItems(nav.value?.ready, dualHeading(d.value)))
/** One line per problem; the board's own text only when it adds something (ui-design.md 20.5). */
const readyWhy = computed(() => readyLines(nav.value?.ready, dualHeading(d.value)))

/** Why the dog cannot be told anything now (pause, resume, end, options, start). */
const ctlWhy = computed(() => {
  if (!online.value) return t('Lite3 离线')
  if (!mine.value) return t('先「取得控制」')
  if (store.l3Moving) return t('先松开方向键')
  if (busy.value) return t('等上一条指令的回复')
  return null
})

const draftPts = computed(() => draft.value?.points ?? [])
const firstProblem = computed(() => draft.value?.check?.problems?.[0] ?? null)
const startWhy = computed(() => {
  if (taskOn.value) return t('已经有一个导航任务')
  if (ctlWhy.value) return ctlWhy.value
  if (!draftPts.value.length) return t('先在地图上点目标或画路线')
  if (draft.value?.checking || (!draft.value?.check && !draft.value?.checkError)) return t('正在检查…')
  if (draft.value?.checkError) return draft.value.checkError
  if (draft.value?.check && !draft.value.check.ok) return firstProblem.value?.text ?? t('检查没通过')
  return headingWait(d.value)
})

/** "1 个点 · 离狗 42 m" or "3 个点 · 总长 186 m · 第一个点离狗 42 m" (the check's numbers, else a local estimate). */
const draftSummary = computed(() => {
  const pts = draftPts.value
  if (!pts.length) return ''
  const c = draft.value?.check
  const pos = d.value.position
  const first = c?.firstM ?? (pos?.lat != null && pos.lon != null ? distance({ lat: pos.lat, lon: pos.lon }, pts[0]!) : null)
  if (pts.length === 1) return t('1 个点 · 离狗 {d}', { d: metresText(first) })
  const total = c?.totalM ?? pathLength(pts)
  return t('{n} 个点 · 总长 {total} · 第一个点离狗 {d}', { n: pts.length, total: metresText(total), d: metresText(first) })
})

const stateText = computed(() => navStateText(nav.value))
const stateCls = computed(() => {
  const s = nav.value?.state
  return s === 'running' || s === 'starting' ? 'run' : s === 'paused' ? 'warn' : s === 'arrived' ? 'ok' : ''
})
/** The last task's outcome while idle: arrived, or ended and why. */
const lastResult = computed(() => {
  const n = nav.value
  if (!n || taskOn.value) return null
  if (n.state === 'arrived') return { cls: 'okc', text: t('到了 · 共 {n} 个点', { n: n.count ?? taskPoints.value.length }) }
  if (n.state === 'ended') return { cls: n.reason === 'cancelled' || n.reason === 'arrived' ? 'dim' : 'warnc', text: t('结束：{reason}', { reason: navReason(n) || '—' }) }
  return null
})

const progress = computed(() => (nav.value && taskOn.value ? progressText(nav.value, taskPoints.value) : ''))
const pausedReason = computed(() => (nav.value?.state === 'paused' ? navReason(nav.value) : ''))
const pausedDetail = computed(() => (nav.value?.state === 'paused' ? navReasonDetail(nav.value) : null))
const pausedAdvice = computed(() => (nav.value?.state === 'paused' ? (nav.value.reason === 'heading_unknown' && dualHeading(d.value) ? t('朝向恢复后点「继续」') : navAdvice(nav.value.reason)) : null))
const offerAvoidOff = computed(() => nav.value?.state === 'paused' && avoidance.value && AVOIDANCE_REASONS.has(nav.value.reason ?? ''))

// -- picking on the map
function pickGoal(): void {
  control.pickingTarget = control.pickingTarget === 'dogGoal' ? null : 'dogGoal'
}
function pickRoute(): void {
  if (!draft.value) v2.draftOpen(id.value, [])
  control.pickingTarget = 'dogRoute'
}
function clearDraft(): void {
  if (picking.value) control.pickingTarget = null
  v2.draftClear()
}

async function openStart(): Promise<void> {
  if (startWhy.value || !draft.value) return
  if (picking.value) control.pickingTarget = null
  const ok = await store.l3NavAskStart(draft.value.points, { routeId: draft.value.routeId, routeName: draft.value.routeName })
  if (ok) v2.draftClear()
}

// -- the route library
const lib = ref<'' | 'list' | 'save' | 'import'>('')
const saveName = ref('')
const libMsg = ref<string | null>(null)
const aircraft = ref<RouteSummary[]>([])

function toggleLib(): void {
  lib.value = lib.value === 'list' ? '' : 'list'
  libMsg.value = null
  if (lib.value === 'list') void v2.routesLoad()
}
async function openRoute(r: Dog2Route): Promise<void> {
  libMsg.value = await v2.routeOpen(id.value, r)
  if (!libMsg.value) lib.value = ''
}
async function removeRoute(r: Dog2Route): Promise<void> {
  const ok = await confirm.ask({ title: t('删除狗的路线'), message: t('删除「{name}」？', { name: r.name }), confirmText: t('删除'), danger: true, focus: 'cancel' })
  if (ok) libMsg.value = await v2.routeRemove(r.id)
}
function startSave(): void {
  lib.value = 'save'
  libMsg.value = null
  saveName.value = draft.value?.routeName ?? ''
}
async function save(): Promise<void> {
  const name = saveName.value.trim()
  if (!name || !draft.value) return
  const r = await v2.routeSave(name, draft.value.points)
  if (typeof r === 'string') libMsg.value = r
  else {
    lib.value = ''
    libMsg.value = t('已保存「{name}」', { name: r.name })
  }
}
async function startImport(): Promise<void> {
  lib.value = 'import'
  libMsg.value = null
  try {
    aircraft.value = await routesApi.list()
  } catch {
    aircraft.value = []
    libMsg.value = t('连不上后端')
  }
}
async function importRoute(r: RouteSummary): Promise<void> {
  libMsg.value = await v2.routeImport(id.value, r.id)
  if (!libMsg.value) lib.value = ''
}

// opening the area reads the dog's settings and lets the dog start its navigation parts (nav_prepare); the dog stops
// them after 10 minutes without navigation, so the warm-up is repeated every 5 minutes while the area is open
let timer: number | null = null
onMounted(() => {
  void v2.navLoad(id.value)
  if (online.value) void v2.navPrepare(id.value)
  timer = window.setInterval(() => {
    void v2.navLoad(id.value)
    if (online.value) void v2.navPrepare(id.value)
  }, 5 * 60_000)
})
onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<template>
  <div class="l3nav" data-test="lite3-nav">
    <div class="nh">
      <span class="st" :class="stateCls" data-test="nav-state">{{ stateText }}</span>
      <span v-if="!avoidance" class="badge warn" data-test="nav-avoid-off">{{ t('避障关') }}</span>
      <span v-if="nav?.dry_run" class="badge" data-test="nav-dry">{{ t('只算不走') }}</span>
    </div>

    <!-- a task is on -->
    <template v-if="taskOn && nav">
      <div class="acts">
        <button v-if="nav.state === 'paused'" class="btn btn-primary" :disabled="!!ctlWhy || !!headingWait(d)" :title="ctlWhy ?? headingWait(d) ?? ''" data-test="nav-resume" @click="store.l3NavResume()">
          <AppIcon name="play" :size="14" />{{ t('继续') }}
        </button>
        <button v-else class="btn" :disabled="!!ctlWhy" :title="ctlWhy ?? ''" data-test="nav-pause" @click="store.l3NavPause()">
          {{ t('暂停') }}
        </button>
        <button class="btn btn-danger" :disabled="!!ctlWhy" :title="ctlWhy ?? t('结束这次导航，狗原地停下')" data-test="nav-cancel" @click="store.l3NavCancel()">
          <AppIcon name="stop" :size="14" />{{ t('结束') }}
        </button>
        <button v-if="offerAvoidOff" class="btn" :disabled="!!ctlWhy" :title="ctlWhy ?? ''" data-test="nav-avoid-off-now" @click="store.l3NavAvoidance(false, true)">
          {{ t('关掉避障') }}
        </button>
      </div>
      <div v-if="nav.state === 'starting'" class="line run"><AppIcon name="spinner" :size="14" />{{ t('正在开始…') }}</div>
      <div v-if="progress" class="line" data-test="nav-progress"><b>{{ progress }}</b></div>
      <div class="line num dim">
        {{ nav.state === 'running'
          ? t('离这个点 {a} · 离终点 {b} · {eta}', { a: metresText(nav.to_point_m), b: metresText(nav.to_end_m), eta: etaText(nav.eta_s) })
          : t('离这个点 {a} · 离终点 {b}', { a: metresText(nav.to_point_m), b: metresText(nav.to_end_m) }) }}
      </div>
      <div class="line num dim">
        {{ t('速度 {v}', { v: nav.speed_mps == null ? '—' : `${nav.speed_mps.toFixed(2)} m/s` }) }}<template v-if="nav.avoidance && nav.front_m != null"> · {{ t('前方 {d}', { d: `${nav.front_m.toFixed(1)} m` }) }}</template>
      </div>
      <div v-if="nav.state === 'paused'" class="paused" data-test="nav-reason">
        <b>{{ t('暂停：{reason}', { reason: pausedReason || '—' }) }}</b>
        <span v-if="pausedDetail" class="dim">{{ pausedDetail }}</span>
        <span v-if="pausedAdvice">{{ pausedAdvice }}</span>
        <span class="dim">{{ t('按住方向键可以接管') }}</span>
      </div>
    </template>

    <!-- no task: readiness, last result, picking and the draft -->
    <template v-else>
      <div v-if="lastResult" class="line" :class="lastResult.cls" data-test="nav-last">{{ lastResult.text }}</div>
      <div v-if="!nav" class="line dim">{{ t('还没收到狗的导航状态') }}</div>
      <div v-else class="ready" data-test="nav-ready">
        <span v-for="r in ready" :key="r.key" class="ri" :class="r.ok === true ? 'ok' : r.ok === false ? 'bad' : ''" :title="r.text">
          {{ r.label }} {{ r.ok === true ? '✓' : r.ok === false ? '✕' : '–' }}
        </span>
      </div>
      <ul v-if="readyWhy.length" class="why" data-test="nav-ready-why">
        <li v-for="(line, i) in readyWhy" :key="i">{{ line }}</li>
      </ul>

      <div class="acts">
        <button class="btn" :class="{ 'btn-primary': control.pickingTarget === 'dogGoal' }" :disabled="!online" data-test="nav-pick-goal" @click="pickGoal">
          <AppIcon name="crosshair" :size="14" />{{ t('点目标') }}
        </button>
        <button class="btn" :class="{ 'btn-primary': control.pickingTarget === 'dogRoute' }" :disabled="!online" data-test="nav-pick-route" @click="pickRoute">
          <AppIcon name="route" :size="14" />{{ draftPts.length > 1 || control.pickingTarget === 'dogRoute' ? t('继续加点') : t('画路线') }}
        </button>
        <button class="btn" :aria-expanded="lib === 'list'" data-test="nav-lib" @click="toggleLib">{{ t('路线库') }}<AppIcon :name="lib === 'list' ? 'up' : 'down'" :size="12" /></button>
      </div>

      <div v-if="lib === 'list'" class="lib" data-test="nav-lib-list">
        <div v-if="v2.routesError" class="badc small">{{ v2.routesError }}</div>
        <div v-else-if="!v2.routes.length" class="dim small">{{ t('还没有存过狗的路线') }}</div>
        <div v-for="r in v2.routes" :key="r.id" class="lrow">
          <button class="lname" @click="openRoute(r)">{{ r.name }}<span class="dim">{{ t('{n} 个点', { n: r.points?.length ?? 0 }) }}</span></button>
          <button class="iconb" :title="t('删除')" @click="removeRoute(r)"><AppIcon name="trash" :size="13" /></button>
        </div>
        <button class="btn btn-sm" data-test="nav-lib-import" @click="startImport">{{ t('从飞机航线导入…') }}</button>
      </div>
      <div v-if="lib === 'import'" class="lib" data-test="nav-lib-aircraft">
        <div v-if="!aircraft.length" class="dim small">{{ t('没有飞机航线') }}</div>
        <button v-for="r in aircraft" :key="r.id" class="lname" @click="importRoute(r)">{{ r.name }}<span class="dim">{{ t('{n} 个点', { n: r.waypointCount }) }}</span></button>
        <button class="btn btn-sm btn-ghost" @click="lib = ''">{{ t('取消') }}</button>
      </div>
      <div v-if="lib === 'save'" class="lib row">
        <input v-model="saveName" class="input" :placeholder="t('路线名字')" data-test="nav-save-name" @keydown.enter="save" />
        <button class="btn btn-sm btn-primary" :disabled="!saveName.trim()" data-test="nav-save-ok" @click="save">{{ t('保存') }}</button>
        <button class="btn btn-sm btn-ghost" @click="lib = ''">{{ t('取消') }}</button>
      </div>
      <div v-if="libMsg" class="small dim" data-test="nav-lib-msg">{{ libMsg }}</div>

      <template v-if="draft">
        <div class="line" data-test="nav-draft">
          <b>{{ draftSummary || t('还没有点') }}</b>
          <span v-if="draft.routeName" class="dim"> · {{ draft.routeName }}</span>
          <AppIcon v-if="draft.checking" name="spinner" :size="13" />
        </div>
        <ul v-if="draft.check && !draft.check.ok" class="problems" data-test="nav-problems">
          <li v-for="(p, i) in draft.check.problems" :key="i">{{ p.index != null ? t('第 {n} 个点：{text}', { n: p.index + 1, text: p.text }) : p.text }}</li>
        </ul>
        <div v-else-if="draft.checkError" class="problems" data-test="nav-problems">{{ t('检查没做成：{why}', { why: draft.checkError }) }}</div>
        <div class="acts">
          <button class="btn btn-sm" :disabled="!draftPts.length" data-test="nav-save" @click="startSave">{{ t('存为路线…') }}</button>
          <button class="btn btn-sm btn-ghost" data-test="nav-clear" @click="clearDraft"><AppIcon name="trash" :size="13" />{{ t('清空') }}</button>
        </div>
      </template>
    </template>

    <!-- options: for the next start while idle, sent at once while a task is on -->
    <div class="opts">
      <label class="sw" :title="!canAvoid ? t('这只狗不支持自动避障') : taskOn ? (ctlWhy ?? '') : ''">
        <input type="checkbox" role="switch" :checked="avoidance" :disabled="!canAvoid || (taskOn && !!ctlWhy)" data-test="nav-avoid"
               @click.prevent="store.l3NavAvoidance(!avoidance, taskOn)" />
        <span class="sw-track" aria-hidden="true"><span class="sw-knob" /></span>
        <span>{{ tc('setting', '自动避障') }}</span>
      </label>
      <div v-if="levels.length" class="seg" role="radiogroup" :aria-label="t('速度档位')" data-test="nav-speed">
        <button v-for="l in levels" :key="l.id" class="segb" :class="{ on: speed === l.id }" role="radio" :aria-checked="speed === l.id"
                :disabled="taskOn && !!ctlWhy" :title="taskOn ? (ctlWhy ?? '') : ''" @click="store.l3NavSpeed(l.id, taskOn)">{{ speedLabel(l) }}</button>
      </div>
      <label v-if="speedMax != null" class="custom" :class="{ on: customOn, bad: customBad }" data-test="nav-speed-custom"
             :title="t('自己输入速度，0.05 ~ {max} m/s，回车生效', { max: speedMax })">
        <span>{{ t('自定') }}</span>
        <input v-model="customDraft" class="input num" type="number" inputmode="decimal" step="0.05" min="0.05" :max="speedMax"
               :placeholder="t('例 0.5')" :disabled="taskOn && !!ctlWhy" data-test="nav-speed-input"
               @keydown.enter.prevent="commitCustom" @change="commitCustom" @input="customBad = false" />
        <span class="dim">m/s</span>
      </label>
      <span v-if="customBad && speedMax != null" class="small warnc" data-test="nav-speed-bad">{{ t('速度要在 0.05 ~ {max} m/s 之间', { max: speedMax }) }}</span>
    </div>

    <div v-if="!taskOn" class="acts">
      <button class="btn btn-primary" :disabled="!!startWhy" :title="startWhy ?? ''" data-test="nav-start" @click="openStart">
        <AppIcon name="play" :size="14" />{{ t('开始导航…') }}
      </button>
      <span v-if="startWhy && draftPts.length" class="small dim" data-test="nav-start-why">{{ startWhy }}</span>
    </div>
  </div>
</template>

<style scoped>
.custom { display: inline-flex; align-items: center; gap: 4px; padding: 0 6px; height: 30px; border: 1px solid var(--border); border-radius: var(--r-ctl); font-size: var(--fs-xs); }
.custom.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }
.custom.bad { border-color: var(--warn); }
.custom input { width: 64px; height: 22px; padding: 0 6px; -moz-appearance: textfield; appearance: textfield; }
.custom input::-webkit-inner-spin-button, .custom input::-webkit-outer-spin-button { -webkit-appearance: none; margin: 0; }
.l3nav { display: flex; flex-direction: column; gap: 6px; }
.nh { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; min-height: 20px; }
.st { padding: 0 8px; border-radius: 999px; border: 1px solid var(--border); font-size: var(--fs-xs); line-height: 18px; }
.st.run { border-color: var(--accent); color: var(--accent); }
.st.warn { border-color: var(--warn); color: var(--warn); }
.st.ok { border-color: var(--ok); color: var(--ok); }
.badge { padding: 0 6px; border-radius: 4px; border: 1px solid var(--border); color: var(--text-dim); font-size: 11px; line-height: 16px; }
.badge.warn { border-color: var(--warn); color: var(--warn); font-weight: 600; }
.line { display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); flex-wrap: wrap; }
.line.run { color: var(--accent); }
.dim { color: var(--text-dim); }
.small { font-size: var(--fs-xs); }
.okc { color: var(--ok); }
.warnc { color: var(--warn); }
.badc { color: var(--danger); }
.num { font-variant-numeric: tabular-nums; }
.paused { display: flex; flex-direction: column; gap: 2px; padding: 6px 8px; border-radius: var(--r-ctl); border: 1px solid var(--warn); background: color-mix(in srgb, var(--warn) 10%, transparent); font-size: var(--fs-sm); }
.paused b { color: var(--warn); }
.acts { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.acts .btn { min-height: 36px; }
.ready { display: flex; gap: 10px; flex-wrap: wrap; font-size: var(--fs-xs); }
.ri.ok { color: var(--ok); }
.ri.bad { color: var(--warn); font-weight: 600; }
.why, .problems { margin: 0; padding-left: 16px; font-size: var(--fs-xs); }
.why { color: var(--warn); }
.problems { color: var(--danger); }
.lib { display: flex; flex-direction: column; gap: 4px; padding: 6px; border: 1px solid var(--border); border-radius: var(--r-ctl); background: var(--panel-2); }
.lib.row { flex-direction: row; align-items: center; }
.lib.row .input { flex: 1; min-width: 0; }
.lrow { display: flex; align-items: center; gap: 4px; }
.lname { flex: 1; display: flex; justify-content: space-between; gap: 8px; padding: 4px 6px; border: none; background: transparent; color: var(--text); font: inherit; font-size: var(--fs-sm); text-align: left; cursor: pointer; border-radius: var(--r-ctl); }
.lname:hover { background: color-mix(in srgb, var(--accent) 15%, transparent); }
.iconb { border: none; background: transparent; color: var(--text-dim); cursor: pointer; padding: 4px; }
.opts { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.sw { position: relative; display: inline-flex; align-items: center; gap: 6px; min-height: 32px; font-size: var(--fs-sm); cursor: pointer; user-select: none; }
.sw input { position: absolute; left: 0; top: 50%; width: 1px; height: 1px; margin: 0; opacity: 0; }
.sw-track { flex: none; position: relative; width: 36px; height: 20px; border-radius: 10px; border: 1px solid var(--border); background: var(--panel-3, var(--panel-2)); }
.sw-knob { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--text-dim); transition: transform 0.12s; }
.sw input:checked + .sw-track { border-color: var(--ok); background: color-mix(in srgb, var(--ok) 28%, var(--panel-2)); }
.sw input:checked + .sw-track .sw-knob { transform: translateX(16px); background: var(--ok); }
.sw input:focus-visible + .sw-track { outline: 2px solid var(--accent); outline-offset: 2px; }
.sw:has(input:disabled) { opacity: 0.45; cursor: not-allowed; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: var(--r-ctl); overflow: hidden; }
.segb { padding: 4px 8px; border: none; border-right: 1px solid var(--border); background: transparent; color: var(--text); font: inherit; font-size: var(--fs-xs); cursor: pointer; white-space: nowrap; }
.segb:last-child { border-right: none; }
.segb.on { background: var(--accent); color: var(--accent-ink); }
.segb:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
