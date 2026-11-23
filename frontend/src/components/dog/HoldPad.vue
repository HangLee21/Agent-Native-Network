
<script setup lang="ts">
/**
 * Hold-to-move pad of the operated dog (ui-design.md 5.3, 9.1). Moves only while a key or button is held; release,
 * pointer leaving, window blur, background, device switch and page exit all stop. Every slot has a fixed height so
 * the pad never changes size (5.9). Keys: W/S forward/back, A/D sideways, Q/E or ←/→ turn (as the drone stick mode),
 * Space lets go, Esc = stop. Space is never the soft e-stop. Keys pressed with ⌘ / Ctrl / Alt are shortcuts, never
 * moves (macOS does not report letters released while ⌘ is down, so ⌘S would otherwise keep the dog walking); an
 * Esc that closes something else (confirmation, photo picking, the manual panel) does not also stop the dog.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useDogStore, navActive, lite3Pose, DOG_NAME, S10_POSTURE, STANDING } from '@/stores/dog'
import { t } from '@/i18n'
import { useConfirmStore } from '@/stores/confirm'
import { s10RunningJob, s10Stowed } from './dogFlow'
import type { DogId } from '@/api/dog'

const props = defineProps<{ dog: DogId }>()
const emit = defineEmits<{ (e: 'stop'): void }>()
const store = useDogStore()
const confirm = useConfirmStore()

type Dir = 'fwd' | 'back' | 'left' | 'right' | 'tl' | 'tr' | 'fl' | 'fr'
const DIRS: Record<Dir, { g: string; l: string; k: string }> = {
  fwd: { g: '↑', l: t('前进'), k: 'W' }, back: { g: '↓', l: t('后退'), k: 'S' }, left: { g: '←', l: t('左移'), k: 'A' }, right: { g: '→', l: t('右移'), k: 'D' },
  tl: { g: '↶', l: t('左转'), k: 'Q' }, tr: { g: '↷', l: t('右转'), k: 'E' }, fl: { g: '↖', l: t('左前'), k: '' }, fr: { g: '↗', l: t('右前'), k: '' },
}
/** Direction names in Chinese for the hold label sent to the backend (shared data stays in one language). */
const DIR_ZH: Record<Dir, string> = { fwd: '前进', back: '后退', left: '左移', right: '右移', tl: '左转', tr: '右转', fl: '左前', fr: '右前' }   // i18n-ignore: sent to the backend, shown via tb()
const GRID: (Dir | 'stop')[] = ['fl', 'fwd', 'fr', 'left', 'stop', 'right', 'tl', 'back', 'tr']

let open = true
try {
  open = localStorage.getItem('uav.dogPadOpen') !== '0'
} catch {
  /* storage unavailable */
}
const shown = ref(open)
watch(shown, (v) => {
  try {
    localStorage.setItem('uav.dogPadOpen', v ? '1' : '0')
  } catch {
    /* storage unavailable */
  }
})

const linear = ref(0.1)
const turn = ref(0.25)

const s10 = computed(() => store.s10)
const l3 = computed(() => store.lite3)
const online = computed(() => store.online(props.dog))
const holdDir = computed<Dir | null>(() => {
  if (props.dog === 's10') return (store.s10Hold?.dir as Dir) ?? null
  const a = store.l3.axes
  if (!a.some((v) => v !== 0)) return null
  return (Object.keys(L3_AXES) as Dir[]).find((d) => L3_AXES[d].every((v, i) => v === a[i])) ?? null
})
const holding = computed(() => (props.dog === 's10' ? !!store.s10Hold : store.l3Moving))

