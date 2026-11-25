<script setup lang="ts">
import { computed } from 'vue'
import { t } from '@/i18n'
import { nodeState } from '@/network/model'
import { ageText } from '@/network/presentation'
import type { NetworkSnapshot } from '@/network/types'
const props = defineProps<{ snapshot: NetworkSnapshot; now: number; interrupted: boolean; paused: boolean; replay: boolean }>()
defineEmits<{ select: [id: string] }>()
const overdue = computed(() => props.snapshot.nodes.filter(n => n.role !== 'gateway' && nodeState(n, props.snapshot, props.now, props.interrupted) === 'stale'))
const missing = computed(() => props.snapshot.nodes.filter(n => n.role !== 'gateway' && n.reportedAt === null))
const unavailable = computed(() => props.interrupted || props.snapshot.receiver.state === 'unavailable')
</script>
<template>
  <section class="network-alerts" :class="{ critical: unavailable || overdue.length > 0 }" :role="unavailable || overdue.length ? 'alert' : 'status'" data-test="network-alerts">
    <div class="alert-overview"><strong v-if="unavailable">⛔ {{ t('观测通道中断 · 当前节点状态未知') }}</strong><strong v-else-if="overdue.length">⚠ {{ t('{n} 个节点报告超时', { n: overdue.length }) }}</strong><strong v-else-if="missing.length">◉ {{ t('{n} 个已知节点尚未观测', { n: missing.length }) }}</strong><strong v-else>✓ {{ t('已观测节点报告均在有效期内') }}</strong><span>{{ replay ? t('历史帧，不代表当前现场') : paused ? t('观测已暂停：只显示最后收到的报告') : t('报告超时不等于确认掉电；请核查电源、接收链路和服务。') }}</span></div>
    <div v-if="overdue.length || missing.length" class="alert-nodes"><button v-for="n in overdue" :key="n.id" class="overdue" @click="$emit('select', n.id)"><b>{{ n.label }}</b><span>{{ t('报告超时') }} · {{ ageText(n.reportedAt === null ? null : now - n.reportedAt) }}</span><small>{{ n.id }}</small></button><button v-for="n in missing" :key="n.id" class="missing" @click="$emit('select', n.id)"><b>{{ n.label }}</b><span>{{ n.registration === 'fleet' ? t('已登记 · 未收到报告') : n.registration === 'label' ? t('仅历史标签 · 未收到报告') : t('仅邻居提及 · 未直接上报') }}</span><small>{{ n.id }}</small></button></div>
    <p v-if="missing.length">{{ t('清单/标签不证明节点当前部署或在线；未观测节点不补造无线连接。') }}</p>
  </section>
</template>
<style scoped>
.network-alerts{border:1px solid #c69138;border-left:6px solid #e4a52d;background:color-mix(in srgb,#c58c27 10%,var(--panel));padding:16px 20px;border-radius:10px;margin:16px 0}.network-alerts.critical{border-color:#ed6778;background:color-mix(in srgb,#d74055 11%,var(--panel))}.alert-overview{display:flex;gap:12px;justify-content:space-between;align-items:center;flex-wrap:wrap}.alert-overview strong{font-size:17px;color:var(--text)}.critical .alert-overview strong{color:#ed6778}.alert-overview>span,.network-alerts p{font-size:12px;color:var(--text-dim)}.alert-nodes{display:flex;gap:10px;flex-wrap:wrap;margin-top:13px}.alert-nodes button{display:grid;text-align:left;gap:5px;padding:10px 15px;min-width:190px;background:var(--panel);border:1px solid #c69138;border-radius:6px;color:var(--text);cursor:pointer}.alert-nodes button.overdue{border:2px solid #ed6778}.alert-nodes b{font-size:15px}.alert-nodes span{color:#dda745;font-size:12px}.alert-nodes .overdue span{color:#ed6778;font-weight:700}.alert-nodes small{font:11px var(--font-num);color:var(--text-dim)}.alert-nodes button:hover,.alert-nodes button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.network-alerts p{margin:12px 0 0}
</style>
