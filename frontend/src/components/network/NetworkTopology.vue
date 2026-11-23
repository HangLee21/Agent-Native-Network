<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { t } from '@/i18n'
import { clearLayout, gpsProjection, linkHistorical, nodeState, readPositions } from '@/network/model'
import { tagLabel } from '@/network/presentation'
import type { LayoutMode, NetworkLink, NetworkSnapshot, Point } from '@/network/types'

const props = defineProps<{ snapshot: NetworkSnapshot; now: number; interrupted: boolean; selected: string; selectedLink: string; layout: LayoutMode; linkFilter: string; namespace: string; demo: boolean }>()
const emit = defineEmits<{ select: [id: string]; link: [id: string] }>()
const svg = ref<SVGSVGElement | null>(null)
const manual = ref<Record<string, Point>>({})
const zoom = ref(1)
const pan = ref<Point>({ x: 0, y: 0 })
const allLinks = ref(false)
const sourceKey = computed(() => `network.layout.v2:${props.namespace}:${props.snapshot.provenance}:${props.snapshot.sourceId}`)
const projection = computed(() => gpsProjection(props.snapshot.nodes, props.now, props.snapshot.reportTimeoutMs))
const scaleMeters = computed(() => Math.round(100 * projection.value.metersPerUnit / zoom.value))
watch(sourceKey, key => { manual.value = readPositions(key); resetView() }, { immediate: true })
watch(() => props.layout, resetView)
const positions = computed(() => {
  if (props.layout === 'gps') return projection.value.positions
  const defaults = clearLayout(props.snapshot.nodes)
  return props.layout === 'manual' ? { ...defaults, ...manual.value } : defaults
})
const visibleNodes = computed(() => props.snapshot.nodes.filter(n => positions.value[n.id]))
const eligible = computed(() => props.snapshot.links.filter(e => (props.linkFilter === 'all' || props.linkFilter === e.kind) && positions.value[e.from] && positions.value[e.to]))
const edges = computed(() => eligible.value.filter(e => allLinks.value || eligible.value.length <= 30 || (!!props.selected && (e.from === props.selected || e.to === props.selected))))
const nearby = computed(() => new Set(props.snapshot.links.filter(e => e.from === props.selected || e.to === props.selected).flatMap(e => [e.from, e.to])))
const transform = computed(() => `translate(${490 + pan.value.x} ${290 + pan.value.y}) scale(${zoom.value}) translate(-490 -290)`)
function resetView() { zoom.value = 1; pan.value = { x: 0, y: 0 } }
function resetLayout() { manual.value = {}; try { localStorage.removeItem(sourceKey.value) } catch { /* optional storage */ } resetView() }
function setZoom(change: number) { zoom.value = Math.max(.45, Math.min(3.5, zoom.value * change)) }
function wheel(event: WheelEvent) { event.preventDefault(); setZoom(event.deltaY > 0 ? .9 : 1.1) }
function curve(e: NetworkLink): string {
  const a = positions.value[e.from]!, b = positions.value[e.to]!
  const dx = b.x - a.x, dy = b.y - a.y, length = Math.hypot(dx, dy) || 1
  const offset = e.kind === 'lora' ? 22 : 10
  const ax = a.x + dx / length * 25, ay = a.y + dy / length * 25
  const bx = b.x - dx / length * 28, by = b.y - dy / length * 28
  return `M ${ax} ${ay} Q ${(ax + bx) / 2 - dy / length * offset} ${(ay + by) / 2 + dx / length * offset} ${bx} ${by}`
}
function linkClass(e: NetworkLink) { return { historical: linkHistorical(e, props.snapshot, props.now, props.interrupted), lost: e.state === 'lost', lora: e.kind === 'lora', picked: props.selectedLink === e.id, muted: !!props.selected && e.from !== props.selected && e.to !== props.selected } }
function point(event: PointerEvent): Point {
  const matrix = svg.value?.getScreenCTM()
  if (!matrix) return { x: event.clientX, y: event.clientY }
  const p = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse())
  return { x: p.x, y: p.y }
}
let drag: { id: string | null; start: Point; original: Point; moved: boolean; pointer: number } | null = null
function down(event: PointerEvent, id: string | null = null) {
  if (event.button !== 0) return
  if (id) emit('select', id)
  if (id && props.layout !== 'manual') return
  drag = { id, start: point(event), original: { ...(id ? positions.value[id]! : pan.value) }, moved: false, pointer: event.pointerId }
  svg.value?.setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!drag) return
  const p = point(event), dx = p.x - drag.start.x, dy = p.y - drag.start.y
  if (Math.hypot(dx, dy) < 3 && !drag.moved) return
  drag.moved = true
  if (drag.id) manual.value = { ...manual.value, [drag.id]: { x: drag.original.x + dx / zoom.value, y: drag.original.y + dy / zoom.value } }
  else pan.value = { x: drag.original.x + dx, y: drag.original.y + dy }
}
function up() {
  if (drag?.id && drag.moved) try { localStorage.setItem(sourceKey.value, JSON.stringify(manual.value)) } catch { /* private browsing */ }
  if (drag && svg.value?.hasPointerCapture(drag.pointer)) svg.value.releasePointerCapture(drag.pointer)
  drag = null
}
onBeforeUnmount(up)
</script>

