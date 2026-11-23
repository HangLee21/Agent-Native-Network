<script setup lang="ts">
/**
 * 监视台 time strip. Replay: play / ±5 s / speed. Live: 实时 badge; drag the timeline back to review (map, readings and
 * video go back), 回到实时 returns, reaching now returns by itself. 「⋯」: review speed (live) and how the camera footprint
 * is drawn.
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { t } from '@/i18n'
import type { WatchEngine } from './engine'
import { Timeline, clockStr, durStr } from './timeline'

const props = defineProps<{ engine: WatchEngine }>()
const E = props.engine
const cv = ref<HTMLCanvasElement | null>(null)
const wrap = ref<HTMLElement | null>(null)
const tip = ref<HTMLElement | null>(null)
let tl: Timeline | null = null
let ro: ResizeObserver | null = null
let lastStatic = 0
let staticDirty = true
const more = ref(false)

/** A fresh shallow copy each tick: the engine state is a plain object, so the same reference would not re-render. */
const ts = computed(() => { void E.ui.tick; return { ...E.S } })
const live = computed(() => E.ui.mode === 'live')
const reviewing = computed(() => E.ui.reviewing)
const ended = computed(() => { void E.ui.tick; return E.S.flights.length > 0 && E.S.flights.every((f) => isFinite(f.landT) && E.S.now > f.landT + 3000) })
const SPEEDS = [1, 2, 4, 8, 16]

onMounted(() => {
  tl = new Timeline(E, cv.value!, wrap.value!, tip.value!)
  ro = new ResizeObserver(() => { staticDirty = true })
  ro.observe(wrap.value!)
  window.addEventListener('resize', markStatic)
  document.addEventListener('click', closeMore)
})
onBeforeUnmount(() => { ro?.disconnect(); window.removeEventListener('resize', markStatic); document.removeEventListener('click', closeMore) })
function markStatic(): void { staticDirty = true }
function closeMore(e: MouseEvent): void { if (!(e.target as HTMLElement).closest('.more')) more.value = false }

/** Called by the page every frame. */
function frame(now: number, moved: boolean): void {
  if (!tl) return
  const cutMoves = E.S.mode === 'live' || (E.S.hideRoute && moved)
  if (staticDirty || (cutMoves && now - lastStatic > 120)) { staticDirty = false; lastStatic = now; tl.drawStatic() }
  tl.draw()
}
defineExpose({ frame, invalidate: markStatic, applyTheme: () => { tl?.applyTheme(); staticDirty = true } })

function speed(v: number): void { E.S.speed = v; E.bump() }
function revSpeed(v: number): void { E.S.revSpeed = v; E.bump() }
function footMode(v: 'gimbal' | 'nadir'): void { E.S.footMode = v; E.bump() }
function charts(): void { E.S.showCharts = !E.S.showCharts; staticDirty = true; E.bump() }
</script>

<template>
  <section class="wt" :class="{ live }" :aria-label="t('时间轴')">
    <div class="transport">
      <template v-if="!live">
        <button class="play" :aria-label="E.ui.playing ? t('暂停') : t('播放')" data-test="watch-play" @click="E.togglePlay()">
          <svg viewBox="0 0 16 16" aria-hidden="true"><template v-if="E.ui.playing"><rect x="3.5" y="2.5" width="3" height="11" rx=".5" fill="currentColor" /><rect x="9.5" y="2.5" width="3" height="11" rx=".5" fill="currentColor" /></template><path v-else d="M4 2.5v11l9.5-5.5z" fill="currentColor" /></svg>
        </button>
        <button class="btn btn-sm" @click="E.seek(E.S.t - 5000)">−5 s</button>
        <button class="btn btn-sm" @click="E.seek(E.S.t + 5000)">+5 s</button>
        <div class="clock"><span class="m">{{ ts.align === 'takeoff' ? durStr(ts.t - ts.refLift, true) : clockStr(ts.t, true) }}</span><span class="s">{{ durStr(ts.t - ts.refLift, true) }}</span></div>
        <div class="seg mono" role="group" :aria-label="t('播放倍速')">
          <button v-for="v in SPEEDS" :key="v" :aria-pressed="ts.speed === v" @click="speed(v)">{{ v }}×</button>
        </div>
        <span class="grow" />
        <span class="hint">{{ t('滚轮缩放时间轴 · 点按或拖动定位 · 空格播放') }}</span>
      </template>
      <template v-else-if="!reviewing">
        <span class="livedot" :class="{ ended }">{{ ended ? t('全部已降落') : t('实时') }}</span>
        <span class="num dim">{{ ts.flights.length ? t('起飞后 {d}', { d: durStr(Math.max(0, Math.min(ts.now, ts.lastLand) - ts.refLift)) }) : t('等待飞机上线') }}</span>
        <span class="grow" />
        <span class="hint">{{ t('拖动时间轴可以回看') }}</span>
      </template>
      <template v-else>
        <button class="play" :aria-label="ts.revPlaying ? t('暂停回看') : t('继续回看')" @click="E.togglePlay()">
          <svg viewBox="0 0 16 16" aria-hidden="true"><template v-if="ts.revPlaying"><rect x="3.5" y="2.5" width="3" height="11" rx=".5" fill="currentColor" /><rect x="9.5" y="2.5" width="3" height="11" rx=".5" fill="currentColor" /></template><path v-else d="M4 2.5v11l9.5-5.5z" fill="currentColor" /></svg>
        </button>
        <span class="revlab"><b>{{ t('回看') }}</b><span class="m">{{ clockStr(ts.t, true) }}</span><span class="k">{{ t('比实时晚 {d}', { d: durStr(ts.now - ts.t) }) }}{{ ts.revSpeed !== 1 ? ' · ' + t('{x}× 播放', { x: ts.revSpeed }) : '' }}</span></span>
        <button class="btn btn-sm btn-primary golive" data-test="watch-go-live" @click="E.goLive()"><span class="ld" />{{ t('回到实时') }}</button>
        <span class="grow" />
      </template>
      <button class="btn btn-sm" :aria-pressed="ts.showCharts" @click="charts">{{ t('曲线') }}</button>
      <div class="more">
        <button class="btn btn-sm morebtn" :aria-label="t('更多选项')" :aria-expanded="more" data-test="watch-more" @click="more = !more">⋯</button>
        <div v-if="more" class="pop">
          <div v-if="live" class="opt">
            <b>{{ t('回看倍速') }}</b>
            <div class="seg mono"><button v-for="v in [1, 2, 4, 8]" :key="v" :aria-pressed="ts.revSpeed === v" @click="revSpeed(v)">{{ v }}×</button></div>
            <span>{{ t('拖动时间轴回看时，视频和地图按这个速度往前放；追上此刻就自动回到实时。') }}</span>
          </div>
          <div class="opt">
            <b>{{ t('相机画面范围') }}</b>
            <div class="seg">
              <button :aria-pressed="ts.footMode === 'gimbal'" @click="footMode('gimbal')">{{ t('按云台角度') }}</button>
              <button :aria-pressed="ts.footMode === 'nadir'" data-test="watch-foot-nadir" @click="footMode('nadir')">{{ t('画在飞机正下方') }}</button>
            </div>
            <span>{{ t('按云台角度：云台往前看时，范围画在飞机前方。画在飞机正下方：不管云台俯仰，都当作朝下拍，方向仍跟云台。「相机看过的区域」也按这里算。') }}</span>
          </div>
        </div>
      </div>
    </div>
    <div ref="wrap" class="tlwrap">
      <canvas ref="cv" />
      <div ref="tip" class="tip" hidden />
    </div>
  </section>
