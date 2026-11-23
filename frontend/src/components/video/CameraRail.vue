<script setup lang="ts">
/**
 * Camera, gimbal and video controls on the right edge of the monitor stage (R-13, R-14; ui-design.md
 * §2.2), visible whichever of video and map is the main view. Every button makes the same call as the
 * former video bar / "更多控制 → 云台与相机" button it replaces (same command keys and labels).
 */
import { computed, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import GimbalPad from '@/components/control/GimbalPad.vue'
import { controlApi } from '@/api/control'
import { LENS_LABELS, QUALITY_LABELS, liveApi } from '@/api/live'
import { useControlStore } from '@/stores/control'
import { useLiveStore } from '@/stores/live'
import { useTelemetryStore } from '@/stores/telemetry'
import { useTargetsStore } from '@/stores/targets'
import { useTasksStore } from '@/stores/tasks'
import { useDroneSn } from '@/composables/useDrone'
import { t } from '@/i18n'

/** The drone this component works on, fixed at setup (D-31). */
const sn = useDroneSn()

const control = useControlStore()
const live = useLiveStore()
const tel = useTelemetryStore()
const targets = useTargetsStore()
const tasks = useTasksStore()

const open = ref<null | 'zoom' | 'gimbal' | 'video'>(null)
const zoom = ref(5)
const quality = ref(0)
const ZOOM_STEPS = [2, 3, 5, 7, 10, 14, 20, 28, 40, 56, 80, 112, 160, 200]
const ZOOM_PRESETS = [2, 5, 10, 20, 56, 200]

const st = computed(() => live.status)
const streaming = computed(() => !!st.value?.streaming)
const lenses = computed(() => (st.value?.lenses ?? []).map((x) => (x === 'ir' ? 'thermal' : x)))
const drc = computed(() => control.drcReady)
const canSelect = computed(() => drc.value && streaming.value)
/** Zoom of the picture on screen for the gimbal speed: the camera's reported factor on the zoom lens, else 1. */
const gimbalZoom = computed(() => (st.value?.lens === 'zoom' ? (tel.drone?.zoomFactor ?? zoom.value) : 1))
const selectHint = computed(() => (!drc.value ? t('需要 DRC 链路（先获取控制权）') : !streaming.value ? t('先开启视频') : t('在视频中点选或框选目标（只转云台并测距）')))

watch(() => st.value?.quality, (q) => {
  if (q !== undefined && q !== null) quality.value = q
}, { immediate: true })

const toggle = (k: 'zoom' | 'gimbal' | 'video') => (open.value = open.value === k ? null : k)
const setLens = (l: string) => control.run('live', t('切换镜头：{lens}', { lens: LENS_LABELS[l] ?? l }), () => liveApi(sn).lens(l))
const photo = () => control.run('payload', t('拍照'), () => controlApi(sn).photo())
const recStart = () => control.run('payload', t('开始录像'), () => controlApi(sn).recordStart())
const recStop = () => control.run('payload', t('停止录像'), () => controlApi(sn).recordStop())
const GIMBAL_LABEL: Record<number, string> = { 0: t('云台回中'), 1: t('云台向下'), 2: t('云台偏航回中'), 3: t('云台俯仰向下') }
const gimbal = (mode: number) => control.run('payload', GIMBAL_LABEL[mode] ?? t('云台回中'), () => controlApi(sn).gimbalReset(mode))
const doZoom = () => control.run('payload', t('变焦 {n}×', { n: zoom.value }), () => controlApi(sn).zoom(zoom.value))

function stepZoom(dir: 1 | -1): void {
  const next = dir > 0 ? ZOOM_STEPS.find((z) => z > zoom.value) : [...ZOOM_STEPS].reverse().find((z) => z < zoom.value)
  if (next === undefined) return
  zoom.value = next
  void doZoom()
}
function preset(f: number): void {
  zoom.value = f
  open.value = null
  void doZoom()
}

function setQuality(q: number): void {
  quality.value = q
  if (streaming.value) void control.run('live', t('设置直播清晰度'), () => liveApi(sn).quality(q))
}
const startVideo = () => control.run('live', t('开启直播'), () => liveApi(sn).start(quality.value))
const stopVideo = () => control.run('live', t('停止直播'), () => liveApi(sn).stop())

function toggleSelect(): void {
  targets.selecting = !targets.selecting
  if (targets.selecting) tasks.show('tgt')
}
</script>

<template>
  <div class="cam-rail" role="toolbar" :aria-label="t('相机与云台')" aria-orientation="vertical" data-test="camera-rail">
    <span v-if="!drc" class="lock">{{ t('相机需 DRC') }}</span>
    <div class="grp" role="group" :aria-label="t('镜头')">
      <button v-for="l in lenses" :key="l" class="lens" :class="{ on: st?.lens === l }" :disabled="!drc" :aria-pressed="st?.lens === l"
        :title="drc ? '' : t('切换镜头需要 DRC 链路')" :data-test="`lens-${l}`" @click="setLens(l)">{{ LENS_LABELS[l] ?? l }}</button>
    </div>
    <span class="sep" />
    <button class="ico" :aria-label="t('放大')" :disabled="!drc" data-test="zoom-in" @click="stepZoom(1)"><AppIcon name="plus" :size="18" /></button>
    <button class="zval num" :aria-label="t('输入变焦倍数')" :aria-expanded="open === 'zoom'" :disabled="!drc" data-test="zoom-open" @click="toggle('zoom')">{{ zoom }}×</button>
    <button class="ico" :aria-label="t('缩小')" :disabled="!drc" data-test="zoom-out" @click="stepZoom(-1)"><AppIcon name="minus" :size="18" /></button>
    <span class="sep" />
    <button class="ico big" :class="{ on: targets.selecting }" :aria-pressed="targets.selecting" :aria-label="t('在视频中选目标')" :title="selectHint"
      :disabled="!canSelect && !targets.selecting" data-test="rail-select-target" @click="toggleSelect"><AppIcon name="crosshair" :size="22" /></button>
    <button class="shutter" :aria-label="t('拍照')" :title="t('拍照')" :disabled="!drc" data-test="rail-photo" @click="photo" />
    <button class="rec" :aria-label="t('开始录像')" :title="t('开始录像')" :disabled="!drc" data-test="rail-record" @click="recStart"><span /></button>
    <button class="recstop" :title="t('停止录像')" :disabled="!drc" data-test="rail-record-stop" @click="recStop"><span class="sq" />{{ t('停录') }}</button>
    <span class="sep" />
    <button class="ico big" :class="{ on: open === 'gimbal' }" :aria-label="t('云台')" :aria-expanded="open === 'gimbal'" :disabled="!drc" data-test="rail-gimbal" @click="toggle('gimbal')">
      <AppIcon name="gimbal" :size="20" /><span class="cap">{{ t('云台') }}</span>
    </button>
    <button class="ico big" :class="{ on: open === 'video' }" :aria-label="t('视频设置')" :aria-expanded="open === 'video'" data-test="rail-video" @click="toggle('video')">
      <AppIcon name="sliders" :size="18" /><span class="cap">{{ t('视频') }}</span>
    </button>

    <div v-if="open === 'zoom'" class="fly zoomfly" role="group" :aria-label="t('变焦')">
      <label class="zin">{{ t('倍数') }} <input v-model.number="zoom" class="input num" type="number" min="2" max="200" />×
        <button class="btn btn-sm btn-primary" :disabled="!drc" @click="doZoom(); open = null">{{ t('变焦') }}</button></label>
      <div class="presets"><button v-for="f in ZOOM_PRESETS" :key="f" class="btn btn-sm" :disabled="!drc" @click="preset(f)">{{ f }}×</button></div>
    </div>
    <div v-if="open === 'gimbal'" class="fly gimbalfly" role="group" :aria-label="t('云台控制')">
      <span class="fly-title">{{ t('按住方向转动，松开停止') }}</span>
      <GimbalPad pad :disabled="!drc" :zoom="gimbalZoom" @reset="gimbal" />
    </div>
    <div v-if="open === 'video'" class="fly videofly" role="group" :aria-label="t('视频设置')">
      <span class="fly-title">{{ t('清晰度') }}</span>
      <button v-for="(lbl, q) in QUALITY_LABELS" :key="q" class="opt" :class="{ on: quality === Number(q) }" :aria-pressed="quality === Number(q)" @click="setQuality(Number(q))">{{ lbl }}</button>
      <hr />
      <button v-if="streaming" class="opt" :disabled="!tel.online" data-test="rail-video-restart"
        :title="t('平台显示视频已开启却一直没有画面时用：再向遥控器发一次开启指令')" @click="startVideo(); open = null">{{ t('重新开启视频') }}</button>
      <button v-if="streaming" class="opt" data-test="rail-video-stop" @click="stopVideo(); open = null">{{ t('关闭视频') }}</button>
      <button v-else class="opt" :disabled="!tel.online" data-test="rail-video-start" @click="startVideo(); open = null">{{ t('开启视频') }}</button>
    </div>
  </div>
</template>

<style scoped>
.cam-rail {
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 950;
  width: 64px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  padding: 10px 0;
  border-radius: 14px;
  background: rgba(5, 8, 12, 0.78);
  border: 1px solid rgba(255, 255, 255, 0.14);
  color: #fff;
}
.lock {
  font-size: 11px;
  line-height: 1.3;
  color: var(--warn);
  text-align: center;
  padding: 0 4px;
}
.grp {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sep {
  width: 36px;
  height: 1px;
  background: rgba(255, 255, 255, 0.16);
}
button {
  font: inherit;
  cursor: pointer;
}
button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.lens {
  width: 48px;
  height: 28px;
  padding: 0;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.22);
  background: transparent;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}
.lens.on,
.ico.on {
  border-color: var(--accent);
  background: var(--accent);
  color: var(--accent-ink);
}
.ico {
  width: 40px;
  height: 30px;
  padding: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.ico.big {
  width: 44px;
  height: 44px;
  border-color: rgba(255, 255, 255, 0.22);
  background: transparent;
}
.cap {
  font-size: 10px;
}
.zval {
  min-width: 44px;
  height: 24px;
  padding: 0 4px;
  border-radius: 6px;
  border: 1px dashed rgba(255, 255, 255, 0.35);
  background: transparent;
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}
.shutter {
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 50%;
  border: 3px solid #fff;
  background: rgba(255, 255, 255, 0.18);
}
.rec {
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.75);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}
.rec span {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #f85149;
}
.recstop {
  width: 48px;
  height: 26px;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
  border-radius: 6px;
  border: 1px solid rgba(255, 255, 255, 0.3);
  background: transparent;
  color: #fff;
  font-size: 11px;
}
.recstop .sq {
  width: 8px;
  height: 8px;
  background: #fff;
}
.fly {
  position: absolute;
  right: 74px;
  box-sizing: border-box;
  padding: 10px;
  border-radius: 12px;
  background: var(--panel);
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  color: var(--text);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.zoomfly {
  top: 80px;
  width: 220px;
}
.gimbalfly {
  bottom: 40px;
  width: 210px;
}
.videofly {
  bottom: 0;
  width: 180px;
  gap: 2px;
}
.fly-title {
  font-size: var(--fs-xs);
  color: var(--text-dim);
}
.zin {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-sm);
}
.zin .input {
  width: 70px;
  min-height: 32px;
}
.presets {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 4px;
}
.presets .btn {
  padding: 0;
}
.opt {
  min-height: 32px;
  padding: 0 8px;
  border-radius: 6px;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: var(--fs-sm);
  text-align: left;
}
.opt.on {
  background: color-mix(in srgb, var(--accent) 20%, transparent);
  color: var(--accent);
  font-weight: 700;
}
.opt:hover:not(:disabled) {
  background: var(--panel-2);
}
hr {
  width: 100%;
  border: 0;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}
</style>
