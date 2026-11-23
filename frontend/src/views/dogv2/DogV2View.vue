<script setup lang="ts">
/**
 * The new dog system while it is being tested next to the old one (docs/dog/v2/design.md 4). Its own page, so the
 * live monitor page and the old dog card stay exactly as they are; when the old system is retired, this card moves
 * into the live monitor page.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { useDog2Store } from '@/stores/dogv2'
import { useConfirmStore } from '@/stores/confirm'
import { DOG2_AXES, MODE_TEXT, dog2Api, type Dog2, type Dog2Dir, type Dog2LogEntry } from '@/api/dogv2'
import Dog2Video from '@/components/dogv2/Dog2Video.vue'
import { depthFrontText } from '@/components/dogv2/depthFront'
import { t, tc } from '@/i18n'

const store = useDog2Store()
const confirm = useConfirmStore()
const selected = ref<string | null>(null)
const stream = ref('rgb')
const log = ref<Dog2LogEntry[]>([])
let logTimer: number | null = null

const dog = computed<Dog2 | null>(() => (selected.value ? store.byId[selected.value] ?? null : store.dogs[0] ?? null))
const isNew = computed(() => dog.value?.mode === 'new')
const switching = computed(() => !!dog.value?.mode?.startsWith('switching'))
const mine = computed(() => !!dog.value && store.hold.dog === dog.value.id && !!store.hold.session)
const busy = computed(() => (dog.value ? store.busy[dog.value.id] : null))
/** Telemetry only while the new system holds the dog and it is fresh; in the old mode the old console's state shows. */
const tel = computed(() => (dog.value?.mode === 'new' && (dog.value.telemetryAgeMs ?? Infinity) < 3000 ? dog.value.telemetry : null))
const st = computed(() => dog.value?.status ?? null)
const depthLine = computed(() => (stream.value === 'depth' ? depthFrontText(dog.value) : null))
const myNotes = computed(() => store.notes.filter((x) => x.dog === dog.value?.id).slice(0, 6))
const lying = computed(() => (isNew.value ? tel.value?.basic_state === 1 : st.value?.old_console?.robot_state === 'LIE_DOWN'))
/** Some Lite3 firmware keeps the state at IDLE ("idle / not initialised") while the dog stands and lies: then the page
 *  cannot tell, and the switch needs the operator to confirm the dog is lying (sent as confirm_lying). */
const stateUnknown = computed(() => (isNew.value ? tel.value?.basic_state === 0 : st.value?.old_console?.robot_state === 'IDLE'))
const canSwitchPosture = computed(() => lying.value || stateUnknown.value)
/** The old console connects to the motion host only once, at its start; when that failed it holds the port anyway
 *  and nobody can drive from the platform until it is restarted (audit 2026-11-09, problem 2). */
const oldStuck = computed(() => !!dog.value?.online && dog.value.mode === 'old' && st.value?.old_console?.connected === false)
/** The old console was retired (2026-11-10 decision): the board takes the dog by itself, there is nothing to switch to. */
const oldGone = computed(() => !!dog.value?.online && st.value?.old_console?.reachable === false)
const modeText = computed(() => {
  const d = dog.value
  if (!d?.online) return t('新系统离线')
  if (oldStuck.value) return t('老系统没连上运动主机')
  return d.mode ? MODE_TEXT[d.mode] : '—'
})
/** Stand / lie is a toggle: after "no reply" it may still arrive late, so it stays grey until the state changes or 15 s pass. */
const standHold = ref<{ until: number; state: number | null } | null>(null)
const standWhy = computed(() => {
  const h = standHold.value
  if (!h) return null
  if (Date.now() > h.until || (tel.value && tel.value.basic_state !== h.state)) return null
  return t('上一次起立/趴下没收到回复，等狗的状态变了或 15 秒后再按')
})

const why = computed(() => {
  const d = dog.value
  if (!d) return t('没有狗')
  if (!d.online) return t('狗不在线')
  if (!d.enabled) return t('这只狗还没启用')
  return null
})
const motionWhy = computed(() => why.value ?? (isNew.value ? (mine.value ? null : t('先取得控制')) : t('板卡现在是老系统在控')))

