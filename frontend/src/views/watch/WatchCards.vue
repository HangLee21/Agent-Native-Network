<script setup lang="ts">
/**
 * Lower part of the 监视台 rail: one card per drone (one line each once there are three or more), the separation
 * line, and the feed. With the route hidden the feed lists only the aircraft's own state changes; otherwise every
 * event and command, filterable (the prototype).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t, tc } from '@/i18n'
import type { WatchEngine } from './engine'
import { DOG_WALK_MPS, EXEC_LABEL, GROUND_MODES, MODE, PHASE_LABEL, dogField, isNum, lastBefore, pairMinAt, phaseOf, sepAt, stateAt, type LogRow, type WatchFlight } from './model'
import { clockStr, durStr } from './timeline'

const props = defineProps<{ engine: WatchEngine }>()
const E = props.engine

const fixed = (v: number, d = 1) => (isNum(v) ? v.toFixed(d) : '–')
const signed = (v: number) => (!isNum(v) ? '–' : (v > 0.05 ? '+' : v < -0.05 ? '−' : '') + Math.abs(v).toFixed(1))
const deg = (v: number) => (!isNum(v) ? '–' : String(Math.round(v)).replace(/^-/, '−'))

/** A dog's readings at the cursor (D-40): GNSS fix, the motion host's state, which system has it and who controls it. */
function dogInfo(f: WatchFlight, i: number): { fix: string; state: string; ctl: string } {
  const fix = dogField(f, i, 'fix') as string | null, sats = dogField(f, i, 'sats') as number | null
  const fixName = !fix ? '–' : fix === 'none' ? t('未定位') : fix === 'rtk_fixed' ? t('RTK 固定') : fix === 'rtk_float' ? t('RTK 浮动') : t('已定位')
  const mode = dogField(f, i, 'mode') as string | null
  const held = dogField(f, i, 'controlHeld') === true
  const label = dogField(f, i, 'controlLabel') as string | null
  return {
    fix: isNum(sats) && fix ? t('{fix} · {n} 颗', { fix: fixName, n: sats }) : fixName,
    state: (dogField(f, i, 'basicStateName') as string | null) ?? '–',
    ctl: (mode === 'new' ? t('新系统') : mode === 'old' ? t('老系统') : '–') + (held ? ' · ' + (label ?? t('有人控制')) : ''),
  }
}

const cards = computed(() => {
  void E.ui.tick
  const S = E.S
  return S.flights.map((f) => {
    const st = stateAt(f, S.t)
    if (f.kind === 'dog') {
      let pill = !st.inside ? (st.before ? t('记录未开始') : t('记录结束')) : PHASE_LABEL[st.hs >= DOG_WALK_MPS ? 'walk' : 'still']
      let pillKind = !st.inside ? 'out' : st.hs >= DOG_WALK_MPS ? 'air' : ''
      if (st.stale >= 6000) { pill = t('失联 {n} 秒', { n: Math.round(st.stale / 1000) }); pillKind = 'out' }
      return {
        f, st, pill, pillKind, exec: '', dog: dogInfo(f, st.i),
        flown: S.t >= f.t0 ? t('活动 {d}', { d: durStr(Math.min(S.t, f.landT) - f.t0) }) : '',
        dist: S.t >= f.t0 ? t('走了 {d} m', { d: Math.round(st.cum) }) : '',
        bat: isNum(st.bat) ? Math.round(st.bat) : null,
        batKind: st.bat <= f.batCrit ? 'crit' : st.bat <= f.batLow ? 'warn' : '',
      }
    }
    const ph = phaseOf(st.mode)
    const airborne = st.inside && isNum(st.mode) && !GROUND_MODES.has(st.mode)
    let pill = !st.inside ? (st.before ? (S.mode === 'live' ? t('地面待机') : t('记录未开始')) : st.rel < 1 ? t('已降落') : t('记录结束'))
      : S.hideRoute ? PHASE_LABEL[ph] : (MODE[st.mode] ?? (isNum(st.mode) ? t('模式 {code}', { code: st.mode }) : t('无数据')))
    let pillKind = !st.inside ? 'out' : S.hideRoute && ph === 'avoid' ? 'avoid' : airborne ? 'air' : ''
    if (st.stale >= 6000) { pill = t('失联 {n} 秒', { n: Math.round(st.stale / 1000) }); pillKind = 'out' }
    let exec = ''
    if (!S.hideRoute) {
      const ex = lastBefore(f.exec, S.t)
      exec = t('未执行航线')
      if (ex) {
        const lab = EXEC_LABEL[ex.state] ?? ex.state
        exec = (ex.state === 'FLYING' || ex.state === 'AT_WAYPOINT') && ex.idx !== null ? `${lab} ${ex.idx + 1}/${ex.total}` : ex.state === 'PAUSED' ? t('航点 {i}/{n} {state}', { i: ex.idx, n: ex.total, state: lab }) : lab
      }
    }
    const lifted = S.t >= f.liftT
    return {
      f, st, pill, pillKind, exec, dog: null,
      flown: lifted ? (S.t > f.landT ? t('飞行 {d}', { d: durStr(Math.min(S.t, f.landT) - f.liftT) }) : t('已飞 {d}', { d: durStr(Math.min(S.t, f.landT) - f.liftT) })) : '',
      dist: lifted ? t('航程 {d} m', { d: Math.round(st.cum) }) : '',
      bat: isNum(st.bat) ? Math.round(st.bat) : null,
      batKind: st.bat <= f.batCrit ? 'crit' : st.bat <= f.batLow ? 'warn' : '',
    }
  })
})
const compact = computed(() => cards.value.length >= 3)
const seps = computed(() => {
  void E.ui.tick
  const S = E.S, cut = E.mapCutoff()
  return S.pairs.map((p) => ({ p, now: sepAt(p, S.t), min: pairMinAt(p, cut) }))
})