</template>

<style scoped>
.wt { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; min-width: 0; }
.transport { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.play { width: 34px; height: 30px; border-radius: 4px; border: 1px solid var(--text); background: var(--text); color: var(--bg); display: grid; place-items: center; cursor: pointer; }
.play svg { width: 14px; height: 14px; }
.clock { display: grid; line-height: 1.15; margin: 0 8px 0 4px; min-width: 148px; }
.clock .m { font: 500 19px var(--font-num); letter-spacing: -.01em; }
.clock .s { font: 400 11px var(--font-num); color: var(--text-dim); }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.seg button { border: 0; background: none; height: 26px; padding: 0 9px; font-size: 12px; color: var(--text-dim); cursor: pointer; white-space: nowrap; }
.seg button + button { border-left: 1px solid var(--border); }
.seg button[aria-pressed='true'] { background: var(--text); color: var(--bg); }
.seg.mono button { font-family: var(--font-num); font-size: 11.5px; }
.grow { flex: 1; }
.hint { color: var(--text-dim); font-size: 11.5px; }
.dim { color: var(--text-dim); font-size: 12px; }
.livedot { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 12px; color: var(--danger); }
.livedot::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--danger); animation: pulse 1.6s ease-in-out infinite; }
.livedot.ended { color: var(--text-dim); }
.livedot.ended::before { background: var(--text-dim); animation: none; }
@keyframes pulse { 50% { opacity: .35; } }
.revlab { font-size: 12px; color: var(--text-dim); display: inline-flex; align-items: baseline; gap: 8px; }
.revlab b { color: var(--warn); font-weight: 600; }
.revlab .m { font: 500 17px var(--font-num); color: var(--text); }
.revlab .k { font-size: 11px; }
.golive .ld { width: 7px; height: 7px; border-radius: 50%; background: var(--danger); display: inline-block; margin-right: 6px; }
.btn[aria-pressed='true'] { border-color: var(--text-dim); }
.more { position: relative; }
.morebtn { width: 30px; justify-content: center; padding: 0; font-size: 15px; }
.pop { position: absolute; bottom: calc(100% + 6px); right: 0; z-index: 30; width: 300px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); padding: 12px; display: grid; gap: 12px; }
.opt { display: grid; gap: 6px; }
.opt b { font-size: 12px; color: var(--text-dim); }
.opt span { font-size: 11.5px; color: var(--text-dim); line-height: 1.5; }
.tlwrap { position: relative; padding: 4px 0 2px; }
.tlwrap canvas { display: block; width: 100%; touch-action: pan-y; cursor: col-resize; }
.tip { position: absolute; z-index: 20; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 6px 9px; font-size: 11.5px; line-height: 1.5; color: var(--text); box-shadow: var(--shadow); white-space: nowrap; }
.tip :deep(.r) { display: flex; align-items: center; gap: 6px; }
.tip :deep(.sw) { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.tip :deep(.k) { color: var(--text-dim); }
@media (max-width: 1360px) { .hint { display: none; } }
@media (prefers-reduced-motion: reduce) { .livedot::before { animation: none; } }
</style>
