<script setup lang="ts">
import { computed, ref } from 'vue'
import { t } from '@/i18n'
import { linkEvidenceState } from '@/network/model'
import { TopologyProjector, type TopologyFrame } from '@/network/topology'
import { ageText, linkEvidenceLabel } from '@/network/presentation'
import type { NetworkLink, NetworkSnapshot } from '@/network/types'
const props = defineProps<{ snapshot: NetworkSnapshot; selected: string; selectedLink: string; now: number; interrupted: boolean; linkFilter: string; frame?: TopologyFrame }>()
defineEmits<{ link: [id: string] }>()
const historyOpen = ref(false), projector = new TopologyProjector()
const frame = computed(() => props.frame ?? projector.project(props.snapshot, props.now, '', props.interrupted))
const node = computed(() => props.snapshot.nodes.find(n => n.id === props.selected))
const links = computed(() => props.snapshot.links.filter(e => (e.from === props.selected || e.to === props.selected) && (props.linkFilter === 'all' || e.kind === props.linkFilter)))
const current = computed(() => links.value.filter(e => frame.value.states[e.id] !== 'hidden'))
const history = computed(() => links.value.filter(e => frame.value.states[e.id] === 'hidden'))
const name = (id: string) => props.snapshot.nodes.find(n => n.id === id)?.label ?? id
const evidence = (e: NetworkLink) => linkEvidenceState(e, props.snapshot, props.now, props.interrupted)
const status = (e: NetworkLink) => linkEvidenceLabel(e, props.snapshot, props.now, props.interrupted)
</script>
<template>
  <section class="relations" data-test="network-relations">
    <header><div><span>DIRECTED RELATIONSHIPS</span><h2>{{ node?.label ?? t('选择节点') }} · {{ t('邻接关系') }}</h2></div><strong>{{ current.filter(e => e.to === selected).length }} {{ t('入向') }} / {{ current.filter(e => e.from === selected).length }} {{ t('出向') }}</strong></header>
    <p>{{ t('同一对节点合并绘制；箭头只表示新鲜方向。历史方向可展开查看。') }}</p>
    <div class="relation-scroll"><table v-if="current.length"><thead><tr><th>{{ t('方向') }}</th><th>{{ t('发送方 → 接收报告者') }}</th><th>{{ t('无线类型') }}</th><th>{{ t('证据状态') }}</th><th>RSSI</th><th>{{ t('样本年龄') }}</th></tr></thead><tbody>
      <tr v-for="e in current" :key="e.id" :class="{ picked: selectedLink === e.id }" :data-link="e.id" :data-visual="frame.states[e.id]" :data-evidence="evidence(e)" :data-kind="e.kind" :data-state="e.state"><td><span class="direction">{{ e.to === selected ? t('入向') : t('出向') }}</span></td><td><button @click="$emit('link', e.id)">{{ name(e.from) }} <b>→</b> {{ name(e.to) }}</button></td><td>{{ e.kind === 'lora' ? t('LoRa 上行') : 'Wi-Fi / ESP-NOW' }}</td><td class="evidence-state" :title="status(e)">{{ frame.states[e.id] === 'fresh' ? t('新鲜') : t('暂时失效') }}</td><td class="num">{{ e.rssiDbm === null ? '—' : e.rssiDbm + ' dBm' }}</td><td class="num">{{ ageText(e.sampledAt === null ? null : now - e.sampledAt) }}</td></tr>
    </tbody></table><div v-else class="no-relations">{{ t('无当前连线；历史证据仍保留。') }}</div></div>
    <details v-if="history.length" :open="historyOpen" class="historical-directions"><summary @click.prevent="historyOpen = !historyOpen">{{ t('历史方向（{count}）', { count: history.length }) }}</summary><div v-if="historyOpen" class="relation-scroll"><table><tbody><tr v-for="e in history" :key="e.id" :data-link="e.id" data-visual="hidden" :data-evidence="evidence(e)"><td><button @click="$emit('link', e.id)">{{ name(e.from) }} → {{ name(e.to) }}</button></td><td class="evidence-state">{{ t('已断开 / 不绘制') }}<small>{{ status(e) }}</small></td><td class="num">{{ ageText(e.sampledAt === null ? null : now - e.sampledAt) }}</td></tr></tbody></table></div></details>
  </section>
</template>
<style scoped>
.relations{margin:18px 0;background:var(--panel);border:1px solid var(--border);border-radius:10px;overflow:hidden}.relations header{display:flex;justify-content:space-between;gap:15px;align-items:center;padding:18px 20px 10px}.relations header span{font:10px var(--font-num);color:var(--accent);letter-spacing:1.6px}.relations h2{font-size:17px;margin:6px 0}.relations header>strong{color:var(--accent);font-size:14px}.relations>p{padding:0 20px;font-size:12px;color:var(--text-dim);line-height:1.7}.relation-scroll{overflow:auto;max-height:360px}.relations table{width:100%;border-collapse:collapse;white-space:nowrap;font-size:12px}.relations th{font-weight:500;text-align:left;color:var(--text-dim);padding:12px 18px;background:var(--panel-2);position:sticky;top:0}.relations td{padding:11px 18px;border-top:1px solid var(--border);color:var(--text)}.relations td button{background:none;border:0;font:600 13px var(--font-ui);color:var(--text);cursor:pointer}.relations td button b{color:var(--accent);padding:0 8px;font-size:19px}.relations tr.picked{background:color-mix(in srgb,var(--accent) 14%,var(--panel))}.direction{padding:4px 8px;border-radius:4px;background:color-mix(in srgb,var(--accent) 14%,var(--panel));color:var(--accent);font-weight:700}.no-relations{padding:20px;color:var(--text-dim);font-size:13px}.relations .evidence-state{font-weight:650}.relations [data-visual="fresh"] .evidence-state{color:#63bafa}.relations [data-visual="impaired"] .evidence-state{color:#efbb55}.relations [data-visual="hidden"] .evidence-state{color:var(--text-dim)}.evidence-state small{display:block;font-size:11px;margin-top:5px;font-weight:400}.historical-directions{border-top:1px solid var(--border)}.historical-directions summary{cursor:pointer;padding:14px 20px;color:var(--text-dim);font-size:12px}
</style>