// ---------------------------------------------------------------- feed
const open = ref(true)
const tight = ref(false)
const filter = ref<'all' | 'cmd' | 'warn'>('all')
const logBox = ref<HTMLElement | null>(null)
const listEl = ref<HTMLElement | null>(null)
const rows = computed<LogRow[]>(() => {
  void E.ui.flightsKey; void E.ui.hideRoute; void E.ui.version
  const hide = E.S.hideRoute
  return E.S.flights.flatMap((f) => (hide ? f.plog : f.log)).filter((r) => hide || filter.value === 'all' || (filter.value === 'cmd' ? r.kind === 'cmd' : !!r.lvl)).sort((a, b) => a.t - b.t)
})
const feed = computed(() => {
  void E.ui.tick
  const S = E.S, cut = E.tlCutoff()
  let cur = -1
  const shown = rows.value.filter((r) => r.t <= cut)
  shown.forEach((r, i) => { if (r.t <= S.t) cur = i })
  return { shown, cur, latest: cur >= 0 ? shown[cur]! : null }
})
let userScroll = 0
function onWheel(): void { userScroll = performance.now() }
watch(() => feed.value.cur, async (i) => {
  if (i < 0 || performance.now() - userScroll < 3000 || !listEl.value) return
  const el = listEl.value.children[i] as HTMLElement | undefined
  if (!el) return
  const ol = listEl.value, top = el.offsetTop, h = ol.clientHeight
  if (top < ol.scrollTop + 8 || top > ol.scrollTop + h - 30) ol.scrollTop = Math.max(0, top - h * 0.6)
})
let ro: ResizeObserver | null = null
onMounted(() => {
  // when the rail has no room left for the list, keep one line with the latest entry
  ro = new ResizeObserver(() => { const b = logBox.value; if (b && open.value) tight.value = b.clientHeight < 92 })
  if (logBox.value) ro.observe(logBox.value)
})
onBeforeUnmount(() => ro?.disconnect())
function toggle(): void { if (tight.value) { tight.value = false; open.value = true; return } open.value = !open.value }
</script>