<template>
  <section class="topology" data-test="network-topology">
    <div class="graph-heading"><div><span class="eyebrow">NETWORK TOPOLOGY</span><h2>{{ layout === 'gps' ? t('GPS 定位与通信关系') : t('节点与通信关系') }}</h2></div><span class="graph-count num">{{ t('{nodes} 个节点 · {links} 条方向', { nodes: snapshot.nodes.length, links: snapshot.links.length }) }}</span></div>
    <div class="graph-tools">
      <span class="coordinate-note">{{ layout === 'gps' ? t('WGS84 局部等比例投影 · 非在线地图底图') : t('逻辑拓扑 · 无地理距离含义') }}</span>
      <div class="view-tools"><button :title="t('缩小')" :aria-label="t('缩小')" @click="setZoom(.8)">−</button><span class="num">{{ Math.round(zoom * 100) }}%</span><button :title="t('放大')" :aria-label="t('放大')" @click="setZoom(1.25)">＋</button><button @click="resetView">{{ t('适配') }}</button><button v-if="layout === 'manual'" @click="resetLayout">{{ t('重置布局') }}</button></div>
    </div>
    <div class="graph-canvas">
      <svg ref="svg" viewBox="0 0 980 580" :aria-label="t('网络拓扑图')" @wheel="wheel" @pointerdown="down($event)" @pointermove="move" @pointerup="up" @pointercancel="up">
        <defs><pattern id="network-grid" width="26" height="26" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="currentColor" /></pattern><marker id="network-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" /></marker></defs>
        <rect width="980" height="580" fill="url(#network-grid)" class="grid" />
        <text v-if="demo" x="490" y="290" text-anchor="middle" class="mock-watermark" data-test="mock-watermark">MOCK · SYNTHETIC</text>
        <g v-if="layout === 'gps' && visibleNodes.length" class="gps-map-guide" data-test="gps-map-guide"><path d="M 925 100 V 50 M 917 63 L 925 50 L 933 63" /><text x="925" y="40" text-anchor="middle">N</text><path d="M 45 530 V 538 H 145 V 530" /><text x="45" y="558">≈ {{ scaleMeters }} m</text></g>
        <g :transform="transform">
          <g v-for="edge in edges" :key="edge.id" class="edge" :class="linkClass(edge)" role="button" tabindex="0" :aria-label="`${edge.from} → ${edge.to}`" @pointerdown.stop @click.stop="emit('link', edge.id)" @keydown.enter="emit('link', edge.id)">
            <path :d="curve(edge)" class="edge-hit" /><path :d="curve(edge)" class="edge-line" marker-end="url(#network-arrow)" />
          </g>
          <g v-for="node in visibleNodes" :key="node.id" class="graph-node" :class="[node.role, node.tag, nodeState(node, snapshot, now, interrupted), { selected: selected === node.id, dimmed: !!selected && selected !== node.id && !nearby.has(node.id), draggable: layout === 'manual' }]" :transform="`translate(${positions[node.id]!.x} ${positions[node.id]!.y})`" role="button" tabindex="0" :data-node="node.id" :aria-label="node.label" :aria-pressed="selected === node.id" @pointerdown.stop="down($event, node.id)" @keydown.enter="emit('select', node.id)">
            <circle v-if="selected === node.id" r="34" class="selection-ring" /><circle r="23" class="node-body" />
            <path v-if="node.role === 'gateway'" d="M -9 5 H 9 M -6 0 H 6 M -3 -5 H 3 M 0 -8 V 8" class="node-symbol" />
            <path v-else-if="node.tag === 'drone'" d="M -10 -10 L 10 10 M -10 10 L 10 -10 M -7 0 H 7 M 0 -7 V 7" class="node-symbol" />
            <path v-else-if="node.tag === 'robot'" d="M -9 -5 H 9 V 4 H -9 Z M -6 4 V 10 M 6 4 V 10" class="node-symbol" />
            <path v-else d="M 0 -9 L 9 0 L 0 9 L -9 0 Z" class="node-symbol" />
            <circle cx="17" cy="-17" r="4" class="node-status" /><text y="45" text-anchor="middle" class="node-label">{{ node.label }}</text><text y="62" text-anchor="middle" class="node-meta">{{ node.role === 'gateway' ? 'GATEWAY' : node.id.slice(-8).toUpperCase() }}</text><text v-if="node.role !== 'gateway' && node.tag && node.tag !== 'node'" y="77" text-anchor="middle" class="node-tag-label">{{ tagLabel(node.tag) }}</text>
          </g>
        </g>
      </svg>
      <div v-if="!visibleNodes.length" class="graph-empty"><strong>{{ snapshot.nodes.length ? t('没有可用的 GPS 位置') : t('等待节点报告') }}</strong><span>{{ snapshot.nodes.length ? t('未定位节点保留在列表，可切换清晰布局查看。') : t('空图不预填节点，也不推断设备离线。') }}</span></div>
      <div v-if="eligible.length > 30" class="density-note"><span>{{ t('已显示 {shown}/{total} 条方向', { shown: edges.length, total: eligible.length }) }}</span><button @click="allLinks = !allLinks">{{ allLinks ? t('聚焦选中节点') : t('展开全部连线') }}</button></div>
      <div v-if="layout === 'manual'" class="drag-note">{{ t('拖动节点调整布局，空白处平移，滚轮缩放。') }}</div>
    </div>
    <div class="legend"><span><i class="wifi-key" />{{ t('Wi-Fi / ESP-NOW 采样') }}</span><span><i class="lora-key" />{{ t('LoRa 上行') }}</span><span><i class="history-key" />{{ t('过期或无法确认') }}</span><small>{{ t('箭头：发送方 → 接收报告者') }}</small></div>
  </section>
