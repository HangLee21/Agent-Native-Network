<script setup lang="ts">
/**
 * Synthetic camera image for mock mode only (no real stream; used to verify the monitoring UI).
 * Drawn as a 16:9 frame with the same camera model as the simulator (heading + gimbal yaw, gimbal pitch,
 * wide-lens FOV 72°, zoom lens 72° / zoom factor) so a tap lands where the simulated laser measures.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useTelemetryStore } from '@/stores/telemetry'
import { frameRect, MOCK_FRAME } from '@/utils/videoCoords'
import { t } from '@/i18n'

const props = defineProps<{ lens: string }>()
const canvas = ref<HTMLCanvasElement | null>(null)
const tel = useTelemetryStore()
let raf = 0

/** MOCK ASSUMPTIONS, kept in sync with SimulatedM4eDevice (WIDE_HFOV_DEG, MOCK_OBJECTS). */
const WIDE_HFOV_DEG = 72
/** [north m, east m, radius m, height m] from home, and a label. */
const MOCK_OBJECTS: [number, number, number, number, string][] = [
  [80, 60, 4, 25, t('模拟塔')],
  [-50, 90, 2.5, 2.5, t('模拟车辆')],
]

const rad = (d: number) => (d * Math.PI) / 180

function draw(): void {
  const c = canvas.value
  if (!c) return
  const dpr = devicePixelRatio
  const W = (c.width = c.clientWidth * dpr)
  const H = (c.height = c.clientHeight * dpr)
  const g = c.getContext('2d')!
  g.fillStyle = '#000'
  g.fillRect(0, 0, W, H)
  const f = frameRect(W, H, MOCK_FRAME.w, MOCK_FRAME.h)
  g.save()
  g.beginPath()
  g.rect(f.left, f.top, f.width, f.height)
  g.clip()

  const dr = tel.drone
  const thermal = props.lens === 'thermal' || props.lens === 'ir'
  const zoomLens = props.lens === 'zoom'
  const hfov = zoomLens ? WIDE_HFOV_DEG / Math.max(1, dr?.zoomFactor ?? 2) : WIDE_HFOV_DEG
  const tanH = Math.tan(rad(hfov / 2))
  const tanV = tanH * (MOCK_FRAME.h / MOCK_FRAME.w)
  const pitch = rad(dr?.gimbalPitch ?? 0)
  const yaw = rad((dr?.attitudeHead ?? 0) + (dr?.gimbalYaw ?? 0))
  const rel = dr?.relativeHeight ?? 0
  const cx = f.left + f.width / 2
  const cy = f.top + f.height / 2

  /** Local offsets (north, east, up relative to the camera) → frame pixels, or null behind the camera. */
  function project(n: number, e: number, up: number): { x: number; y: number } | null {
    const fwd = n * Math.cos(yaw) + e * Math.sin(yaw)
    const right = -n * Math.sin(yaw) + e * Math.cos(yaw)
    const fz = fwd * Math.cos(pitch) + up * Math.sin(pitch)
    const uz = -fwd * Math.sin(pitch) + up * Math.cos(pitch)
    if (fz < 0.5) return null
    return { x: cx + (right / fz / tanH) * (f.width / 2), y: cy - (uz / fz / tanV) * (f.height / 2) }
  }

  const horizon = Math.max(f.top - 1, Math.min(f.top + f.height + 1, cy + (Math.tan(pitch) / tanV) * (f.height / 2)))
  const sky = g.createLinearGradient(0, f.top, 0, horizon)
  sky.addColorStop(0, thermal ? '#1b1035' : '#5b8fc9')
  sky.addColorStop(1, thermal ? '#3d1f5c' : '#c8dcef')
  g.fillStyle = sky
  g.fillRect(f.left, f.top, f.width, Math.max(0, horizon - f.top))
  const ground = g.createLinearGradient(0, horizon, 0, f.top + f.height)
  ground.addColorStop(0, thermal ? '#7a2e2e' : '#6f8f5a')
  ground.addColorStop(1, thermal ? '#f2a33a' : '#3c5233')
  g.fillStyle = ground
  g.fillRect(f.left, horizon, f.width, f.top + f.height - horizon)

  // ground grid every 20 m around the drone, projected with the camera model
  if (dr && rel > 0.5) {
    g.strokeStyle = 'rgba(255,255,255,0.16)'
    g.lineWidth = dpr
    const offN = ((dr.lat ?? 0) * 111_320) % 20
    const offE = ((dr.lon ?? 0) * 111_320 * Math.cos(rad(dr.lat ?? 0))) % 20
    for (let i = -15; i <= 15; i++) {
      const a: Array<[number, number]> = [[i * 20 - offN, -300], [i * 20 - offN, 300]]
      const b: Array<[number, number]> = [[-300, i * 20 - offE], [300, i * 20 - offE]]
      for (const seg of [a, b]) {
        const p1 = project(seg[0]![0], seg[0]![1], -rel)
        const p2 = project(seg[1]![0], seg[1]![1], -rel)
        if (p1 && p2) {
          g.beginPath()
          g.moveTo(p1.x, p1.y)
          g.lineTo(p2.x, p2.y)
          g.stroke()
        }
      }
    }
  }

  // simulated objects (the laser hits them in the simulator)
  if (dr?.lat != null && dr.lon != null && dr.homeLat != null && dr.homeLon != null) {
    for (const [on, oe, r, oh, label] of MOCK_OBJECTS) {
      const n = (dr.homeLat - dr.lat) * 111_320 + on
      const e = (dr.homeLon - dr.lon) * 111_320 * Math.cos(rad(dr.lat)) + oe
      const bottom = project(n, e, -rel)
      const top = project(n, e, oh - rel)
      if (!bottom || !top) continue
      const dist = Math.hypot(n, e)
      const halfW = Math.max(2 * dpr, (r / Math.max(1, dist) / tanH) * (f.width / 2))
      g.fillStyle = thermal ? '#fef08a' : oh > 5 ? '#b45309' : '#dc2626'
      g.fillRect(bottom.x - halfW, top.y, halfW * 2, Math.max(2 * dpr, bottom.y - top.y))
      g.font = `${11 * dpr}px sans-serif`
      g.fillStyle = '#fff'
      g.textAlign = 'center'
      g.fillText(label, top.x, top.y - 4 * dpr)
    }
  }

  const label = t('模拟画面（mock）· {lens}', { lens: thermal ? t('红外') : zoomLens ? t('变焦 {n}×', { n: dr?.zoomFactor ?? 2 }) : t('广角') })
  g.font = `${12 * dpr}px sans-serif`
  const tw = g.measureText(label).width + 16 * dpr
  g.fillStyle = 'rgba(0,0,0,0.45)'
  g.fillRect(cx - tw / 2, f.top + 108 * dpr, tw, 24 * dpr)
  g.fillStyle = '#fff'
  g.textAlign = 'center'
  g.fillText(label, cx, f.top + 124 * dpr)
  g.textAlign = 'left'
  g.restore()
  raf = requestAnimationFrame(draw)
}

onMounted(() => (raf = requestAnimationFrame(draw)))
onBeforeUnmount(() => cancelAnimationFrame(raf))
</script>

<template>
  <canvas ref="canvas" class="mock-feed" data-test="mock-feed" />
</template>

<style scoped>
.mock-feed {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
</style>
