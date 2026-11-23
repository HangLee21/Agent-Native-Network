<script setup lang="ts">
/**
 * 监视台 (docs/demo-redesign/monitor-station-design.md): an audience page that follows the flights live and replays
 * flight records. Large area: the map (tilt up to the prototype's 斜视, rotate, auto-rotate) or a video swapped in;
 * right rail: videos in the configured order, readings, separation, feed; bottom: the time strip.
 * No control buttons. The shared setting 「只显示已经飞过的轨迹」 (default on) hides everything about routes.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { dateLocale, isEn, t } from '@/i18n'
import { useFleetStore } from '@/stores/fleet'
import { useHistoryStore } from '@/stores/history'
import { useSystemStore } from '@/stores/system'
import { useTelemetryStore } from '@/stores/telemetry'
import { OUTCOME_LABELS } from '@/api/history'
import { dateTime, duration } from '@/utils/format'
import type { RecordOption } from './watch/engine'
import { createWatchEngine } from './watch/engine'
import WatchMap from './watch/WatchMap.vue'
import WatchVideo from './watch/WatchVideo.vue'
import WatchDogVideo from './watch/WatchDogVideo.vue'
import WatchCards from './watch/WatchCards.vue'
import WatchTimeline from './watch/WatchTimeline.vue'
import GroupThumb from './watch/GroupThumb.vue'
import { clockStr, durStr, hmStr } from './watch/timeline'

const fleet = useFleetStore()
const system = useSystemStore()
const route = useRoute()
const E = createWatchEngine(fleet, (sn) => useHistoryStore(sn).currentId)
const ui = E.ui

const root = ref<HTMLElement | null>(null)
const mapRef = ref<InstanceType<typeof WatchMap> | null>(null)
const tlRef = ref<InstanceType<typeof WatchTimeline> | null>(null)
const pop = ref<'' | 'rec' | 'align'>('')
const fullscreen = ref(false)

// ---------------------------------------------------------------- devices and video order
interface Tile { key: string; label: string; color: string; flight: (typeof E.S.flights)[number] }
const tiles = computed<Tile[]>(() => {
  void ui.flightsKey; void ui.tick
  const list = E.S.flights.map((f) => ({ key: f.input.gatewaySn, label: f.label, color: f.color, flight: f }))
  const order = ui.videoOrder
  const rank = (k: string) => { const i = order.indexOf(k); return i < 0 ? 1000 : i }
  return list.sort((a, b) => rank(a.key) - rank(b.key) || a.label.localeCompare(b.label))
})
const tileKeys = computed(() => tiles.value.map((x) => x.key).join(','))
watch(tileKeys, () => { if (ui.mainKey !== 'map' && !tiles.value.some((x) => x.key === ui.mainKey)) ui.mainKey = 'map' })
const slotSel = (k: string) => `[data-wslot="${k}"]`
const mapTarget = computed(() => (ui.mainKey === 'map' ? '#watch-main' : slotSel(ui.mainKey)))
const videoTarget = (k: string) => (ui.mainKey === k ? '#watch-main' : slotSel(k))
function enlarge(k: string): void { ui.mainKey = k }
function restoreMap(): void { ui.mainKey = 'map' }

// ---------------------------------------------------------------- live data
function syncLive(): void {
  if (ui.mode !== 'live') return
  const devs = fleet.enabled
  E.syncLive(devs)
  for (const d of devs) E.seedTelemetry(d.gatewaySn, useTelemetryStore(d.gatewaySn).drone)
}
// devices, their open records, and the first telemetry of each (a drone on the ground has no record yet)
watch(() => [fleet.enabled.map((d) => `${d.gatewaySn}:${d.label}:${d.color}`).join(','), ...fleet.enabled.map((d) => useHistoryStore(d.gatewaySn).currentId),
  ...fleet.enabled.map((d) => !!useTelemetryStore(d.gatewaySn).drone)], syncLive)

// ---------------------------------------------------------------- header
const live = computed(() => ui.mode === 'live')
/** A fresh shallow copy each tick: the engine state is a plain object, so the same reference would not re-render. */
const S = computed(() => { void ui.tick; return { ...E.S } })
const sub = computed(() => {
  void ui.tick
  // with dogs (D-40) the count is of devices, not drones
  const dogs = E.S.flights.some((f) => f.kind === 'dog')
  if (live.value) {
    const labels = E.S.flights.map((f) => f.label).join(isEn() ? ', ' : '、'), n = E.S.flights.length
    return n ? (dogs ? t('实时 · {labels} 共 {n} 台', { labels, n }) : t('实时 · {labels} 共 {n} 架', { labels, n })) : t('实时 · 还没有飞机在线')
  }
  const fl = E.S.flights
  const date = new Date(E.S.full[0]).toLocaleDateString(dateLocale()), time = hmStr(E.S.refLift)
  return fl.length
    ? (dogs ? t('回放 · {date} {time} · {n} 台', { date, time, n: fl.length }) : t('回放 · {date} {time} · {n} 架', { date, time, n: fl.length }))
    : t('回放')
})
const ended = computed(() => { void ui.tick; return E.S.flights.length > 0 && E.S.flights.every((f) => isFinite(f.landT) && E.S.now > f.landT + 3000) })
/**
 * Picker rows: flights that overlap in time (`together`, D-33) form one row, picked with one click. Time and duration
 * are the same as on the 飞行记录 page: take-off (else record start) to landing.
 */
