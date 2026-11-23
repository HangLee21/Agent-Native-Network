<script setup lang="ts">
/**
 * Live video (R-14, R-15; ui-design.md §7 video states): not started / connecting / playing / error.
 * Playback: WHEP (WebRTC) first, HLS fallback, MOCK synthetic feed in mock mode.
 * A stream that has just started is often not playable yet (the media server answers 404 until the first segments
 * arrive: "manifestLoadError", 2026-11-04 field test), so a failed connection is retried for a while before the
 * error and its 重试 button are shown.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type Hls from 'hls.js'
import AppIcon from '@/components/common/AppIcon.vue'
import CommandStatus from '@/components/control/CommandStatus.vue'
import FlightHud from './FlightHud.vue'
import MockFeed from './MockFeed.vue'
import TargetSelectOverlay from '@/components/target/TargetSelectOverlay.vue'
import { LENS_LABELS, QUALITY_LABELS, liveApi, playWhep } from '@/api/live'
import { useLiveStore } from '@/stores/live'
import { useTelemetryStore } from '@/stores/telemetry'
import { useControlStore } from '@/stores/control'
import { useTargetsStore } from '@/stores/targets'
import { MOCK_FRAME } from '@/utils/videoCoords'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

/** `controls=false`: the flight monitor puts lens / quality / video off on its camera rail instead (ui-design.md §2.2). */
const props = withDefaults(defineProps<{ compact?: boolean; hud?: boolean; reserveLeft?: number; controls?: boolean }>(), { compact: false, hud: true, reserveLeft: 0, controls: true })
const live = useLiveStore()
const tel = useTelemetryStore()
const control = useControlStore()
const targets = useTargetsStore()
const video = ref<HTMLVideoElement | null>(null)
const quality = ref(0)
const playError = ref<string | null>(null)
/** Also true while waiting for the next automatic retry: the operator sees one neutral "connecting" state. */
const connecting = ref(false)
/** Automatic retries made in the current connect window (shown as a hint once there is one). */
const retries = ref(0)
let pc: RTCPeerConnection | null = null
let hls: Hls | null = null
let attempt = 0 // bumped by teardown() and failed(): a connection or player event from an older attempt is dropped
let retryTimer: ReturnType<typeof setTimeout> | undefined
let windowStart = 0

const st = computed(() => live.status)
const playback = computed(() => st.value?.playback ?? null)
const streaming = computed(() => !!st.value?.streaming)
/** What the player is connected to; a status push that keeps the same stream (lens, quality) must not reconnect. */
const streamKey = computed(() => {
  const p = playback.value
  return streaming.value && p ? `${p.protocol} ${p.url ?? ''} ${p.fallbackUrl ?? ''}` : ''
})
const lenses = computed(() => {
  const l = st.value?.lenses ?? []
  return l.map((x) => (x === 'ir' ? 'thermal' : x))
})

/** How long failed connections are retried before the error is shown, counted from attach(). */
const CONNECT_WINDOW_MS = 30_000
/** Wait before automatic retry n (0-based): 2 s for the first three, then 3 s. */
const retryDelay = (n: number) => (n < 3 ? 2000 : 3000)

function teardown(): void {
  attempt++
  connecting.value = false
  clearTimeout(retryTimer)
  retryTimer = undefined
  pc?.close()
  pc = null
  hls?.destroy()
  hls = null
  if (video.value) video.value.srcObject = null
}

/** Opens a new connect window: the stream or the <video> element changed, or the operator pressed 重试. */
function attach(): Promise<void> {
  windowStart = Date.now()
  retries.value = 0
  return connect()
}

