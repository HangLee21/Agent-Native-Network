<script setup lang="ts">
/**
 * One dog stream over WebRTC from MediaMTX (dog/<id>-<stream>). While shown, tells the backend about every 20 s
 * so the dog keeps pushing; the dog stops pushing a minute after nobody looks.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { playWhep } from '@/api/live'
import { ApiError } from '@/api/http'
import { dog2Api, type Dog2Video } from '@/api/dogv2'
import { t } from '@/i18n'

const props = defineProps<{ dog: string; stream: string; video: Dog2Video | undefined }>()
const el = ref<HTMLVideoElement | null>(null)
const problem = ref<string | null>(null)
const playing = ref(false)
const wasPlaying = ref(false)
const canPlay = computed(() => props.video?.ready ?? props.video?.state === 'live')
const CONNECT_WINDOW_MS = 25_000
const RETRY_DELAY_MS = 1_500
let pc: RTCPeerConnection | null = null
let keep: number | null = null
let request: AbortController | null = null
let retry: number | undefined
let deadline: number | undefined

function ask(): void {
  void dog2Api.video(props.dog, props.stream).catch(() => undefined)
}

function close(): void {
  request?.abort()
  request = null
  window.clearTimeout(retry)
  retry = undefined
  pc?.close()
  pc = null
  playing.value = false
  if (el.value) el.value.srcObject = null
}

function fail(message: string): void {
  close()
  window.clearTimeout(deadline)
  problem.value = message
}

function startWindow(): void {
  close()
  problem.value = null
  window.clearTimeout(deadline)
  deadline = window.setTimeout(() => fail(t('暂未收到视频')), CONNECT_WINDOW_MS)
}

function retryPlayback(): void {
  const reconnecting = playing.value
  if (reconnecting) startWindow()
  else close()
  retry = window.setTimeout(() => {
    retry = undefined
    void play()
  }, RETRY_DELAY_MS)
}

async function play(): Promise<void> {
  const target = el.value
  const url = props.video?.whep
  if (!target || !url || !canPlay.value || pc || request || problem.value) return
  const pending = new AbortController()
  request = pending
  try {
    const conn = await playWhep(url, target, pending.signal)
    if (pending.signal.aborted) {
      conn.close()
      return
    }
    pc = conn
    conn.onconnectionstatechange = () => {
      if (pc === conn && (conn.connectionState === 'failed' || conn.connectionState === 'disconnected')) {
        retryPlayback()
      }
    }
    conn.onconnectionstatechange(new Event('connectionstatechange'))
  } catch (e) {
    if (pending.signal.aborted) return
    if (e instanceof ApiError && e.status >= 400 && e.status < 500 && e.status !== 404) {
      fail(e.message)
      return
    }
    retryPlayback()
  }
}

function played(): void {
  if (!pc && !request) return
  playing.value = true
  wasPlaying.value = true
  window.clearTimeout(deadline)
}

function retryNow(): void {
  startWindow()
  ask()
  void play()
}

watch(() => [props.dog, props.stream], () => {
  wasPlaying.value = false
  retryNow()
  if (keep !== null) window.clearInterval(keep)
  keep = window.setInterval(ask, 20000)
}, { immediate: true })
watch([() => props.video?.whep, canPlay, el], () => {
  if (playing.value || (problem.value && canPlay.value)) startWindow()
  else close()
  void play()
}, { flush: 'post' })

onBeforeUnmount(() => {
  close()
  window.clearTimeout(deadline)
  if (keep !== null) window.clearInterval(keep)
})
</script>

<template>
  <div class="d2v">
    <video ref="el" autoplay muted playsinline @playing="played" />
    <div v-if="!video?.whep" class="hint">{{ t('服务器没有配置视频播放地址') }}</div>
    <div v-else-if="problem" class="hint" role="status">
      <span>{{ problem }} <button type="button" class="btn btn-sm" @click="retryNow">{{ t('重试') }}</button></span>
    </div>
    <div v-else-if="!playing" class="hint" role="status">
      {{ wasPlaying ? t('视频正在重连…') : t('正在等待狗的视频…') }}
    </div>
  </div>
</template>

<style scoped>
.d2v {
  position: relative;
  background: #000;
  border-radius: var(--r-panel);
  overflow: hidden;
  aspect-ratio: 16 / 9;
}
video {
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.hint {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: var(--text-dim);
  font-size: var(--fs-sm);
}
</style>