interface RecGroup { key: string; ids: string[]; members: RecordOption[]; takeoff: number; seconds: number | null; video: boolean; open: boolean; simulated: boolean }
const groups = computed<RecGroup[]>(() => {
  const byId = new Map(ui.records.map((r) => [r.s.id, r]))
  const seen = new Set<string>()
  const out: RecGroup[] = []
  for (const r of ui.records) {
    if (seen.has(r.s.id)) continue
    const ids = [r.s.id, ...(r.s.together ?? []).map((x) => x.id)]
    ids.forEach((id) => seen.add(id))
    const members = ids.map((id) => byId.get(id)).filter((m): m is RecordOption => !!m).sort((a, b) => a.label.localeCompare(b.label))
    const from = Math.min(...members.map((m) => m.s.takeoffAt ?? m.s.startedAt))
    const ends = members.map((m) => m.s.landedAt ?? m.s.endedAt)
    const to = ends.every((e) => e) ? Math.max(...(ends as number[])) : null
    out.push({ key: ids.join(','), ids, members, takeoff: from, seconds: to ? (to - from) / 1000 : null,
      video: members.some((m) => m.s.videoStatus === 'READY'), open: members.some((m) => m.s.status === 'OPEN'), simulated: members.some((m) => m.s.simulated) })
  }
  return out
})
const isPicked = (g: RecGroup) => g.ids.length === ui.selectedIds.length && g.ids.every((id) => ui.selectedIds.includes(id))
/** Row chosen in the picker; nothing loads until 确认 (or 假装实时). */
const pendingKey = ref<string | null>(null)
const pending = computed(() => groups.value.find((g) => g.key === pendingKey.value) ?? null)
function openPicker(): void {
  if (pop.value === 'rec') { pop.value = ''; return }
  pop.value = 'rec'
  pendingKey.value = groups.value.find(isPicked)?.key ?? null
  void E.loadRecords()
}
function confirmPick(): void { const g = pending.value; if (!g) return; pop.value = ''; void E.loadReplay(g.ids) }
function fakeLive(): void { const g = pending.value; if (!g) return; pop.value = ''; void E.startFakeLive(g.ids).then(() => tlRef.value?.invalidate()) }
function toggleRecord(id: string, on: boolean): void {
  const ids = new Set(ui.selectedIds)
  if (on) ids.add(id); else ids.delete(id)
  if (!ids.size) return
  void E.loadReplay([...ids])
}
function removeFlight(id: string): void { toggleRecord(id, false) }
function setMode(m: 'live' | 'replay'): void {
  E.setMode(m)
  if (m === 'live') syncLive()
  else if (!ui.records.length) void E.loadRecords()
  tlRef.value?.invalidate()
}
/** Opens the 监视台 in its own window (same one on repeated clicks), e.g. to drag onto the audience screen. */
const inWindow = computed(() => route.query.window === '1')
function openWindow(): void {
  const url = `${location.origin}${location.pathname}#/watch?window=1`
  const w = window.open(url, 'uav-watch', 'popup=yes,width=1600,height=900')
  w?.focus()
}
function toggleFull(): void {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void root.value?.requestFullscreen?.()
}
function onFullChange(): void { fullscreen.value = !!document.fullscreenElement }
function onDocClick(e: MouseEvent): void { if (!(e.target as HTMLElement).closest('.hpop, .hpopbtn')) pop.value = '' }
function onKey(e: KeyboardEvent): void {
  const t = e.target as HTMLElement
  if (t.closest('input, select, textarea')) return
  if (e.key === 'Escape') { pop.value = ''; if (ui.mainKey !== 'map') restoreMap(); return }
  if (t.closest('button') && (e.key === ' ' || e.key === 'Enter')) return
  if (e.key === ' ') { e.preventDefault(); E.togglePlay() }
  else if (e.key === 'ArrowRight') { e.preventDefault(); E.seek(E.S.t + (e.shiftKey ? 1000 : 5000)) }
  else if (e.key === 'ArrowLeft') { e.preventDefault(); E.seek(E.S.t - (e.shiftKey ? 1000 : 5000)) }
}

