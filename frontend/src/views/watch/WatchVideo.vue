<script setup lang="ts">
/**
 * One device's video on the 监视台 (monitor-station-design.md «视频从哪来»):
 * - live: the live stream (WHEP, HLS fallback; mock feed in mock mode), retried for a while when it does not connect;
 * - live review: clips of the recording still being written (backend → MediaMTX, up to ~2 s before now); when no clip
 *   can be had, the live picture stays (user decision 2026-11-09);
 * - replay: the flight's archived recording, kept on the timeline cursor like the replay page does.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type Hls from 'hls.js'
import { playWhep } from '@/api/live'
import { t } from '@/i18n'
import { historyApi } from '@/api/history'
import { watchApi } from '@/api/watch'
import { useLiveStore } from '@/stores/live'
import DroneScope from '@/components/common/DroneScope.vue'
import MockFeed from '@/components/video/MockFeed.vue'
import { videoAt } from '@/utils/replay'
import type { WatchEngine } from './engine'
import type { WatchFlight } from './model'
import { clockStr } from './timeline'

const props = defineProps<{ engine: WatchEngine; gatewaySn: string; label: string; color: string; flight: WatchFlight | null; big: boolean }>()
const emit = defineEmits<{ enlarge: []; restore: [] }>()

const E = props.engine
const live = useLiveStore(props.gatewaySn)
const liveEl = ref<HTMLVideoElement | null>(null)
const recEl = ref<HTMLVideoElement | null>(null)

const mode = computed(() => { void E.ui.tick; return E.S.mode })
const reviewing = computed(() => { void E.ui.tick; return E.S.mode === 'live' && E.S.reviewing })
/** 「假装实时」: the recording plays as the live picture (no live stream, no clips). */
const fake = computed(() => E.ui.fake)
/** Recorded parts drive the tile: replay, and 假装实时. */
const fromParts = computed(() => mode.value === 'replay' || fake.value)
const status = computed(() => live.status)
const playback = computed(() => status.value?.playback ?? null)
const streaming = computed(() => !!status.value?.streaming)
const isMock = computed(() => playback.value?.protocol === 'MOCK')

// ---------------------------------------------------------------- live stream
const connecting = ref(false)
const liveError = ref<string | null>(null)
let pc: RTCPeerConnection | null = null
let hls: Hls | null = null
let attempt = 0
let retryTimer: ReturnType<typeof setTimeout> | undefined
let windowStart = 0
const CONNECT_WINDOW_MS = 30_000

function teardown(): void {
  attempt++
  clearTimeout(retryTimer)
  pc?.close(); pc = null
  hls?.destroy(); hls = null
  if (liveEl.value) liveEl.value.srcObject = null
  connecting.value = false
}
async function connect(): Promise<void> {
  teardown()
  const mine = attempt
  liveError.value = null
  const p = playback.value, el = liveEl.value
  if (!streaming.value || !p || p.protocol === 'MOCK' || !el) return
  if (p.protocol === 'NONE' || !p.url) { liveError.value = t('没有配置播放地址'); return }
  connecting.value = true
  try {
    if (p.protocol === 'WHEP') {
      try {
        const conn = await playWhep(p.url, el)
        if (mine !== attempt) { conn.close(); return }
        pc = conn; connecting.value = false
      } catch (e) {
        if (mine !== attempt) return
        if (!p.fallbackUrl) throw e
        await startHls(p.fallbackUrl, el, mine)
      }
    } else if (p.protocol === 'HLS') await startHls(p.url, el, mine)
  } catch (e) {
    failed(mine, e instanceof Error ? e.message : t('未知错误'))
  }
}
async function startHls(url: string, el: HTMLVideoElement, mine: number): Promise<void> {
  const { default: HlsLib } = await import('hls.js')
  if (mine !== attempt) return
  if (HlsLib.isSupported()) {
    const h = new HlsLib({ liveSyncDurationCount: 2 })
    hls = h
    h.on(HlsLib.Events.MANIFEST_PARSED, () => { if (mine === attempt) connecting.value = false })
    h.on(HlsLib.Events.ERROR, (_e, data) => { if (data.fatal) failed(mine, data.details) })
    h.loadSource(url); h.attachMedia(el)
  } else { el.src = url; connecting.value = false }
}
function failed(mine: number, reason: string): void {
  if (mine !== attempt) return
  attempt++
  if (Date.now() - windowStart + 2500 <= CONNECT_WINDOW_MS) {
    connecting.value = true
    retryTimer = setTimeout(() => void connect(), 2500)
    return
  }
  connecting.value = false
  liveError.value = t('视频连接失败：{msg}', { msg: reason })
}
function attach(): void { windowStart = Date.now(); void connect() }
const streamKey = computed(() => (mode.value === 'live' && !fake.value && streaming.value && playback.value ? `${playback.value.protocol} ${playback.value.url ?? ''}` : ''))
watch([streamKey, liveEl], () => { if (streamKey.value) attach(); else teardown() }, { flush: 'post' })

