
<script setup lang="ts">
/**
 * Main view of a dog (ui-design.md 5.2, 7): S10 wrist camera (colour / depth), 2D map or point cloud; Lite3 colour /
 * depth live video from the new dog system (WebRTC, since 2026-11-10). Every picture carries its age; old pictures are greyed and say so — a picture
 * that loaded fine is not proof it is live (the S10 board serves old files with HTTP 200).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import AppIcon from '@/components/common/AppIcon.vue'
import { useDogStore, DOG_NAME } from '@/stores/dog'
import { dogApi, s10MapUrl, s10MediaUrl, type DogId } from '@/api/dog'
import Dog2Video from '@/components/dogv2/Dog2Video.vue'
import { depthFrontText } from '@/components/dogv2/depthFront'
import { useDog2Store } from '@/stores/dogv2'
import { grasp } from './s10Grasp'
import { t } from '@/i18n'

const props = defineProps<{ dog: DogId }>()
const store = useDogStore()

type S10View = 'camera' | 'map' | 'cloud'
const s10View = ref<S10View>('camera')
const channel = ref<'rgb' | 'depth'>('rgb')
const cloudWhich = ref<'map' | 'raw'>('map')
const online = computed(() => store.online(props.dog))
const s = computed(() => store.s10)
const holding = computed(() => props.dog === 's10' && !!store.s10Hold)

// ---------------------------------------------------------------- S10 camera
const s10Row = computed(() => (channel.value === 'rgb' ? s.value?.topics.rgb : s.value?.topics.depth))
const s10Age = computed(() => store.age(`s10.${channel.value}`, s10Row.value?.age, s.value?.stateAt))
const s10Src = computed(() => (s10Row.value?.image ? s10MediaUrl(s10Row.value.image, s10Row.value.last ?? 0) : null))
/** Fresh < 3 s (same threshold as the dog page), stale up to 30 s, then off. */
const s10Fresh = computed(() => fres(s10Age.value, 3, 30))

// ---------------------------------------------------------------- Lite3 camera (new dog system)
const v2 = useDog2Store()
const l3d = computed(() => v2.dogs.find((d) => d.model === 'lite3') ?? null)
const l3Video = computed(() => l3d.value?.video?.[channel.value])
const l3Fresh = computed(() => (l3Video.value?.state === 'live' ? 'ok' : 'off'))
/** The front depth distance (as on the old Lite3 card), over both pictures: the board computes it whichever is shown. */
const l3Depth = computed(() => depthFrontText(l3d.value))

function fres(age: number | null, fresh: number, stale: number): 'ok' | 'warn' | 'off' {
  if (age == null) return 'off'
  return age < fresh ? 'ok' : age < stale ? 'warn' : 'off'
}
function ageText(a: number | null): string {
  if (a == null) return '—'
  if (a < 10) return t('{n} 秒前', { n: a.toFixed(1) })
  if (a < 60) return t('{n} 秒前', { n: Math.round(a) })
  return t('{n} 分钟前', { n: Math.round(a / 60) })
}

