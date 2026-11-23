<script setup lang="ts">
/**
 * 监视台 map tile. Large: tools (斜视 / 俯视, drag = move or rotate, 视野, auto-rotate, layers), compass and zoom.
 * Small (its place was taken by a video): no interaction; a click swaps it back.
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '@/i18n'
import type { WatchEngine } from './engine'
import { MAX_PITCH, MapScene } from './mapScene'
import { MODE, PHASE_LABEL, phaseOf } from './model'
import { clockStr } from './timeline'

const props = defineProps<{ engine: WatchEngine; small: boolean }>()
const emit = defineEmits<{ restore: [] }>()
const E = props.engine

const box = ref<HTMLElement | null>(null)
const mapEl = ref<HTMLElement | null>(null)
const overlay = ref<HTMLCanvasElement | null>(null)
const tip = ref<HTMLElement | null>(null)
let scene: MapScene | null = null
let ro: ResizeObserver | null = null
const pitch = ref(MAX_PITCH)
const bearing = ref(0)
const openPop = ref<'' | 'layers' | 'rotate'>('')

onMounted(() => {
  scene = new MapScene(E, mapEl.value!, overlay.value!)
  scene.onViewChange = () => { pitch.value = scene?.pitch() ?? 0; bearing.value = scene?.bearing() ?? 0 }
  scene.onHover = (h) => {
    const el = tip.value
    if (!el) return
    if (!h || props.small) { el.hidden = true; return }
    const f = h.f, i = h.i
    const ph = E.S.hideRoute ? PHASE_LABEL[phaseOf(f.mode[i])] : (MODE[f.mode[i]!] ?? '')
    el.innerHTML = `<div class="r"><span class="sw" style="background:${f.color}"></span><b>${f.label}</b>&nbsp;<span class="num">${clockStr(f.t[i]!, true)}</span></div>`
      + `<div class="num">${t('高度 {h} m · 水平 {v} m/s', { h: f.rel[i]!.toFixed(1), v: f.hs[i]!.toFixed(1) })}</div><div class="num">${ph}${Number.isFinite(f.bat[i]) ? ' · ' + t('电量 {b}%', { b: f.bat[i] }) : ''}</div>`
      + `<div class="k">${E.S.mode === 'live' ? t('点击回看这一刻') : t('点击跳到这一刻')}</div>`
    el.hidden = false
    const W = box.value!.clientWidth, H = box.value!.clientHeight, tw = el.offsetWidth, th = el.offsetHeight
    let lx = h.x + 14, ly = h.y + 14
    if (lx + tw > W - 6) lx = h.x - tw - 14
    if (ly + th > H - 6) ly = h.y - th - 12
    el.style.left = Math.max(6, lx) + 'px'; el.style.top = Math.max(6, ly) + 'px'
  }
  scene.mount()
  ro = new ResizeObserver(() => scene?.resize())
  ro.observe(box.value!)
  scene.resize()
})
onBeforeUnmount(() => { ro?.disconnect(); scene?.destroy(); scene = null })

watch(() => props.small, (s) => { void nextTick(() => { scene?.setInteractive(!s); scene?.resize() }) })
// first data (or another set of drones): centre on it
watch(() => E.ui.flightsKey, (k, old) => {
  if (!scene || !k) return
  const before = new Set((old ?? '').split(',')), now = k.split(',')
  if (!old || now.every((id) => !before.has(id))) { scene.updateGeo(); scene.jumpToFit(); if (E.S.cam === 'free') E.S.cam = 'all' }
})

const tick = computed(() => E.ui.tick)
const cam = computed(() => { void tick.value; return E.S.cam })
const drag = computed(() => { void tick.value; return E.S.drag })
const autoRotate = computed(() => { void tick.value; return E.S.autoRotate })
const camOptions = computed(() => { void tick.value; return [{ v: 'all', l: t('全部') }, ...E.S.flights.map((f) => ({ v: f.id, l: f.label }))] })
const layerItems = computed(() => {
  void tick.value
  const items: [keyof typeof E.S.layers, string][] = []
  if (!E.S.hideRoute) items.push(['route', t('计划航线与航点')], ['plan', t('飞行器规划路径')])
  items.push(['track', t('实际轨迹')], ['curtain', t('地面投影与垂幕')], ['seen', t('相机看过的区域')], ['foot', t('相机此刻的画面范围')], ['los', t('云台视线')], ['sep', t('两机连线与间距')], ['rc', t('遥控器位置')], ['labels', t('文字标注')], ['roads', t('道路与地名')])
  return items
})
const ROTATE = [{ v: 0, l: t('关') }, { v: 1, l: t('慢') }, { v: 2, l: t('中') }, { v: 3, l: t('快') }]

function setCam(v: string): void { scene?.setCam(v) }
function setDrag(v: 'pan' | 'rotate'): void { scene?.setDrag(v); E.bump() }
function setRotate(v: number): void { E.S.autoRotate = v; E.bump() }
function toggleLayer(k: keyof typeof E.S.layers, on: boolean): void { E.S.layers[k] = on; if (k === 'roads') scene?.applyRoads(); E.bump(); scene?.repaint() }
function pop(p: 'layers' | 'rotate'): void { openPop.value = openPop.value === p ? '' : p }
function onDocClick(e: MouseEvent): void { if (!(e.target as HTMLElement).closest('.wm-pop, .wm-popbtn')) openPop.value = '' }
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

/** Called by the page every frame: moving aircraft are redrawn every frame (a 20/s cap made them visibly step). */
function frame(dt: number, moved: boolean): void {
  if (!scene) return
  scene.step(dt)
  if (moved) scene.repaint()
}
defineExpose({ frame, applyTheme: () => scene?.applyTheme(), repaint: () => scene?.repaint() })
</script>