function fmt(n: number | null | undefined, digits = 1): string {
  return n === null || n === undefined || Number.isNaN(n) ? '—' : n.toFixed(digits)
}

async function switchTo(to: 'new' | 'old'): Promise<void> {
  const d = dog.value
  if (!d) return
  const unsure = !lying.value && stateUnknown.value
  const ok = await confirm.ask(to === 'new'
    ? { title: t('切到新系统'), message: t('切换前请确认：'), details: [unsure ? t('狗是趴着的（狗报的状态是 IDLE，看不出趴没趴：请你亲眼确认）') : t('狗是趴着的'), t('平台老 Lite3 卡片和狗方网页都没人占着控制权'), t('现场拿实体遥控的人知道要切了'), t('切过去以后，狗方网页只能看图、不能控狗')], confirmText: t('切到新系统'), focus: 'cancel' }
    : { title: t('切回老系统'), message: t('狗会先停下，新系统交出控制，老控制台重新连上运动主机（约 15 秒）。'), details: unsure ? [t('狗是趴着的（狗报的状态是 IDLE，看不出趴没趴：请你亲眼确认）')] : undefined, confirmText: t('切回老系统'), focus: unsure ? 'cancel' : 'confirm' })
  if (!ok) return
  if (to === 'old' && mine.value) store.leave('切回老系统') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
  await store.command(d.id, 'switch_mode', to === 'new' ? t('切到新系统') : t('切回老系统'), unsure ? { to, confirm_lying: true } : { to })
}

async function repairOld(): Promise<void> {
  const d = dog.value
  if (!d) return
  const ok = await confirm.ask({ title: t('修复老系统'), message: t('重启狗方的老控制台，让它重新连上运动主机（约 15 秒）。这段时间平台老卡片和狗方网页没有画面。'), confirmText: t('重启老控制台'), focus: 'confirm' })
  if (ok) await store.command(d.id, 'switch_mode', t('修复老系统'), { to: 'old' })
}

async function standToggle(): Promise<void> {
  const d = dog.value
  if (!d) return
  const before = tel.value?.basic_state ?? null
  const r = await store.command(d.id, 'stand_toggle', t('起立/趴下'))
  if (r?.result === 'no_reply') standHold.value = { until: Date.now() + 15000, state: before }
}

async function enable(on: boolean): Promise<void> {
  if (!dog.value) return
  if (!on && mine.value) store.leave('停用这只狗') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
  await dog2Api.enable(dog.value.id, on).catch(() => undefined)
  await store.refresh(true)
}

// -- hold to move ----------------------------------------------------------------------------------------------
const held = ref<Dog2Dir | null>(null)
const KEYS: Record<string, Dog2Dir> = { w: 'fwd', s: 'back', a: 'left', d: 'right', q: 'tl', e: 'tr' }
const LABEL: Record<Dog2Dir, string> = { fwd: t('前进'), back: t('后退'), left: t('左移'), right: t('右移'), tl: t('左转'), tr: t('右转') }

function press(dir: Dog2Dir): void {
  if (motionWhy.value) return
  held.value = dir
  store.setAxes([...DOG2_AXES[dir]] as [number, number, number])
}
function letGo(): void {
  held.value = null
  store.setAxes([0, 0, 0])
}
function onKey(ev: KeyboardEvent): void {
  const dir = KEYS[ev.key.toLowerCase()]
  const target = ev.target
  if (!dir || ev.repeat || (target instanceof Element && target.closest('input, textarea'))) return
  ev.preventDefault()
  press(dir)
}
function onKeyUp(ev: KeyboardEvent): void {
  if (KEYS[ev.key.toLowerCase()] === held.value) letGo()
}
function onHidden(): void {
  if (document.hidden) letGo()
}

// -- soft e-stop: long press 0.8 s, like the old dog page ---------------------------------------------------------
const estopAt = ref<number | null>(null)
let estopTimer: number | null = null
function estopDown(): void {
  if (!dog.value) return
  estopAt.value = Date.now()
  estopTimer = window.setTimeout(() => {
    estopAt.value = null
    if (dog.value) {
      if (mine.value) store.leave('软急停') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
      void store.command(dog.value.id, 'soft_estop', t('软急停'))
    }
  }, 800)
}
function estopUp(): void {
  if (estopTimer !== null) window.clearTimeout(estopTimer)
  estopTimer = null
  estopAt.value = null
}

