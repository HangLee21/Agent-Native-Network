<script setup lang="ts">
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { t } from '@/i18n'
import { useNetworkStore } from '@/stores/network'
import { row, type LegacyRow } from '@/network/legacy'
import { PacketLog, decodePayload, timelineEvents, type PacketEvent, type PacketRow } from '@/network/packet-evidence'
import { ageText, timeText } from '@/network/presentation'
const network = useNetworkStore()
const expanded = ref(false), observing = ref(false), loading = ref(false), error = ref(''), readAt = ref(0), incomplete = ref(false)
const state = shallowRef<LegacyRow | null>(null), packetRows = shallowRef<PacketRow[]>([]), events = shallowRef<PacketEvent[]>([])
const selectedPacket = ref('')
const packet = computed(() => packetRows.value.find(p => p.key === selectedPacket.value))
const agents = computed(() => { const v = state.value?.nodes; return Array.isArray(v) ? v.filter(row) : [] })
const wifiEdges = computed(() => { const v = state.value?.edges; return Array.isArray(v) ? v.filter(row) : [] })
const status = computed(() => network.engineeringStatus)
const source = computed(() => status.value?.sources)
const field = (value: unknown): LegacyRow => row(value) ? value : {}
const text = (value: unknown) => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const numeric = (value: unknown) => typeof value === 'number' && Number.isFinite(value) ? value : null
const label = (id: unknown) => network.snapshot?.nodes.find(n => n.id === String(id))?.label ?? text(id)
const raw = (value: unknown) => JSON.stringify(value, null, 2)
const coverage = computed(() => incomplete.value || agents.value.some(n => Number(field(n.agent).record_overwritten) > 0 || Number(field(n.agent).sampled_records_skipped) > 0 || Number(n.events_dropped) > 0))
let cursor = 0, instance = '', log = new PacketLog(), sequence = 0, pending: AbortController | null = null
function stop() { observing.value = false; sequence++; pending?.abort(); pending = null; loading.value = false }
function reset() { stop(); state.value = null; packetRows.value = []; events.value = []; selectedPacket.value = ''; cursor = 0; instance = ''; log = new PacketLog(); readAt.value = 0; incomplete.value = false; error.value = '' }
watch(() => `${network.connectionKey}:${status.value?.instance ?? ''}:${network.mode}`, reset)
watch(expanded, open => { if (!open) stop() })
async function poll() {
  if (!observing.value || !expanded.value || loading.value || document.hidden || network.paused || network.mode !== 'live' || !network.capabilities?.engineering || network.status === 'disabled') return
  const ticket = sequence, controller = new AbortController(); pending = controller; loading.value = true
  const timeout = setTimeout(() => controller.abort(), 6000)
  try {
    let value = await network.readEvidence(cursor, controller.signal)
    if (instance && instance !== value.state.gateway_instance) value = await network.readEvidence(0, controller.signal)
    if (ticket !== sequence || controller.signal.aborted || !observing.value) return
    if (instance !== value.state.gateway_instance) { log = new PacketLog(); events.value = []; selectedPacket.value = ''; incomplete.value = false }
    instance = String(value.state.gateway_instance); cursor = Number(value.timeline.cursor)
    const rawIncoming = (value.timeline.events as unknown[]).filter(row) as PacketEvent[]
    const incoming = timelineEvents(rawIncoming, instance)
    state.value = value.state; incomplete.value ||= value.windowTruncated || value.timeline.truncated === true || Number(value.timeline.oldest_cursor) > 1
    const nodes = (value.state.nodes as unknown[]).filter(row)
    packetRows.value = log.merge(incoming, { timelineTruncated: incomplete.value, nodes, pinnedKey: selectedPacket.value })
    events.value = [...events.value, ...rawIncoming].slice(-512)
    if (!packetRows.value.some(p => p.key === selectedPacket.value)) selectedPacket.value = packetRows.value[0]?.key ?? ''
    readAt.value = Date.now(); error.value = ''
  } catch (e) { if (ticket === sequence && observing.value && !document.hidden) error.value = e instanceof Error ? e.message : String(e) }
  finally { clearTimeout(timeout); if (ticket === sequence) { loading.value = false; pending = null } }
}
function toggleEvidence() { if (observing.value) stop(); else { observing.value = true; void poll() } }
const timer = setInterval(() => void poll(), 5000)
function visibility() { if (document.hidden) { sequence++; pending?.abort(); loading.value = false } else void poll() }
document.addEventListener('visibilitychange', visibility)
onBeforeUnmount(() => { stop(); clearInterval(timer); document.removeEventListener('visibilitychange', visibility) })
</script>
<template>
  <section class="engineering" data-test="network-engineering">
    <header><div><span>BASELINE ENGINEERING CORE</span><h2>{{ t('接收、身份与原始证据') }}</h2></div><b :class="{ available: network.capabilities?.engineering }">{{ network.capabilities?.engineering ? t('本机工程接口已接入') : t('当前为拓扑只读接口') }}</b></header>
    <p v-if="!network.capabilities?.engineering" class="scope-note">{{ t('持久录放、清单与逐包证据需要本机 Studio 工程服务，通常为 http://127.0.0.1:8794。直连接收器 8780 只有拓扑，不会伪造其余能力。') }}</p>
    <template v-else>
      <p v-if="network.mode === 'replay'" class="scope-note">{{ t('回放只显示原采集帧；实时来源、登记与健康信息不叠加。') }}</p>
      <div v-if="network.mode === 'live'" class="core-health"><div><small>{{ t('实际接收源 / epoch') }}</small><strong>{{ source?.selected_source_id ?? t('尚未选定') }} / {{ source?.selection_epoch ?? '—' }}</strong><span>{{ source?.selection === 'manual' ? t('手动偏好') + ': ' + source.preferred_source_id : t('自动选择 / 故障回退') }}</span></div><div><small>{{ t('登记清单') }}</small><strong>{{ status?.fleet.length ?? 0 }} {{ t('个登记节点') }}</strong><span>{{ status?.fleetError || t('登记仅用于身份和缺席提示，不等于在线') }}</span></div><div><small>{{ t('服务恢复状态') }}</small><strong>{{ text(status?.recovery?.state) }}</strong><span>{{ text(status?.recovery?.reason) }}</span></div><div><small>{{ t('SQLite 录制状态') }}</small><strong>{{ status?.recordingId ? t('记录进行中') : t('未在录制') }}</strong><span>{{ status?.recordingError || status?.recordingId || t('由本机服务持久写入') }}</span></div></div>
      <p v-if="network.mode === 'live' && (status?.error || source?.udp_error)" class="core-warning">{{ status?.error || source?.udp_error }}</p>
      <details v-if="network.mode === 'live'" class="core-raw"><summary>{{ t('查看接收器与来源原始健康信息') }}</summary><pre>{{ raw({ receiver: status?.receiver, sources: source, recovery: status?.recovery, service_instance: status?.instance }) }}</pre></details>
      <details class="evidence-details" @toggle="expanded = ($event.target as HTMLDetailsElement).open">
        <summary>{{ t('板内 Agent、Wi-Fi 即时证据与原始业务收件') }}</summary>
        <p class="scope-note">{{ t('此处通过原工程 IP/RAM 只读接口取证，独立于 LoRa 接收源。点击开始后会触发后端只读状态查询；不启动 Agent、不发送业务、不配置串口或节点。SQLite 回放不包含本区实时证据。') }}</p>
        <div class="evidence-tools"><button :disabled="network.mode !== 'live' || network.paused" @click="toggleEvidence">{{ observing ? t('停止读取证据') : t('开始读取只读证据') }}</button><span>{{ network.mode === 'replay' ? t('历史回放不叠加当前 IP/Agent 数据') : network.paused ? t('观测暂停，不读取板内证据') : loading ? t('读取中…') : readAt ? t('最近读取') + ' ' + timeText(readAt) : t('尚未读取板内证据') }}</span></div>
        <p v-if="error" class="core-warning" role="alert">{{ error }} · {{ t('只保留上次证据，不把读取失败判为业务丢包。') }}</p>
        <p v-if="coverage" class="core-warning">{{ t('证据不完整：存在 RAM 覆盖、抽样跳过、事件溢出或时间线截断。缺少收件记录不能证明未交付。') }}</p>
        <template v-if="state && network.mode === 'live'">
          <div class="table-scroll"><table><caption>{{ t('Agent 状态与累计计数（不是逐包交付证明）') }}</caption><thead><tr><th>NODE / MAC</th><th>Agent</th><th>{{ t('源提交') }}</th><th>{{ t('中继收到') }}</th><th>{{ t('目的收到') }}</th><th>{{ t('RAM 覆盖 / 抽样跳过') }}</th></tr></thead><tbody><tr v-for="n in agents" :key="text(n.node_id)"><td><b>{{ label(n.node_id) }}</b><small>{{ text(n.node_id) }}</small></td><td>{{ field(n.agent).running === true ? t('运行') : field(n.agent).running === false ? t('停止') : t('未知') }}<small>{{ text(field(n.agent).source) }}</small></td><td>{{ text(field(field(n.agent).counters).source_submitted) }}</td><td>{{ text(field(field(n.agent).counters).relay_received) }}</td><td>{{ text(field(field(n.agent).counters).destination_received) }}</td><td>{{ text(field(n.agent).record_overwritten) }} / {{ text(field(n.agent).sampled_records_skipped) }}</td></tr></tbody></table><p v-if="!agents.length" class="scope-note">{{ t('IP/RAM 接口暂无节点报告；不从 LoRa 或热点连接编造 Agent 状态。') }}</p></div>
          <div class="table-scroll"><table><caption>{{ t('原 Wi-Fi 即时方向（原 API 快照判定，非 LoRa 邻居样本）') }}</caption><thead><tr><th>{{ t('发送方 → 接收报告者') }}</th><th>{{ t('采样新鲜度 / 互证') }}</th><th>{{ t('年龄 / 下界') }}</th><th>RSSI</th><th>{{ t('失效原因') }}</th></tr></thead><tbody><tr v-for="e in wifiEdges" :key="text(e.from) + ':' + text(e.to)"><td>{{ label(e.from) }} → {{ label(e.to) }}</td><td>{{ text(e.sample_freshness) }} / {{ e.mutual_confirmed === true ? t('API 声明互证') : t('未互证') }}</td><td>{{ e.age_is_lower_bound === true ? '≥ ' + ageText(numeric(e.sample_age_lower_bound_ms)) : ageText(numeric(e.sample_age_ms)) }}</td><td>{{ e.rf_source === 'measured' ? text(e.rssi_dbm) : '—' }}</td><td>{{ text(e.invalidated_reason) }}</td></tr></tbody></table><p v-if="!wifiEdges.length" class="scope-note">{{ t('本次 IP/RAM 报告未提供 Wi-Fi 邻居；不以热点在线或 LoRa 样本补造即时互证。') }}</p></div>
          <p class="scope-note">{{ t('只有目的节点自己的 rx_local、完整原包身份与原始字节才构成目的本地收件证据；板选路径、计数和本跳成功不等于交付。以下仍受旧协议未声明性质和观察窗口限制。') }}</p>
          <div class="table-scroll packet-table"><table><caption>{{ t('逐包证据（最多保留128个包，原身份跨窗口累积）') }}</caption><thead><tr><th>{{ t('原始包身份') }}</th><th>{{ t('源 → 目的') }}</th><th>{{ t('交付证据') }}</th><th>{{ t('原字节种类') }}</th></tr></thead><tbody><tr v-for="p in packetRows" :key="p.key" :class="{ picked: p.key === selectedPacket, conflict: p.payloads.length > 1 }"><td><button @click="selectedPacket = p.key">{{ p.origin_boot }} / {{ p.seq }}</button></td><td>{{ label(p.origin) }} → {{ label(p.dst) }}</td><td>{{ t(p.stateLabel) }}</td><td>{{ p.payloads.length }}{{ p.coverageNotes.length ? ' ⚠' : '' }}</td></tr></tbody></table><p v-if="!packetRows.length" class="scope-note">{{ t('尚无可核对原身份的业务事件；累计计数不作为逐包交付证明。') }}</p></div>
          <article v-if="packet" class="packet-inspector"><h3>{{ t(packet.stateLabel) }}</h3><code>{{ packet.key }}</code><p>{{ t(packet.reason) }}</p><p v-for="note in packet.coverageNotes" :key="note" class="core-warning">{{ t(note) }}</p><div v-for="hex in packet.payloads" :key="hex" class="payload"><b>{{ t('原始字节 HEX') }}</b><code>{{ hex || '∅' }}</code><span>{{ t('UTF-8 解码（不替代原字节）') }}: {{ decodePayload(hex) ?? t('不是有效 UTF-8') }}</span></div><p v-if="packet.payloads.length > 1" class="core-warning">{{ t('同一身份存在原字节冲突，不标为一致交付。') }}</p><h4>{{ t('板端选路（不等于沿途实收）') }}</h4><p v-for="(r, i) in packet.routes" :key="i">{{ r.path.map(label).join(' → ') }}</p><h4>{{ t('提交与收到的局部片段') }}</h4><p v-for="(s, i) in packet.segments" :key="i"><code>{{ s.type }}</code> · {{ label(s.from) }} → {{ label(s.to) }}</p><details><summary>{{ t('查看该包完整保留事件') }}</summary><pre>{{ raw(packet.events) }}</pre></details></article>
          <details class="core-raw"><summary>{{ t('原始时间线 / 状态快照（最多保留512条时间线事件）') }}</summary><pre>{{ raw({ state, events, cursor, instance, incomplete }) }}</pre></details>
        </template>
      </details>
    </template>
  </section>