</template>

<style scoped>
.mock-watermark{font:700 64px var(--font-num);fill:var(--warn);opacity:.11;pointer-events:none;letter-spacing:4px}.gps-map-guide{fill:var(--text-dim);pointer-events:none;font:12px var(--font-num)}.gps-map-guide path{stroke:var(--text-dim);stroke-width:1.5;fill:none}.node-tag-label{fill:var(--accent);font:10px var(--font-ui);pointer-events:none}
.topology{height:100%;min-height:420px;display:flex;flex-direction:column;background:var(--panel);border:1px solid var(--border);border-radius:var(--r-panel);overflow:hidden}.graph-heading{display:flex;justify-content:space-between;align-items:center;padding:20px 22px 14px;gap:12px}.eyebrow{font:10px var(--font-num);letter-spacing:2px;color:var(--text-dim)}h2{font-size:16px;margin-top:5px}.graph-count{font-size:11px;color:var(--text-dim)}.graph-tools{display:flex;justify-content:space-between;align-items:center;padding:0 22px 12px;gap:8px;flex-wrap:wrap}.coordinate-note{font-size:11px;color:var(--text-dim)}.view-tools{display:flex;align-items:center;gap:5px}.view-tools button,.density-note button{border:1px solid var(--border);background:var(--panel-2);color:var(--text-dim);border-radius:5px;font-size:11px;cursor:pointer;padding:4px 8px}.view-tools span{font-size:10px;min-width:36px;text-align:center}.graph-canvas{position:relative;flex:1;min-height:300px;background:radial-gradient(ellipse at center,color-mix(in srgb,var(--accent) 4%,var(--bg)),var(--bg))}.graph-canvas svg{position:absolute;width:100%;height:100%;touch-action:none;user-select:none}.grid{color:var(--border);opacity:.5}.edge{cursor:pointer;outline:none}.edge-line{stroke:var(--accent);stroke-width:1.5;fill:none;opacity:.55;transition:opacity .15s}.edge-hit{stroke:transparent;stroke-width:15;fill:none}.edge.lora .edge-line{stroke:#45bcb4;stroke-dasharray:4 6}.edge.lost .edge-line{stroke:var(--danger);stroke-dasharray:2 5}.edge.historical .edge-line{stroke:var(--text-dim);stroke-dasharray:3 7;opacity:.3}.edge.muted .edge-line{opacity:.12}.edge.picked .edge-line,.edge:focus .edge-line,.edge:hover .edge-line{stroke-width:3;opacity:1}.graph-node{cursor:pointer;outline:none}.graph-node.draggable{cursor:grab}.node-body{fill:var(--panel-2);stroke:var(--accent);stroke-width:1.6}.gateway .node-body{fill:color-mix(in srgb,#33b5aa 15%,var(--panel));stroke:#40bcb1}.robot .node-body{stroke:var(--dog-s10)}.relay .node-body{stroke:#94a3b8}.node-symbol{stroke:var(--text);stroke-width:1.5;fill:none;stroke-linecap:round}.node-status{fill:var(--ok);stroke:var(--bg);stroke-width:2}.stale .node-status{fill:var(--warn)}.unknown .node-status,.interrupted .node-status{fill:var(--text-dim)}.stale .node-body,.interrupted .node-body{stroke-dasharray:4 3}.node-label{fill:var(--text);font-size:12px;font-weight:600;paint-order:stroke;stroke:var(--bg);stroke-width:4px;stroke-linejoin:round}.node-meta{fill:var(--text-dim);font:9px var(--font-num);letter-spacing:1px}.selection-ring{fill:color-mix(in srgb,var(--accent) 8%,transparent);stroke:var(--accent);stroke-opacity:.4}.selected .node-body,.graph-node:focus .node-body{stroke-width:3}.dimmed{opacity:.4}.graph-empty{position:absolute;inset:0;display:flex;justify-content:center;align-items:center;flex-direction:column;gap:10px;pointer-events:none;color:var(--text-dim);padding:24px;text-align:center}.graph-empty strong{font-size:17px;color:var(--text)}.graph-empty span{font-size:12px}.density-note{position:absolute;left:14px;bottom:12px;display:flex;gap:12px;align-items:center;background:var(--panel);padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-size:11px;color:var(--text-dim)}.drag-note{position:absolute;right:14px;bottom:14px;max-width:50%;font-size:10px;color:var(--text-dim);pointer-events:none}.legend{display:flex;align-items:center;gap:18px;flex-wrap:wrap;padding:12px 20px;border-top:1px solid var(--border);font-size:10px;color:var(--text-dim)}.legend span{display:flex;align-items:center;gap:6px}.legend i{width:18px;border-top:2px solid var(--accent)}.legend .lora-key{border-color:#45bcb4;border-top-style:dashed}.legend .history-key{border-color:var(--text-dim);border-top-style:dotted}.legend small{margin-left:auto;font-size:10px}@media(max-width:1100px){.graph-count{display:none}.legend{gap:10px}.legend small{display:none}}@media(prefers-reduced-motion:reduce){.edge-line{transition:none}}
</style>