<template>
  <div class="cards">
    <template v-if="!compact">
      <article v-for="c in cards" :key="c.f.id" class="card" :class="{ sel: c.f.id === E.S.sel }" :style="{ '--c': c.f.color }" data-test="watch-card" @click="E.select(c.f.id)">
        <header class="hd">
          <span class="sw" /><span class="lt">{{ c.f.label }}</span><span class="nm">{{ c.f.devName }}</span>
          <span class="sn">{{ c.f.sn ? '…' + c.f.sn.slice(-5) : '' }}</span>
          <span class="pill" :class="c.pillKind">{{ c.pill }}</span>
        </header>
        <div v-if="c.exec" class="exec"><span>{{ c.exec }}</span><span class="k">{{ t('航线 {name}', { name: c.f.routeName }) }}</span></div>
        <div v-if="c.dog" class="gauges dog" data-test="watch-dog-card">
          <div class="g"><span class="gl">{{ t('速度') }}</span><span class="gv"><b>{{ fixed(c.st.hs) }}</b><i>m/s</i></span></div>
          <div class="g"><span class="gl">{{ t('定位') }}</span><span class="gv"><b class="txt">{{ c.dog.fix }}</b></span></div>
          <div class="g"><span class="gl">{{ t('状态') }}</span><span class="gv"><b class="txt">{{ c.dog.state }}</b></span></div>
          <div class="g"><span class="gl">{{ t('在控') }}</span><span class="gv"><b class="txt">{{ c.dog.ctl }}</b></span></div>
          <div class="g dial"><span class="gl">{{ t('朝向') }}</span><span class="gv">
            <svg viewBox="-12 -12 24 24" aria-hidden="true"><circle r="10.5" fill="none" stroke="var(--border)" stroke-width="1" />
              <path d="M0-10.5v2.6M10.5 0H7.9M0 10.5V7.9M-10.5 0h2.6" stroke="var(--text-dim)" stroke-width="1" />
              <g v-if="isNum(c.f.head[c.st.i])" :transform="`rotate(${c.st.head})`"><path d="M0-8 3.6 4.5 0 2.4-3.6 4.5Z" fill="var(--c)" /></g></svg>
            <b>{{ isNum(c.f.head[c.st.i]) ? deg(c.st.head) + '°' : '–' }}</b></span></div>
        </div>
        <div v-else class="gauges">
          <div class="g"><span class="gl">{{ t('高度') }}</span><span class="gv"><b>{{ fixed(c.st.rel) }}</b><i>m</i></span></div>
          <div class="g"><span class="gl">{{ tc('short', '水平速度') }}</span><span class="gv"><b>{{ fixed(c.st.hs) }}</b><i>m/s</i></span></div>
          <div class="g"><span class="gl">{{ tc('short', '垂直速度') }}</span><span class="gv"><b>{{ signed(c.st.vs) }}</b><i>m/s</i></span></div>
          <div class="g"><span class="gl">{{ tc('short', '距起飞点') }}</span><span class="gv"><b>{{ fixed(c.st.home, 0) }}</b><i>m</i></span></div>
          <div class="g dial"><span class="gl">{{ t('朝向') }}</span><span class="gv">
            <svg viewBox="-12 -12 24 24" aria-hidden="true"><circle r="10.5" fill="none" stroke="var(--border)" stroke-width="1" />
              <path d="M0-10.5v2.6M10.5 0H7.9M0 10.5V7.9M-10.5 0h2.6" stroke="var(--text-dim)" stroke-width="1" />
              <g :transform="`rotate(${c.st.gy})`"><path d="M0 0V-9" stroke="var(--text-dim)" stroke-width="1" stroke-dasharray="1.5 1.5" /></g>
              <g :transform="`rotate(${c.st.head})`"><path d="M0-8 3.6 4.5 0 2.4-3.6 4.5Z" fill="var(--c)" /></g></svg>
            <b>{{ deg(c.st.head) }}°</b></span></div>
        </div>
        <div class="bat">
          <span class="gl">{{ t('电量') }}</span><span class="meter" :class="c.batKind"><span :style="{ width: (c.bat ?? 0) + '%' }" /></span><span class="bv">{{ c.bat ?? '–' }}%</span>
          <span class="sub"><span>{{ c.flown }}</span><span>{{ c.dist }}</span><span v-if="!c.dog && isNum(c.st.gps)">{{ t('卫星 {n}', { n: c.st.gps }) }}</span><span v-if="!c.dog && isNum(c.st.wind)">{{ t('风速 {v} m/s', { v: c.st.wind.toFixed(1) }) }}</span></span>
        </div>
      </article>
    </template>
    <template v-else>
      <article v-for="c in cards" :key="c.f.id" class="crow" :class="{ sel: c.f.id === E.S.sel }" :style="{ '--c': c.f.color }" @click="E.select(c.f.id)">
        <span class="sw" /><span class="lt">{{ c.f.label }}</span><span class="pill" :class="c.pillKind">{{ c.pill }}</span>
        <span class="rv"><b>{{ c.dog ? '–' : fixed(c.st.rel) }}</b><i>{{ c.dog ? '' : 'm' }}</i></span><span class="rv"><b>{{ fixed(c.st.hs) }}</b><i>m/s</i></span><span class="rv"><b>{{ c.bat ?? '–' }}</b><i>%</i></span>
      </article>
    </template>
  </div>

  <div v-if="seps.length" class="sepcard" data-test="watch-sep">
    <template v-for="s in seps" :key="s.p.label">
      <div class="sep-row">
        <span class="gl">{{ t('{label} 间距', { label: s.p.label }) }}</span><span class="gv"><b>{{ s.now ? s.now.d.toFixed(1) : '–' }}</b><i>m</i></span>
        <span class="det">{{ s.now ? t('水平 {h} · 高差 {v} m', { h: s.now.dh.toFixed(1), v: Math.abs(s.now.dv).toFixed(1) }) : t('此刻不在同一时段') }}</span>
      </div>
      <button v-if="s.min" class="linkbtn" @click="E.seek(s.min.t)">{{ t('两机都在空中时最近 {d} m · {time}', { d: s.min.d.toFixed(1), time: clockStr(s.min.t) }) }}</button>
    </template>
  </div>

  <section ref="logBox" class="log" :class="{ closed: !open, tight }" :aria-label="t('动态')">
    <div class="log-h" @click="toggle">
      <span class="t">{{ t('动态') }}</span>
      <span class="latest"><template v-if="feed.latest"><span class="num">{{ clockStr(feed.latest.t) }}</span> <b>{{ feed.latest.f.label }}</b> {{ feed.latest.title }}</template><template v-else>{{ t('还没有动态') }}</template></span>
      <div v-if="!E.ui.hideRoute && open && !tight" class="seg" @click.stop>
        <button :aria-pressed="filter === 'all'" @click="filter = 'all'">{{ t('全部') }}</button>
        <button :aria-pressed="filter === 'cmd'" @click="filter = 'cmd'">{{ t('指令') }}</button>
        <button :aria-pressed="filter === 'warn'" @click="filter = 'warn'">{{ t('告警') }}</button>
      </div>
      <button class="chev" :aria-expanded="open && !tight" :aria-label="t('收起或展开动态')" @click.stop="toggle"><svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
    </div>
    <ol ref="listEl" @wheel.passive="onWheel">
      <li v-for="(r, i) in feed.shown" :key="`${r.f.id}-${r.t}-${i}`" :class="[r.lvl, { past: i <= feed.cur, cur: i === feed.cur }]" @click="E.seek(r.t)">
        <time>{{ clockStr(r.t) }}</time>
        <span class="who" :style="{ '--c': r.f.color }"><span class="sw" />{{ r.f.label }}</span>
        <span class="txt"><span v-if="r.kind === 'cmd'" class="kind">{{ t('指令') }}</span><span v-else-if="r.lvl === 'warn'" class="kind">{{ t('告警') }}</span><span v-else-if="r.lvl === 'crit'" class="kind">{{ t('严重') }}</span>{{ r.title }}<span v-if="r.detail" class="d">{{ r.detail }}</span></span>
      </li>
      <li v-if="!feed.shown.length" class="none">{{ t('还没有动态。') }}</li>
    </ol>
  </section>