// ---------------------------------------------------------------- frame loop
let raf = 0
let last = performance.now()
function frame(now: number): void {
  const dt = Math.min(400, now - last)
  last = now
  const moved = E.step(now, dt)
  mapRef.value?.frame(dt, moved)
  tlRef.value?.frame(now, moved)
  raf = requestAnimationFrame(frame)
}
watch(() => system.theme, () => { setTimeout(() => { mapRef.value?.applyTheme(); tlRef.value?.applyTheme() }, 0) })
watch(() => [ui.hideRoute, ui.flightsKey], () => { tlRef.value?.invalidate(); mapRef.value?.repaint() })

onMounted(async () => {
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
  document.addEventListener('fullscreenchange', onFullChange)
  E.startLive()
  void E.loadSettings()
  const ids = typeof route.query.ids === 'string' ? route.query.ids.split(',').filter(Boolean) : []
  if (ids.length) { E.setMode('replay'); void E.loadRecords(); void E.loadReplay(ids) }
  else syncLive()
  raf = requestAnimationFrame(frame)
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  E.stop()
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
  document.removeEventListener('fullscreenchange', onFullChange)
})
</script>

<template>
  <div ref="root" class="watch" :class="{ full: fullscreen }" data-test="watch-page">
    <header class="top">
      <div class="brand">
        <svg viewBox="0 0 26 26" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.4"><rect x="1.5" y="1.5" width="23" height="23" rx="2.5" stroke-opacity=".35" /><path d="M5 19.5 L9 12 L14 15 L20.5 6.5" stroke-linecap="round" stroke-linejoin="round" /><path d="M5 21.5 H21" stroke-opacity=".35" stroke-dasharray="1.5 2" /><circle cx="20.5" cy="6.5" r="1.9" fill="currentColor" stroke="none" /></svg>
        <div><div class="bn">{{ t('监视台') }}</div><div class="bs">{{ sub }}</div></div>
      </div>
      <div class="seg lg" role="group" :aria-label="t('实时或回放')">
        <button :aria-pressed="live" data-test="watch-mode-live" @click="setMode('live')"><span class="ld" />{{ t('实时') }}</button>
        <button :aria-pressed="!live" data-test="watch-mode-replay" @click="setMode('replay')">{{ t('回放') }}</button>
      </div>
      <template v-if="!live">
        <div class="popwrap">
          <button class="btn btn-sm hpopbtn" data-test="watch-pick" @click="openPicker">{{ t('选择记录') }}</button>
          <div v-if="pop === 'rec'" class="hpop rec" data-test="watch-records">
            <b>{{ t('记录 · 开始时间和时长同「记录」页') }}</b>
            <div class="reclist">
            <button v-for="g in groups" :key="g.key" class="recrow" :class="{ on: pendingKey === g.key, cur: isPicked(g), short: g.seconds !== null && g.seconds < 10 }"
              :aria-pressed="pendingKey === g.key" @click="pendingKey = g.key" @dblclick="pendingKey = g.key; confirmPick()">
              <GroupThumb class="th" :tracks="g.members.map((m) => ({ points: m.s.trackPreview, color: m.color }))" />
              <span class="who"><template v-for="m in g.members" :key="m.s.id"><span class="sw" :style="{ '--c': m.color }" /><b>{{ m.label }}</b></template></span>
              <span class="num">{{ dateTime(g.takeoff) }}</span>
              <span class="num dim">{{ g.seconds === null ? t('记录中') : duration(g.seconds) }}</span>
              <span class="tags">
                <span v-if="g.video" class="tag">{{ t('有视频') }}</span>
                <span v-if="g.simulated" class="tag">{{ t('模拟') }}</span>
                <span v-if="isPicked(g)" class="tag">{{ t('正在回放') }}</span>
                <span v-if="!ui.hideRoute && g.members.some((m) => m.kind !== 'dog')" class="routes">{{ g.members.filter((m) => m.kind !== 'dog').map((m) => m.s.routeName ?? t('无航线')).join(' · ') }}</span>
              </span>
            </button>
            </div>
            <span v-if="!groups.length" class="dim">{{ t('还没有记录') }}</span>
            <span class="dim">{{ t('同一时段的飞机和狗在同一行。选好后点「确认」回放；「假装实时」按实时的样子从起飞前开始播，时间显示成现在。只想看其中一台，回放时在上面的标签上点 ×。') }}</span>
            <div class="recbar">
              <button class="btn btn-sm" @click="pop = ''">{{ t('取消') }}</button>
              <span class="grow" />
              <button class="btn btn-sm" :disabled="!pending" data-test="watch-fake-live" @click="fakeLive">{{ t('假装实时') }}</button>
              <button class="btn btn-sm btn-primary" :disabled="!pending" data-test="watch-pick-confirm" @click="confirmPick">{{ t('确认') }}</button>
            </div>
          </div>
        </div>
        <div class="chips">
          <div v-for="f in S.flights" :key="f.id" class="chip" :style="{ '--c': f.color }" data-test="watch-chip">
            <span class="sw" /><b>{{ f.label }}</b>
            <span v-if="!ui.hideRoute" class="nm">{{ f.routeName }}</span>
            <span class="meta">{{ new Date(f.t0).toLocaleDateString(dateLocale(), { month: '2-digit', day: '2-digit' }) }} {{ hmStr(isFinite(f.liftT) ? f.liftT : f.t0) }} · {{ durStr((isFinite(f.landT) ? f.landT : f.t1) - (isFinite(f.liftT) ? f.liftT : f.t0)) }}</span>
            <span v-if="!ui.hideRoute && f.input.detail?.outcome" class="tag">{{ OUTCOME_LABELS[f.input.detail.outcome] ?? f.input.detail.outcome }}</span>
            <button v-if="S.flights.length > 1" class="x" :aria-label="t('不回放 {label}', { label: f.label })" @click="removeFlight(f.id)">×</button>
          </div>
        </div>
      </template>
      <span class="grow" />
      <div v-if="live" class="clock">
        <span class="livedot" :class="{ rev: ui.reviewing, ended: !ui.reviewing && ended }">{{ ui.reviewing ? t('回看中') : ended ? t('全部已降落') : t('实时') }}</span>
        <span class="m">{{ clockStr(S.t) }}</span>
        <span class="s">{{ ui.reviewing ? t('此刻 {time}', { time: clockStr(S.now) }) : t('北京时间') }}</span>
      </div>
      <div v-else class="popwrap">
        <button class="btn btn-sm hpopbtn" @click="pop = pop === 'align' ? '' : 'align'">{{ S.align === 'abs' ? t('同一时钟') : t('起飞对齐') }} · {{ S.scene.clock === 'device' ? t('机载时间') : t('平台接收') }}</button>
        <div v-if="pop === 'align'" class="hpop align">
          <b>{{ t('多条记录怎么对齐') }}</b>
          <div class="seg"><button :aria-pressed="S.align === 'abs'" @click="E.setAlign('abs')">{{ t('同一时钟') }}</button><button :aria-pressed="S.align === 'takeoff'" @click="E.setAlign('takeoff')">{{ t('起飞时刻对齐') }}</button></div>
          <b>{{ t('位置点用哪个时间戳') }}</b>
          <div class="seg"><button :aria-pressed="S.scene.clock === 'device'" @click="E.setClock('device')">{{ t('机载时间') }}</button><button :aria-pressed="S.scene.clock === 'server'" @click="E.setClock('server')">{{ t('平台接收时间') }}</button></div>
        </div>
      </div>
      <button v-if="!inWindow" class="btn btn-sm" :title="t('在新窗口打开监视台（不带平台顶栏），可以拖到观众屏上再全屏')" data-test="watch-new-window" @click="openWindow">{{ t('新窗口') }}</button>
      <button class="btn btn-sm" :title="fullscreen ? t('退出全屏') : t('全屏（给观众大屏用）')" data-test="watch-fullscreen" @click="toggleFull">{{ fullscreen ? t('退出全屏') : t('全屏') }}</button>
    </header>

    <section id="watch-main" class="main">
      <div v-if="!S.flights.length" class="empty">
        <b>{{ live ? t('还没有在线的飞机') : (ui.loading ? t('正在加载记录…') : (ui.error ?? t('选择一条记录回放'))) }}</b>
        <span v-if="live">{{ t('飞机或有定位的狗上线后，这里显示它的位置、轨迹和视频。') }}</span>
      </div>
    </section>

    <aside class="rail" :aria-label="t('视频与读数')">
      <div class="videos" :class="{ grid2: tiles.length >= 3 }">
        <div v-for="tile in tiles" :key="tile.key" class="slot" :data-wslot="tile.key" />
      </div>
      <WatchCards :engine="E" />
    </aside>

    <WatchTimeline ref="tlRef" class="time" :engine="E" />

    <Teleport defer :to="mapTarget">
      <WatchMap ref="mapRef" :engine="E" :small="ui.mainKey !== 'map'" @restore="restoreMap" />
    </Teleport>
    <Teleport v-for="tile in tiles" :key="tile.key" defer :to="videoTarget(tile.key)">
      <WatchDogVideo v-if="tile.flight.kind === 'dog'" :engine="E" :dog-id="tile.key" :label="tile.label" :color="tile.color" :flight="tile.flight" :big="ui.mainKey === tile.key" @enlarge="enlarge(tile.key)" @restore="restoreMap" />
      <WatchVideo v-else :engine="E" :gateway-sn="tile.key" :label="tile.label" :color="tile.color" :flight="tile.flight" :big="ui.mainKey === tile.key" @enlarge="enlarge(tile.key)" @restore="restoreMap" />
    </Teleport>
  </div>