function stopNow(): void {
  if (!dog.value) return
  letGo()
  void store.command(dog.value.id, 'stop', t('停止'))
}

async function loadLog(): Promise<void> {
  if (dog.value) log.value = await dog2Api.log(dog.value.id).catch(() => log.value)
}

watch(() => dog.value?.id, (id, old) => {
  if (old && store.hold.dog === old) store.leave('换了一只狗') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
  void loadLog()
})

onMounted(() => {
  store.start()
  window.addEventListener('keydown', onKey)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('blur', letGo)
  document.addEventListener('visibilitychange', onHidden)
  logTimer = window.setInterval(() => void loadLog(), 3000)
})
onBeforeRouteLeave(() => {
  store.leave('离开新狗系统页') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
})
onBeforeUnmount(() => {
  // the poll keeps running: the live page's Lite3 card reads the same store (since 2026-11-10)
  letGo()
  store.leave('离开新狗系统页') // i18n-ignore: the reason goes to the backend in Chinese and comes back translated
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('blur', letGo)
  document.removeEventListener('visibilitychange', onHidden)
  if (logTimer !== null) window.clearInterval(logTimer)
})

// -- outdoor navigation, engineering view (docs/dog/ui-design.md 19.10): raw state, one point, "只算不走"
const navCap = computed(() => dog.value?.navCapability ?? null)
const navOn = computed(() => ['starting', 'running', 'paused'].includes(dog.value?.nav?.state ?? ''))
const dryRun = ref(false)
const navPoint = ref('')
const navPointParsed = computed(() => {
  const m = /^\s*(-?\d+(?:\.\d+)?)\s*[,，\s]\s*(-?\d+(?:\.\d+)?)\s*$/.exec(navPoint.value)
  if (!m) return null
  const lat = Number(m[1])
  const lon = Number(m[2])
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? { lat, lon } : null
})
const navWhy = computed(() => why.value ?? (!mine.value ? t('先取得控制') : null))
function navStart(): void {
  const d = dog.value
  const p = navPointParsed.value
  if (!d || !p || navWhy.value) return
  void store.askStart(d.id, [p], { dryRun: dryRun.value && !!navCap.value?.dry_run })
}

function logLine(e: Dog2LogEntry): string {
  if (e.kind === 'command') return t('{action}：{result}', { action: e.action ?? '', result: e.result ?? '' }) + (e.code ? t('（{code}）', { code: e.code }) : '') + (e.text ? ` ${e.text}` : '')
  if (e.kind === 'control') return t('控制权结束：{reason}', { reason: e.ended ?? '' })
  if (e.kind === 'hold') return e.stopped ?? ''
  return e.kind
}
</script>

