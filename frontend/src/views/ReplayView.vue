<script setup lang="ts">
/**
 * Flight replay (R-22 draft, ui-design.md §2.6). One time cursor drives the map, the side panel,
 * the timeline and the video. Keyboard: Space play/pause, ←/→ 1 s (Shift 10 s), [ / ] previous /
 * next event.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppIcon from '@/components/common/AppIcon.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import MapCanvas from '@/components/map/MapCanvas.vue'
import ReplayOverlays, { type ReplayLayers } from '@/components/history/ReplayOverlays.vue'
import ReplayTimeline from '@/components/history/ReplayTimeline.vue'
import ReplaySidePanel from '@/components/history/ReplaySidePanel.vue'
import SaveRouteDialog from '@/components/history/SaveRouteDialog.vue'
import { ApiError } from '@/api/http'
import {
  historyApi, OUTCOME_LABELS, VIDEO_LABELS, type FlightCommand, type FlightEvent, type Sample, type SessionDetail, type VideoStatus,
} from '@/api/history'
import type { Route } from '@/api/routes'
import { useToastStore } from '@/stores/toast'
import { useConfirmStore } from '@/stores/confirm'
import { useHistoryStore } from '@/stores/history'
import { useFleetStore } from '@/stores/fleet'
import { dateTime, time } from '@/utils/format'
import type { LatLon } from '@/utils/coord'
import { t, tc } from '@/i18n'
import {
  alertMarks, commandMarks, elapsed, fillForward, indexAt, jumpTimes, linkGaps, nextTime, phases as buildPhases, photoMarks, targetMarks, targetsAt,
  plannedPaths, prevTime, stateAt, videoAt,
} from '@/utils/replay'

const route = useRoute()
const router = useRouter()
const toast = useToastStore()
const confirm = useConfirmStore()
const history = useHistoryStore()
const fleet = useFleetStore()
const id = computed(() => String(route.params.id))

const detail = ref<SessionDetail | null>(null)
const samples = ref<Sample[]>([])
const events = ref<FlightEvent[]>([])
const commands = ref<FlightCommand[]>([])
const error = ref<string | null>(null)
const loading = ref(true)

async function load(keepCursor = false): Promise<void> {
  try {
    const [d, s, e, c] = await Promise.all([
      historyApi.get(id.value), historyApi.samples(id.value), historyApi.events(id.value), historyApi.commands(id.value),
    ])
    detail.value = d
    samples.value = s
    events.value = e
    commands.value = c
    if (!keepCursor) cursor.value = d.takeoffAt ?? start.value
    error.value = null
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('加载失败')
  } finally {
    loading.value = false
  }
}

const filled = computed(() => fillForward(samples.value, detail.value?.takeoffEllipsoidHeight ?? null))
/**
 * Axis start: shortly before the first command or take-off. The session also holds up to 2 minutes of
 * standby telemetry before that, which would otherwise squeeze the flight into a corner of the axis.
 */
const start = computed(() => {
  const d = detail.value
  const first = Math.min(d?.startedAt ?? Infinity, filled.value[0]?.ts ?? Infinity)
  const lead = Math.min(d?.takeoffAt ?? Infinity, commands.value[0]?.createdAt ?? Infinity)
  return Number.isFinite(lead) ? Math.max(first, lead - 5000) : first
})
const end = computed(() => {
  const last = filled.value[filled.value.length - 1]?.ts ?? 0
  return Math.max(detail.value?.endedAt ?? 0, last, start.value + 1000)
})
const cursor = ref(0)
const state = computed(() => stateAt(filled.value, cursor.value))

const phaseList = computed(() => buildPhases(filled.value, events.value))
const cmdMarks = computed(() => commandMarks(commands.value))
const alerts = computed(() => alertMarks(events.value))
const photos = computed(() => photoMarks(commands.value))
const targetEvents = computed(() => targetMarks(events.value))
const replayTargets = computed(() => targetsAt(events.value, cursor.value))
const gaps = computed(() => linkGaps(filled.value, events.value))
const planned = computed(() => plannedPaths(events.value))
const jumps = computed(() => jumpTimes([...cmdMarks.value, ...alerts.value, ...photos.value], phaseList.value, events.value))