// ---------------------------------------------------------------- 2D map and cloud
const mapStamp = ref(Date.now())
watch(() => s.value?.workAt, () => (mapStamp.value = Date.now()))
const hasMap = computed(() => !!s.value?.map && (s.value.map as { has_map?: boolean }).has_map !== false)
const mapInfo = computed(() => {
  const m = (s.value?.map ?? {}) as Record<string, unknown>
  const tr = (m.trust ?? {}) as { verdict?: string; detail?: string }
  const w = Number(m.width ?? 0)
  const h = Number(m.height ?? 0)
  const r = Number(m.resolution ?? 0)
  return t('地图 {id} · {w} × {h} 格 · {r} m/格（约 {wm} × {hm} m）· 定位可信度：{trust} · {mode}', {
    id: String(m.map_id ?? t('新地图')), w, h, r, wm: (w * r).toFixed(1), hm: (h * r).toFixed(1), trust: tr.verdict ?? t('未知'), mode: String(m.mode ?? t('模式未知')),
  })
})
const cloud = ref<{ map?: { pointsXYZ: number[][]; frame?: string; age?: number | null }; raw?: { pointsXYZ: number[][]; frame?: string; age?: number | null } } | null>(null)
const cloudErr = ref<string | null>(null)
const canvas = ref<HTMLCanvasElement | null>(null)
let cloudTimer = 0
let angle = -0.6
let zoom = 34
let drag: number | null = null
async function fetchCloud(): Promise<void> {
  if (props.dog !== 's10' || s10View.value !== 'cloud' || holding.value) return
  try {
    cloud.value = await dogApi.s10Clouds()
    cloudErr.value = null
    draw()
  } catch (e) {
    cloudErr.value = e instanceof Error ? e.message : t('取点云失败')
  }
}
function draw(): void {
  const cv = canvas.value
  if (!cv) return
  const box = cv.parentElement!
  const W = box.clientWidth
  const H = box.clientHeight
  const dpr = window.devicePixelRatio || 1
  cv.width = W * dpr
  cv.height = H * dpr
  const c = cv.getContext('2d')
  if (!c) return
  c.scale(dpr, dpr)
  c.fillStyle = '#05090f'
  c.fillRect(0, 0, W, H)
  const pts = (cloudWhich.value === 'map' ? cloud.value?.map?.pointsXYZ : cloud.value?.raw?.pointsXYZ) ?? []
  const z = cloudWhich.value === 'map' ? zoom : zoom * 2.2
  const cx = W / 2
  const cy = H * 0.56
  const ca = Math.cos(angle)
  const sa = Math.sin(angle)
  for (const p of pts) {
    const [x = 0, y = 0, h = 0] = p
    const u = x * ca - y * sa
    const v = x * sa + y * ca
    c.fillStyle = `hsl(${200 - h * 110},80%,${55 + h * 8}%)`
    c.fillRect(cx + u * z, cy - v * z * 0.55 - h * z, 1.8, 1.8)
  }
}
function onWheel(e: WheelEvent): void {
  e.preventDefault()
  zoom = Math.min(160, Math.max(4, zoom * Math.exp(-e.deltaY * 0.001)))
  draw()
}
function onDown(e: PointerEvent): void {
  drag = e.clientX
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
function onMove(e: PointerEvent): void {
  if (drag == null) return
  angle += (e.clientX - drag) * 0.01
  drag = e.clientX
  draw()
}
watch([s10View, cloudWhich], () => {
  if (s10View.value === 'cloud') void fetchCloud()
})

// ---------------------------------------------------------------- grasp picking on the photo
const snapUrl = computed(() => (grasp.image ? s10MediaUrl(grasp.image.replace(/^\/media\//, ''), grasp.snapAt) : null))
function pick(e: MouseEvent): void {
  const img = e.currentTarget as HTMLImageElement
  const r = img.getBoundingClientRect()
  grasp.u = Math.floor(((e.clientX - r.left) * grasp.width) / r.width)
  grasp.v = Math.floor(((e.clientY - r.top) * grasp.height) / r.height)
  grasp.solution = null
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && grasp.selecting) {
    e.preventDefault()   // this Esc leaves photo picking; it is not the pad's "stop"
    grasp.selecting = false
  }
}

onMounted(() => {
  cloudTimer = window.setInterval(() => void fetchCloud(), 2000)
  window.addEventListener('keydown', onKey)
  window.addEventListener('resize', draw)
})
onBeforeUnmount(() => {
  window.clearInterval(cloudTimer)
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', draw)
})

</script>

<template>
  <div class="dogmain" :class="[`f-${dog === 's10' ? s10Fresh : l3Fresh}`, { offline: !online }]" data-test="dog-main">
    <!-- view switches -->
    <div class="views">
      <div v-if="dog === 's10'" class="seg">
        <button :class="{ on: s10View === 'camera' && !grasp.selecting }" @click="s10View = 'camera'; grasp.selecting = false"><AppIcon name="camera" :size="15" />{{ t('S10 相机') }}</button>
        <button :class="{ on: s10View === 'map' }" @click="s10View = 'map'; grasp.selecting = false"><AppIcon name="map" :size="15" />{{ t('二维地图') }}</button>
        <button :class="{ on: s10View === 'cloud' }" @click="s10View = 'cloud'; grasp.selecting = false"><AppIcon name="layers" :size="15" />{{ t('点云') }}</button>
      </div>
      <div v-if="dog === 'lite3' || s10View === 'camera'" class="seg">
        <button :class="{ on: channel === 'rgb' }" @click="channel = 'rgb'">{{ t('彩色') }}</button>
        <button :class="{ on: channel === 'depth' }" @click="channel = 'depth'">{{ t('深度') }}</button>
      </div>
      <div v-if="dog === 's10' && s10View === 'cloud'" class="seg">
        <button :class="{ on: cloudWhich === 'map' }" @click="cloudWhich = 'map'">{{ t('累计地图') }}</button>
        <button :class="{ on: cloudWhich === 'raw' }" @click="cloudWhich = 'raw'">{{ t('实时雷达') }}</button>
      </div>
    </div>

    <!-- S10 -->
    <template v-if="dog === 's10'">
      <div v-if="grasp.selecting && snapUrl" class="pickwrap">
        <img :src="snapUrl" class="fit pickimg" :alt="t('拍照得到的画面')" @click="pick" />
        <div v-if="grasp.u != null" class="cross" :style="{ left: `${(grasp.u / grasp.width) * 100}%`, top: `${(grasp.v! / grasp.height) * 100}%` }" />
        <div class="pickbar">{{ t('选点模式：在照片上点目标中心 · 只计算，不会移动 · Esc 退出') }}
          <button class="btn btn-sm" @click="grasp.selecting = false">{{ t('退出选点') }}</button></div>
      </div>
      <template v-else-if="s10View === 'camera'">
        <img v-if="s10Src" :src="s10Src" class="fit" :alt="channel === 'rgb' ? t('S10 腕部相机彩色') : t('S10 腕部相机深度')" />
        <div v-else class="empty"><AppIcon name="camera" :size="28" /><p>{{ online ? t('正在取第一张画面…') : t('没有画面') }}</p></div>
      </template>
      <template v-else-if="s10View === 'map'">
        <img v-if="hasMap" :src="s10MapUrl(mapStamp)" class="fit map" :alt="t('S10 二维地图')" />
        <div v-else class="empty"><AppIcon name="map" :size="28" /><p>{{ t('狗方还没有地图') }}</p></div>
        <div class="mapinfo">{{ mapInfo }}</div>
        <div class="mapnote dim">{{ t('这张图不画狗的位置和目标（狗方网页也没有）') }}</div>
      </template>
      <template v-else>
        <canvas ref="canvas" class="cloud" @wheel="onWheel" @pointerdown="onDown" @pointermove="onMove" @pointerup="drag = null" />
        <div class="mapinfo">{{ cloudWhich === 'map' ? t('三维累计地图（关键帧更新）') : t('实时雷达扫描') }} · {{ t('坐标系') }} {{ (cloudWhich === 'map' ? cloud?.map?.frame : cloud?.raw?.frame) ?? '—' }} · {{ t('拖动旋转 / 滚轮缩放') }}{{ cloudErr ? ` · ${cloudErr}` : '' }}</div>
      </template>
      <div class="badge" data-test="dog-age">
        <span class="sd" :class="s10Fresh" />S10 · {{ s10View === 'camera' ? t('腕部相机 · {ch}', { ch: channel === 'rgb' ? t('彩色') : t('深度') }) : s10View === 'map' ? t('二维地图') : t('点云') }} ·
        <template v-if="!online">{{ store.pageStale('s10') ? t('本页没收到更新 · 最后数据') : store.lost('s10') ? t('失联 · 最后数据') : t('离线 · 最后数据') }}</template>
        <template v-else-if="holding">{{ t('按住移动中，画面暂停刷新') }}</template>
        <template v-else-if="s10View === 'camera' && s10Fresh !== 'ok'">{{ t('画面已停 · 最后一帧 {age}', { age: ageText(s10Age) }) }}</template>
        <template v-else-if="s10View === 'camera'">{{ ageText(s10Age) }}</template>
        <template v-else>{{ ageText(store.age('s10.work', 0, s?.workAt)) }}</template>
      </div>
    </template>

    <!-- Lite3 -->
    <template v-else>
      <Dog2Video v-if="l3d" :key="`${l3d.id}-${channel}`" class="fit l3v" :dog="l3d.id" :stream="channel" :video="l3Video" />
      <div v-else class="empty"><AppIcon name="camera" :size="28" /><p>{{ t('没有画面') }}</p></div>
      <div class="badge" data-test="dog-age">
        <span class="sd" :class="l3Fresh" />Lite3 · {{ channel === 'rgb' ? t('彩色') : t('深度') }} ·
        <template v-if="!online">{{ store.pageStale('lite3') ? t('本页没收到更新 · 最后数据') : t('离线 · 最后数据') }}</template>
        <template v-else-if="l3Video?.state === 'live'">{{ t('实时') }}</template>
        <template v-else>{{ t('等狗开始推流…') }}</template>
      </div>
      <div v-if="l3Depth" class="mapinfo" data-test="dog-depth-front">{{ l3Depth }}</div>
    </template>
    <div v-if="!online" class="offcard" :class="{ stale: store.pageStale(dog) }">
      <AppIcon name="alert" :size="18" />{{ store.pageStale(dog) ? t('{name}：本页 {n} 秒没收到新状态，下面是最后收到的数据', { name: DOG_NAME[dog], n: store.staleSecs(dog) }) : store.lost(dog) ? t('{name} 失联 · 下面是最后收到的数据，指令发不出去', { name: DOG_NAME[dog] }) : t('{name} 离线 · 下面是最后收到的数据，指令发不出去', { name: DOG_NAME[dog] }) }}
    </div>
  </div>
</template>

<style scoped>
.dogmain {
  position: absolute;
  inset: 0;
  background: #000;
  overflow: hidden;
}
.fit {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.map { background: #555; }
.l3v { border-radius: 0; aspect-ratio: auto; }
.f-off .l3v { filter: none; }
.f-warn .fit, .f-off .fit, .offline .fit { filter: grayscale(0.7) brightness(0.7); }
.views {
  position: absolute;
  left: 16px;
  top: 16px;
  z-index: 20;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.seg {
  display: flex;
  border-radius: var(--r-ctl);
  overflow: hidden;
  border: 1px solid var(--border);
  background: var(--overlay);
}
.seg button {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 36px;
  padding: 0 12px;
  border: none;
  background: transparent;
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
.seg button.on { background: var(--accent); color: var(--accent-ink); }
.srcbtn { background: var(--overlay); height: 38px; }
.srcpop {
  position: absolute;
  left: 16px;
  top: 62px;
  z-index: 30;
  padding: 12px;
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.srcpop label { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-xs); }
.badge {
  position: absolute;
  left: 16px;
  top: 62px;
  z-index: 15;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--overlay);
  font-size: var(--fs-xs);
}
.sd { width: 8px; height: 8px; border-radius: 50%; background: var(--text-dim); }
.sd.ok { background: var(--ok); }
.sd.warn { background: var(--warn); }
.sd.off { background: var(--text-dim); }
.f-warn .badge { color: var(--warn); }
.mapinfo {
  position: absolute;
  left: 16px;
  top: 96px;
  z-index: 15;
  max-width: calc(100% - 380px);
  padding: 4px 10px;
  border-radius: var(--r-ctl);
  background: var(--overlay);
  font-size: var(--fs-xs);
}
.mapnote {
  position: absolute;
  left: 16px;
  top: 126px;
  z-index: 15;
  padding: 4px 10px;
  border-radius: var(--r-ctl);
  background: var(--overlay);
  font-size: var(--fs-xs);
}
.cloud { position: absolute; inset: 0; width: 100%; height: 100%; cursor: grab; }
.empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-dim);
  background: repeating-linear-gradient(45deg, #0b0f14 0 14px, #0e141b 14px 28px);
}
.offcard {
  position: absolute;
  left: 50%;
  top: 16px;
  transform: translateX(-50%);
  z-index: 25;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: var(--r-ctl);
  background: color-mix(in srgb, var(--danger) 85%, #000);
  color: #fff;
  font-weight: 600;
}
.offcard.stale {
  background: color-mix(in srgb, var(--warn) 85%, #000);
}
.pickwrap { position: absolute; inset: 0; }
.pickimg { cursor: crosshair; outline: 3px solid var(--accent); outline-offset: -3px; }
.cross {
  position: absolute;
  width: 34px;
  height: 34px;
  margin: -17px 0 0 -17px;
  border: 3px solid #ff445d;
  border-radius: 50%;
  pointer-events: none;
}
.pickbar {
  position: absolute;
  left: 50%;
  bottom: 16px;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-radius: var(--r-ctl);
  background: var(--accent);
  color: var(--accent-ink);
  font-weight: 600;
}
</style>