</template>

<style scoped>
.cards { display: grid; gap: 8px; flex: none; }
.card { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 9px 12px 8px; display: grid; gap: 7px; cursor: pointer; }
.card.sel, .crow.sel { border-color: var(--text-dim); }
.hd { display: flex; align-items: center; gap: 7px; min-width: 0; }
.sw { width: 10px; height: 10px; border-radius: 2px; flex: none; background: var(--c); display: inline-block; }
.lt { font-weight: 600; font-size: 15px; line-height: 1; }
.nm { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.sn { font: 400 10.5px var(--font-num); color: var(--text-dim); white-space: nowrap; }
.pill { margin-left: auto; font-size: 11px; line-height: 1; padding: 4px 7px; border-radius: 3px; background: var(--panel-2); color: var(--text-dim); white-space: nowrap; border: 1px solid var(--border); }
.pill.air { background: color-mix(in srgb, var(--c) 16%, var(--panel)); border-color: color-mix(in srgb, var(--c) 40%, var(--panel)); color: var(--text); }
.pill.avoid { background: color-mix(in srgb, var(--warn) 18%, var(--panel)); border-color: color-mix(in srgb, var(--warn) 45%, var(--panel)); color: var(--text); }
.pill.out { background: none; border-style: dashed; }
.exec { font-size: 12px; color: var(--text-dim); display: flex; gap: 8px; align-items: baseline; min-width: 0; }
.exec span:first-child { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; color: var(--text); }
.exec .k { margin-left: auto; flex: none; font-size: 11px; }
.gauges { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px 8px; }
.g { display: grid; gap: 1px; min-width: 0; }
.gl { font-size: 11px; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gv { display: flex; align-items: baseline; gap: 3px; white-space: nowrap; }
.gv b { font: 500 16px/1.15 var(--font-num); letter-spacing: -.02em; }
.gv i { font: 400 10.5px var(--font-num); color: var(--text-dim); font-style: normal; }
.dial .gv { align-items: center; gap: 5px; }
.dial svg { width: 20px; height: 20px; flex: none; overflow: visible; }
/* a dog's words (GNSS fix, state, control) are text, not numbers */
.gv b.txt { font: 500 12.5px/1.3 var(--font-ui); letter-spacing: 0; overflow: hidden; text-overflow: ellipsis; }
.gauges.dog .g { min-width: 0; }
.gauges.dog .gv { overflow: hidden; }
.bat { display: grid; grid-template-columns: auto minmax(40px, 1fr) auto; gap: 3px 8px; align-items: center; font-size: 11.5px; }
.meter { height: 5px; border-radius: 2px; background: var(--panel-3); overflow: hidden; }
.meter span { display: block; height: 100%; background: var(--text-dim); border-radius: 2px; }
.meter.warn span { background: var(--warn); }
.meter.crit span { background: var(--danger); }
.bv { font: 500 12px var(--font-num); white-space: nowrap; }
.sub { grid-column: 1 / -1; color: var(--text-dim); font: 400 11px var(--font-num); display: flex; gap: 4px 12px; flex-wrap: wrap; }
.crow { display: grid; grid-template-columns: auto auto minmax(0, 1fr) repeat(3, auto); gap: 0 10px; align-items: center; background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; cursor: pointer; }
.crow .lt { font-size: 13px; }
.crow .pill { margin-left: 0; justify-self: start; }
.rv { display: flex; align-items: baseline; gap: 2px; justify-content: flex-end; min-width: 52px; }
.rv b { font: 500 13px var(--font-num); }
.rv i { font: 400 10px var(--font-num); color: var(--text-dim); font-style: normal; }
.sepcard { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 6px 12px; display: grid; gap: 1px; flex: none; }
.sep-row { display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }
.sep-row .gv b { font-size: 15px; }
.det { font: 400 11px var(--font-num); color: var(--text-dim); margin-left: auto; }
.linkbtn { border: 0; background: none; padding: 0; color: var(--text-dim); font-size: 11px; text-decoration: underline; text-decoration-color: var(--border); text-underline-offset: 3px; cursor: pointer; text-align: left; }
.linkbtn:hover { color: var(--text); }
.log { flex: 1 1 0; min-height: 36px; background: var(--panel); border: 1px solid var(--border); border-radius: 4px; display: flex; flex-direction: column; min-width: 0; }
.log.closed { flex: none; }
.log-h { display: flex; align-items: center; gap: 8px; padding: 6px 8px 6px 10px; cursor: pointer; user-select: none; }
.log:not(.closed):not(.tight) .log-h { border-bottom: 1px solid var(--border); }
.t { font-weight: 600; font-size: 12px; color: var(--text-dim); flex: none; }
.latest { min-width: 0; flex: 1; font-size: 11.5px; color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.latest b { color: var(--text); font-weight: 500; }
.log:not(.closed):not(.tight) .latest { visibility: hidden; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; flex: none; }
.seg button { border: 0; background: none; height: 22px; padding: 0 8px; font-size: 11.5px; color: var(--text-dim); cursor: pointer; }
.seg button + button { border-left: 1px solid var(--border); }
.seg button[aria-pressed='true'] { background: var(--text); color: var(--bg); }
.chev { width: 22px; height: 22px; border: 0; background: none; color: var(--text-dim); display: grid; place-items: center; cursor: pointer; flex: none; padding: 0; }
.chev svg { width: 12px; height: 12px; transition: transform .15s; }
.log.closed .chev svg, .log.tight .chev svg { transform: rotate(-90deg); }
.log.closed ol, .log.tight ol { display: none; }
ol { list-style: none; margin: 0; padding: 4px 0; overflow: auto; flex: 1; min-height: 0; }
li { display: grid; grid-template-columns: 58px 30px minmax(0, 1fr); gap: 0 6px; padding: 3px 10px; cursor: pointer; opacity: .42; align-items: baseline; }
li.past { opacity: 1; }
li.cur, li:hover { background: var(--panel-2); opacity: 1; }
time { font: 400 11px var(--font-num); color: var(--text-dim); }
.who { display: flex; align-items: center; gap: 4px; font-weight: 600; font-size: 11.5px; }
.who .sw { width: 7px; height: 7px; }
.txt { min-width: 0; font-size: 12px; line-height: 1.4; }
.txt .d { display: block; color: var(--text-dim); font-size: 11.5px; overflow-wrap: anywhere; }
.kind { font-size: 10px; color: var(--text-dim); border: 1px solid var(--border); border-radius: 2px; padding: 0 3px; margin-right: 5px; }
li.warn .kind { border-color: transparent; color: #241a00; background: var(--warn); }
li.crit .kind { border-color: transparent; color: #fff; background: var(--danger); }
li.none { display: block; color: var(--text-dim); font-size: 12px; cursor: default; opacity: 1; padding: 12px; }
</style>