<template>
  <div ref="box" class="wm" :class="{ small, rot: drag === 'rotate' }" data-test="watch-map">
    <div ref="mapEl" class="map" />
    <canvas ref="overlay" class="overlay" />
    <template v-if="!small">
      <div class="tools">
        <div class="seg" role="group" :aria-label="t('视角')">
          <button :aria-pressed="pitch >= MAX_PITCH - 0.5" @click="scene?.setView('tilt')">{{ t('斜视') }}</button>
          <button :aria-pressed="pitch <= 0.5" @click="scene?.setView('top')">{{ t('俯视') }}</button>
        </div>
        <div class="grp" :title="t('左键拖动地图时做什么；右键拖动总是旋转')">
          <span class="gl">{{ t('拖动') }}</span>
          <div class="seg" role="group" :aria-label="t('拖动地图')">
            <button :aria-pressed="drag === 'pan'" @click="setDrag('pan')">{{ t('移动') }}</button>
            <button :aria-pressed="drag === 'rotate'" data-test="watch-drag-rotate" @click="setDrag('rotate')">{{ t('旋转') }}</button>
          </div>
        </div>
        <div class="grp">
          <span class="gl">{{ t('视野') }}</span>
          <div class="seg" role="group" :aria-label="t('视野')">
            <button v-for="o in camOptions" :key="o.v" :aria-pressed="cam === o.v" :title="o.v === 'all' ? t('自动把所有飞机放进画面') : t('镜头跟着 {label}', { label: o.l })" @click="setCam(o.v)">{{ o.l }}</button>
          </div>
        </div>
        <div class="popwrap">
          <button class="btn btn-sm wm-popbtn" :class="{ on: autoRotate > 0 }" data-test="watch-autorotate" @click="pop('rotate')">{{ t('自动旋转') }}{{ autoRotate ? ` · ${ROTATE[autoRotate]!.l}` : '' }}</button>
          <div v-if="openPop === 'rotate'" class="wm-pop">
            <b>{{ t('自动旋转') }}</b>
            <div class="seg">
              <button v-for="r in ROTATE" :key="r.v" :aria-pressed="autoRotate === r.v" @click="setRotate(r.v)">{{ r.l }}</button>
            </div>
            <span>{{ t('绕当前画面中心慢慢转。自己拖动地图时暂停，松手后接着转。') }}</span>
          </div>
        </div>
        <div class="popwrap">
          <button class="btn btn-sm wm-popbtn" @click="pop('layers')">{{ t('图层') }}</button>
          <div v-if="openPop === 'layers'" class="wm-pop">
            <label v-for="[k, n] in layerItems" :key="k" class="chk"><input type="checkbox" :checked="E.S.layers[k]" @change="toggleLayer(k, ($event.target as HTMLInputElement).checked)"> {{ n }}</label>
          </div>
        </div>
      </div>
      <div class="nav">
        <button class="navbtn" :title="t('朝北')" @click="scene?.north()">
          <svg viewBox="0 0 16 16" aria-hidden="true" :style="{ transform: `rotate(${-bearing}deg)` }"><path d="M8 1.5 10.4 8H5.6Z" fill="#e5484d" /><path d="M8 14.5 5.6 8h4.8Z" fill="currentColor" opacity=".55" /></svg>
        </button>
        <div class="zoom">
          <button class="navbtn" :title="t('放大')" @click="scene?.zoom(1)"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg></button>
          <button class="navbtn" :title="t('缩小')" @click="scene?.zoom(-1)"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg></button>
        </div>
      </div>
      <div class="legend">{{ E.ui.hideRoute ? t('高度从各自起飞点算起') : t('高度从各自起飞点算起 · 虚线为计划航线') }}</div>
    </template>
    <button v-else class="restore" data-test="watch-map-restore" @click="emit('restore')"><span>{{ t('地图') }}</span><b>{{ t('点一下换回大画面') }}</b></button>
    <div ref="tip" class="tip" hidden />
  </div>