async function connect(): Promise<void> {
  teardown()
  const mine = attempt
  playError.value = null
  const p = playback.value
  const el = video.value
  if (!streaming.value || !p || p.protocol === 'MOCK') return
  if (p.protocol === 'NONE' || !p.url) {
    playError.value = t('未配置播放地址（LIVE_WHEP_PLAY / LIVE_HLS_PLAY）')
    return
  }
  if (!el) return // the watcher below runs again once the <video> element is rendered
  connecting.value = true
  try {
    if (p.protocol === 'WHEP') {
      try {
        const conn = await playWhep(p.url, el)
        if (mine !== attempt) {
          conn.close()
          return
        }
        pc = conn
        connecting.value = false
      } catch (e) {
        if (mine !== attempt) return
        if (!p.fallbackUrl) throw e
        await startHls(p.fallbackUrl, el, mine)
      }
    } else if (p.protocol === 'HLS') {
      await startHls(p.url, el, mine)
    } else {
      connecting.value = false
    }
  } catch (e) {
    failed(mine, e instanceof Error ? e.message : t('未知错误'))
  }
}

/**
 * A connection attempt failed: while the connect window lasts, wait and retry (the whole WHEP → HLS sequence),
 * still showing "connecting"; after that, show the error with 重试.
 */
function failed(mine: number, reason: string): void {
  if (mine !== attempt) return // a newer attempt, a teardown or the unmount took over
  attempt++ // later reports from the failed player are ignored; the next connect() / teardown() destroys it
  const delay = retryDelay(retries.value)
  if (Date.now() - windowStart + delay <= CONNECT_WINDOW_MS) {
    connecting.value = true
    retryTimer = setTimeout(() => {
      retryTimer = undefined
      retries.value++
      void connect()
    }, delay)
    return
  }
  connecting.value = false
  playError.value = t('视频连接失败：{reason}', { reason })
}

async function startHls(url: string, el: HTMLVideoElement, mine: number): Promise<void> {
  const { default: HlsLib } = await import('hls.js') // loaded only when the HLS fallback is used
  if (mine !== attempt) return
  if (HlsLib.isSupported()) {
    const h = new HlsLib({ liveSyncDurationCount: 2 })
    hls = h
    h.on(HlsLib.Events.MANIFEST_PARSED, () => {
      if (mine === attempt) connecting.value = false
    })
    h.on(HlsLib.Events.ERROR, (_e, data) => {
      if (data.fatal) failed(mine, data.details)
    })
    h.loadSource(url)
    h.attachMedia(el)
  } else {
    el.src = url // native HLS (Safari): no load events to wait for
    connecting.value = false
  }
}

// Watching the element itself with flush 'post': it exists only after the render that follows `streaming` turning
// true, and a panel mounted while a stream is already running (back from another page) gets it right after mount.
watch([streamKey, video], () => void attach(), { flush: 'post' })
watch(() => st.value?.quality, (q) => {
  if (q !== undefined && q !== null) quality.value = q
}, { immediate: true })
onBeforeUnmount(teardown)

const startRec = () => control.run('live', t('开启直播'), () => liveApi(sn).start(quality.value))
const stopRec = () => control.run('live', t('停止直播'), () => liveApi(sn).stop())
const setQuality = () => control.run('live', t('设置直播清晰度'), () => liveApi(sn).quality(quality.value))
const setLens = (l: string) => control.run('live', t('切换镜头：{lens}', { lens: LENS_LABELS[l] ?? l }), () => liveApi(sn).lens(l))
</script>