</template>

<style scoped>
.watch {
  box-sizing: border-box; height: 100%;
  display: grid; gap: 8px;
  grid-template-columns: minmax(0, 1fr) clamp(340px, 27vw, 520px);
  grid-template-rows: auto minmax(0, 1fr) auto;
  grid-template-areas: "top top" "main rail" "time rail";
  padding: 10px 16px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
}
.watch.full { padding: 12px 18px; }
.top { grid-area: top; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; min-width: 0; }
.brand { display: flex; align-items: center; gap: 10px; margin-right: 4px; }
.brand svg { width: 26px; height: 26px; flex: none; }
.bn { font-weight: 600; font-size: 15px; line-height: 1.1; letter-spacing: .02em; }
.bs { font-size: 11px; color: var(--text-dim); margin-top: 2px; white-space: nowrap; }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 4px; background: var(--panel); overflow: hidden; }
.seg button { border: 0; background: none; height: 26px; padding: 0 9px; font-size: 12px; color: var(--text-dim); cursor: pointer; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
.seg button + button { border-left: 1px solid var(--border); }
.seg button[aria-pressed='true'] { background: var(--text); color: var(--bg); }
.seg.lg button { height: 30px; padding: 0 12px; font-size: 12.5px; }
.ld { width: 7px; height: 7px; border-radius: 50%; background: var(--danger); }
.chips { display: flex; gap: 6px; flex-wrap: wrap; min-width: 0; }
.chip { display: inline-flex; align-items: center; gap: 8px; height: 32px; padding: 0 4px 0 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel); }
.chip .nm { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 120px; }
.meta { font: 400 11px var(--font-num); color: var(--text-dim); white-space: nowrap; }
.tag { font-size: 10.5px; color: var(--text-dim); border: 1px solid var(--border); border-radius: 2px; padding: 0 4px; }
.x { width: 22px; height: 22px; border: 0; background: none; color: var(--text-dim); cursor: pointer; border-radius: 2px; }
.x:hover { background: var(--panel-2); color: var(--text); }
.sw { width: 10px; height: 10px; border-radius: 2px; flex: none; background: var(--c); display: inline-block; }
.grow { flex: 1; }
.popwrap { position: relative; }
.hpop { position: absolute; top: calc(100% + 6px); z-index: 40; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); padding: 12px; display: grid; gap: 8px; }
.hpop.rec { left: 0; width: 460px; }
.hpop.align { right: 0; width: 280px; }
.hpop > b { font-size: 12px; color: var(--text-dim); }
.reclist { display: grid; gap: 2px; max-height: 46vh; overflow: auto; margin: 0 -4px; padding: 0 4px; }
.recbar { display: flex; gap: 8px; align-items: center; border-top: 1px solid var(--border); padding-top: 10px; }
.recrow .th { grid-row: span 2; }
.recrow.cur:not(.on) { border-color: var(--border); }
.recrow { display: grid; grid-template-columns: 72px 74px minmax(0, 1fr) auto; gap: 2px 10px; align-items: center; padding: 6px 8px; border: 1px solid transparent; border-radius: 4px; background: none; color: var(--text); cursor: pointer; font-size: 12.5px; text-align: left; }
.recrow:hover { background: var(--panel-2); }
.recrow.on { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, transparent); }
.recrow.short { opacity: .55; }
.recrow .who { display: inline-flex; align-items: center; gap: 4px; }
.recrow .who b + .sw { margin-left: 4px; }
.recrow .tags { grid-column: 3 / -1; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.recrow .tags:empty { display: none; }
.recrow .routes { font-size: 11.5px; color: var(--text-dim); }
.dim { color: var(--text-dim); font-size: 12px; line-height: 1.5; }
.clock { display: flex; align-items: center; gap: 10px; }
.clock .m { font: 500 20px var(--font-num); }
.clock .s { font: 400 11px var(--font-num); color: var(--text-dim); }
.livedot { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 12px; color: var(--danger); }
.livedot::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); animation: pulse 1.6s ease-in-out infinite; }
.livedot.rev { color: var(--warn); }
.livedot.rev::before { background: var(--warn); animation: none; }
.livedot.ended { color: var(--text-dim); }
.livedot.ended::before { background: var(--text-dim); animation: none; }
@keyframes pulse { 50% { opacity: .35; } }
.main { grid-area: main; position: relative; min-height: 260px; }
.empty { position: absolute; inset: 0; z-index: 8; display: grid; place-content: center; text-align: center; gap: 6px; pointer-events: none; background: color-mix(in srgb, var(--bg) 70%, transparent); }
.empty b { font-size: 16px; font-weight: 600; }
.empty span { color: var(--text-dim); }
.rail { grid-area: rail; display: flex; flex-direction: column; gap: 8px; min-height: 0; min-width: 0; overflow-y: auto; overscroll-behavior: contain; }
.videos { display: grid; gap: 8px; grid-template-columns: minmax(0, 1fr); flex: none; }
.videos.grid2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.slot { position: relative; aspect-ratio: 16 / 9; }
.time { grid-area: time; }
@media (max-width: 980px) {
  .watch { height: auto; grid-template-columns: minmax(0, 1fr); grid-template-rows: auto; grid-template-areas: "top" "main" "rail" "time"; }
  .main { height: 60vh; min-height: 340px; }
}
@media (prefers-reduced-motion: reduce) { .livedot::before { animation: none; } }
</style>
