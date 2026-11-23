<script setup lang="ts">
/**
 * Records replayed together (D-33, D-40; ui-design.md 2.6.1, 2.7.1): drones' flights and dogs' records that overlap
 * in time, in any combination, on one map and one time axis; also a single dog record (a dog has no other replay).
 * One cursor drives the map, the side panel, the timeline and the video (one device at a time). The separation and
 * the proximity alarm are shown only with two drones. Keyboard as in the single replay: Space play/pause, ←/→ 1 s
 * (Shift 10 s), [ / ] previous / next event. Per-flight actions (save as route, export, protect, delete, video offset)
 * stay on the single flight replay.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import JointReplayOverlays, { type JointLayers } from '@/components/history/JointReplayOverlays.vue'
import JointTimeline from '@/components/history/JointTimeline.vue'
import JointSidePanel from '@/components/history/JointSidePanel.vue'
import { ApiError } from '@/api/http'
import { historyApi, OUTCOME_LABELS } from '@/api/history'
import { DOG_OUTCOME_LABELS, dogName, type DogOutcome } from '@/api/dogRecords'
import { useFleetStore } from '@/stores/fleet'
import { dateTime, time } from '@/utils/format'
import { elapsed, nextTime, prevTime, videoAt } from '@/utils/replay'
import {
  DOG_TRACK_COLORS, TRACK_COLORS, axis, buildTrack, dronePair, jointJumpTimes, loadDogTrack, mergedItems, position, proximitySpans, separationAt,
  separationSeries, trackState, within, type Track,
} from '@/utils/jointReplay'
import { parseRefs, togetherPath, type RecordRef } from '@/utils/records'
import type { LatLon } from '@/utils/coord'
import { t, tc } from '@/i18n'

const route = useRoute()
const router = useRouter()
const fleet = useFleetStore()
const refs = computed<RecordRef[]>(() => parseRefs(String(route.query.ids ?? '')))

const tracks = ref<Track[]>([])
const error = ref<string | null>(null)
const loading = ref(true)

async function load(keepCursor = false): Promise<void> {
  if (refs.value.length < 1) {
    error.value = t('没有要回放的记录')
    loading.value = false
    return
  }
  try {
    let dogN = 0
    const loaded = await Promise.all(refs.value.map(async (r, i) => {
      if (r.kind === 'dog') return loadDogTrack(r.id, DOG_TRACK_COLORS[dogN++ % DOG_TRACK_COLORS.length]!, dogName)
      const id = r.id
      const [d, s, e, c] = await Promise.all([historyApi.get(id), historyApi.samples(id), historyApi.events(id), historyApi.commands(id)])
      const dev = fleet.byGateway(d.gatewaySn ?? d.droneSn)
      const label = dev?.label ?? d.droneSn ?? t('飞机 {n}', { n: i + 1 })
      const color = dev?.color && !dev.color.startsWith('var(') ? dev.color : TRACK_COLORS[i % TRACK_COLORS.length]!
      return buildTrack(id, label, color, d, s, e, c)
    }))
    // earliest start first, so the first drone is the one that went up first
    tracks.value = loaded.sort((a, b) => (a.detail.takeoffAt ?? a.detail.startedAt) - (b.detail.takeoffAt ?? b.detail.startedAt))
    if (!keepCursor) cursor.value = Math.min(...tracks.value.map((t) => t.detail.takeoffAt ?? Infinity), range.value.end)
    error.value = null
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('加载失败')
  } finally {
    loading.value = false
  }
}

const range = computed(() => axis(tracks.value))
const start = computed(() => range.value.start)
const end = computed(() => range.value.end)
const cursor = ref(0)
const takeoff = computed(() => Math.min(...tracks.value.map((t) => t.detail.takeoffAt ?? Infinity), start.value))

const states = computed(() => tracks.value.map((t) => trackState(t, cursor.value)))
const spans = computed(() => proximitySpans(tracks.value))
const alarm = computed(() => within(spans.value, cursor.value))
/** Separation and proximity alarm: between the first two drones, only when there are two. */
const pair = computed(() => dronePair(tracks.value))
const drones = computed(() => tracks.value.filter((tr) => tr.kind === 'drone').length)
const dogRouteOptions = computed(() => tracks.value.flatMap((track) => track.dogRoutes.map((plan) => ({
  ...plan, label: t('{name} · 第 {n} 次 · {time} · {count} 个点', {
    name: track.label, n: plan.number, time: time(plan.start), count: plan.points.length,
  }),
}))).sort((a, b) => a.start - b.start))
const selectedDogRoute = ref('')
watch(dogRouteOptions, (options) => {
  if (!options.some((plan) => plan.id === selectedDogRoute.value)) selectedDogRoute.value = ''
})
const separation = computed(() => (pair.value ? separationAt(pair.value[0], pair.value[1], cursor.value) : null))
const series = computed(() => (pair.value ? separationSeries(pair.value[0], pair.value[1], start.value, end.value) : []))
const items = computed(() => mergedItems(tracks.value))
const jumps = computed(() => jointJumpTimes(tracks.value))