// ---------------------------------------------------------------- recorded video (live review clips, replay parts)
/** Clip of the recording in use while reviewing: [start, end) in server time. */
let clip: { start: number; end: number; url: string } | null = null
const clipFailed = ref(false)
const clipUrl = ref<string | null>(null)
const replaySrc = ref<string | null>(null)

/** The flight's clock → the video server's clock (the timeline runs on the aircraft clock). */
const serverT = (t: number) => t + (props.flight?.off ?? 0)

function wantClip(): void {
  const f = props.flight
  if (!f?.input.sessionId) { clipFailed.value = true; return }
  const start = serverT(E.S.t), latest = serverT(E.S.now) - 2000
  const dur = Math.min(30, (latest - start) / 1000)
  if (dur < 1.5) { clipFailed.value = true; return }
  clip = { start, end: start + dur * 1000, url: watchApi.clipUrl(f.input.sessionId, start, dur) }
  clipUrl.value = clip.url
  clipFailed.value = false
}
function onRecError(): void {
  if (!fromParts.value) { clipFailed.value = true; clip = null; clipUrl.value = null }
  else replayMissing.value = t('录像读取失败')
}

const replayMissing = ref<string | null>(null)
function replayPos(): { src: string; seconds: number } | null {
  const f = props.flight, d = f?.input.detail
  if (!f?.input.sessionId || !d) { replayMissing.value = t('这次飞行没有录像'); return null }
  if (d.videoStatus === 'PENDING' || d.videoStatus === 'ARCHIVING') { replayMissing.value = t('录像还在整理，降落后几分钟可看'); return null }
  const parts = d.videoParts ?? []
  if (d.videoStatus !== 'READY' || !parts.length) { replayMissing.value = t('这次飞行没有录像'); return null }
  const p = videoAt(parts, serverT(E.S.t), d.videoOffsetMs ?? 0)
  if (!p) { replayMissing.value = t('这一段没有录像'); return null }
  replayMissing.value = null
  return { src: historyApi.videoUrl(f.input.sessionId, p.index), seconds: p.seconds }
}

/** Keeps the recorded <video> on the cursor: plays along at the playback speed, seeks when it drifts. */
function syncRecorded(): void {
  const v = recEl.value
  if (!v) return
  const S = E.S
  let target: number | null = null, playing = false, rate = 1
  if (S.mode === 'live' && S.reviewing && !S.fake) {
    if (!clip || serverT(S.t) < clip.start || serverT(S.t) > clip.end - 800) wantClip()
    if (!clip || clipFailed.value) return
    target = (serverT(S.t) - clip.start) / 1000
    playing = S.revPlaying; rate = S.revSpeed
  } else if (S.mode === 'replay' || S.fake) {
    const p = replayPos()
    if (!p) { replaySrc.value = null; return }
    if (replaySrc.value !== p.src) replaySrc.value = p.src
    target = p.seconds
    if (S.mode === 'replay') { playing = S.playing && S.speed <= 8; rate = S.speed }
    else { playing = S.reviewing ? S.revPlaying : true; rate = S.reviewing ? S.revSpeed : 1 }
  } else return
  if (v.readyState < 1) return
  const drift = Math.abs(v.currentTime - target)
  if (playing) {
    if (v.playbackRate !== rate) v.playbackRate = rate
    if (v.paused) void v.play().catch(() => undefined)
    if (drift > 0.8 * Math.max(1, rate / 2)) v.currentTime = target
  } else {
    if (!v.paused) v.pause()
    if (drift > 0.15) v.currentTime = target
  }
}
watch(() => E.ui.tick, syncRecorded)
watch(reviewing, (r) => { if (!r) { clip = null; clipUrl.value = null; clipFailed.value = false } })