<template>
  <div class="video" :class="{ compact }" data-test="video-panel">
    <template v-if="streaming">
      <MockFeed v-if="playback?.protocol === 'MOCK'" :lens="st?.lens ?? 'wide'" />
      <video v-else ref="video" class="player" autoplay muted playsinline />
      <div v-if="!tel.online" class="overlay error" data-test="video-link-lost">
        <AppIcon name="alert" :size="28" /><span>{{ t('设备连接中断，视频不可用（画面非实时）') }}</span>
      </div>
      <div v-else-if="connecting" class="overlay" data-test="video-connecting">
        <AppIcon name="spinner" :size="28" /><span>{{ t('正在连接视频…') }}</span>
        <small v-if="retries > 0 && !compact" class="hint">{{ t('视频流可能刚开始推送，正在自动重试') }}</small>
        <!-- the RC can report "pushing" while nothing reaches the media server (field test 2026-11-05, B): no other way back -->
        <button v-if="retries > 0 && !compact" class="btn btn-sm" data-test="video-restart" @click="startRec">{{ t('一直没有画面？重新开启视频') }}</button>
      </div>
      <div v-else-if="playError" class="overlay error" data-test="video-error">
        <AppIcon name="alert" :size="28" /><span>{{ playError }}</span>
        <div class="row">
          <button class="btn btn-sm" data-test="video-retry" @click="attach">{{ t('重试') }}</button>
          <button v-if="!compact" class="btn btn-sm" data-test="video-restart" @click="startRec">{{ t('重新开启视频') }}</button>
        </div>
      </div>
      <FlightHud v-if="hud && !compact" />
      <TargetSelectOverlay v-if="targets.selecting && !compact && tel.online" :video="video" :lens="st?.lens ?? 'wide'"
        :frame="playback?.protocol === 'MOCK' ? MOCK_FRAME : null" />
      <div v-if="!compact && controls" class="controls" :style="{ left: `calc(var(--sp-4) + ${props.reserveLeft}px)` }">
        <div class="seg" role="group" :aria-label="t('镜头')">
          <button v-for="l in lenses" :key="l" class="btn btn-sm" :class="{ 'btn-primary': st?.lens === l }" :disabled="!control.drcReady"
            :title="control.drcReady ? '' : t('切换镜头需要 DRC 链路')" @click="setLens(l)">{{ LENS_LABELS[l] ?? l }}</button>
        </div>
        <select v-model.number="quality" class="input" :aria-label="t('清晰度')" @change="setQuality">
          <option v-for="(lbl, q) in QUALITY_LABELS" :key="q" :value="Number(q)">{{ lbl }}</option>
        </select>
        <button class="btn btn-sm" @click="stopRec"><AppIcon name="stop" :size="15" />{{ t('关闭视频') }}</button>
        <CommandStatus class="status" :record="control.byAction('live')" compact />
      </div>
    </template>
    <div v-else class="placeholder">
      <AppIcon name="camera" :size="34" />
      <b>{{ tel.online ? t('视频未开启') : t('设备未连接') }}</b>
      <template v-if="!compact">
        <span class="dim">{{ tel.online ? t('选择清晰度后开启相机实时视频（RTMP 推流至自建流媒体服务器）') : t('设备连接后即可开启实时视频') }}</span>
        <div class="row">
          <select v-model.number="quality" class="input" :aria-label="t('清晰度')">
            <option v-for="(lbl, q) in QUALITY_LABELS" :key="q" :value="Number(q)">{{ lbl }}</option>
          </select>
          <button class="btn btn-primary" :disabled="!tel.online" data-test="start-video" @click="startRec"><AppIcon name="play" />{{ t('开启视频') }}</button>
        </div>
        <CommandStatus :record="control.byAction('live')" />
        <span v-if="st && !st.pushConfigured" class="warn">{{ t('未配置推流地址（LIVE_RTMP_PUSH），无法开启') }}</span>
      </template>
    </div>
  </div>
</template>

<style scoped>
.video {
  position: absolute;
  inset: 0;
  background: #000;
  overflow: hidden;
}
.player {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
}
.overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  color: #fff;
  background: rgba(0, 0, 0, 0.55);
}
.overlay.error {
  color: #fecaca;
}
.overlay .hint {
  font-size: var(--fs-xs);
  opacity: 0.8;
}
.controls {
  position: absolute;
  z-index: 6;
  left: var(--sp-4);
  right: var(--sp-4);
  bottom: var(--sp-4);
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  flex-wrap: wrap;
  padding: 6px var(--sp-2);
  border-radius: var(--r-ctl);
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
}
.controls .input {
  min-height: 32px;
}
.seg {
  display: flex;
  gap: 4px;
}
.status {
  max-width: 260px;
}
.placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
  color: #cbd5e1;
  background: radial-gradient(circle at center, #1b2430, #05080c);
  text-align: center;
  padding: var(--sp-4);
}
.placeholder b {
  color: #fff;
  font-size: var(--fs-lg);
}
.placeholder .dim {
  max-width: 420px;
  font-size: var(--fs-sm);
}
.warn {
  color: var(--warn);
  font-size: var(--fs-xs);
}
.compact .placeholder {
  gap: 4px;
}
</style>
