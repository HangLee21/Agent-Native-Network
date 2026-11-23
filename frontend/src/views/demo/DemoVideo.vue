<script setup lang="ts">
/**
 * One aircraft's camera on the demo pages. Simulated aircraft get a synthetic picture drawn from their pose;
 * real ones play their stream (WHEP, HLS fallback). On top of either: the target bracket (the selection box
 * while it is fresh, otherwise the target projected with the camera model), the recommended path for the dog,
 * the dog, the other aircraft, and a small HUD. Projection is approximate (pinhole, flat ground, wide lens).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type Hls from 'hls.js'
import { playWhep } from '@/api/live'
import { t } from '@/i18n'
import { frameRect } from '@/utils/videoCoords'
import { useDemoStore } from './useDemoStore'
import { COLORS, type DemoDrone, type LatLon } from './demoApi'
import { distanceM, offset, projectToFrame, toLocal, type CameraPose } from './demoGeo'

const props = withDefaults(defineProps<{ drone: DemoDrone | null; role?: string; compact?: boolean }>(), { role: '', compact: false })
const demo = useDemoStore()
const canvas = ref<HTMLCanvasElement | null>(null)
const video = ref<HTMLVideoElement | null>(null)
const wrap = ref<HTMLDivElement | null>(null)
const playError = ref<string | null>(null)
let raf = 0
let pc: RTCPeerConnection | null = null
let hls: Hls | null = null
let attempt = 0

const ASPECT = 16 / 9
const BOX_FRESH_MS = 15000
const live = computed(() => {
  const v = props.drone?.video
  return v && (v.protocol === 'WHEP' || v.protocol === 'HLS') && v.url ? v : null
})
const color = computed(() => (props.drone?.label ? COLORS[props.drone.label] : '#94a3b8'))

// ---------------------------------------------------------------- smoothed camera pose (5 Hz pushes → 60 fps drawing)

let pose: CameraPose | null = null
function targetPose(): CameraPose | null {
  const d = props.drone
  if (!d || d.lat == null || d.lon == null) return null
  return { lat: d.lat, lon: d.lon, height: Math.max(0.5, d.relativeHeight ?? 0), yaw: (d.heading ?? 0) + (d.gimbalYaw ?? 0), pitch: d.gimbalPitch ?? 0 }
}
function smooth(): CameraPose | null {
  const tp = targetPose()
  if (!tp) return (pose = null)
  if (!pose || distanceM(pose, tp) > 50) return (pose = { ...tp })
  const k = 0.18
  const dyaw = ((tp.yaw - pose.yaw + 540) % 360) - 180
  pose = {
    lat: pose.lat + (tp.lat - pose.lat) * k,
    lon: pose.lon + (tp.lon - pose.lon) * k,
    height: pose.height + (tp.height - pose.height) * k,
    yaw: pose.yaw + dyaw * k,
    pitch: pose.pitch + (tp.pitch - pose.pitch) * k,
  }
  return pose
}

// ---------------------------------------------------------------- synthetic ground (simulation only)

function hash(i: number, j: number): number {
  let h = (i * 73856093) ^ (j * 19349663)
  h = Math.imul(h ^ (h >>> 13), 0x5bd1e995)
  h ^= h >>> 15
  return ((h >>> 0) % 65536) / 65536
}

const PALETTE = ['#2f4a1f', '#3b5a26', '#4a6b2e', '#5b5135', '#6b6248']

function drawGround(g: CanvasRenderingContext2D, W: number, H: number, cam: CameraPose): void {
  const tanV = Math.tan((36 * Math.PI) / 180) / ASPECT
  const horizon = 0.5 + Math.tan((cam.pitch * Math.PI) / 180) / tanV / 2
  const hy = Math.max(0, Math.min(1, horizon)) * H
  const sky = g.createLinearGradient(0, 0, 0, hy)
  sky.addColorStop(0, '#1e3a5f')
  sky.addColorStop(1, '#6b8fb3')
  g.fillStyle = sky
  g.fillRect(0, 0, W, hy)
  const ground = g.createLinearGradient(0, hy, 0, H)
  ground.addColorStop(0, '#4b5a3a')
  ground.addColorStop(1, '#33452a')
  g.fillStyle = ground
  g.fillRect(0, hy, W, H - hy)

  // patches and bushes on a 12 m world grid around the camera: they move with the aircraft
  // fixed origin (0.1° ≈ 11 km): objects keep their place while the aircraft moves across the demo area
  const origin = { lat: Math.round(cam.lat * 10) / 10, lon: Math.round(cam.lon * 10) / 10 }
  const c = toLocal(origin, cam)
  const CELL = 12
  const ci = Math.round(c.n / CELL)
  const cj = Math.round(c.e / CELL)
  const R = Math.min(30, Math.ceil((cam.height * 6 + 120) / CELL))
  const items: { y: number; draw: () => void }[] = []
  for (let i = ci - R; i <= ci + R; i++) {
    for (let j = cj - R; j <= cj + R; j++) {
      const h1 = hash(i, j)
      const p = offset(origin, i * CELL + (hash(j, i) - 0.5) * CELL, j * CELL + (h1 - 0.5) * CELL)
      const s = projectToFrame(cam, p)
      if (!s || s.x < -0.2 || s.x > 1.2 || s.y < -0.2 || s.y > 1.2) continue
      const far = projectToFrame(cam, offset(p, 0, 1))
      const pxPerM = far ? Math.hypot((far.x - s.x) * W, (far.y - s.y) * H) : 1
      const kind = h1 < 0.55 ? 'patch' : h1 < 0.85 ? 'bush' : 'rock'
      const size = (kind === 'patch' ? 5 : kind === 'bush' ? 1.6 : 0.8) * (0.6 + hash(i + 7, j - 3))
      const r = size * pxPerM
      if (r < 0.6) continue
      items.push({
        y: s.y,
        draw: () => {
          g.beginPath()
          g.fillStyle = kind === 'patch' ? PALETTE[Math.floor(hash(i - 5, j + 9) * PALETTE.length)]! : kind === 'bush' ? '#1f3a17' : '#8a8478'
          g.globalAlpha = kind === 'patch' ? 0.55 : 0.9
          g.ellipse(s.x * W, s.y * H, r, r * (kind === 'patch' ? 0.6 : 1), 0, 0, Math.PI * 2)
          g.fill()
          g.globalAlpha = 1
        },
      })
    }
  }
  items.sort((a, b) => a.y - b.y).forEach((it) => it.draw())
}

// ---------------------------------------------------------------- overlays (simulation and live)

function polylineOnFrame(g: CanvasRenderingContext2D, f: { left: number; top: number; width: number; height: number }, cam: CameraPose, path: LatLon[]): void {
  // sample every 2 m so segments close to the camera are clipped correctly
  g.beginPath()
  let pen = false
  for (let k = 1; k < path.length; k++) {
    const a = path[k - 1]!
    const b = path[k]!
    const n = Math.max(1, Math.ceil(distanceM(a, b) / 2))
    for (let s = 0; s <= n; s++) {
      const p = { lat: a.lat + ((b.lat - a.lat) * s) / n, lon: a.lon + ((b.lon - a.lon) * s) / n }
      const q = projectToFrame(cam, p)
      if (!q) {
        pen = false
        continue
      }
      const x = f.left + q.x * f.width
      const y = f.top + q.y * f.height
      if (pen) g.lineTo(x, y)
      else g.moveTo(x, y)
      pen = true
    }
  }
  g.stroke()
}

function bracket(g: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, col: string): void {
  const c = Math.max(8, Math.min(w, h) * 0.3)
  g.strokeStyle = col
  g.lineWidth = 3
  g.beginPath()
  for (const [sx, sy, dx, dy] of [[x, y, 1, 1], [x + w, y, -1, 1], [x, y + h, 1, -1], [x + w, y + h, -1, -1]] as const) {
    g.moveTo(sx + dx * c, sy)
    g.lineTo(sx, sy)
    g.lineTo(sx, sy + dy * c)
  }
  g.stroke()
}

function label(g: CanvasRenderingContext2D, text: string, x: number, y: number, bg: string, fg = '#0b1220'): void {
  g.font = `600 ${props.compact ? 11 : 13}px ${getComputedStyle(document.body).getPropertyValue('--font-ui') || 'sans-serif'}`
  const w = g.measureText(text).width + 10
  g.fillStyle = bg
  g.fillRect(x, y, w, props.compact ? 16 : 19)
  g.fillStyle = fg
  g.fillText(text, x + 5, y + (props.compact ? 12 : 14))
}

function drawOverlays(g: CanvasRenderingContext2D, f: { left: number; top: number; width: number; height: number }, cam: CameraPose): void {
  const s = demo.state
  const d = props.drone
  if (!s || !d) return
  const isLow = d.label === s.lowLabel
  // recommended path for the dog (stage 3 / 4)
  if (s.dogPath.length >= 2 && s.dogMode !== 'SKIP') {
    g.save()
    g.strokeStyle = COLORS.dog
    g.lineWidth = 3
    g.setLineDash([12, 8])
    g.lineDashOffset = -((performance.now() / 40) % 20)
    polylineOnFrame(g, f, cam, s.dogPath)
    g.restore()
  }
  // dog
  const dg = demo.dog
  if (dg && dg.lat != null && dg.lon != null && s.dogMode !== 'SKIP') {
    const q = projectToFrame(cam, { lat: dg.lat, lon: dg.lon })
    if (q && q.x > 0 && q.x < 1 && q.y > 0 && q.y < 1) {
      const x = f.left + q.x * f.width
      const y = f.top + q.y * f.height
      g.fillStyle = COLORS.dog
      g.strokeStyle = '#0b1220'
      g.lineWidth = 2
      g.beginPath()
      g.arc(x, y, 6, 0, Math.PI * 2)
      g.fill()
      g.stroke()
      label(g, t('机器狗'), x + 9, y - 22, COLORS.dog)
    }
  }
  // the other aircraft
  for (const o of demo.drones) {
    if (!o.label || o.label === d.label || o.lat == null || o.lon == null || o.phase === 'GROUND') continue
    const q = projectToFrame(cam, { lat: o.lat, lon: o.lon }, o.relativeHeight ?? 0)
    if (q && q.x > 0 && q.x < 1 && q.y > 0 && q.y < 1) {
      const x = f.left + q.x * f.width
      const y = f.top + q.y * f.height
      g.strokeStyle = COLORS[o.label]
      g.lineWidth = 2
      g.strokeRect(x - 7, y - 7, 14, 14)
      label(g, t('{label} 机', { label: o.label }), x + 10, y - 9, COLORS[o.label])
    }
  }
  // target
  const tg = s.target
  if (tg) {
    let box: { x: number; y: number; w: number; h: number } | null = null
    if (tg.box && tg.droneId === d.id && Date.now() - tg.at < BOX_FRESH_MS) {
      box = { x: f.left + tg.box.x * f.width, y: f.top + tg.box.y * f.height, w: tg.box.w * f.width, h: tg.box.h * f.height }
    } else {
      const q = projectToFrame(cam, tg)
      const q2 = projectToFrame(cam, offset(tg, 0, 2))
      if (q && q.x > -0.05 && q.x < 1.05 && q.y > -0.05 && q.y < 1.05) {
        const r = Math.max(14, q2 ? Math.hypot((q2.x - q.x) * f.width, (q2.y - q.y) * f.height) * 1.2 : 14)
        box = { x: f.left + q.x * f.width - r, y: f.top + q.y * f.height - r, w: 2 * r, h: 2 * r }
      }
    }
    if (box) {
      if (live.value == null) {
        // the simulated "sample": an orange rock at the target
        g.fillStyle = '#d97706'
        g.beginPath()
        g.ellipse(box.x + box.w / 2, box.y + box.h / 2, box.w * 0.22, box.h * 0.16, 0, 0, Math.PI * 2)
        g.fill()
      }
      const blink = isLow && Date.now() - tg.at < 4000 && Math.floor(performance.now() / 250) % 2 === 0
      bracket(g, box.x, box.y, box.w, box.h, blink ? '#fff' : COLORS.target)
      const dist = distanceM(cam, tg)
      label(g, t('采样目标 · {d} m', { d: Math.round(Math.hypot(dist, cam.height)) }), box.x, box.y - (props.compact ? 19 : 23), COLORS.target, '#fff')
    }
  }
}

function drawHud(g: CanvasRenderingContext2D, f: { left: number; top: number; width: number; height: number }): void {
  const d = props.drone
  if (!d) return
  const pad = props.compact ? 6 : 10
  label(g, `${d.label ?? ''}${props.role ? ' · ' + props.role : ''}`, f.left + pad, f.top + pad, color.value)
  if (Math.floor(performance.now() / 600) % 2 === 0) {
    g.fillStyle = '#ef4444'
    g.beginPath()
    g.arc(f.left + f.width - pad - 6, f.top + pad + 8, 5, 0, Math.PI * 2)
    g.fill()
  }
  const fmt = (v: number | null | undefined, digits = 0) => (v == null ? '--' : v.toFixed(digits))
  const text = t('高度 {h} m   速度 {v} m/s   航向 {hd}°   云台 {p}°', {
    h: fmt(d.relativeHeight, 1),
    v: fmt(d.horizontalSpeed, 1),
    hd: fmt(d.heading),
    p: fmt(d.gimbalPitch),
  })
  g.font = `500 ${props.compact ? 11 : 13}px ${getComputedStyle(document.body).getPropertyValue('--font-num') || 'monospace'}`
  const w = g.measureText(text).width + 16
  g.fillStyle = 'rgba(5,8,12,0.6)'
  g.fillRect(f.left + pad, f.top + f.height - pad - (props.compact ? 18 : 22), w, props.compact ? 18 : 22)
  g.fillStyle = '#e2e8f0'
  g.fillText(text, f.left + pad + 8, f.top + f.height - pad - (props.compact ? 5 : 7))
}

function draw(): void {
  raf = requestAnimationFrame(draw)
  const c = canvas.value
  const el = wrap.value
  if (!c || !el) return
  const dpr = devicePixelRatio
  const W = el.clientWidth
  const H = el.clientHeight
  if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) {
    c.width = Math.round(W * dpr)
    c.height = Math.round(H * dpr)
  }
  const g = c.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.clearRect(0, 0, W, H)
  const cam = smooth()
  const v = video.value
  const f = live.value && v && v.videoWidth ? frameRect(W, H, v.videoWidth, v.videoHeight) : frameRect(W, H, 1920, 1080)
  if (!live.value) {
    g.fillStyle = '#000'
    g.fillRect(0, 0, W, H)
    if (cam) {
      g.save()
      g.beginPath()
      g.rect(f.left, f.top, f.width, f.height)
      g.clip()
      g.translate(f.left, f.top)
      drawGround(g, f.width, f.height, cam)
      g.restore()
    }
  }
  if (cam) {
    g.save()
    g.beginPath()
    g.rect(f.left, f.top, f.width, f.height)
    g.clip()
    drawOverlays(g, f, cam)
    drawHud(g, f)
    g.restore()
  }
}

// ---------------------------------------------------------------- live stream

function teardown(): void {
  attempt++
  pc?.close()
  pc = null
  hls?.destroy()
  hls = null
  if (video.value) video.value.srcObject = null
}

async function attach(): Promise<void> {
  teardown()
  const mine = attempt
  playError.value = null
  const v = live.value
  const el = video.value
  if (!v || !el) return
  try {
    if (v.protocol === 'WHEP') {
      try {
        const conn = await playWhep(v.url!, el)
        if (mine === attempt) pc = conn
        else conn.close()
        return
      } catch (e) {
        if (!v.fallbackUrl) throw e
      }
    }
    const url = v.protocol === 'HLS' ? v.url! : v.fallbackUrl!
    const { default: HlsLib } = await import('hls.js')
    if (mine !== attempt) return
    if (HlsLib.isSupported()) {
      hls = new HlsLib({ liveSyncDurationCount: 2 })
      hls.loadSource(url)
      hls.attachMedia(el)
    } else {
      el.src = url
    }
  } catch (e) {
    if (mine === attempt) playError.value = t('视频连接失败：{msg}', { msg: e instanceof Error ? e.message : t('未知错误') })
  }
}

const streamKey = computed(() => (live.value ? `${live.value.protocol} ${live.value.url} ${live.value.fallbackUrl ?? ''}` : ''))
watch([streamKey, video], () => void attach(), { flush: 'post' })
watch(() => props.drone?.id, () => (pose = null))

onMounted(() => (raf = requestAnimationFrame(draw)))
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  teardown()
})
</script>

<template>
  <div ref="wrap" class="demo-video" :class="{ compact: props.compact }">
    <video v-if="live" ref="video" class="feed" autoplay muted playsinline />
    <canvas ref="canvas" class="overlay" />
    <div v-if="!props.drone" class="empty">{{ t('没有画面') }}</div>
    <div v-else-if="playError" class="empty">{{ playError }}</div>
    <div v-else-if="!live && props.drone.video?.protocol !== 'SIM'" class="empty">{{ t('这架飞机没有在推流') }}</div>
  </div>
</template>

<style scoped>
.demo-video {
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
}
.feed,
.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.feed {
  object-fit: contain;
}
.empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #94a3b8;
  font-size: var(--fs-sm);
}
</style>