<template>
  <div class="d2">
    <header class="d2-head">
      <h1>{{ t('新狗系统（测试）') }}</h1>
      <span class="sub">{{ t('和老的 Lite3 卡片同时在。同一时刻只有一套能控狗，取决于板卡现在的模式。') }}</span>
      <span v-if="store.mode === 'off'" class="pill bad">{{ t('新狗系统没有开启（DOG2_MODE=off）') }}</span>
      <span v-else-if="store.mode === 'on' && !store.broker" class="pill bad">{{ t('平台没连上 MQTT') }}</span>
      <span v-if="store.error" class="pill bad">{{ store.error }}</span>
    </header>

    <div v-if="store.dogs.length > 1" class="d2-tabs">
      <button v-for="d in store.dogs" :key="d.id" class="btn" :class="{ 'btn-primary': d.id === dog?.id }" @click="selected = d.id">
        {{ d.label }} <small>{{ d.online ? t('在线') : t('离线') }}</small>
      </button>
    </div>

    <p v-if="!dog" class="empty">{{ store.mode === 'off' ? t('新狗系统没有开启。') : t('还没有狗连上来。狗装好新程序、开机联网后，会自动出现在这里。') }}</p>

    <div v-else class="d2-body">
      <section class="d2-main">
        <div class="d2-mode" :class="{ new: isNew, old: dog.mode === 'old', off: !dog.online }">
          <strong>{{ t('{name}（新）', { name: dog.label }) }}</strong>
          <span class="mode" :class="{ stuck: oldStuck }">{{ modeText }}</span>
          <span v-if="dog.software" class="dim">{{ t('软件 {version}', { version: dog.software }) }}</span>
          <label class="en"><input type="checkbox" :checked="dog.enabled" @change="enable(($event.target as HTMLInputElement).checked)"> {{ tc('state', '启用') }}</label>
        </div>
        <div class="d2-streams">
          <button v-for="(_, s) in dog.video" :key="s" class="btn" :class="{ 'btn-primary': stream === s }" @click="stream = String(s)">
            {{ s === 'rgb' ? t('彩色') : s === 'depth' ? t('深度') : s }}
          </button>
        </div>
        <Dog2Video :dog="dog.id" :stream="stream" :video="dog.video[stream]" />
        <p v-if="depthLine" class="dim" data-test="d2-depth-front">{{ depthLine }}</p>
        <p v-if="st?.last_error" class="pill warn">{{ st.last_error.text }}</p>
        <p v-if="isNew && (st?.motion_host?.feedback_age_s ?? 0) > 1" class="pill warn">{{ t('运动主机状态包断了：狗已停下，切不切回老系统由你决定') }}</p>
        <p v-if="store.hold.lostReason && !mine" class="pill warn">{{ t('控制权已失去：{reason}', { reason: store.hold.lostReason }) }}</p>
      </section>

      <aside class="d2-side">
        <div class="card">
          <h3>{{ t('状态') }}</h3>
          <dl>
            <dt>{{ t('运动状态') }}</dt><dd>{{ tel?.basic_state_name ?? st?.old_console?.robot_state ?? '—' }}</dd>
            <dt>{{ t('电量') }}</dt><dd>{{ fmt(tel?.battery_pct ?? st?.old_console?.battery_pct, 0) }}%</dd>
            <dt>{{ tc('imu', '姿态') }}</dt><dd>{{ tel ? `${fmt(tel.rpy[0])} / ${fmt(tel.rpy[1])} / ${fmt(tel.rpy[2])}` : '—' }}</dd>
            <dt>{{ t('速度') }}</dt><dd>{{ tel ? `${fmt(tel.vel_body[0], 2)} m/s` : '—' }}</dd>
            <dt>{{ t('状态包') }}</dt><dd>{{ tel ? t('{ms} ms 前', { ms: Math.round(tel.feedback_age_s * 1000) }) : '—' }}</dd>
            <dt>{{ t('谁在控') }}</dt><dd>{{ mine ? t('你（新系统）') : dog.control.held ? (dog.control.label ?? t('别处')) : isNew ? t('没人') : t('老系统') }}</dd>
          </dl>
        </div>

        <div class="card">
          <h3>{{ t('新老切换') }}</h3>
          <p v-if="oldGone" class="dim">{{ isNew ? t('老系统已停用，新系统一直在控。') : t('老系统已停用，新系统正在接管运动主机…') }}</p>
          <template v-else-if="!isNew">
            <button v-if="oldStuck" class="btn btn-primary" :disabled="!!busy || switching" @click="repairOld">{{ t('修复老系统（重启老控制台）') }}</button>
            <button v-else class="btn btn-primary" :disabled="!!why || switching || !!busy || !canSwitchPosture"
                    :title="why ?? (!canSwitchPosture ? t('先让狗趴下') : '')" @click="switchTo('new')">{{ t('切到新系统') }}</button>
            <small v-if="oldStuck" class="dim">{{ t('老控制台只在启动时连一次运动主机，那一下没连上，平台的老卡片和新系统都控不了狗。点上面的按钮让它重新连。') }}</small>
          </template>
          <button v-else-if="!oldGone" class="btn" :disabled="!!busy || switching || !canSwitchPosture" :title="!canSwitchPosture ? t('先让狗趴下再切回老系统') : ''" @click="switchTo('old')">{{ t('切回老系统') }}</button>
          <small v-if="busy" class="dim">{{ busy }}…</small>
        </div>

        <div class="card">
          <h3>{{ t('控制') }}</h3>
          <div class="row">
            <button v-if="!mine" class="btn btn-primary" :disabled="!!why || !isNew || !!busy" :title="why ?? (!isNew ? t('先切到新系统') : '')" @click="store.take(dog.id)">{{ t('取得控制') }}</button>
            <button v-else class="btn" @click="store.release()">{{ t('交出控制') }}</button>
          </div>
          <div class="pad" @pointerup="letGo" @pointerleave="letGo">
            <button v-for="d in (['tl', 'fwd', 'tr', 'left', 'back', 'right'] as Dog2Dir[])" :key="d" class="btn dir"
                    :class="{ on: held === d }" :disabled="!!motionWhy" :title="motionWhy ?? ''"
                    @pointerdown.prevent="press(d)" @pointercancel="letGo">{{ LABEL[d] }}</button>
          </div>
          <small class="dim">{{ t('按住移动，松手就停（键盘 W/S/A/D 前后左右，Q/E 转向）。网络卡一下狗会先停下，控制权保留，再按就接着走。') }}</small>
          <div class="row">
            <button class="btn" :disabled="!!motionWhy || store.moving || !!standWhy" :title="standWhy ?? ''" @click="standToggle">{{ t('起立/趴下') }}</button>
            <button class="btn" :disabled="!!motionWhy || store.moving" @click="store.command(dog.id, 'moving_mode', t('移动模式'))">{{ t('移动模式') }}</button>
            <button class="btn" :disabled="!!motionWhy || store.moving" @click="store.command(dog.id, 'low_gait', t('低速步态'))">{{ t('低速步态') }}</button>
          </div>
        </div>

        <div v-if="navCap" class="card" data-test="dog2-nav">
          <h3>{{ t('导航（户外 GPS）') }}</h3>
          <dl>
            <dt>{{ t('状态') }}</dt><dd>{{ dog.nav?.state ?? '—' }}{{ dog.nav?.reason ? ` · ${dog.nav.reason}` : '' }}</dd>
            <dt>{{ t('任务') }}</dt><dd>{{ dog.nav?.taskId ?? dog.nav?.task_id ?? '—' }}</dd>
          </dl>
          <label v-if="navCap.dry_run" class="en"><input v-model="dryRun" type="checkbox" data-test="dog2-dry-run"> {{ t('只算不走') }}</label>
          <div class="row">
            <input v-model="navPoint" class="input" :placeholder="t('纬度, 经度（WGS84）')" data-test="dog2-nav-point" />
            <button class="btn btn-primary" :disabled="!!navWhy || !navPointParsed || navOn" :title="navWhy ?? (!navPointParsed ? t('填一个点：纬度, 经度') : '')" data-test="dog2-nav-start" @click="navStart">{{ t('开始导航…') }}</button>
          </div>
          <div class="row">
            <button class="btn" :disabled="!!navWhy || dog.nav?.state !== 'running'" @click="store.navPause(dog.id)">{{ t('暂停') }}</button>
            <button class="btn" :disabled="!!navWhy || dog.nav?.state !== 'paused'" @click="store.navResume(dog.id)">{{ t('继续') }}</button>
            <button class="btn btn-danger" :disabled="!!navWhy || !navOn" @click="store.navCancel(dog.id)">{{ t('结束导航') }}</button>
          </div>
          <details>
            <summary>{{ t('导航能力') }}</summary>
            <pre class="raw">{{ JSON.stringify(navCap, null, 2) }}</pre>
          </details>
          <details open>
            <summary>{{ t('导航原始状态') }}</summary>
            <pre class="raw" data-test="dog2-nav-raw">{{ dog.nav ? JSON.stringify(dog.nav, null, 2) : '—' }}</pre>
          </details>
        </div>

        <div class="card safety">
          <button class="btn btn-danger big" :disabled="!dog" @click="stopNow">{{ t('停止') }}</button>
          <button class="btn estop big" :class="{ arming: estopAt }" @pointerdown="estopDown" @pointerup="estopUp" @pointerleave="estopUp" @pointercancel="estopUp">{{ t('软急停（长按）') }}</button>
          <small class="dim">{{ t('停止和软急停在新老两种模式下都能用，也不需要先取得控制。') }}</small>
        </div>

        <div class="card">
          <h3>{{ t('最近') }}</h3>
          <ul class="notes">
            <li v-for="n in myNotes" :key="n.at + n.text" :class="n.tone">{{ n.text }}</li>
          </ul>
          <details>
            <summary>{{ t('指令记录') }}</summary>
            <ul class="log"><li v-for="(e, i) in log.slice(0, 40)" :key="i"><time>{{ new Date(e.at).toLocaleTimeString() }}</time> {{ logLine(e) }}</li></ul>
          </details>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.d2 { padding: var(--sp-4); display: flex; flex-direction: column; gap: var(--sp-3); height: 100%; overflow: auto; }
