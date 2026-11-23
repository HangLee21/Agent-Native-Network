<script setup lang="ts">
/**
 * A dog's video on the 监视台 (D-40; monitor-station-design.md «机器狗»):
 * - live: the dog's colour stream over WebRTC (the dog streams while someone looks; the tile tells the backend);
 *   reviewing in live mode keeps the live picture (dog recordings are fetched only after the record ends);
 * - replay and 假装实时: the dog record's archived video, kept on the timeline cursor like a drone's.
 */
import { computed, ref, watch } from 'vue'
import { t } from '@/i18n'
import Dog2Video from '@/components/dogv2/Dog2Video.vue'
import { dogRecordsApi } from '@/api/dogRecords'
import { videoAt } from '@/utils/replay'
import type { WatchEngine } from './engine'
import type { WatchFlight } from './model'
import { clockStr } from './timeline'

const props = defineProps<{ engine: WatchEngine; dogId: string; label: string; color: string; flight: WatchFlight | null; big: boolean }>()
const emit = defineEmits<{ enlarge: []; restore: [] }>()

const E = props.engine
const recEl = ref<HTMLVideoElement | null>(null)
const fromParts = computed(() => { void E.ui.tick; return E.S.mode === 'replay' || E.ui.fake })

/** The colour stream of this dog: "rgb", else the first whose name has rgb (S10 wrist-rgb), else the first. */
const view = computed(() => E.ui.dogs[props.dogId] ?? null)
const stream = computed(() => {
  const keys = Object.keys(view.value?.video ?? {})
  return keys.find((k) => k === 'rgb') ?? keys.find((k) => k.includes('rgb')) ?? keys[0] ?? null
})
const liveVideo = computed(() => (stream.value ? view.value?.video?.[stream.value] : undefined))

// ---------------------------------------------------------------- recorded video (replay parts)
const replaySrc = ref<string | null>(null)
const missing = ref<string | null>(null)

function replayPos(): { src: string; seconds: number } | null {
  const f = props.flight, d = f?.input.detail, id = f?.input.sessionId
  if (!id || !d) { missing.value = t('这段记录没有录像'); return null }
  if (d.videoStatus === 'PENDING' || d.videoStatus === 'ARCHIVING') { missing.value = t('录像还在整理，记录结束后几分钟可看'); return null }
  const parts = d.videoParts ?? []
  if (d.videoStatus !== 'READY' || !parts.length) { missing.value = t('这段记录没有录像'); return null }
  const p = videoAt(parts, E.S.t, d.videoOffsetMs ?? 0)
  if (!p) { missing.value = t('这一段没有录像'); return null }
  missing.value = null
  return { src: dogRecordsApi.videoUrl(id, p.index), seconds: p.seconds }
}

function sync(): void {
  if (!fromParts.value) return
  const S = E.S
  const p = replayPos()
  if (!p) { replaySrc.value = null; return }
  if (replaySrc.value !== p.src) replaySrc.value = p.src
  const v = recEl.value
  if (!v || v.readyState < 1) return
  const playing = S.mode === 'replay' ? S.playing && S.speed <= 8 : S.reviewing ? S.revPlaying : true
  const rate = S.mode === 'replay' ? S.speed : S.reviewing ? S.revSpeed : 1
  const drift = Math.abs(v.currentTime - p.seconds)
  if (playing) {
    if (v.playbackRate !== rate) v.playbackRate = rate
    if (v.paused) void v.play().catch(() => undefined)
    if (drift > 0.8 * Math.max(1, rate / 2)) v.currentTime = p.seconds
  } else {
    if (!v.paused) v.pause()
    if (drift > 0.15) v.currentTime = p.seconds
  }
}
watch(() => E.ui.tick, sync)

const badge = computed(() => {
  void E.ui.tick
  if (E.S.mode === 'replay') return { text: t('录像 {time}', { time: clockStr(E.S.t) }), live: false }
  return { text: t('实时'), live: true }
})
</script>

<template>
  <figure class="wv" :class="{ big }" :style="{ '--c': color }" data-test="watch-dog-video">
    <template v-if="fromParts">
      <video v-show="replaySrc" ref="recEl" class="v" :src="replaySrc ?? undefined" muted playsinline preload="auto" @loadedmetadata="sync" />
      <div v-if="!replaySrc" class="state"><div><b>{{ missing ?? t('这段记录没有录像') }}</b></div></div>
    </template>
    <template v-else>
      <Dog2Video v-if="stream" class="v live" :dog="dogId" :stream="stream" :video="liveVideo" />
      <div v-else class="state"><div><b>{{ t('{label} 没有画面', { label }) }}</b></div></div>
    </template>
    <figcaption class="cap"><span class="sw" /><span>{{ label }}</span><span class="vs">{{ t('机器狗') }}</span></figcaption>
    <span v-if="fromParts ? !!replaySrc : !!stream" class="badge" :class="{ live: badge.live }">{{ badge.text }}</span>
    <button v-if="!big" class="exp" :title="t('放到大画面（地图换到这里）')" :aria-label="t('放到大画面')" @click.stop="emit('enlarge')">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" stroke-linecap="round" stroke-linejoin="round" /></svg>
    </button>
    <button v-else class="back btn btn-sm" @click.stop="emit('restore')">{{ t('换回地图') }}</button>
  </figure>
</template>

<style scoped>
.wv { position: absolute; inset: 0; margin: 0; background: #05080a; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.wv.big { border-color: color-mix(in srgb, var(--c) 55%, var(--border)); }
.v { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; background: #05080a; }
.v.live { aspect-ratio: auto; border-radius: 0; }
.state { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; color: #9fb0b7; font-size: 12px; padding: 12px; z-index: 2; }
.state b { display: block; color: #dfe6e8; font-weight: 500; font-size: 13px; }
.cap { position: absolute; left: 8px; top: 7px; z-index: 3; display: flex; align-items: center; gap: 6px; padding: 3px 8px 3px 6px; border-radius: 3px; background: rgba(6, 10, 12, .62); color: #eef3f4; font-weight: 600; font-size: 12px; }
.cap .sw { width: 10px; height: 10px; border-radius: 3px; background: var(--c); }
.cap .vs { font-weight: 400; font-size: 11px; color: #b9c5ca; }
.badge { position: absolute; right: 8px; top: 7px; z-index: 3; display: inline-flex; align-items: center; gap: 6px; padding: 3px 7px; border-radius: 3px; background: rgba(6, 10, 12, .62); color: #eef3f4; font: 500 11px var(--font-num); }
.badge.live::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: #ef4444; animation: pulse 1.6s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: .35; } }
.exp { position: absolute; left: 8px; bottom: 6px; z-index: 4; width: 28px; height: 28px; border-radius: 3px; border: 0; background: rgba(6, 10, 12, .7); color: #eef3f4; display: grid; place-items: center; cursor: pointer; opacity: .55; padding: 0; }
.wv:hover .exp, .exp:focus-visible { opacity: 1; }
.exp svg { width: 15px; height: 15px; }
.back { position: absolute; left: 10px; bottom: 10px; z-index: 4; }
@media (prefers-reduced-motion: reduce) { .badge.live::before { animation: none; } }
</style>