/** Lite3 axes [W−S, D−A, E−Q] (interface doc 2.6: +yaw = turn right). */
const L3_AXES: Record<Dir, [number, number, number]> = {
  fwd: [1, 0, 0], back: [-1, 0, 0], left: [0, -1, 0], right: [0, 1, 0], tl: [0, 0, -1], tr: [0, 0, 1], fl: [1, -1, 0], fr: [1, 1, 0],
}
/** S10 velocity signs (x forward, y left, yaw left: interface doc 2.6, S10 +yaw = turn left). */
const S10_SIGN: Record<Dir, [number, number, number]> = {
  fwd: [1, 0, 0], back: [-1, 0, 0], left: [0, 1, 0], right: [0, -1, 0], tl: [0, 0, 1], tr: [0, 0, -1], fl: [1, 1, 0], fr: [1, -1, 0],
}

interface Check { ok: boolean | null; t: string; title?: string }
const avail = computed<{ ok: boolean; reason: string; cls: string; checks: Check[] }>(() => {
  const name = DOG_NAME[props.dog]
  if (!online.value) {
    return { ok: false, reason: store.pageStale(props.dog) ? t('本页 {n} 秒没收到 {name} 的新状态', { n: store.staleSecs(props.dog), name }) : store.lost(props.dog) ? t('{name} 失联，指令发不出去，请用实体遥控器', { name }) : t('{name} 离线', { name }), cls: 'bad', checks: [] }
  }
  if (props.dog === 's10') {
    const s = s10.value!
    const rl = s.posture === 'rl_control' || s.topics.motion?.state === 17
    const stowed = s10Stowed(s)
    const nav = navActive(s.nav)
    const rtt = s.link.rttMs
    const checks: Check[] = [
      { ok: rl, t: t('可走') }, { ok: stowed, t: t('臂已收') }, { ok: !nav, t: t('无导航') }, { ok: null, t: t('步态'), title: t('狗会检查步态') },
    ]
    if (rtt != null && rtt > 500) checks.push({ ok: false, t: t('链路 {n}ms', { n: rtt }) })
    const job = s10RunningJob(s)
    if (job) return { ok: false, reason: t('S10 一次只做一件事：正在执行「{job}」，等它结束', { job: job.label ?? job.action }), cls: 'warn', checks }
    if (!rl) return { ok: false, reason: t('要先进入可走状态（RL 控制），当前：{now}', { now: S10_POSTURE[s.posture ?? ''] ?? s.posture ?? t('未知') }), cls: 'warn', checks }
    if (stowed === false) return { ok: false, reason: t('机械臂没收好：先在「准备 · 走动」页「收回机械臂」'), cls: 'warn', checks }
    if (nav) return { ok: false, reason: t('导航进行中，先取消导航'), cls: 'warn', checks }
    if (!s.link.clockOk) return { ok: false, reason: t('控制连接延迟过高（和狗的时钟同步过期），稍后再按'), cls: 'warn', checks }
    if (store.armHold) return { ok: false, reason: t('机械臂点动中'), cls: 'warn', checks }
    return { ok: true, reason: '', cls: '', checks }
  }
  const l = l3.value!
  const mine = !!store.l3.session
  const pose = lite3Pose(l.robot.robot_state)
  // lite3-01 reports IDLE standing or lying: "standing" is then unknown (–), not a cross
  const checks: Check[] = [
    { ok: mine, t: t('控制权') },
    pose === 'unknown'
      ? { ok: null, t: STANDING, title: t('狗报的状态认不出是站着还是趴着，看画面判断') }
      : { ok: pose === 'standing', t: STANDING },
  ]
  if (l.robot.controller === 'other') return { ok: false, reason: t('Lite3 正被别处控制，不能移动'), cls: 'warn', checks }
  if (!mine) return { ok: false, reason: t('先「取得控制」才能移动'), cls: 'warn', checks }
  return { ok: true, reason: '', cls: '', checks }
})