.d2-head { display: flex; align-items: baseline; gap: var(--sp-3); flex-wrap: wrap; }
.d2-head h1 { font-size: var(--fs-lg); margin: 0; }
.sub, .dim { color: var(--text-dim); font-size: var(--fs-sm); }
.d2-tabs, .d2-streams, .row { display: flex; gap: var(--sp-2); flex-wrap: wrap; }
.empty { color: var(--text-dim); }
.d2-body { display: grid; grid-template-columns: minmax(0, 1fr) 340px; gap: var(--sp-4); align-items: start; }
.d2-main { display: flex; flex-direction: column; gap: var(--sp-2); }
.d2-mode { display: flex; align-items: center; gap: var(--sp-3); padding: var(--sp-2) var(--sp-3); border-radius: var(--r-ctl); background: var(--panel-2); border: 1px solid var(--border); }
.d2-mode.new { border-color: var(--ok); }
.d2-mode.old .mode { color: var(--text-dim); }
.d2-mode.new .mode { color: var(--ok); font-weight: 600; }
.d2-mode.off .mode { color: var(--danger); }
.en { margin-left: auto; font-size: var(--fs-sm); }
.d2-side { display: flex; flex-direction: column; gap: var(--sp-3); }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: var(--r-panel); padding: var(--sp-3); display: flex; flex-direction: column; gap: var(--sp-2); }
.card h3 { margin: 0; font-size: var(--fs-md); }
dl { display: grid; grid-template-columns: auto 1fr; gap: 4px var(--sp-3); margin: 0; font-size: var(--fs-sm); }
dt { color: var(--text-dim); }
dd { margin: 0; font-family: var(--font-num); }
.pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--sp-2); touch-action: none; user-select: none; }
.dir { min-height: 48px; }
.dir.on { background: var(--accent); color: var(--accent-ink); }
.safety { flex-direction: row; flex-wrap: wrap; }
.big { flex: 1; min-height: 48px; font-weight: 600; }
.estop { background: var(--estop); color: #fff; touch-action: none; user-select: none; }
.dir { touch-action: none; }
.mode.stuck { color: var(--warn); font-weight: 600; }
.estop.arming { outline: 3px solid var(--warn); }
.pill { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: var(--fs-sm); margin: 0; }
.pill.bad { background: color-mix(in srgb, var(--danger) 20%, transparent); color: var(--danger); }
.pill.warn { background: color-mix(in srgb, var(--warn) 20%, transparent); color: var(--warn); }
.notes, .log { list-style: none; margin: 0; padding: 0; font-size: var(--fs-sm); display: flex; flex-direction: column; gap: 2px; }
.notes .ok { color: var(--ok); }
.notes .warn { color: var(--warn); }
.notes .bad { color: var(--danger); }
.raw { margin: 4px 0 0; max-height: 260px; overflow: auto; font: 11px/1.4 var(--font-num); white-space: pre-wrap; word-break: break-all; }
.log time { color: var(--text-dim); font-family: var(--font-num); margin-right: 6px; }
@media (max-width: 900px) { .d2-body { grid-template-columns: 1fr; } }
</style>