function posAt(t: number): LatLon | null {
  const s = stateAt(filled.value, t)
  return s && s.lat !== null && s.lon !== null ? { lat: s.lat, lon: s.lon } : null
}
const pins = computed(() =>
  [...alerts.value, ...photos.value].flatMap((m) => {
    const pos = posAt(m.ts)
    return pos ? [{ ...m, pos }] : []
  }),
)
const routePoints = computed<LatLon[]>(() => detail.value?.routeSnapshot?.waypoints.map((w) => ({ lat: w.lat, lon: w.lon })) ?? [])
const rcPos = computed<LatLon | null>(() => {
  const rc = events.value.filter((e) => e.eventType === 'RC_POSITION' && e.ts <= cursor.value).pop()
  return rc?.payload ? { lat: Number(rc.payload.lat), lon: Number(rc.payload.lon) } : null
})
const home = computed<LatLon | null>(() =>
  detail.value?.homeLat != null && detail.value.homeLon != null ? { lat: detail.value.homeLat, lon: detail.value.homeLon } : null,
)
const fit = computed<LatLon[]>(() => {
  const pts = filled.value.filter((s) => s.lat !== null && s.lon !== null).map((s) => ({ lat: s.lat!, lon: s.lon! }))
  return [...pts, ...routePoints.value]
})
const mapCenter = computed(() => fit.value[0] ?? null)

const layers = ref<ReplayLayers>({ track: true, route: true, planned: true, pins: true, rc: true, targets: true })
const colorBy = ref<'height' | 'speed'>('height')

// ------------------------------------------------------------------ playback

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

function jump(dir: 1 | -1): void {
  const t = dir > 0 ? nextTime(jumps.value, cursor.value) : prevTime(jumps.value, cursor.value)
  if (t !== null) seek(t)
}

function onKey(ev: KeyboardEvent): void {
  const tag = (ev.target as HTMLElement | null)?.tagName
  if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA' || saveOpen.value) return
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

// ------------------------------------------------------------------ video

const videoEl = ref<HTMLVideoElement | null>(null)
const videoMain = ref(false)
const parts = computed(() => detail.value?.videoParts ?? [])
const hasVideo = computed(() => detail.value?.videoStatus === 'READY' && parts.value.length > 0)
const offsetMs = ref(0)
const videoPos = computed(() => (hasVideo.value ? videoAt(parts.value, cursor.value, offsetMs.value) : null))
const videoSrc = computed(() => (videoPos.value ? historyApi.videoUrl(id.value, videoPos.value.index) : null))

/** Keeps the video on the cursor: plays along at 1×/4×, seeks every frame above that. */
function syncVideo(force = false): void {
  const v = videoEl.value
  const p = videoPos.value
  if (!v || !p) return
  const drift = Math.abs(v.currentTime - p.seconds)
  const canPlay = playing.value && speed.value <= 4
  if (canPlay) {
    if (v.playbackRate !== speed.value) v.playbackRate = speed.value
    if (v.paused) void v.play().catch(() => undefined)
    if (drift > 0.8 || force) v.currentTime = p.seconds
  } else {
    if (!v.paused) v.pause()
    if (drift > 0.15 || force) v.currentTime = p.seconds
  }
}
watch(videoSrc, () => setTimeout(() => syncVideo(true), 0))

async function nudge(ms: number): Promise<void> {
  offsetMs.value += ms
  syncVideo(true)
  try {
    await historyApi.patch(id.value, { videoOffsetMs: offsetMs.value })
  } catch {
    /* offset still applies in this view */
  }
}

// ------------------------------------------------------------------ actions

const saveOpen = ref(false)
const defaultRouteName = computed(() => t('航迹 {time}', { time: dateTime(detail.value?.takeoffAt ?? detail.value?.startedAt) }))

function saved(r: Route): void {
  saveOpen.value = false
  toast.push('ok', t('已存为航线「{name}」', { name: r.name }), 6000, { label: t('编辑'), to: `/plan?route=${r.id}` })
}

async function protect(): Promise<void> {
  const d = detail.value
  if (!d) return
  await historyApi.patch(d.id, { protectedFlag: !d.protectedFlag })
  d.protectedFlag = !d.protectedFlag
  toast.push('ok', d.protectedFlag ? t('已保护') : t('已取消保护'))
}

async function remove(): Promise<void> {
  const d = detail.value
  if (!d) return
  const ok = await confirm.ask({ title: t('删除飞行记录'), message: t('航迹、指令、事件和视频都会删除，不可撤销。'), confirmText: t('删除'), danger: true, focus: 'cancel' })
  if (!ok) return
  try {
    await historyApi.remove(d.id)
    toast.push('ok', t('已删除'))
    void router.push('/history')
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('删除失败'))
  }
}