function begin(dir: Dir): void {
  if (!avail.value.ok || holding.value) return
  if (props.dog === 's10') {
    const [sx, sy, sw] = S10_SIGN[dir]
    const lin = Math.min(0.15, Math.max(0.01, Number(linear.value) || 0.1))
    const tr = Math.min(0.3, Math.max(0.01, Number(turn.value) || 0.25))
    void store.s10HoldStart(dir, sx * lin, sy * lin, sw * tr, `按住移动 · ${DIR_ZH[dir]}`)   // i18n-ignore: sent to the backend, shown via tb()
  } else {
    store.l3SetAxes([...L3_AXES[dir]])
  }
}

function end(): void {
  if (props.dog === 's10') void store.s10HoldEnd('松手')   // i18n-ignore: sent to the backend, shown via tb()
  else store.l3SetAxes([0, 0, 0])
}

function padStop(): void {
  end()
  emit('stop')
}

// ---------------------------------------------------------------- keyboard
const held = new Set<string>()
const KEY_DIR: Record<string, 'w' | 's' | 'a' | 'd' | 'q' | 'e'> = { w: 'w', s: 's', a: 'a', d: 'd', q: 'q', e: 'e', arrowleft: 'q', arrowright: 'e' }

function inField(e: KeyboardEvent): boolean {
  return e.target instanceof Element && !!e.target.closest('input, select, textarea, [contenteditable="true"]')
}

function keyDir(): Dir | null {
  const h = (k: string) => held.has(k)
  if (h('w') && h('a')) return 'fl'
  if (h('w') && h('d')) return 'fr'
  for (const k of held) {
    const m = ({ w: 'fwd', s: 'back', a: 'left', d: 'right', q: 'tl', e: 'tr' } as const)[k as 'w']
    if (m) return m
  }
  return null
}

function applyKeys(): void {
  if (props.dog === 'lite3') {
    // Lite3: held keys add up like the dog side's page (W+A diagonal, W+Q forward while turning)
    const ax: [number, number, number] = [Number(held.has('w')) - Number(held.has('s')), Number(held.has('d')) - Number(held.has('a')), Number(held.has('e')) - Number(held.has('q'))]
    if (!ax.some((v) => v !== 0)) store.l3SetAxes([0, 0, 0])
    else if (avail.value.ok) store.l3SetAxes(ax)
    return
  }
  const dir = keyDir()
  if (store.s10Hold && store.s10Hold.dir !== dir) void store.s10HoldEnd('松手')   // i18n-ignore: sent to the backend, shown via tb()
  if (dir && !store.s10Hold) begin(dir)
}

/** Lets go of every key (a shortcut is starting, or a keyup will not come). */
function releaseKeys(): void {
  if (!held.size) return
  held.clear()
  applyKeys()
}

function onKeyDown(e: KeyboardEvent): void {
  if (e.defaultPrevented || inField(e) || confirm.current) return
  if (e.key === 'Meta' || e.key === 'Control' || e.key === 'Alt') {
    releaseKeys()
    return
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return
  if (e.key === 'Escape') {
    // all window listeners run before this microtask: stop only if no other overlay took this Esc
    queueMicrotask(() => {
      if (!e.defaultPrevented) padStop()
    })
    return
  }
  if (e.key === ' ') {
    e.preventDefault()
    held.clear()
    end()
    return
  }
  const k = KEY_DIR[e.key.toLowerCase()]
  if (!k || e.repeat) return
  e.preventDefault()
  held.add(k)
  applyKeys()
}

function onKeyUp(e: KeyboardEvent): void {
  if (e.key === 'Meta') {
    releaseKeys()   // macOS: letters released while ⌘ was down send no keyup
    return
  }
  const k = KEY_DIR[e.key.toLowerCase()]
  if (!k) return
  held.delete(k)
  applyKeys()
}

function onWindowUp(): void {
  if (!held.size) end()
}

function onBlur(): void {
  held.clear()
}

/** Hidden without losing focus (tab switch): keyups may never come, so a stale key must not join the next press. */
function onVisibility(): void {
  if (document.hidden) held.clear()
}

onMounted(() => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('pointerup', onWindowUp)
  window.addEventListener('blur', onBlur)
  document.addEventListener('visibilitychange', onVisibility)
})
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('pointerup', onWindowUp)
  window.removeEventListener('blur', onBlur)
  document.removeEventListener('visibilitychange', onVisibility)
  held.clear()
  end()
})

