<script setup lang="ts">
/**
 * Audience page (docs/demo-design.md §6): full screen over the platform's top bar, no controls and no alerts.
 * Map with both aircraft, the dog and the scripted links; one camera (follows the stage unless the presenter
 * picks one); aircraft cards; the dog's semantic map in stage 3–4; the running message log.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { t } from '@/i18n'
import DemoMap from './DemoMap.vue'
import DemoVideo from './DemoVideo.vue'
import DemoCommLog from './DemoCommLog.vue'
import DemoStageBar from './DemoStageBar.vue'
import DemoSemanticMap from './DemoSemanticMap.vue'
import { useDemoStore } from './useDemoStore'
import { COLORS, EXEC_TEXT, STAGE_TEXT, stageIndex, type DemoDrone, type Label, type Stage } from './demoApi'

const demo = useDemoStore()
const now = ref(Date.now())
let timer = 0
onMounted(() => {
  demo.start()
  timer = window.setInterval(() => (now.value = Date.now()), 500)
})
onBeforeUnmount(() => window.clearInterval(timer))

const stage = computed<Stage>(() => demo.state?.stage ?? 'READY')
const idx = computed(() => stageIndex(stage.value))

const CAPTIONS: Partial<Record<Stage, string>> = {
  READY: t('两架无人机与机器狗在基地待命'),
  S1_EXPLORE: t('两架无人机并行出发，分头探索左右两片区域'),
  S1_RENDEZVOUS: t('两机汇合，交换探索信息，决定复查左侧区域'),
  S2_RESCAN: t('高空俯瞰全局，低空斜视细查：两个视角互补'),
  S3_TARGET: t('低空无人机识别出需要采样的目标，并算出它的坐标'),
  S4_GUIDE: t('无人机为没有地图的机器狗规划路径并实时引导'),
  DONE: t('机器狗抵达目标，任务完成'),
  ABORTED: t('演示暂停'),
}

const elapsed = computed(() => {
  const s = demo.state
  if (!s?.startedAt) return '00:00'
  const end = s.stage === 'DONE' ? s.stageAt.DONE ?? now.value : s.stage === 'ABORTED' ? s.stageAt.ABORTED ?? now.value : now.value
  const sec = Math.max(0, Math.floor((end - s.startedAt) / 1000))
  return `${String(Math.floor(sec / 60)).padStart(2, '0')}:${String(sec % 60).padStart(2, '0')}`
})

/** Which aircraft the camera follows: A while exploring, the low one from stage 2 on (its oblique view tells the story). */
const autoLabel = computed<Label>(() => (idx.value >= 3 ? demo.state?.lowLabel ?? 'B' : 'A'))
const picked = ref<Label | null>(null)
const camLabel = computed<Label>(() => picked.value ?? autoLabel.value)
const camDrone = computed<DemoDrone | null>(() => demo.byLabel[camLabel.value] ?? null)

function role(l: Label): string {
  const s = demo.state
  if (!s || idx.value < 3) return l === 'A' ? t('左侧探索') : t('右侧探索')
  return l === s.highLabel ? t('高空 · 全局') : t('低空 · 细查')
}

const showDog = computed(() => demo.state?.dogMode !== 'SKIP' && idx.value >= 4)

// a big caption for a few seconds when the stage changes
const banner = ref<string | null>(null)
let bannerTimer = 0
watch(stage, (s, prev) => {
  if (!prev || s === prev || s === 'READY') return
  banner.value = STAGE_TEXT[s]
  window.clearTimeout(bannerTimer)
  bannerTimer = window.setTimeout(() => (banner.value = null), 3500)
})

function fullscreen(): void {
  if (document.fullscreenElement) void document.exitFullscreen()
  else void document.documentElement.requestFullscreen()
}

function pct(d: DemoDrone): number {
  const e = d.execution
  if (e.state === 'COMPLETED') return 100
  return e.total ? Math.round((e.currentIndex / e.total) * 100) : 0
}
</script>