</template>
<style scoped>
.engineering{margin:18px 0;background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:20px;color:var(--text)}.engineering header{display:flex;justify-content:space-between;align-items:center;gap:15px;flex-wrap:wrap}.engineering header span{font:10px var(--font-num);letter-spacing:1.5px;color:var(--accent)}.engineering h2{font-size:18px;margin:7px 0}.engineering header>b{font-size:12px;color:var(--text-dim)}.engineering header>b.available{color:var(--accent)}.scope-note{font-size:12px;line-height:1.8;color:var(--text-dim)}.core-health{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:18px 0}.core-health>div{padding:13px;border:1px solid var(--border);border-radius:6px;display:grid;gap:7px;overflow-wrap:anywhere}.core-health small{color:var(--text-dim);font-size:11px}.core-health strong{font:600 13px var(--font-num)}.core-health span{color:var(--text-dim);font-size:11px;line-height:1.7}.core-warning{padding:10px 12px;border-left:4px solid #efbb55;background:color-mix(in srgb,#c59735 10%,var(--panel));font-size:12px;line-height:1.8;color:#dba948;overflow-wrap:anywhere}.engineering summary{font-size:13px;font-weight:650;cursor:pointer;padding:12px 0}.engineering details{border-top:1px solid var(--border);margin-top:10px}.engineering pre{font:11px/1.7 var(--font-num);padding:14px;background:var(--panel-2);overflow:auto;max-height:340px;white-space:pre-wrap;overflow-wrap:anywhere}.engineering code{font:11px var(--font-num);overflow-wrap:anywhere}.evidence-tools{display:flex;align-items:center;gap:15px;flex-wrap:wrap;margin:12px 0}.evidence-tools>span{font-size:12px;color:var(--text-dim)}.engineering button{border:1px solid var(--border);border-radius:5px;background:var(--panel-2);color:var(--text);padding:8px 12px;cursor:pointer}.engineering button:disabled{opacity:.4;cursor:not-allowed}.table-scroll{overflow:auto;margin:16px 0;max-height:340px}.engineering table{width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap}.engineering caption{text-align:left;font-weight:650;padding:10px 0}.engineering td,.engineering th{padding:11px 13px;text-align:left;border-bottom:1px solid var(--border)}.engineering th{font-size:11px;color:var(--text-dim);background:var(--panel-2)}.engineering td small{display:block;color:var(--text-dim);font:10px var(--font-num);margin-top:5px}.picked{background:color-mix(in srgb,var(--accent) 12%,var(--panel))}.conflict{color:#fb748c}.packet-inspector{border:1px solid var(--border);padding:16px;border-radius:6px;font-size:12px;line-height:1.8}.packet-inspector h3{margin-top:0}.payload{display:grid;gap:8px;padding:12px;margin:10px 0;background:var(--panel-2);border-radius:6px;overflow-wrap:anywhere}.payload>b{font-size:11px;color:var(--text-dim)}
@media(max-width:1000px){.core-health{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:600px){.core-health{grid-template-columns:1fr}.engineering{padding:14px}}
</style>