const link = computed(() => {
  const s = separation.value
  const p = pair.value
  if (!p) return null
  const a = position(states.value[tracks.value.indexOf(p[0])] ?? null)
  const b = position(states.value[tracks.value.indexOf(p[1])] ?? null)
  if (!s || !a || !b) return null
  const v = s.verticalM === null ? t('高度差未知') : t('高度差 {n} m', { n: Math.round(s.verticalM) })
  return { a, b, text: t('水平 {m} m · {v}', { m: Math.round(s.horizontalM), v }), alarm: alarm.value }
})

/** Every record overlaps at least one other in time (take-off to landing); otherwise the page says so. */
const overlapping = computed(() => {
  if (tracks.value.length < 2) return true
  const w = tracks.value.map((t) => [t.detail.takeoffAt ?? t.detail.startedAt, t.detail.landedAt ?? t.detail.endedAt ?? Date.now()] as const)
  return w.every((a, i) => w.some((b, j) => j !== i && a[0] < b[1] && b[0] < a[1]))
})

/** Takes one record out of the replay (at least one stays). */
function without(tr: Track): void {
  const rest = refs.value.filter((r) => !(r.id === tr.id && r.kind === tr.kind))
  if (rest.length) void router.replace(togetherPath(rest))
}
function outcomeLabel(tr: Track): string | null {
  const o = tr.detail.outcome as string | null
  if (!o) return null
  return tr.kind === 'dog' ? DOG_OUTCOME_LABELS[o as DogOutcome] ?? o : OUTCOME_LABELS[o as keyof typeof OUTCOME_LABELS] ?? o
}
function openAlone(tr: Track): void {
  if (tr.kind === 'drone') void router.push(`/history/${tr.id}`)
  else void router.push(togetherPath([{ kind: 'dog', id: tr.id }]))
}

const fit = computed<LatLon[]>(() => tracks.value.flatMap((t) => [
  ...t.filled.filter((s) => s.lat !== null && s.lon !== null).map((s) => ({ lat: s.lat!, lon: s.lon! })),
  ...(t.detail.routeSnapshot?.waypoints.map((w) => ({ lat: w.lat, lon: w.lon })) ?? []),
  ...t.dogRoutes.flatMap((plan) => plan.points),
]))
const mapCenter = computed(() => fit.value[0] ?? null)
const hasPositions = computed(() => fit.value.length > 0)

const layers = ref<JointLayers>({ track: true, route: true, dogRoute: true, pins: true, link: true })

// ------------------------------------------------------------------ playback (as the single replay)

const playing = ref(false)
const speed = ref(4)
const SPEEDS = [1, 4, 16, 64]
let raf = 0
let lastFrame = 0

function frame(now: number): void {
  if (!playing.value) return
  const dt = lastFrame ? now - lastFrame : 0
  lastFrame = now
  cursor.value = Math.min(end.value, cursor.value + dt * speed.value)
  if (cursor.value >= end.value) playing.value = false
  syncVideo()
  raf = requestAnimationFrame(frame)
}

function togglePlay(): void {
  if (!playing.value && cursor.value >= end.value) cursor.value = start.value
  playing.value = !playing.value
  if (playing.value) {
    lastFrame = 0
    raf = requestAnimationFrame(frame)
  } else {
    cancelAnimationFrame(raf)
    videoEl.value?.pause()
  }
}

function seek(t: number): void {
  cursor.value = Math.min(end.value, Math.max(start.value, t))
  syncVideo(true)
}

function selectDogRoute(id: string): void {
  selectedDogRoute.value = id
  layers.value.dogRoute = true
  const plan = dogRouteOptions.value.find((option) => option.id === id)
  if (plan) seek(plan.start)
}

function jump(dir: 1 | -1): void {
  const t = dir > 0 ? nextTime(jumps.value, cursor.value) : prevTime(jumps.value, cursor.value)
  if (t !== null) seek(t)
}