<template>
  <div class="show">
    <header class="top">
      <div class="title">
        <h1>{{ t('空地协同 · 自主探索演示') }}</h1>
        <p>{{ CAPTIONS[stage] }}</p>
      </div>
      <DemoStageBar class="bar" />
      <div class="clock">
        <span v-if="demo.state?.simulated" class="sim">{{ t('模拟数据') }}</span>
        <span class="t num">{{ elapsed }}</span>
      </div>
    </header>

    <main class="body">
      <section class="map">
        <DemoMap base-map-switch />
        <div class="legend">
          <span><i :style="{ background: COLORS.A }" />{{ t('{label} 机', { label: 'A' }) }}</span>
          <span><i :style="{ background: COLORS.B }" />{{ t('{label} 机', { label: 'B' }) }}</span>
          <span v-if="demo.state?.dogMode !== 'SKIP'"><i :style="{ background: COLORS.dog }" />{{ t('机器狗') }}</span>
          <span><i :style="{ background: COLORS.target }" />{{ t('采样目标') }}</span>
          <span><i class="line" />{{ t('通信链路') }}</span>
        </div>
        <transition name="fade">
          <div v-if="banner" class="banner">{{ banner }}</div>
        </transition>
      </section>

      <aside class="side">
        <div class="cam">
          <DemoVideo :drone="camDrone" :role="role(camLabel)" />
          <div class="cam-tabs">
            <button v-for="l in ['A', 'B'] as Label[]" :key="l" type="button" :class="{ on: camLabel === l }" :style="{ '--c': COLORS[l] }" @click="picked = l">{{ t('{label} 机画面', { label: l }) }}</button>
            <button type="button" :class="{ on: picked === null }" :title="t('按阶段自动切换')" @click="picked = null">{{ t('自动') }}</button>
          </div>
        </div>

        <div class="cards">
          <div v-for="l in ['A', 'B'] as Label[]" :key="l" class="card" :style="{ '--c': COLORS[l] }">
            <template v-if="demo.byLabel[l]">
              <div class="card-head">
                <b class="badge">{{ l }}</b>
                <span class="role">{{ role(l) }}</span>
                <span class="st" :class="demo.byLabel[l]!.execution.state.toLowerCase()">{{ EXEC_TEXT[demo.byLabel[l]!.execution.state] }}</span>
              </div>
              <div class="metrics">
                <div><span>{{ t('高度') }}</span><b class="num">{{ demo.byLabel[l]!.relativeHeight?.toFixed(1) ?? '--' }}<small>m</small></b></div>
                <div><span>{{ t('速度') }}</span><b class="num">{{ demo.byLabel[l]!.horizontalSpeed?.toFixed(1) ?? '--' }}<small>m/s</small></b></div>
                <div><span>{{ t('电量') }}</span><b class="num">{{ demo.byLabel[l]!.battery ?? '--' }}<small>%</small></b></div>
              </div>
              <div class="prog"><i :style="{ width: pct(demo.byLabel[l]!) + '%' }" /></div>
            </template>
            <div v-else class="dim">{{ t('未连接') }}</div>
          </div>
        </div>

        <div v-if="showDog" class="dog">
          <div class="dog-map"><DemoSemanticMap /></div>
          <div class="dog-info">
            <h3><i :style="{ background: COLORS.dog }" />{{ t('机器狗 · 语义地图') }}</h3>
            <p class="dim">{{ t('无人机实时下发的导航指令') }}</p>
            <div class="cmd num">{{ demo.dog?.lastCommand?.text ?? t('等待指令') }}</div>
            <p class="dim small">{{ demo.dog?.arrived ? t('已抵达目标') : demo.dog?.online ? t('前往目标中') : t('等待机器狗数据') }}</p>
          </div>
        </div>

        <div class="log">
          <h3>{{ t('协同通信') }}</h3>
          <DemoCommLog :kinds="['STAGE', 'COMM', 'TARGET', 'COMMAND']" />
        </div>
      </aside>
    </main>

    <div class="corner">
      <button type="button" @click="fullscreen">{{ t('全屏') }}</button>
      <RouterLink to="/demo/console">{{ t('控制页') }}</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.show {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  background: #070b12;
  color: #e2e8f0;
}
.top {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 24px;
  height: 76px;
  padding: 0 24px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, #0d1626, #070b12);
}
.title h1 {
  margin: 0;
  font-size: 22px;
  letter-spacing: 0.06em;
}
.title p {
  margin: 4px 0 0;
  color: #94a3b8;
  font-size: 14px;
}
.clock {
  justify-self: end;
  display: flex;
  align-items: center;
  gap: 12px;
}
.clock .t {
  font-size: 28px;
  font-weight: 600;
}
.sim {
  padding: 2px 8px;
  border: 1px solid var(--warn);
  border-radius: 10px;
  color: var(--warn);
  font-size: 12px;
}
.body {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) clamp(380px, 33vw, 640px);
}
.map {
  position: relative;
  min-width: 0;
}
.legend {
  position: absolute;
  left: 12px;
  bottom: 34px;
  z-index: 600;
  display: flex;
  gap: 14px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(7, 11, 18, 0.78);
  font-size: 13px;
}
.legend i {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 5px;
  border-radius: 50%;
}
.legend i.line {
  width: 18px;
  height: 0;
  border-top: 2px dashed #e2e8f0;
  border-radius: 0;
  vertical-align: 3px;
}
.banner {
  position: absolute;
  left: 50%;
  top: 16%;
  z-index: 700;
  transform: translate(-50%, -50%);
  padding: 18px 36px;
  border: 1px solid rgba(56, 189, 248, 0.6);
  border-radius: 14px;
  background: rgba(7, 11, 18, 0.85);
  font-size: 30px;
  font-weight: 700;
  letter-spacing: 0.08em;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.6);
  pointer-events: none;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.5s, transform 0.5s;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translate(-50%, -40%);
}
.side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 10px;
  border-left: 1px solid rgba(148, 163, 184, 0.18);
  background: #0a101b;
}
.cam {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  flex: none;
}
.cam-tabs {
  position: absolute;
  right: 8px;
  top: 8px;
  display: flex;
  gap: 4px;
  opacity: 0.25;
  transition: opacity 0.2s;
}
.cam:hover .cam-tabs {
  opacity: 1;
}
.cam-tabs button {
  padding: 2px 8px;
  border: 1px solid rgba(226, 232, 240, 0.4);
  border-radius: 6px;
  background: rgba(7, 11, 18, 0.75);
  color: #e2e8f0;
  font-size: 12px;
  cursor: pointer;
}
.cam-tabs button.on {
  border-color: var(--c, #e2e8f0);
  color: var(--c, #fff);
}
.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  flex: none;
}
.card {
  padding: 10px 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-top: 3px solid var(--c);
  border-radius: 10px;
  background: #0f1726;
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--c);
  color: #0b1220;
}
.role {
  font-weight: 600;
  font-size: 14px;
}
.st {
  margin-left: auto;
  font-size: 12px;
  color: #94a3b8;
}
.st.paused,
.st.failed {
  color: var(--warn);
}
.st.completed {
  color: #4ade80;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  margin-top: 8px;
}
.metrics span {
  display: block;
  color: #64748b;
  font-size: 12px;
}
.metrics b {
  font-size: 22px;
  font-weight: 600;
}
.metrics small {
  margin-left: 2px;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 400;
}
.prog {
  height: 4px;
  margin-top: 8px;
  border-radius: 2px;
  background: rgba(148, 163, 184, 0.2);
  overflow: hidden;
}
.prog i {
  display: block;
  height: 100%;
  background: var(--c);
  transition: width 0.4s;
}
.dog {
  display: grid;
  grid-template-columns: 170px 1fr;
  gap: 12px;
  padding: 10px;
  border: 1px solid rgba(74, 222, 128, 0.35);
  border-radius: 10px;
  background: #0d1a14;
  flex: none;
}
.dog-map {
  height: 170px;
}
.dog-info h3,
.log h3 {
  margin: 0 0 4px;
  font-size: 14px;
}
.dog-info h3 i {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 2px;
  transform: rotate(45deg);
}
.dog-info p {
  margin: 0;
  font-size: 12px;
}
.cmd {
  margin: 10px 0 6px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(74, 222, 128, 0.12);
  color: #bbf7d0;
  font-size: 18px;
  font-weight: 600;
}
.small {
  font-size: 12px;
}
.log {
  flex: 1;
  min-height: 120px;
  display: flex;
  flex-direction: column;
}
.log > :last-child {
  flex: 1;
  min-height: 0;
}
.corner {
  position: fixed;
  right: 10px;
  bottom: 8px;
  z-index: 3100;
  display: flex;
  gap: 6px;
  opacity: 0;
  transition: opacity 0.2s;
}
.corner:hover {
  opacity: 1;
}
.corner button,
.corner a {
  padding: 3px 10px;
  border: 1px solid rgba(226, 232, 240, 0.4);
  border-radius: 6px;
  background: rgba(7, 11, 18, 0.8);
  color: #e2e8f0;
  font-size: 12px;
  text-decoration: none;
  cursor: pointer;
}
@media (max-width: 1100px) {
  .body {
    grid-template-columns: 1fr;
    grid-template-rows: minmax(300px, 1fr) auto;
  }
  .bar {
    display: none;
  }
  .top {
    grid-template-columns: 1fr auto;
  }
}
</style>