/** What the tile shows. */
const view = computed<'live' | 'mock' | 'rec' | 'none'>(() => {
  void E.ui.tick
  if (fromParts.value) return replaySrc.value ? 'rec' : 'none'
  if (reviewing.value && clipUrl.value && !clipFailed.value) return 'rec'
  if (!streaming.value) return 'none'
  return isMock.value ? 'mock' : 'live'
})
const recSrc = computed(() => (fromParts.value ? replaySrc.value : clipUrl.value))
const badge = computed(() => {
  void E.ui.tick
  if (mode.value === 'replay') return { text: t('录像 {time}', { time: clockStr(E.S.t) }), live: false }
  if (fake.value) return reviewing.value ? { text: t('回看 {time}', { time: clockStr(E.S.t) }), live: false } : { text: t('实时'), live: true }
  if (reviewing.value) return view.value === 'rec' ? { text: t('回看 {time}', { time: clockStr(E.S.t) }), live: false } : { text: t('实时画面'), live: true }
  return { text: t('实时'), live: true }
})
const emptyText = computed(() => {
  if (mode.value === 'replay') return replayMissing.value ?? t('这次飞行没有录像')
  return t('{label} 没有开启视频', { label: props.label })
})
const lensLabel = computed(() => ({ wide: t('广角'), zoom: t('变焦'), thermal: t('红外'), ir: t('红外') } as Record<string, string>)[status.value?.lens ?? 'wide'] ?? t('广角'))

onBeforeUnmount(teardown)
</script>

<template>
  <figure class="wv" :class="{ big }" :style="{ '--c': color }" data-test="watch-video">
    <video v-show="view === 'live'" ref="liveEl" class="v" muted playsinline autoplay />
    <video v-show="view === 'rec'" ref="recEl" class="v" :src="recSrc ?? undefined" muted playsinline preload="auto" @error="onRecError" @loadedmetadata="syncRecorded" />
    <DroneScope v-if="view === 'mock'" :sn="gatewaySn"><MockFeed :lens="status?.lens ?? 'wide'" class="v" /></DroneScope>
    <div v-if="view === 'none'" class="state"><div><b>{{ emptyText }}</b></div></div>
    <div v-else-if="view === 'live' && connecting" class="state"><div><div class="spin" /><b>{{ t('正在连接 {label} 的视频', { label }) }}</b></div></div>
    <div v-else-if="view === 'live' && liveError" class="state"><div><b>{{ liveError }}</b><button class="btn btn-sm" @click.stop="attach">{{ t('重试') }}</button></div></div>
    <figcaption class="cap"><span class="sw" /><span>{{ label }}</span><span class="vs">{{ lensLabel }}</span></figcaption>
    <span v-if="view !== 'none'" class="badge" :class="{ live: badge.live }">{{ badge.text }}</span>
    <button v-if="!big" class="exp" :title="t('放到大画面（地图换到这里）')" :aria-label="t('放到大画面')" data-test="watch-video-enlarge" @click.stop="emit('enlarge')">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" stroke-linecap="round" stroke-linejoin="round" /></svg>
    </button>
    <button v-else class="back btn btn-sm" data-test="watch-video-restore" @click.stop="emit('restore')">{{ t('换回地图') }}</button>
  </figure>
</template>

<style scoped>
.wv { position: absolute; inset: 0; margin: 0; background: #05080a; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.wv.big { border-color: color-mix(in srgb, var(--c) 55%, var(--border)); }
.v { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #05080a; }
.state { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; color: #9fb0b7; font-size: 12px; padding: 12px; z-index: 2; }
.state b { display: block; color: #dfe6e8; font-weight: 500; font-size: 13px; margin-bottom: 6px; }
.spin { width: 18px; height: 18px; border-radius: 50%; border: 2px solid #33444c; border-top-color: #b9c5ca; animation: spin 1s linear infinite; margin: 0 auto 8px; }
@keyframes spin { to { transform: rotate(360deg); } }
.cap { position: absolute; left: 8px; top: 7px; z-index: 3; display: flex; align-items: center; gap: 6px; padding: 3px 8px 3px 6px; border-radius: 3px; background: rgba(6, 10, 12, .62); color: #eef3f4; font-weight: 600; font-size: 12px; }
.cap .sw { width: 10px; height: 10px; border-radius: 2px; background: var(--c); }
.cap .vs { font-weight: 400; font-size: 11px; color: #b9c5ca; }
.badge { position: absolute; right: 8px; top: 7px; z-index: 3; display: inline-flex; align-items: center; gap: 6px; padding: 3px 7px; border-radius: 3px; background: rgba(6, 10, 12, .62); color: #eef3f4; font: 500 11px var(--font-num); }
.badge.live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #ef4444; animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .35; } }
.exp { position: absolute; left: 8px; bottom: 6px; z-index: 4; width: 28px; height: 28px; border-radius: 3px; border: 0; background: rgba(6, 10, 12, .7); color: #eef3f4; display: grid; place-items: center; cursor: pointer; opacity: .55; padding: 0; }
.wv:hover .exp, .exp:focus-visible { opacity: 1; }
.exp svg { width: 15px; height: 15px; }
.back { position: absolute; left: 10px; bottom: 10px; z-index: 4; }
@media (prefers-reduced-motion: reduce) { .spin, .badge.live::before { animation: none; } }
</style>