</template>

<style scoped>
.wm { position: absolute; inset: 0; background: #1d2428; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.map { position: absolute; inset: 0; }
.overlay { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2; }
.wm.hot :deep(.maplibregl-canvas-container) { cursor: pointer; }
.wm.rot :deep(.maplibregl-canvas-container) { cursor: move; }
.tools { position: absolute; top: 10px; left: 10px; display: flex; gap: 6px; flex-wrap: wrap; align-items: center; z-index: 5; max-width: calc(100% - 70px); }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 4px; background: var(--panel); overflow: hidden; }
.seg button { border: 0; background: none; height: 26px; padding: 0 9px; font-size: 12px; color: var(--text-dim); cursor: pointer; white-space: nowrap; }
.seg button + button { border-left: 1px solid var(--border); }
.seg button:hover { background: var(--panel-2); color: var(--text); }
.seg button[aria-pressed='true'] { background: var(--text); color: var(--bg); }
.grp { display: inline-flex; align-items: center; gap: 6px; padding: 3px 4px 3px 8px; background: color-mix(in srgb, var(--panel) 88%, transparent); border: 1px solid var(--border); border-radius: 5px; }
.gl { font-size: 11px; color: var(--text-dim); }
.popwrap { position: relative; }
.btn.on { border-color: var(--accent); color: var(--accent); }
.wm-pop { position: absolute; top: calc(100% + 6px); left: 0; z-index: 30; width: 240px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow); padding: 12px; display: grid; gap: 6px; }
.wm-pop b { font-size: 12px; color: var(--text-dim); }
.wm-pop span { font-size: 11.5px; color: var(--text-dim); line-height: 1.5; }
.chk { display: flex; gap: 8px; align-items: center; font-size: 12.5px; cursor: pointer; }
.nav { position: absolute; top: 10px; right: 10px; z-index: 5; display: grid; gap: 6px; justify-items: end; }
.navbtn { width: 32px; height: 32px; border-radius: 4px; border: 1px solid var(--border); background: color-mix(in srgb, var(--panel) 92%, transparent); color: var(--text); display: grid; place-items: center; cursor: pointer; padding: 0; }
.navbtn svg { width: 16px; height: 16px; }
.zoom { display: grid; border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.zoom .navbtn { border: 0; border-radius: 0; }
.zoom .navbtn + .navbtn { border-top: 1px solid var(--border); }
.legend { position: absolute; left: 12px; bottom: 34px; z-index: 4; font: 400 10.5px/1.5 var(--font-num); color: #e8eef0; text-shadow: 0 0 3px rgba(0, 0, 0, .9); pointer-events: none; }
.restore { position: absolute; inset: 0; z-index: 6; border: 0; background: linear-gradient(transparent 55%, rgba(4, 8, 10, .55)); color: #eef3f4; cursor: pointer; display: flex; flex-direction: column; justify-content: flex-end; align-items: flex-start; gap: 2px; padding: 8px 10px; text-align: left; }
.restore span { font-weight: 600; font-size: 12px; }
.restore b { font-weight: 400; font-size: 11px; color: #cfd9dd; }
.wm.small :deep(.maplibregl-ctrl-bottom-left), .wm.small :deep(.maplibregl-ctrl-bottom-right) { display: none; }
.tip { position: absolute; z-index: 20; pointer-events: none; background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 6px 9px; font-size: 11.5px; line-height: 1.5; color: var(--text); box-shadow: var(--shadow); white-space: nowrap; }
.tip :deep(.r) { display: flex; align-items: center; gap: 6px; }
.tip :deep(.sw) { width: 8px; height: 8px; border-radius: 2px; display: inline-block; }
.tip :deep(.k) { color: var(--text-dim); }
:deep(.maplibregl-ctrl-scale) { background: rgba(10, 16, 18, .55); color: #e8eef0; border-color: #e8eef0; font: 400 10px var(--font-num); }
:deep(.maplibregl-ctrl-attrib) { font-size: 10px; background: rgba(0, 0, 0, .35) !important; color: #dfe6e8; }
:deep(.maplibregl-ctrl-attrib a) { color: #dfe6e8; }
</style>
