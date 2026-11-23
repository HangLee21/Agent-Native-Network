<script setup lang="ts">
/** The dog's semantic map seen from above, centred on the dog (about 40 m across), with the path and target. */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { t, tb } from '@/i18n'
import { useDemoStore } from './useDemoStore'
import { CELL_COLORS, COLORS, cellColor, type LatLon } from './demoApi'
import { toLocal } from './demoGeo'

const props = withDefaults(defineProps<{ spanM?: number }>(), { spanM: 40 })
const demo = useDemoStore()
const canvas = ref<HTMLCanvasElement | null>(null)
let raf = 0
let last = 0

function draw(now: number): void {
  raf = requestAnimationFrame(draw)
  if (now - last < 200) return // 5 fps is plenty for a map that changes at walking speed
  last = now
  const c = canvas.value
  if (!c) return
  const dpr = devicePixelRatio
  const W = c.clientWidth
  const H = c.clientHeight
  c.width = Math.round(W * dpr)
  c.height = Math.round(H * dpr)
  const g = c.getContext('2d')!
  g.setTransform(dpr, 0, 0, dpr, 0, 0)
  g.fillStyle = '#0b1220'
  g.fillRect(0, 0, W, H)
  const dg = demo.dog
  const centre: LatLon | null = dg?.lat != null && dg.lon != null ? { lat: dg.lat, lon: dg.lon } : demo.state?.dogStart ?? null
  if (!centre) {
    g.fillStyle = '#64748b'
    g.font = '13px sans-serif'
    g.fillText(t('等待机器狗数据'), 12, H / 2)
    return
  }
  const s = Math.min(W, H) / props.spanM
  const px = (p: LatLon) => {
    const l = toLocal(centre, p)
    return { x: W / 2 + l.e * s, y: H / 2 - l.n * s }
  }
  // grid
  g.strokeStyle = 'rgba(148,163,184,0.12)'
  g.lineWidth = 1
  for (let m = -props.spanM; m <= props.spanM; m += 5) {
    g.beginPath()
    g.moveTo(W / 2 + m * s, 0)
    g.lineTo(W / 2 + m * s, H)
    g.moveTo(0, H / 2 + m * s)
    g.lineTo(W, H / 2 + m * s)
    g.stroke()
  }
  // cells
  for (const cell of demo.cells.values()) {
    const p = px(cell)
    const half = (cell.sizeM * s) / 2
    if (p.x < -half || p.x > W + half || p.y < -half || p.y > H + half) continue
    g.fillStyle = cellColor(cell.label)
    g.globalAlpha = 0.8
    g.fillRect(p.x - half, p.y - half, half * 2 - 0.5, half * 2 - 0.5)
  }
  g.globalAlpha = 1
  // path and track
  const path = demo.state?.dogPath ?? []
  if (path.length >= 2) {
    g.strokeStyle = '#fff'
    g.setLineDash([6, 5])
    g.lineWidth = 1.5
    g.beginPath()
    path.forEach((p, i) => {
      const q = px(p)
      if (i) g.lineTo(q.x, q.y)
      else g.moveTo(q.x, q.y)
    })
    g.stroke()
    g.setLineDash([])
  }
  const t2 = demo.state?.target
  if (t2) {
    const q = px(t2)
    g.strokeStyle = COLORS.target
    g.lineWidth = 2.5
    g.beginPath()
    g.arc(q.x, q.y, 7, 0, Math.PI * 2)
    g.stroke()
  }
  // dog
  g.save()
  g.translate(W / 2, H / 2)
  g.rotate(((dg?.heading ?? 0) * Math.PI) / 180)
  g.fillStyle = COLORS.dog
  g.strokeStyle = '#0b1220'
  g.lineWidth = 1.5
  g.beginPath()
  g.moveTo(0, -10)
  g.lineTo(7, 8)
  g.lineTo(0, 4)
  g.lineTo(-7, 8)
  g.closePath()
  g.fill()
  g.stroke()
  g.restore()
}

onMounted(() => (raf = requestAnimationFrame(draw)))
onBeforeUnmount(() => cancelAnimationFrame(raf))

const legend = Object.entries(CELL_COLORS).filter(([k]) => k !== tb('未知'))
</script>

<template>
  <div class="sem">
    <canvas ref="canvas" class="cv" />
    <div class="legend">
      <span v-for="[k, c] in legend" :key="k"><i :style="{ background: c }" />{{ k }}</span>
    </div>
  </div>
</template>

<style scoped>
.sem {
  position: relative;
  width: 100%;
  height: 100%;
}
.cv {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  border-radius: 6px;
}
.legend {
  position: absolute;
  left: 6px;
  bottom: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  padding: 3px 6px;
  border-radius: 4px;
  background: rgba(11, 18, 32, 0.7);
  color: #cbd5e1;
  font-size: 11px;
}
.legend i {
  display: inline-block;
  width: 9px;
  height: 9px;
  margin-right: 3px;
  border-radius: 2px;
  vertical-align: -1px;
}
</style>