async function toggleFlightVideo(): Promise<void> {
  const d = detail.value
  if (!d) return
  try {
    await historyApi.patch(d.id, { videoWanted: !d.videoWanted })
    d.videoWanted = !d.videoWanted
    toast.push('ok', d.videoWanted ? t('本次飞行将录像') : t('本次飞行不再录像'))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('操作失败'))
  }
}

const exportOpen = ref(false)
const recording = computed(() => detail.value?.status === 'OPEN')

/**
 * Archive the video again (field test 2026-11-04: a gap in the recording had failed the whole archive). Offered after a
 * failed, empty or not-configured archive; stays visible (disabled) while the archive it started runs.
 */
const REARCHIVABLE: VideoStatus[] = ['FAILED', 'NONE', 'UNAVAILABLE']
const rearchiveSending = ref(false)
const rearchiveStarted = ref(false)
const videoBusy = computed(() => detail.value?.videoStatus === 'ARCHIVING' || detail.value?.videoStatus === 'PENDING')
const showRearchive = computed(() => {
  const st = detail.value?.videoStatus
  return !recording.value && !!st && (REARCHIVABLE.includes(st) || (rearchiveStarted.value && videoBusy.value))
})

async function rearchive(): Promise<void> {
  const d = detail.value
  if (!d || rearchiveSending.value || videoBusy.value) return
  rearchiveSending.value = true
  try {
    detail.value = await historyApi.archiveVideo(d.id)
    rearchiveStarted.value = true
    toast.push('info', t('已开始重新归档视频，完成后自动刷新'))
  } catch (e) {
    toast.push('danger', e instanceof ApiError ? e.message : t('重新归档失败'))
  } finally {
    rearchiveSending.value = false
  }
}

watch(() => detail.value?.videoStatus, (now, before) => {
  if (!rearchiveStarted.value || !before || now === before || now === 'ARCHIVING' || now === 'PENDING') return
  rearchiveStarted.value = false
  if (now === 'READY') toast.push('ok', t('视频已重新归档'))
  else toast.push('warn', t('重新归档未取回视频：{reason}', { reason: detail.value?.videoMessage ?? (now ? VIDEO_LABELS[now] : '') }), 8000)
})

let poll: number | undefined

onMounted(async () => {
  await load()
  offsetMs.value = detail.value?.videoOffsetMs ?? 0
  window.addEventListener('keydown', onKey)
  poll = window.setInterval(() => {
    if (recording.value || detail.value?.videoStatus === 'PENDING' || detail.value?.videoStatus === 'ARCHIVING') void load(true)
  }, 5000)
})
watch(() => history.changed, () => void load(true))
watch(id, () => {
  loading.value = true
  void load()
})
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('keydown', onKey)
  window.clearInterval(poll)
})

const OUTCOME_CLASS: Record<string, string> = { COMPLETED: 'ok', STOPPED: 'warn', EMERGENCY_STOP: 'danger', LINK_LOST: 'danger', INTERRUPTED: 'warn' }
const cursorIndex = computed(() => indexAt(filled.value, cursor.value))
</script>