const statusLine = computed<{ cls: string; icon: string; text: string }>(() => {
  if (holding.value && holdDir.value) {
    const d = DIRS[holdDir.value]
    if (props.dog === 's10') {
      const h = store.s10Hold!
      if (h.starting) return { cls: 'run', icon: 'spinner', text: t('已发送：{dir}，等狗受理…', { dir: d.l }) }
      const sp = holdDir.value.startsWith('t') ? `${turn.value} rad/s` : `${linear.value} m/s`
      const health = h.ignored ? t('（{n} 次没续租）', { n: h.ignored }) : t(' 正常')
      return { cls: 'run', icon: 'play', text: t('移动中 · {dir} {speed} · 心跳 #{beats}{health} · 链路 {rtt} ms。松手、切到别的程序或设备都会立即停', { dir: d.l, speed: sp, beats: h.beats, health, rtt: s10.value?.link.rttMs ?? '—' }) }
    }
    return { cls: 'run', icon: 'play', text: t('移动中 · {dir}。松手、切到别的程序或设备都会立即停', { dir: d.l }) }
  }
  const n = store.notes[props.dog]
  if (n && Date.now() - n.at < 6000) return { cls: n.cls === 'ok' ? 'ok' : n.cls, icon: n.cls === 'ok' ? 'check' : 'alert', text: n.text }
  if (!avail.value.ok) return { cls: avail.value.cls, icon: 'alert', text: avail.value.reason }
  return { cls: 'dim', icon: 'info', text: t('按住才动、松手即停 · W/S 前后 · A/D 平移 · Q/E 或 ←/→ 转向 · Esc 停止') }
})
</script>

<template>
  <button v-if="!shown" class="btn padshow" :style="{ '--c': `var(--dog-${dog})` }" data-test="dog-pad-show" @click="shown = true">
    <AppIcon name="joystick" :size="16" />{{ t('按住移动') }}<AppIcon name="chevron" :size="14" />
  </button>
  <div v-else class="pad" :style="{ '--c': `var(--dog-${dog})` }" data-test="dog-pad">
    <div class="padh">
      <AppIcon name="joystick" :size="17" />{{ t('按住移动 · {name}', { name: DOG_NAME[dog] }) }}
      <span class="grow" />
      <button class="btn btn-ghost btn-sm btn-icon" :title="t('收起')" :aria-label="t('收起按住移动')" @click="shown = false"><AppIcon name="minus" :size="14" /></button>
    </div>
    <template v-if="dog === 's10'">
      <div class="spd">
        <label>{{ t('直线速度') }}<span class="in"><input v-model.number="linear" class="input num" type="number" min="0.01" max="0.15" step="0.01" :disabled="holding"><span class="dim">m/s</span></span></label>
        <label>{{ t('转向速度') }}<span class="in"><input v-model.number="turn" class="input num" type="number" min="0.01" max="0.30" step="0.01" :disabled="holding"><span class="dim">rad/s</span></span></label>
      </div>
      <div class="hint" :class="{ warnc: holding }">{{ holding ? t('按住时速度锁定，松手后再按才生效') : t('范围：直线 0.01–0.15 · 转向 0.01–0.30') }}</div>
    </template>
    <div v-else class="l3note">{{ t('只有一档速度（按下就是这个方向的全速）。想慢些，先在右栏按「低速步态」。') }}</div>
    <div class="checks">
      <span v-for="c in avail.checks" :key="c.t" :class="c.ok === null ? 'dim' : c.ok ? 'okc' : 'badc'" :title="c.title ?? ''">
        <AppIcon :name="c.ok === null ? 'minus' : c.ok ? 'check' : 'x'" :size="12" />{{ c.t }}
      </span>
    </div>
    <div class="grid">
      <template v-for="k in GRID" :key="k">
        <button v-if="k === 'stop'" class="pk stopk" :disabled="!online" :title="t('停止（Esc）')" data-test="dog-pad-stop" @click="padStop">
          <b><AppIcon name="stop" :size="20" /></b><small>{{ t('停止 Esc') }}</small>
        </button>
        <button v-else class="pk" :class="{ on: holdDir === k }" :disabled="!avail.ok && holdDir !== k" :title="avail.ok ? DIRS[k].l : avail.reason"
                :aria-label="DIRS[k].l" :data-test="`dog-pad-${k}`"
                @pointerdown.prevent="(e) => { (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId); begin(k) }"
                @pointerup="end" @pointercancel="end" @lostpointercapture="end" @contextmenu.prevent>
          <b>{{ DIRS[k].g }}</b><small>{{ DIRS[k].l }}{{ DIRS[k].k ? ` ${DIRS[k].k}` : '' }}</small>
        </button>
      </template>
    </div>
    <div class="st" :class="statusLine.cls" data-test="dog-pad-status"><AppIcon :name="statusLine.icon" :size="14" /><span>{{ statusLine.text }}</span></div>
  </div>