function onKey(ev: KeyboardEvent): void {
  const tag = (ev.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return
  if (ev.key === ' ') {
    ev.preventDefault()
    togglePlay()
  } else if (ev.key === 'ArrowRight' || ev.key === 'ArrowLeft') {
    ev.preventDefault()
    seek(cursor.value + (ev.key === 'ArrowRight' ? 1 : -1) * (ev.shiftKey ? 10_000 : 1000))
  } else if (ev.key === ']') {
    jump(1)
  } else if (ev.key === '[') {
    jump(-1)
  }
}

// ------------------------------------------------------------------ video: one drone at a time

const videoEl = ref<HTMLVideoElement | null>(null)
const videoMain = ref(false)
/** The video fills the main view when asked, and always when there is no position to map (a dog record imported from its video). */
const videoBig = computed(() => videoMain.value || !hasPositions.value)
const withVideo = computed(() => tracks.value.map((t, i) => ({ t, i }))
  .filter(({ t }) => t.detail.videoStatus === 'READY' && (t.detail.videoParts?.length ?? 0) > 0))
const videoTrack = ref(0)
watch(withVideo, (v) => {
  if (v.length && !v.some((x) => x.i === videoTrack.value)) videoTrack.value = v[0]!.i
}, { immediate: true })
const shownVideo = computed(() => withVideo.value.find((x) => x.i === videoTrack.value)?.t ?? null)
const videoPos = computed(() => {
  const t = shownVideo.value
  return t ? videoAt(t.detail.videoParts ?? [], cursor.value, t.detail.videoOffsetMs ?? 0) : null
})
const videoSrc = computed(() => (shownVideo.value && videoPos.value ? shownVideo.value.videoUrl(videoPos.value.index) : null))

function syncVideo(force = false): void {
  const v = videoEl.value
  const p = videoPos.value
  if (!v || !p) return
  const drift = Math.abs(v.currentTime - p.seconds)
  if (playing.value && speed.value <= 4) {
    if (v.playbackRate !== speed.value) v.playbackRate = speed.value
    if (v.paused) void v.play().catch(() => undefined)
    if (drift > 0.8 || force) v.currentTime = p.seconds
  } else {
    if (!v.paused) v.pause()
    if (drift > 0.15 || force) v.currentTime = p.seconds
  }
}
watch(videoSrc, () => setTimeout(() => syncVideo(true), 0))

// ------------------------------------------------------------------ lifecycle

const recording = computed(() => tracks.value.some((t) => t.detail.status === 'OPEN'))
let poll: number | undefined

onMounted(async () => {
  await load()
  window.addEventListener('keydown', onKey)
  poll = window.setInterval(() => {
    if (recording.value) void load(true)
  }, 5000)
})
watch(() => route.query.ids, () => {
  loading.value = true
  void load()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('keydown', onKey)
  window.clearInterval(poll)
})

const OUTCOME_CLASS: Record<string, string> = { COMPLETED: 'ok', STOPPED: 'warn', EMERGENCY_STOP: 'danger', LINK_LOST: 'danger', INTERRUPTED: 'warn', SOFT_ESTOP: 'danger' }
</script>

<template>
  <div class="replay">
    <EmptyState v-if="loading" icon="spinner" :title="t('正在加载记录…')" />
    <EmptyState v-else-if="error" icon="alert" :title="error">
      <button class="btn" @click="router.push('/history')">{{ t('返回记录') }}</button>
    </EmptyState>
    <template v-else>
      <header class="bar panel">
        <button class="btn btn-ghost btn-sm" @click="router.push('/history')"><AppIcon name="left" :size="16" />{{ tc('tab', '记录') }}</button>
        <div class="title">
          <b>{{ dateTime(takeoff) }}</b>
          <span class="dim">·</span>
          <b>{{ tracks.length > 1 ? t('一起回放') : t('回放') }}</b>
          <span v-for="tr in tracks" :key="`${tr.kind}-${tr.id}`" class="chip-drone" :class="tr.kind" :style="{ '--c': tr.color }" :data-test="`joint-chip-${tr.label}`">
            <span class="dot" />{{ tr.label }}
            <span v-if="tr.kind === 'drone'" class="dim">{{ tr.detail.routeName ?? t('无航线') }}</span>
            <span v-if="tr.detail.status === 'OPEN'" class="badge danger">{{ t('● 记录中') }}</span>
            <span v-else-if="outcomeLabel(tr)" class="badge" :class="OUTCOME_CLASS[tr.detail.outcome ?? '']">{{ outcomeLabel(tr) }}</span>
            <button v-if="tracks.length > 1" class="chip-x" :title="t('不看 {name}', { name: tr.label })" :aria-label="t('不看 {name}', { name: tr.label })"
              :data-test="`joint-drop-${tr.label}`" @click="without(tr)"><AppIcon name="x" :size="12" /></button>
          </span>
          <span v-if="tracks.some((tr) => tr.detail.simulated)" class="tag">{{ t('模拟') }}</span>
        </div>
        <div v-if="tracks.length > 1" class="row">
          <button v-for="tr in tracks" :key="`${tr.kind}-${tr.id}`" class="btn btn-sm" :data-test="`joint-single-${tr.label}`" @click="openAlone(tr)">
            <AppIcon name="play" :size="14" />{{ t('单独回放 {name}', { name: tr.label }) }}
          </button>
        </div>
      </header>
      <div v-if="!overlapping" class="notice" data-test="joint-no-overlap">{{ t('有的记录和其他记录时间不重叠：时间轴从最早的开始，到最晚的结束。') }}</div>

      <section class="stage panel">
        <div class="main-view">
          <EmptyState v-if="!hasPositions && !shownVideo" icon="map" :title="t('这些记录都没有位置数据')" />
          <MapCanvas v-else-if="!videoBig" :center="mapCenter" :zoom="16" :fit="fit">
            <JointReplayOverlays :tracks="tracks" :states="states" :link="link" :layers="layers" :selected-dog-route="selectedDogRoute" />
          </MapCanvas>
          <div v-if="shownVideo" class="video" :class="videoBig ? 'main' : 'pip'">
            <video v-show="videoPos" ref="videoEl" :src="videoSrc ?? undefined" muted playsinline preload="auto" data-test="joint-video" />
            <div v-if="!videoPos" class="no-video dim">{{ t('{name} 此时刻没有视频', { name: shownVideo.label }) }}</div>
            <div v-if="withVideo.length > 1" class="video-pick" role="group" :aria-label="t('看谁的画面')">
              <button v-for="v in withVideo" :key="v.t.id" class="btn btn-sm" :class="{ 'btn-primary': v.i === videoTrack }" @click="videoTrack = v.i">{{ v.t.label }}</button>
            </div>
            <span v-else class="video-who" :style="{ '--c': shownVideo.color }">{{ shownVideo.label }}</span>
          </div>
          <div class="map-tools panel">
            <label><input v-model="layers.track" type="checkbox" />{{ drones === tracks.length ? t('航迹') : t('轨迹') }}</label>
            <label v-if="drones > 0"><input v-model="layers.route" type="checkbox" />{{ t('航线快照') }}</label>
            <label v-if="dogRouteOptions.length"><input v-model="layers.dogRoute" type="checkbox" data-test="joint-dog-routes" />{{ t('机器狗规划路线') }}</label>
            <select v-if="dogRouteOptions.length > 1" class="input dog-route-select" :aria-label="t('选择导航路线')"
              data-test="joint-dog-route-select" :value="selectedDogRoute" @keydown.stop
              @change="selectDogRoute(($event.target as HTMLSelectElement).value)">
              <option value="">{{ t('全部导航') }}</option>
              <option v-for="plan in dogRouteOptions" :key="plan.id" :value="plan.id">{{ plan.label }}</option>
            </select>
            <label><input v-model="layers.pins" type="checkbox" />{{ t('告警 / 拍照') }}</label>
            <label v-if="pair"><input v-model="layers.link" type="checkbox" />{{ t('两机连线') }}</label>
            <button v-if="shownVideo && hasPositions" class="btn btn-sm" @click="videoMain = !videoMain"><AppIcon name="swap" :size="14" />{{ videoMain ? t('地图为主') : t('视频为主') }}</button>
          </div>
        </div>
        <JointSidePanel :tracks="tracks" :states="states" :separation="separation" :alarm="alarm" :items="items" :cursor="cursor" :start="takeoff"
          @seek="seek" />
      </section>

      <section class="bottom panel">
        <div class="controls">
          <button class="btn btn-icon" :title="playing ? t('暂停（空格）') : t('播放（空格）')" data-test="joint-play" @click="togglePlay">
            <AppIcon :name="playing ? 'stop' : 'play'" />
          </button>
          <button class="btn btn-ghost btn-sm" :title="t('上一个事件（[）')" @click="jump(-1)"><AppIcon name="left" :size="14" />{{ t('事件') }}</button>
          <button class="btn btn-ghost btn-sm" :title="t('下一个事件（]）')" @click="jump(1)">{{ t('事件') }}<AppIcon name="chevron" :size="14" /></button>
          <div class="speeds" role="group" :aria-label="t('播放速度')">
            <button v-for="s in SPEEDS" :key="s" class="btn btn-sm" :class="{ 'btn-primary': speed === s }" @click="speed = s">{{ s }}×</button>
          </div>
          <span class="clock num" data-test="joint-clock">T+{{ elapsed(cursor - takeoff) }} · {{ time(cursor) }}</span>
        </div>
        <JointTimeline :start="start" :end="end" :cursor="cursor" :tracks="tracks" :proximity="spans" :separation="series"
          :base-m="fleet.safety?.proximityBaseM ?? null" :selected-dog-route="selectedDogRoute" @seek="seek" @select-dog-route="selectDogRoute" />
        <div class="keys dim">{{ t('空格 播放/暂停 · ← → 1 秒（Shift 10 秒） · [ ] 上/下一个事件（每台设备都算） · 点击或拖动时间轴跳转') }}</div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.replay {
  display: flex;
  flex-direction: column;
  gap: var(--sp-3);
  height: 100%;
  padding: var(--sp-3) var(--sp-4);
}
.bar {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
  padding: var(--sp-2) var(--sp-3);
}
.title {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
}
.chip-drone {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px;
  border: 1px solid var(--border);
  border-left: 3px solid var(--c);
  border-radius: 12px;
  font-size: var(--fs-sm);
  font-weight: 600;
}
.chip-drone .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--c);
}
/* dogs are squares, as on the map */
.chip-drone.dog .dot {
  border-radius: 2px;
}
.chip-x {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  margin-left: 2px;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
}
.chip-x:hover {
  background: var(--panel-2);
  color: var(--text);
}
.badge {
  display: inline-block;
  padding: 0 6px;
  border-radius: 10px;
  border: 1px solid var(--border);
  font-size: var(--fs-xs);
  font-weight: 600;
}
.badge.ok { color: var(--ok); border-color: var(--ok); }
.badge.warn { color: var(--warn); border-color: var(--warn); }
.badge.danger { color: var(--danger); border-color: var(--danger); }
.row {
  display: flex;
  gap: var(--sp-2);
}
.notice {
  padding: 6px var(--sp-3);
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--warn) 18%, transparent);
  border: 1px solid var(--warn);
  font-size: var(--fs-sm);
}
.stage {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  min-height: 0;
  overflow: hidden;
}
.main-view {
  position: relative;
  min-height: 0;
  border-right: 1px solid var(--border);
}
.video {
  background: #000;
  display: flex;
  align-items: center;
  justify-content: center;
}
.video.main {
  position: absolute;
  inset: 0;
}
.video.pip {
  position: absolute;
  right: 12px;
  bottom: 12px;
  width: 320px;
  aspect-ratio: 16 / 9;
  z-index: 600;
  border-radius: var(--r-ctl);
  overflow: hidden;
  box-shadow: var(--shadow);
}
.video video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.no-video {
  font-size: var(--fs-sm);
}
.video-pick {
  position: absolute;
  left: 8px;
  top: 8px;
  display: flex;
  gap: 4px;
}
.video-who {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--c);
  color: #0d1117;
  font-weight: 700;
  font-size: var(--fs-xs);
}
.map-tools {
  position: absolute;
  left: 12px;
  top: 12px;
  z-index: 700;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--sp-2) var(--sp-3);
  max-width: calc(100% - 24px);
  padding: 6px var(--sp-3);
  background: var(--overlay);
  font-size: var(--fs-sm);
}
.map-tools label {
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.dog-route-select {
  max-width: 100%;
  font-size: inherit;
}
.bottom {
  padding: var(--sp-2) var(--sp-3);
}
.controls {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  margin-bottom: var(--sp-1);
}
.speeds {
  display: flex;
  gap: 2px;
}
.clock {
  margin-left: auto;
  font-size: var(--fs-sm);
}
.keys {
  font-size: var(--fs-xs);
  margin-top: 2px;
}
@media (max-width: 1100px) {
  .stage {
    grid-template-columns: minmax(0, 1fr) 280px;
  }
}
</style>