<template>
  <div class="replay">
    <EmptyState v-if="loading" icon="spinner" :title="t('正在加载飞行记录…')" />
    <EmptyState v-else-if="error && !detail" icon="alert" :title="error">
      <button class="btn" @click="router.push('/history')">{{ t('返回记录') }}</button>
    </EmptyState>
    <template v-else-if="detail">
      <header class="bar panel">
        <button class="btn btn-ghost btn-sm" @click="router.push('/history')"><AppIcon name="left" :size="16" />{{ tc('tab', '记录') }}</button>
        <div class="title">
          <b>{{ dateTime(detail.takeoffAt ?? detail.startedAt) }}</b>
          <span class="dim">·</span>
          <span>{{ detail.routeName ?? t('无航线') }}</span>
          <span v-if="recording" class="badge danger">{{ t('● 记录中') }}</span>
          <span v-else-if="detail.outcome" class="badge" :class="OUTCOME_CLASS[detail.outcome]">{{ OUTCOME_LABELS[detail.outcome] }}</span>
          <span v-if="detail.simulated" class="tag">{{ t('模拟') }}</span>
          <span v-if="detail.resumed" class="tag" :title="t('记录开始时飞行器已在空中')">{{ t('续录') }}</span>
        </div>
        <div class="row">
          <button v-for="o in detail.together ?? []" :key="o.id" class="btn btn-sm btn-primary" :data-test="`replay-together-${o.id}`"
            :title="t('{name} 在这段时间也在飞：两架放在同一张地图、同一条时间轴上回放', { name: fleet.label(o.gatewaySn) })"
            @click="router.push({ path: '/history/together', query: { ids: `${detail.id},${o.id}` } })">
            <AppIcon name="play" :size="15" />{{ t('与 {name} 一起回放', { name: fleet.label(o.gatewaySn) }) }}
          </button>
          <button v-if="recording && detail.videoStatus !== 'UNAVAILABLE'" class="btn btn-sm" @click="toggleFlightVideo">
            <AppIcon name="record" :size="15" />{{ detail.videoWanted ? t('本次不录像') : t('本次录像') }}
          </button>
          <button class="btn btn-sm" :disabled="recording" data-test="open-save-route" @click="saveOpen = true"><AppIcon name="save" :size="15" />{{ t('存为航线') }}</button>
          <div class="menu-wrap">
            <button class="btn btn-sm" @click="exportOpen = !exportOpen"><AppIcon name="download" :size="15" />{{ t('导出') }}</button>
            <div v-if="exportOpen" class="menu panel" @click="exportOpen = false">
              <a :href="historyApi.exportUrl(detail.id, 'geojson')" download>{{ t('航迹 GeoJSON') }}</a>
              <a :href="historyApi.exportUrl(detail.id, 'kml')" download>{{ t('航迹 KML') }}</a>
              <a :href="historyApi.exportUrl(detail.id, 'csv')" download>{{ t('遥测 CSV') }}</a>
              <a :href="historyApi.exportUrl(detail.id, 'json')" download>{{ t('完整记录 JSON') }}</a>
            </div>
          </div>
          <button class="btn btn-sm" @click="protect"><AppIcon name="lock" :size="15" />{{ detail.protectedFlag ? t('取消保护') : t('保护') }}</button>
          <button class="btn btn-sm btn-danger" :disabled="recording" @click="remove"><AppIcon name="trash" :size="15" />{{ t('删除') }}</button>
        </div>
      </header>

      <section class="stage panel">
        <div class="main-view">
          <EmptyState v-if="!filled.length" icon="map" :title="t('这次飞行没有位置数据')" />
          <MapCanvas v-else-if="!videoMain" :center="mapCenter" :zoom="16" :fit="fit">
            <ReplayOverlays :filled="filled" :state="state" :route="routePoints" :planned="planned" :pins="pins" :targets="replayTargets" :rc="rcPos" :home="home"
              :color-by="colorBy" :layers="layers" />
          </MapCanvas>
          <div v-if="videoMain || (hasVideo && !videoMain)" class="video" :class="{ main: videoMain, pip: !videoMain }">
            <video v-show="videoPos" ref="videoEl" :src="videoSrc ?? undefined" muted playsinline preload="auto" data-test="replay-video" />
            <div v-if="!videoPos" class="no-video dim">{{ t('此时刻没有视频') }}</div>
          </div>
          <div class="map-tools panel">
            <label><input v-model="layers.track" type="checkbox" />{{ t('航迹') }}</label>
            <select v-model="colorBy" class="input" :aria-label="t('航迹着色')">
              <option value="height">{{ t('按高度着色') }}</option>
              <option value="speed">{{ t('按速度着色') }}</option>
            </select>
            <label><input v-model="layers.route" type="checkbox" />{{ t('航线快照') }}</label>
            <label><input v-model="layers.planned" type="checkbox" />{{ t('规划路径') }}</label>
            <label><input v-model="layers.pins" type="checkbox" />{{ t('告警 / 拍照') }}</label>
            <label><input v-model="layers.rc" type="checkbox" />{{ t('遥控器') }}</label>
            <label><input v-model="layers.targets" type="checkbox" />{{ t('目标') }}</label>
            <button v-if="hasVideo" class="btn btn-sm" @click="videoMain = !videoMain"><AppIcon name="swap" :size="14" />{{ videoMain ? t('地图为主') : t('视频为主') }}</button>
          </div>
        </div>
        <ReplaySidePanel :detail="detail" :state="state" :cursor="cursor" :start="detail.takeoffAt ?? start" :commands="commands" :events="events" @seek="seek" />
      </section>

      <section class="bottom panel">
        <div class="controls">
          <button class="btn btn-icon" :title="playing ? t('暂停（空格）') : t('播放（空格）')" data-test="replay-play" @click="togglePlay">
            <AppIcon :name="playing ? 'stop' : 'play'" />
          </button>
          <button class="btn btn-ghost btn-sm" :title="t('上一个事件（[）')" @click="jump(-1)"><AppIcon name="left" :size="14" />{{ t('事件') }}</button>
          <button class="btn btn-ghost btn-sm" :title="t('下一个事件（]）')" @click="jump(1)">{{ t('事件') }}<AppIcon name="chevron" :size="14" /></button>
          <div class="speeds" role="group" :aria-label="t('播放速度')">
            <button v-for="s in SPEEDS" :key="s" class="btn btn-sm" :class="{ 'btn-primary': speed === s }" @click="speed = s">{{ s }}×</button>
          </div>
          <span v-if="hasVideo" class="offset dim">
            {{ t('视频偏移 {s} s', { s: (offsetMs / 1000).toFixed(1) }) }}
            <button class="btn btn-ghost btn-sm" @click="nudge(-500)">−0.5</button>
            <button class="btn btn-ghost btn-sm" @click="nudge(500)">+0.5</button>
          </span>
          <span v-else-if="detail.videoStatus" class="dim video-state">{{ VIDEO_LABELS[detail.videoStatus] }}</span>
          <button v-if="showRearchive" class="btn btn-sm" data-test="rearchive-video" :disabled="rearchiveSending || videoBusy"
            :title="detail.videoMessage ? t('{reason}。按飞行时段从流媒体服务器重新取回录像', { reason: detail.videoMessage }) : t('按飞行时段从流媒体服务器重新取回录像')"
            @click="rearchive">
            <AppIcon :name="rearchiveSending || videoBusy ? 'spinner' : 'sync'" :size="14" />{{ rearchiveSending || videoBusy ? t('归档中…') : t('重新归档视频') }}
          </button>
          <span class="clock num" data-test="replay-clock">
            T+{{ elapsed(cursor - (detail.takeoffAt ?? start)) }} · {{ time(cursor) }}
            <span class="dim">{{ t('（{i}/{n}）', { i: cursorIndex + 1, n: filled.length }) }}</span>
          </span>
        </div>
        <ReplayTimeline :start="start" :end="end" :cursor="cursor" :filled="filled" :phases="phaseList" :commands="cmdMarks" :alerts="alerts"
          :photos="photos" :targets="targetEvents" :gaps="gaps" @seek="seek" />
        <div class="keys dim">{{ t('空格 播放/暂停 · ← → 1 秒（Shift 10 秒） · [ ] 上/下一个事件 · 点击或拖动时间轴跳转') }}</div>
      </section>
    </template>
    <SaveRouteDialog v-if="saveOpen && detail" :session-id="detail.id" :default-name="defaultRouteName" @saved="saved" @cancel="saveOpen = false" />
  </div>
</template>

<style scoped>
.replay {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
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
.badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  border: 1px solid var(--border);
  font-size: var(--fs-xs);
  font-weight: 600;
}
.badge.ok { color: var(--ok); border-color: var(--ok); }
.badge.warn { color: var(--warn); border-color: var(--warn); }
.badge.danger { color: var(--danger); border-color: var(--danger); }
.menu-wrap {
  position: relative;
}
.menu {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 1200;
  display: flex;
  flex-direction: column;
  min-width: 160px;
  padding: var(--sp-1) 0;
  box-shadow: var(--shadow);
}
.menu a {
  padding: 6px var(--sp-3);
  color: var(--text);
  text-decoration: none;
  font-size: var(--fs-sm);
}
.menu a:hover {
  background: var(--panel-2);
}
.stage {
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
.map-tools .input {
  width: auto;
  padding: 2px 6px;
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
.offset,
.video-state {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-sm);
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