</template>

<style scoped>
.pad {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 960;
  width: 272px;
  padding: 10px 12px;
  border-radius: var(--r-panel);
  border: 1px solid var(--border);
  border-top: 3px solid var(--c);
  background: var(--overlay);
  backdrop-filter: blur(8px);
  box-shadow: var(--shadow);
  user-select: none;
}
.padshow {
  position: absolute;
  right: 16px;
  bottom: 16px;
  z-index: 960;
  background: var(--overlay);
  border-color: var(--c);
}
.padh {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  height: 28px;
}
.spd {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.spd .in {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 2px;
}
.spd input {
  width: 72px;
  height: 28px;
}
.hint, .l3note {
  height: 20px;
  font-size: var(--fs-xs);
  color: var(--text-dim);
  margin-top: 4px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.l3note {
  height: 72px;
  white-space: normal;
}
.warnc { color: var(--warn); }
.checks {
  display: flex;
  gap: 4px 6px;
  height: 20px;
  overflow: hidden;
  white-space: nowrap;
  font-size: 11.5px;
  margin-top: 4px;
}
.checks span { display: inline-flex; align-items: center; gap: 2px; }
.okc { color: var(--ok); }
.badc { color: var(--danger); }
.grid {
  display: grid;
  grid-template-columns: repeat(3, 64px);
  gap: 8px;
  justify-content: center;
  margin: 8px 0;
}
.pk {
  width: 64px;
  height: 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  border-radius: var(--r-ctl);
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text);
  cursor: pointer;
  touch-action: none;
}
.pk b { font-size: 22px; line-height: 1; }
.pk small { font-size: 11px; color: var(--text-dim); }
.pk:disabled { opacity: 0.4; cursor: not-allowed; }
.pk.on { background: var(--c); color: #0b0f14; border-color: var(--c); }
.pk.on small { color: #0b0f14; }
.stopk { border-color: var(--danger); color: var(--danger); }
.st {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  height: 36px;
  overflow: hidden;
  font-size: var(--fs-xs);
  line-height: 1.4;
}
.st.dim { color: var(--text-dim); }
.st.run { color: var(--accent); }
.st.ok { color: var(--ok); }
.st.warn { color: var(--warn); }
.st.bad { color: var(--danger); }
.grow { flex: 1; }
@media (max-height: 800px) {
  .pad { width: 248px; }
  .grid { grid-template-columns: repeat(3, 56px); }
  .pk { width: 56px; height: 56px; }
  .l3note { height: 54px; }
}
</style>
